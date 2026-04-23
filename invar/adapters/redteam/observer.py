"""
invar.adapters.redteam.observer
================================
Read-only red team observation adapter over Invar structures.

RedTeamObserver maps Invar persistence structures to red team observables
without modifying any underlying state.  All outputs are derived on demand
from the five Invar objects provided at construction.

Domain mapping (interpretation only — these are NOT Invar concepts):

    ExecutionWindow → "operation cycle"
    Gate identity   → "artifact / signal"
    CausalField     → "activity intensity"
    ProtoCausality  → "shared infrastructure usage"

API:
    observer.activity(cycle_id)           → float ∈ [0,1]
    observer.shared_infra(a, b)           → frozenset of gate keys
    observer.strong_links(threshold=0.5)  → [(a, b, weight), ...]
    observer.summary(cycle_id)            → dict with cycle observables

Safety:
    - No Invar objects modified (Pearl, Gate, TemporalGraph, ExecutionWindows,
      ProtoCausality, CausalField)
    - No Layer 0 physics touched
    - Adapter stores only references to provided objects — derives everything,
      stores nothing new
    - Discardable: zero side-effects on destruction
    - Deterministic: same input state → same outputs

Usage:
    from invar.persistence.pearl_archive import PearlArchive
    from invar.persistence.temporal_graph import TemporalGraph
    from invar.persistence.execution_window import ExecutionWindows
    from invar.persistence.proto_causality import ProtoCausality
    from invar.persistence.causal_field import CausalField
    from invar.adapters.redteam.observer import RedTeamObserver

    archive = PearlArchive()
    engine.add_listener(archive.record)
    # ... ingest ...

    pearls = archive.pearls
    temporal = TemporalGraph.build(pearls)
    windows = ExecutionWindows.build(pearls)
    causal = ProtoCausality.build(windows)
    field = CausalField.build(causal, windows)

    observer = RedTeamObserver(archive, temporal, windows, causal, field)
    print(observer.summary("cycle-A"))
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Tuple

from invar.persistence.causal_field import CausalField
from invar.persistence.execution_window import ExecutionWindows
from invar.persistence.pearl_archive import PearlArchive
from invar.persistence.proto_causality import ProtoCausality
from invar.persistence.temporal_graph import TemporalGraph

# Gate identity triple (workload_id, node_key, gate_id)
GateKey = Tuple[str, str, str]


class RedTeamObserver:
    """
    Read-only observation adapter mapping Invar structures to red team context.

    Derives all outputs from the provided Invar objects.  Stores only
    references — no new canonical state is introduced.
    """

    def __init__(
        self,
        archive: PearlArchive,
        temporal: TemporalGraph,
        windows: ExecutionWindows,
        causal: ProtoCausality,
        field: CausalField,
    ) -> None:
        self._archive = archive
        self._temporal = temporal
        self._windows = windows
        self._causal = causal
        self._field = field

    # ------------------------------------------------------------------
    # Observation API
    # ------------------------------------------------------------------

    @property
    def cycle_ids(self) -> List[str]:
        """Return ordered cycle_ids of all execution windows."""
        return self._windows.cycle_ids

    def activity(self, cycle_id: str) -> float:
        """
        Return the activity intensity of a cycle ∈ [0.0, 1.0].

        Derived from CausalField: the normalized accumulated incoming
        proto-causal weight for this cycle.  0.0 = no incoming influence;
        1.0 = highest relative incoming influence in the field.

        Returns 0.0 for unknown cycle_id.
        """
        return self._field.value(cycle_id)

    def shared_infra(self, a: str, b: str) -> FrozenSet[GateKey]:
        """
        Return gate identities shared between cycles a and b.

        Derived from ProtoCausality.shared_gates().  Each element is a
        (workload_id, node_key, gate_id) triple representing a reused
        artifact or signal across both operation cycles.

        Returns an empty frozenset if the cycles share no gates or either
        cycle_id is unknown.
        """
        return self._causal.shared_gates(a, b)

    def strong_links(self, threshold: float = 0.5) -> List[Tuple[str, str, float]]:
        """
        Return proto-causal links with weight ≥ threshold.

        Each element is (earlier_cycle, later_cycle, weight).  Links are in
        the same order as ProtoCausality.weighted_links().

        threshold must be in [0.0, 1.0].  At threshold=0.0 all links are
        returned; at threshold=1.0 only full-containment links are returned.
        """
        return [
            (a, b, w)
            for a, b, w in self._causal.weighted_links()
            if w >= threshold
        ]

    def summary(self, cycle_id: str) -> Dict:
        """
        Return a read-only observation summary for cycle_id.

        Returns
        -------
        dict with keys:
            "cycle_id"       : str   — the cycle identifier
            "activity"       : float — normalized incoming influence [0,1]
            "num_artifacts"  : int   — distinct gate identities in this cycle
            "incoming_links" : int   — number of cycles linking into this one
            "outgoing_links" : int   — number of cycles this one links into

        For unknown cycle_id, activity=0.0, num_artifacts=0, links=0.
        """
        window = self._windows.get(cycle_id)
        gate_keys: FrozenSet[GateKey] = frozenset(
            (p.workload_id, p.node_key, p.gate_id) for p in window
        )
        return {
            "cycle_id": cycle_id,
            "activity": self._field.value(cycle_id),
            "num_artifacts": len(gate_keys),
            "incoming_links": len(self._causal.links_to(cycle_id)),
            "outgoing_links": len(self._causal.links_from(cycle_id)),
        }
