"""
skg.core.gravity
================
The gravity field — the entropy-gradient instrument scheduler.

Gravity follows Definition 4 of Work 5:

    Φ(I, L, t) = Σ_{g ∈ W(I) ∩ G(L) : state(g)=U} H(g) / c(I) × penalty(I, L, t)

Φ is the expected entropy reduction potential of instrument I on manifestation L
per unit cost. Gravity ranks instruments by Φ and produces a DispatchEnvelope.

This is the substrate's read path. It never writes gate state. It reads the
SupportEngine and produces DispatchEnvelopes for domain adapters to execute.

Instrument registration:
    Instruments declare their gate coverage W(I) — the set of gate_ids they
    can observe — and their cost c(I). Domain adapters register instruments
    with the gravity field via InstrumentProfile.

The substrate does not know what an instrument does. It knows:
  - which gates the instrument can observe (W(I))
  - how much it costs (c(I))
  - its penalty at this moment (penalty)

This is the domain-agnostic contract.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .envelope import DispatchEnvelope, InstrumentTarget
from .gate import GateState
from .support_engine import SupportEngine


# ---------------------------------------------------------------------------
# Instrument profile
# ---------------------------------------------------------------------------

@dataclass
class InstrumentProfile:
    """
    Everything the gravity field needs to know about an instrument.

    instrument_id  — opaque, matches what adapters and ObsGateEnvelopes use
    gate_coverage  — set of gate_ids this instrument can observe
    cost           — c(I) ≥ 1; higher cost = lower Φ per unit entropy
    penalty_fn     — optional callable(node_key, workload_id, t) → float in [0, 1]
                     returns 1.0 if no penalty (default), 0.0 if fully blocked
    args_fn        — optional callable(node_key, workload_id) → dict
                     provides instrument-specific args for DispatchEnvelope
    """
    instrument_id: str
    gate_coverage: Set[str]           # gate_ids this instrument resolves
    cost:          float = 1.0        # c(I) — instrument execution cost
    penalty_fn:    Optional[Callable[[str, str, float], float]] = None
    args_fn:       Optional[Callable[[str, str], Dict[str, Any]]] = None

    def penalty(self, node_key: str, workload_id: str, t: float) -> float:
        if self.penalty_fn is None:
            return 1.0
        try:
            return float(self.penalty_fn(node_key, workload_id, t))
        except Exception:
            return 1.0

    def args(self, node_key: str, workload_id: str) -> Dict[str, Any]:
        if self.args_fn is None:
            return {}
        try:
            return dict(self.args_fn(node_key, workload_id))
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Gravity field
# ---------------------------------------------------------------------------

class GravityField:
    """
    Computes entropy-reduction potential Φ(I, L, t) for all registered
    instruments and manifestations, and produces a ranked DispatchEnvelope.

    Domain adapters call register_instrument() to declare their instruments.
    The kernel calls rank() to get the current dispatch schedule.
    """

    def __init__(self, engine: SupportEngine) -> None:
        self._engine = engine
        self._instruments: Dict[str, InstrumentProfile] = {}

    def register_instrument(self, profile: InstrumentProfile) -> None:
        """Register an instrument with the gravity field."""
        self._instruments[profile.instrument_id] = profile

    def unregister_instrument(self, instrument_id: str) -> None:
        self._instruments.pop(instrument_id, None)

    # ------------------------------------------------------------------
    # Core gravity computation
    # ------------------------------------------------------------------

    def phi(
        self,
        instrument_id: str,
        workload_id: str,
        node_key: str,
        t: Optional[float] = None,
    ) -> float:
        """
        Φ(I, L, t) = Σ H(g) / c(I) × penalty

        Sum is over gates in W(I) ∩ G(L) that are in state U.
        Returns 0.0 if instrument unknown or no gates match.
        """
        if t is None:
            t = time.time()

        profile = self._instruments.get(instrument_id)
        if profile is None:
            return 0.0

        gates = self._engine.gates(workload_id, node_key)
        entropy_sum = 0.0

        for gate_id in profile.gate_coverage:
            gate = gates.get(gate_id)
            if gate is None:
                # Gate has never been observed — it is in maximum superposition
                # H(g) = 1.0 bit (zero-observation limit)
                entropy_sum += 1.0
            elif gate.state(t) == GateState.U:
                entropy_sum += gate.energy(t)
            # Collapsed gates contribute 0 (already included by default)

        if entropy_sum == 0.0:
            return 0.0

        p = profile.penalty(node_key, workload_id, t)
        c = max(profile.cost, 1e-10)
        return (entropy_sum / c) * p

    def rank(
        self,
        workload_id: Optional[str] = None,
        node_key: Optional[str] = None,
        t: Optional[float] = None,
        top_k: int = 20,
    ) -> List[InstrumentTarget]:
        """
        Rank all (instrument, manifestation) pairs by Φ.

        If workload_id and/or node_key are given, restrict to that manifestation.
        Otherwise rank across all known manifestations.

        Returns top_k InstrumentTargets sorted by priority descending.
        """
        if t is None:
            t = time.time()

        # Determine which manifestations to score
        if workload_id and node_key:
            manifestations = [(workload_id, node_key)]
        elif workload_id:
            manifestations = [
                (wid, nk) for (wid, nk) in self._engine.manifestations()
                if wid == workload_id
            ]
        elif node_key:
            manifestations = [
                (wid, nk) for (wid, nk) in self._engine.manifestations()
                if nk == node_key
            ]
        else:
            manifestations = list(self._engine.manifestations())

        targets: List[InstrumentTarget] = []

        for wid, nk in manifestations:
            for iid, profile in self._instruments.items():
                phi_val = self.phi(iid, wid, nk, t)
                if phi_val <= 0.0:
                    continue
                targets.append(InstrumentTarget(
                    instrument_id=iid,
                    node_key=nk,
                    workload_id=wid,
                    priority=phi_val,
                    reason=f"Φ={phi_val:.4f} (Σ H(g)/c×penalty)",
                    args=profile.args(nk, wid),
                ))

        targets.sort(key=lambda t_: t_.priority, reverse=True)
        return targets[:top_k]

    def dispatch(
        self,
        workload_id: Optional[str] = None,
        node_key: Optional[str] = None,
        t: Optional[float] = None,
        top_k: int = 20,
    ) -> DispatchEnvelope:
        """
        Produce a DispatchEnvelope with the ranked instrument targets.
        This is the gravity field's output to domain adapters.
        """
        if t is None:
            t = time.time()
        targets = self.rank(workload_id, node_key, t, top_k)
        return DispatchEnvelope(
            targets=targets,
            field_energy=self._engine.field_energy(t),
        )

    # ------------------------------------------------------------------
    # Phase / fiber tensor (for master equation coupling)
    # ------------------------------------------------------------------

    def fiber_tensor(
        self, workload_id: str, node_key: str, t: Optional[float] = None
    ) -> complex:
        """
        Ψᵢ = Σ_{g ∈ Ωᵢ} H(g) · e^(iθ(g))   (Work 6 Definition 1)

        H-weighted phase sum. High-entropy (uncertain) gates dominate.
        Near-collapsed gates (H≈0) contribute negligibly.

        |Ψᵢ| ≤ E_self(Ωᵢ) = Σ H(g), with equality iff all phases aligned.
        Local incoherence: C(Ψᵢ) = 1 - |Ψᵢ| / E_self(Ωᵢ).
        """
        if t is None:
            t = time.time()
        gates = self._engine.gates(workload_id, node_key)
        if not gates:
            return complex(0.0)
        return sum(g.weighted_phase(t) for g in gates.values())

    def self_energy(
        self, workload_id: str, node_key: str, t: Optional[float] = None
    ) -> float:
        """
        E_self(Ωᵢ) = Σ H(g) = total gate entropy in manifestation i.

        This is the upper bound on |Ψᵢ|. When all phases are aligned,
        |Ψᵢ| = E_self (fully coherent). In general |Ψᵢ| ≤ E_self.
        """
        return self._engine.manifestation_energy(workload_id, node_key, t)

    def local_incoherence(
        self, workload_id: str, node_key: str, t: Optional[float] = None
    ) -> float:
        """
        C(Ψᵢ) = 1 - |Ψᵢ| / E_self(Ωᵢ)    ∈ [0, 1]

        0 = fully coherent (all phases aligned, max information compression)
        1 = fully incoherent (phases cancel, no net coherence)

        Derived from the H-weighted Ψ definition — not a bolted-on penalty.
        """
        e = self.self_energy(workload_id, node_key, t)
        if e < 1e-12:
            return 0.0
        psi = self.fiber_tensor(workload_id, node_key, t)
        return 1.0 - abs(psi) / e

    def global_coherence(self, t: Optional[float] = None) -> float:
        """
        r(Ψ) = |Σᵢ Ψᵢ| / Σᵢ|Ψᵢ|    ∈ [0, 1]

        Global Kuramoto order parameter over all active manifestations.
        Used to compute T_eff(r) = T₀·(1 - r + ε).
        """
        if t is None:
            t = time.time()
        psi_sum = complex(0.0)
        amp_sum = 0.0
        for wid, nk in self._engine.manifestations():
            psi = self.fiber_tensor(wid, nk, t)
            psi_sum += psi
            amp_sum += abs(psi)
        if amp_sum < 1e-12:
            return 0.0
        return abs(psi_sum) / amp_sum

    def effective_temperature(self, T0: float = 1.0, t: Optional[float] = None) -> float:
        """
        T_eff(Ψ) = T₀ · (1 - r(Ψ) + ε)

        High coherence (r→1): T_eff → 0, gravity concentrates on highest-Φ instruments.
        Low coherence  (r→0): T_eff → T₀, gravity explores broadly.
        """
        r = self.global_coherence(t)
        return T0 * (1.0 - r + 1e-10)

    def receptivity(
        self, workload_id: str, node_key: str, t: Optional[float] = None
    ) -> float:
        """
        sin(π(1 - p̄)) — derived receptivity for Kuramoto coupling.

        p̄ is the mean realization probability across all gates in the
        manifestation. At superposition (p̄=0.5): receptivity = 1.0.
        At collapse: receptivity → 0.
        """
        if t is None:
            t = time.time()
        gates = self._engine.gates(workload_id, node_key)
        if not gates:
            return 1.0   # no observations → maximum receptivity
        p_bar = sum(g.p(t) for g in gates.values()) / len(gates)
        return math.sin(math.pi * (1.0 - p_bar))
