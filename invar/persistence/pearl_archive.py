"""
invar.persistence.pearl_archive
================================
Append-only canonical Pearl archive with monotone seq_id enforcement.

PearlArchive is the Layer 1 audit surface.  It records Pearls emitted by a
SupportEngine and can restore substrate state into a fresh engine without
re-running ingest().

Two restoration paths:

  replay_into(engine)   — approximate replay
      Uses Pearl.phi_R_after / phi_B_after / state_after / ts as a decaying
      base layer via Gate._restore_from_pearl_snapshot().  Does not call
      engine.ingest(); does not fire listeners; does not advance engine._seq.
      Energy is mathematically equivalent to the original (exponential decay
      chain rule is exact).

  restore_into(engine)  — Pearl-native restoration scaffold (ET-G1B)
      Same mechanism as replay_into.  Gate._contributions remains empty —
      no SupportContribution objects are created.  engine._seq stays 0.
      Gate is accessible via engine.gate() immediately after restoration.

Safety:
  - No narration, no labels, no topology annotations
  - Pearl schema is defined by invar.core.support_engine.Pearl (truth only)
  - Non-canonical: archive state does not affect live substrate truth
  - Authorized to call Gate._restore_from_pearl_snapshot() (invar/persistence/ scope)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from invar.core.gate import Gate, GateState
from invar.core.support_engine import Pearl, SupportEngine


class PearlArchive:
    """
    Append-only canonical Pearl record with monotone seq_id enforcement.

    Usage:
        archive = PearlArchive()
        engine.add_listener(archive.record)

        # ... ingest observations ...

        engine_new = SupportEngine()
        archive.restore_into(engine_new)
    """

    def __init__(self) -> None:
        self._pearls: List[Pearl] = []
        self._last_seq: int = 0  # seq_ids start at 1; 0 is the sentinel floor

    # ------------------------------------------------------------------
    # Record (Pearl listener interface)
    # ------------------------------------------------------------------

    def record(self, pearl: Pearl) -> None:
        """
        Append one Pearl to the archive.

        Called as a Pearl listener (engine.add_listener(archive.record)).
        Enforces strict monotone seq_id ordering.

        Raises
        ------
        ValueError
            If pearl.seq_id <= last recorded seq_id (non-monotone).
        """
        if pearl.seq_id <= self._last_seq:
            raise ValueError(
                f"Non-monotone seq_id: received {pearl.seq_id}, "
                f"last was {self._last_seq}"
            )
        self._pearls.append(pearl)
        self._last_seq = pearl.seq_id

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    @property
    def pearls(self) -> List[Pearl]:
        """
        Return all recorded Pearls as an independent copy, in seq_id order.

        Mutating the returned list does not affect the archive.
        Pearls are always stored in emission order (seq_id monotone by
        record() invariant), so the copy is already sorted.
        """
        return list(self._pearls)

    def __len__(self) -> int:
        return len(self._pearls)

    # ------------------------------------------------------------------
    # Restoration paths
    # ------------------------------------------------------------------

    def replay_into(self, engine: SupportEngine) -> None:
        """
        Approximate replay: restore gate state into a fresh engine.

        For each unique (workload_id, node_key, gate_id) triple, takes the
        most recently recorded Pearl (highest seq_id) and sets the gate's
        base layer via Gate._restore_from_pearl_snapshot().

        Guarantees:
          - engine.ingest() is never called
          - engine._seq remains unchanged
          - engine listeners are never fired
          - gate._contributions remains empty
          - energy is mathematically equivalent to original (exponential chain rule)
        """
        self._restore_gates(engine)

    def restore_into(self, engine: SupportEngine) -> None:
        """
        Pearl-native restoration (ET-G1B).

        Identical mechanics to replay_into.  Gate state is established via
        Gate._restore_from_pearl_snapshot() from Pearl fields.  No
        SupportContribution objects are created; engine._seq stays 0.

        Gates are immediately accessible via engine.gate() after this call.
        """
        self._restore_gates(engine)

    # ------------------------------------------------------------------
    # Multi-adapter merge
    # ------------------------------------------------------------------

    @classmethod
    def merge(cls, *archives: "PearlArchive") -> "PearlArchive":
        """
        Merge multiple independent archives into one sorted by timestamp.

        Used when parallel adapters (e.g. MeasurementAdapter and
        WindowsIngestAdapter) each maintain their own archive with
        independently monotone seq_ids.  The merged archive assigns new
        seq_ids in ascending timestamp order so the monotone invariant is
        satisfied on the combined record.

        The source archives are not modified.
        """
        all_pearls = sorted(
            (p for a in archives for p in a._pearls),
            key=lambda p: (p.ts, p.seq_id),
        )
        merged = cls()
        for i, pearl in enumerate(all_pearls, start=1):
            from dataclasses import replace
            merged._pearls.append(replace(pearl, seq_id=i))
            merged._last_seq = i
        return merged

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _restore_gates(self, engine: SupportEngine) -> None:
        """
        Core restoration logic shared by replay_into and restore_into.

        For each gate, finds the last Pearl and uses its phi_R_after /
        phi_B_after / state_after / ts fields to establish a decaying base
        state in a fresh Gate.  Injects the gate directly into engine._gates
        without calling ingest() — authorized by invar/persistence/ scope.
        """
        # Collect most-recent Pearl per (workload_id, node_key, gate_id)
        # Pearls are in seq_id order, so iterating forward and overwriting
        # naturally yields the last Pearl per gate.
        latest: Dict[Tuple[str, str, str], Pearl] = {}
        for pearl in self._pearls:
            key = (pearl.workload_id, pearl.node_key, pearl.gate_id)
            latest[key] = pearl

        for (workload_id, node_key, gate_id), pearl in latest.items():
            gate = Gate(
                gate_id=gate_id,
                workload_id=workload_id,
                node_key=node_key,
            )
            gate._restore_from_pearl_snapshot(
                phi_R=pearl.phi_R_after,
                phi_B=pearl.phi_B_after,
                state=pearl.state_after,
                ts=pearl.ts,
            )
            mkey = (workload_id, node_key)
            engine._gates[mkey][gate_id] = gate
