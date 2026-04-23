"""
invar.persistence.proto_causality
===================================
Non-canonical, deterministic cross-window structural continuity detection
with bounded causal weight measurement.

ProtoCausality detects which execution windows share gate identity — the same
(workload_id, node_key, gate_id) triple appears in both windows.  When two
windows share at least one gate, a proto-causal link exists between them.

This is structural continuity, not causation:

    window A ↔ window B  ⟺  ∃ gate g : g ∈ A ∧ g ∈ B

Links are ordered (earlier window first) by window position in
ExecutionWindows.cycle_ids ordering (which is itself ordered by min seq_id).

Causal weight measures link strength as a normalized fraction of shared gates:

    weight(A, B) = |shared_gates(A,B)| / min(|A|, |B|)

Weight is bounded in [0, 1].  A weight of 1.0 means the smaller window is
entirely contained in the larger.  Weight is 0.0 when no link exists.

API:
    causal.links()               → list of (cycle_id_a, cycle_id_b) pairs
    causal.links_from(cycle_id)  → later windows linked from this cycle
    causal.links_to(cycle_id)    → earlier windows linking into this cycle
    causal.shared_gates(a, b)    → frozenset of gate keys shared by a and b
    causal.weight(a, b)          → normalized link strength ∈ [0, 1]
    causal.weighted_links()      → list of (cycle_id_a, cycle_id_b, weight)

Gate key: (workload_id, node_key, gate_id) — the canonical triple.

Safety:
    - No Pearl fields modified
    - No Layer 0 physics touched
    - Non-canonical: discarding this object has zero substrate effect
    - No mutations to ExecutionWindows or its Pearls
    - Deterministic: same input → same links and weights

Usage:
    from invar.persistence.execution_window import ExecutionWindows
    from invar.persistence.proto_causality import ProtoCausality

    ew = ExecutionWindows.build(archive.pearls)
    causal = ProtoCausality.build(ew)

    for a, b, w in causal.weighted_links():
        print(a, "→", b, f"weight={w:.3f}", "gates:", causal.shared_gates(a, b))
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, FrozenSet, List, Tuple, Union

from invar.persistence.execution_window import ExecutionWindows

# Gate identity triple
GateKey = Tuple[str, str, str]  # (workload_id, node_key, gate_id)


class ProtoCausality:
    """
    Non-canonical cross-window structural continuity graph.

    Links two execution windows when they share at least one gate identity.
    Links are ordered pairs (earlier, later) by window position.
    """

    def __init__(self, windows: ExecutionWindows) -> None:
        cycle_ids = windows.cycle_ids

        # Gate-key sets and sizes per window
        gate_sets: Dict[str, FrozenSet[GateKey]] = {}
        window_sizes: Dict[str, int] = {}
        for cid in cycle_ids:
            w = windows.get(cid)
            gate_sets[cid] = frozenset(
                (p.workload_id, p.node_key, p.gate_id) for p in w
            )
            window_sizes[cid] = len(gate_sets[cid])

        # Build ordered links, shared-gate index, and weights
        self._links: List[Tuple[str, str]] = []
        self._shared: Dict[Tuple[str, str], FrozenSet[GateKey]] = {}
        self._weights: Dict[Tuple[str, str], float] = {}
        self._from: Dict[str, List[str]] = defaultdict(list)
        self._to: Dict[str, List[str]] = defaultdict(list)

        for i, a in enumerate(cycle_ids):
            for b in cycle_ids[i + 1 :]:
                shared = gate_sets[a] & gate_sets[b]
                if shared:
                    key = (a, b)
                    self._links.append(key)
                    self._shared[key] = shared
                    denom = min(window_sizes[a], window_sizes[b])
                    self._weights[key] = len(shared) / denom if denom > 0 else 0.0
                    self._from[a].append(b)
                    self._to[b].append(a)

    @classmethod
    def build(cls, windows: ExecutionWindows) -> "ProtoCausality":
        """Construct ProtoCausality from an ExecutionWindows object."""
        return cls(windows)

    # ------------------------------------------------------------------
    # Link access
    # ------------------------------------------------------------------

    def links(self) -> List[Tuple[str, str]]:
        """
        Return all proto-causal links as ordered (earlier, later) pairs.

        Links are in the order they were discovered (outer loop = earlier
        window, inner loop = later window by position).
        """
        return list(self._links)

    def links_from(self, cycle_id: str) -> List[str]:
        """
        Return cycle_ids of later windows linked from cycle_id.

        Returns [] if cycle_id has no forward links or is not in any window.
        """
        return list(self._from.get(cycle_id, []))

    def links_to(self, cycle_id: str) -> List[str]:
        """
        Return cycle_ids of earlier windows that link into cycle_id.

        Returns [] if cycle_id has no backward links or is not in any window.
        """
        return list(self._to.get(cycle_id, []))

    def shared_gates(self, a: str, b: str) -> FrozenSet[GateKey]:
        """
        Return the frozenset of gate keys shared by windows a and b.

        Checks both (a, b) and (b, a) orderings.
        Returns an empty frozenset if the pair has no link.
        """
        key = (a, b)
        if key in self._shared:
            return self._shared[key]
        rev = (b, a)
        if rev in self._shared:
            return self._shared[rev]
        return frozenset()

    def weight(self, a: str, b: str) -> float:
        """
        Return the causal weight of the link between windows a and b.

        weight = |shared_gates(a,b)| / min(|gates(a)|, |gates(b)|)

        Bounded in [0.0, 1.0].  Returns 0.0 when no link exists or either
        cycle_id is unknown.  Checks both (a,b) and (b,a) orderings.
        """
        key = (a, b)
        if key in self._weights:
            return self._weights[key]
        rev = (b, a)
        if rev in self._weights:
            return self._weights[rev]
        return 0.0

    def weighted_links(self) -> List[Tuple[str, str, float]]:
        """
        Return all links as (earlier_cycle, later_cycle, weight) triples.

        Same ordering as links().  Weight is in [0.0, 1.0].
        """
        return [(a, b, self._weights[(a, b)]) for a, b in self._links]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Number of proto-causal links."""
        return len(self._links)
