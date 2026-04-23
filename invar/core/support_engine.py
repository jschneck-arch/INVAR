"""
skg.core.support_engine
=======================
The SupportEngine ingests ObsGateEnvelopes from adapters and maintains the
live gate store.

This is the substrate's write path. It is the only thing that touches gate
state. Domain adapters never access gates directly — they produce envelopes,
the engine consumes them.

Responsibilities:
  1. Accept ObsGateEnvelope → route each SupportContribution to the right gate
  2. Create gates on first observation (lazy instantiation)
  3. Fire collapse events when threshold is crossed
  4. Emit Pearl records for every entropy-changing observation

The engine does not schedule instruments. It does not read the gravity field.
It does not know what domains exist. It knows gates.

Pearl emission (Definition 5, Work 5):
  Pearl = (gate_id, H_before, H_after, φ changes, ts, seq_id, instrument, cycle_id)
  ΔH = H_after - H_before (negative = confirming, positive = contradiction/fold)
  seq_id = monotone emission counter per SupportEngine instance (ET-G5 — Layer 3)
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Final, Iterator, List, Optional, Tuple

from .envelope import ObsGateEnvelope, SupportContribution
from .gate import Gate, GateState, gate_energy

log = logging.getLogger("invar.core.support_engine")


# ---------------------------------------------------------------------------
# ET-G6: Sequencer enforcement capability token
# ---------------------------------------------------------------------------

#: Private sentinel. Imported only by invar/core/ingest_sequencer.py.
#: SupportEngine.ingest() checks for this token; calls without it increment
#: _bypass_count (soft enforcement — direct calls still succeed).
_SEQUENCER_WRITE_TOKEN: Final = object()


# ---------------------------------------------------------------------------
# Pearl
# ---------------------------------------------------------------------------

@dataclass
class Pearl:
    """
    A measurement event in the entropy landscape. Definition 5 of Work 5.

    ΔH < 0 → confirming observation (entropy reduced, superposition collapsing)
    ΔH > 0 → contradicting observation (entropy increased, fold detected)
    ΔH = 0 → null observation (gate already collapsed, no change)

    seq_id: monotone canonical emission order within one SupportEngine instance.
    Assigned by SupportEngine._seq at the moment this Pearl is constructed.
    seq_id is wall-clock independent. It is not globally unique across instances.
    First Pearl from a fresh engine has seq_id=1. See INVAR_EXECUTION_TEMPORAL_CONTRACT.md §4.2.

    coupling_propagated: support deltas propagated to bonded manifestations.
    Each entry is (node_key_j, gate_id, ΔP_j) per Work 5 §coupling_propagated.
    ΔP_j = A_ij × Δφ — the fraction of this observation's support change that
    reaches bonded node j. Empty when no coupling_field is provided to ingest().
    """
    gate_id:       str
    node_key:      str
    workload_id:   str
    instrument_id: str
    cycle_id:      str
    ts:            float
    seq_id:        int    # monotone emission counter — see §4.2 of execution/temporal contract

    H_before:    float
    H_after:     float
    delta_H:     float          # H_after - H_before

    phi_R_before: float
    phi_R_after:  float
    phi_B_before: float
    phi_B_after:  float

    state_before: GateState
    state_after:  GateState

    # Work 5 §coupling_propagated — populated when coupling_field is passed to ingest()
    coupling_propagated: List[Tuple[str, str, float]] = field(default_factory=list)

    @property
    def is_fold(self) -> bool:
        """ΔH > 0 indicates a contradiction — the field is oscillating."""
        return self.delta_H > 0.0

    @property
    def is_collapse_event(self) -> bool:
        return self.state_before == GateState.U and self.state_after != GateState.U


# ---------------------------------------------------------------------------
# Manifestation key
# ---------------------------------------------------------------------------

ManifestationKey = Tuple[str, str]  # (workload_id, node_key)


def manifestation_key(workload_id: str, node_key: str) -> ManifestationKey:
    return (workload_id, node_key)


# ---------------------------------------------------------------------------
# Canonical ingest fingerprint (ET-G3)
# ---------------------------------------------------------------------------

# Content-based identity key for one execution unit.
# Excludes cycle_id (transport id), t0 (wall clock), raw_evidence (passthrough).
_ContribKey = Tuple[str, float, float, str]   # (gate_id, phi_R, phi_B, decay_class.value)
_IngestKey  = Tuple[str, str, str, Tuple[_ContribKey, ...]]  # (instrument, workload, node, contribs)


def _ingest_fingerprint(envelope: "ObsGateEnvelope") -> _IngestKey:
    contribs = tuple(sorted(
        (c.gate_id, c.phi_R, c.phi_B, c.decay_class.value)
        for c in envelope.contributions
    ))
    return (envelope.instrument_id, envelope.workload_id, envelope.node_key, contribs)


# ---------------------------------------------------------------------------
# SupportEngine
# ---------------------------------------------------------------------------

class SupportEngine:
    """
    The substrate write path: envelope in, gate state updated, pearls out.

    Thread safety: not thread-safe by default. Callers serialise writes or
    provide their own locking. For async use, wrap ingest() in an executor.
    """

    def __init__(self) -> None:
        # gate_store[(workload_id, node_key)][gate_id] = Gate
        self._gates: Dict[ManifestationKey, Dict[str, Gate]] = defaultdict(dict)
        # Pearl listeners — called synchronously on each pearl emitted
        self._listeners: List[Callable[[Pearl], None]] = []
        # Monotone emission counter — incremented once per Pearl construction (ET-G5 fix)
        self._seq: int = 0
        # ET-G3: idempotency guard. Maps content fingerprint → immutable Pearl tuple.
        # Scope: per SupportEngine instance lifetime. Not persisted. Not distributed.
        self._admitted: Dict[_IngestKey, Tuple[Pearl, ...]] = {}
        # ET-G6: bypass counter. Incremented when ingest() is called without
        # _SEQUENCER_WRITE_TOKEN. Observability metadata — does not affect physics.
        self._bypass_count: int = 0

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        envelope: ObsGateEnvelope,
        coupling_field: Any = None,
        *,
        _sequencer_token: Any = None,
    ) -> List[Pearl]:
        """
        Process one ObsGateEnvelope. Returns the list of Pearls emitted.

        For each SupportContribution:
          1. Look up (or create) the gate
          2. Compute H_before
          3. Apply contribution
          4. Compute H_after
          5. Emit Pearl if H changed

        coupling_field (optional): any object with an .edges() method returning
        objects with .i, .j (ManifestationKey), and .value (float A_ij).
        When provided, each Pearl records coupling_propagated entries for bonded
        manifestations: ΔP_j = A_ij × Δφ  (Work 5 §coupling_propagated).
        SupportEngine does not import CouplingField — duck-typed at call site.

        _sequencer_token (private, keyword-only): Internal capability token.
        Must only be passed by IngestSequencer.flush(). When absent,
        _bypass_count is incremented (soft enforcement, ET-G6).
        """
        # ET-G6: track unauthorized write path.
        if _sequencer_token is not _SEQUENCER_WRITE_TOKEN:
            self._bypass_count += 1

        # ET-G3: idempotency guard — same normalized content on same engine instance.
        # Returns cached Pearls; skips gate mutation, seq_id advancement, listener calls.
        _key = _ingest_fingerprint(envelope)
        if _key in self._admitted:
            return list(self._admitted[_key])

        t = time.time()
        mkey = manifestation_key(envelope.workload_id, envelope.node_key)
        pearls: List[Pearl] = []

        for contribution in envelope.contributions:
            gate = self._get_or_create(mkey, contribution.gate_id, envelope)

            # Snapshot before
            phi_R_before, phi_B_before = gate.accumulated(t)
            state_before = gate.state(t)
            H_before = gate.energy(t)

            # Apply contribution
            gate.add_contribution(contribution)

            # Snapshot after
            phi_R_after, phi_B_after = gate.accumulated(t)
            state_after = gate.state(t)
            H_after = gate.energy(t)

            delta_H = H_after - H_before

            # Propagation law (Work 5 §coupling_propagated):
            #   ΔP_j = A_ij × Δφ
            # where Δφ is the net support change at this gate (R direction).
            # Only computed when coupling_field is provided and support changed.
            coupling_propagated: List[Tuple[str, str, float]] = []
            if coupling_field is not None:
                delta_phi_R = phi_R_after - phi_R_before
                delta_phi_B = phi_B_after - phi_B_before
                # Dominant support change: confirming (R) takes precedence
                delta_phi = delta_phi_R if abs(delta_phi_R) >= abs(delta_phi_B) else delta_phi_B
                if abs(delta_phi) > 1e-12:
                    for edge in coupling_field.edges():
                        other_mkey = None
                        if edge.i == mkey:
                            other_mkey = edge.j
                        elif edge.j == mkey:
                            other_mkey = edge.i
                        if other_mkey is None:
                            continue
                        a_ij = edge.value
                        if a_ij < 1e-12:
                            continue
                        delta_P = a_ij * delta_phi
                        # Entry: (node_key_j, gate_id, ΔP_j)
                        coupling_propagated.append((other_mkey[1], contribution.gate_id, delta_P))

            self._seq += 1
            pearl = Pearl(
                gate_id=contribution.gate_id,
                node_key=envelope.node_key,
                workload_id=envelope.workload_id,
                instrument_id=envelope.instrument_id,
                cycle_id=envelope.cycle_id,
                ts=t,
                seq_id=self._seq,
                H_before=H_before,
                H_after=H_after,
                delta_H=delta_H,
                phi_R_before=phi_R_before,
                phi_R_after=phi_R_after,
                phi_B_before=phi_B_before,
                phi_B_after=phi_B_after,
                state_before=state_before,
                state_after=state_after,
                coupling_propagated=coupling_propagated,
            )
            pearls.append(pearl)

            if abs(delta_H) > 1e-9:
                for listener in self._listeners:
                    try:
                        listener(pearl)
                    except Exception:
                        log.exception("[support_engine] pearl listener raised")

            if pearl.is_collapse_event:
                log.debug(
                    "[support_engine] gate collapsed: %s/%s → %s",
                    mkey, contribution.gate_id, state_after,
                )

        self._admitted[_key] = tuple(pearls)
        return pearls

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def gate(self, workload_id: str, node_key: str, gate_id: str) -> Optional[Gate]:
        mkey = manifestation_key(workload_id, node_key)
        return self._gates[mkey].get(gate_id)

    def gates(
        self, workload_id: str, node_key: str
    ) -> Dict[str, Gate]:
        mkey = manifestation_key(workload_id, node_key)
        return dict(self._gates.get(mkey, {}))

    def manifestations(self) -> Iterator[ManifestationKey]:
        """Iterate over all known (workload_id, node_key) pairs."""
        yield from self._gates.keys()

    def field_energy(self, t: Optional[float] = None) -> float:
        """
        L(F) = Σ H(g) over all unresolved gates in the field.

        This is the full field energy functional (gate level, no coupling).
        Coupling and dissipation are added by the gravity layer.
        """
        if t is None:
            t = time.time()
        total = 0.0
        for gate_map in self._gates.values():
            for g in gate_map.values():
                total += g.energy(t)
        return total

    def manifestation_energy(
        self, workload_id: str, node_key: str, t: Optional[float] = None
    ) -> float:
        """E_self(L) = Σ H(g) for all gates in this manifestation."""
        if t is None:
            t = time.time()
        mkey = manifestation_key(workload_id, node_key)
        return sum(g.energy(t) for g in self._gates.get(mkey, {}).values())

    # ------------------------------------------------------------------
    # Pearl listener registry
    # ------------------------------------------------------------------

    def add_listener(self, fn: Callable[[Pearl], None]) -> None:
        """Register a function to be called on every Pearl emission."""
        self._listeners.append(fn)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(
        self,
        mkey: ManifestationKey,
        gate_id: str,
        envelope: ObsGateEnvelope,
    ) -> Gate:
        if gate_id not in self._gates[mkey]:
            self._gates[mkey][gate_id] = Gate(
                gate_id=gate_id,
                workload_id=envelope.workload_id,
                node_key=envelope.node_key,
            )
        return self._gates[mkey][gate_id]
