"""
invar.persistence.temporal_graph
=================================
Deterministic linear temporal structure over Pearl sequences.

TemporalGraph takes an ordered Pearl sequence from PearlArchive and makes it
navigable: each Pearl is a node, adjacent Pearls are connected by directed
edges in seq_id order.  The structure is strictly linear — no branching, no
merging, no loops.

    p[0] → p[1] → p[2] → ... → p[N-1]

API:
    graph.next(pearl)        → next Pearl in chain, or None at tail
    graph.prev(pearl)        → previous Pearl in chain, or None at head
    graph.path(start, end)   → list of Pearls from start to end inclusive
    graph.validate()         → raises ValueError on any consistency violation
    graph.replay(engine)     → restore gate state from chain's final snapshot

Consistency invariants enforced by validate():
    - seq_id strictly increasing:  seq[i+1] > seq[i]
    - no gaps:                     seq[i+1] == seq[i] + 1
    - no duplicates:               all seq_ids distinct
    - no cycles:                   guaranteed by linear structure (checked via
                                   the above — any cycle would break monotonicity)

Safety:
    - No Pearl fields are modified
    - No Layer 0 physics are touched
    - Non-canonical: graph is a read-only overlay; discarding it has zero effect
    - replay() uses Gate._restore_from_pearl_snapshot() (authorized scope)
    - replay() does not call engine.ingest(); engine._seq is not advanced
    - replay() does not create SupportContribution objects

Usage:
    from invar.persistence.pearl_archive import PearlArchive
    from invar.persistence.temporal_graph import TemporalGraph

    archive = PearlArchive()
    engine.add_listener(archive.record)
    # ... ingest observations ...

    graph = TemporalGraph.build(archive.pearls)
    graph.validate()

    # Navigate:
    first = graph.pearls[0]
    second = graph.next(first)

    # Path between two Pearls:
    segment = graph.path(first, second)

    # Replay into a fresh engine:
    engine_new = SupportEngine()
    graph.replay(engine_new)
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from invar.core.gate import Gate
from invar.core.support_engine import Pearl, SupportEngine


class TemporalGraph:
    """
    Deterministic linear temporal graph over a Pearl sequence.

    Nodes are Pearls; edges form a strict forward chain in seq_id order.
    Built from a list of Pearls (typically from PearlArchive.pearls).
    """

    def __init__(self, pearls: List[Pearl]) -> None:
        # Sort by seq_id — PearlArchive guarantees emission order, but accept
        # any ordering at construction and normalise here.
        self._pearls: List[Pearl] = sorted(pearls, key=lambda p: p.seq_id)
        # O(1) lookup: seq_id → index in sorted list
        self._by_seq: Dict[int, int] = {
            p.seq_id: i for i, p in enumerate(self._pearls)
        }

    @classmethod
    def build(cls, pearls: List[Pearl]) -> "TemporalGraph":
        """Construct a TemporalGraph from a Pearl sequence."""
        return cls(pearls)

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._pearls)

    @property
    def pearls(self) -> List[Pearl]:
        """Sorted copy of all Pearls in the graph (seq_id order)."""
        return list(self._pearls)

    def head(self) -> Optional[Pearl]:
        """First Pearl (lowest seq_id), or None if empty."""
        return self._pearls[0] if self._pearls else None

    def tail(self) -> Optional[Pearl]:
        """Last Pearl (highest seq_id), or None if empty."""
        return self._pearls[-1] if self._pearls else None

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next(self, pearl: Pearl) -> Optional[Pearl]:
        """
        Return the immediately following Pearl in the chain, or None.

        Returns None if pearl is the tail or is not in the graph.
        """
        idx = self._by_seq.get(pearl.seq_id)
        if idx is None or idx + 1 >= len(self._pearls):
            return None
        return self._pearls[idx + 1]

    def prev(self, pearl: Pearl) -> Optional[Pearl]:
        """
        Return the immediately preceding Pearl in the chain, or None.

        Returns None if pearl is the head or is not in the graph.
        """
        idx = self._by_seq.get(pearl.seq_id)
        if idx is None or idx == 0:
            return None
        return self._pearls[idx - 1]

    def path(self, start: Pearl, end: Pearl) -> List[Pearl]:
        """
        Return the inclusive subchain from start to end (seq_id order).

        Returns an empty list if either Pearl is not in the graph or if
        start comes after end in seq_id order.
        """
        i = self._by_seq.get(start.seq_id)
        j = self._by_seq.get(end.seq_id)
        if i is None or j is None or i > j:
            return []
        return list(self._pearls[i : j + 1])

    def contains(self, pearl: Pearl) -> bool:
        """Return True if pearl is in this graph."""
        return pearl.seq_id in self._by_seq

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """
        Assert temporal consistency of the graph.

        Checks (in order):
            1. No duplicate seq_ids
            2. seq_ids strictly increasing (monotone)
            3. No gaps: seq[i+1] == seq[i] + 1 (contiguous chain)
            4. No cycles (guaranteed by strict monotonicity — any cycle
               requires a non-monotone edge)

        Raises
        ------
        ValueError
            On the first consistency violation found, with a descriptive message.
        """
        seen: set = set()
        for i, p in enumerate(self._pearls):
            if p.seq_id in seen:
                raise ValueError(f"Duplicate seq_id in graph: {p.seq_id}")
            seen.add(p.seq_id)
            if i > 0:
                prev_p = self._pearls[i - 1]
                if p.seq_id <= prev_p.seq_id:
                    raise ValueError(
                        f"Non-monotone seq_id: {p.seq_id} after {prev_p.seq_id}"
                    )
                if p.seq_id != prev_p.seq_id + 1:
                    raise ValueError(
                        f"seq_id gap: expected {prev_p.seq_id + 1}, got {p.seq_id}"
                    )

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay(self, engine: SupportEngine) -> None:
        """
        Restore gate state from this temporal chain into a fresh engine.

        For each unique (workload_id, node_key, gate_id) triple, takes the
        most recently seen Pearl in the chain and establishes the gate's base
        layer via Gate._restore_from_pearl_snapshot().

        Guarantees:
          - engine.ingest() is never called
          - engine._seq remains unchanged
          - engine listeners are never fired
          - gate._contributions remains empty
          - energy is mathematically equivalent to original

        Authorized to use Gate._restore_from_pearl_snapshot() and to write
        directly to engine._gates (invar/persistence/ scope).
        """
        latest: Dict[Tuple[str, str, str], Pearl] = {}
        for pearl in self._pearls:
            key = (pearl.workload_id, pearl.node_key, pearl.gate_id)
            latest[key] = pearl  # later Pearls overwrite earlier ones

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
