"""
invar.core.proto_topology
=========================
Non-canonical bounded proto-topological regional structure — Stage 22.

ProtoTopology surfaces connected components of committed gate-pair edges as
bounded, reversible, non-canonical proto-regions.  It is the first step where
structure appears as multi-node form rather than only pairwise edges.

Formation rule:

    (i, j) ∈ K  ⟹  (i, j) ∈ G_proto
    proto-regions = connected components of G_proto with |region| ≥ 2

Where K is the committed pair set from TopologyCommitments.  The canonical
graph is never read, written, or modified by this module.

Safety properties:
    - Entirely non-canonical: no write-back to canonical graph, Gate, or Pearl
    - Deterministic: same committed edges → same proto-regions
    - Reversible: reset() / recompute() clear proposals without substrate effect
    - Symmetric: region membership is order-independent (undirected edges)
    - Bounded: proto-region count and size are bounded by input edge set
    - Gate.step() NOT modified; phi_R, phi_B, energy(), p() NOT touched

Relationship to earlier stages:
    Stage 15: TopologyTrace          — bounded historical coherence memory
    Stage 17: TopologyCandidates     — candidate pair identification
    Stage 19: TopologyCommitments    — committed pair surface
    Stage 20: kappa_commitment       — commitment causal influence on weights
    Stage 21: regulation_signal()    — over-stabilization counter-pressure
    Stage 22: ProtoTopology          — regional structure from committed pairs
                                       (this module)

Usage:
    from invar.core.topology_commitments import TopologyCommitments
    from invar.core.proto_topology import ProtoTopology

    comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)
    # ... (evaluate commitments per time step) ...

    proto = ProtoTopology()
    proto.evaluate_edges(comms.edges())

    # Query regional structure:
    proto.regions()               # list of frozensets of node ids
    proto.region_of("gate_id")    # frozenset or None
    proto.contains_node("gate_id") # bool
    proto.region_count()          # int
    proto.node_count()            # int

    # Reset / rebuild (non-destructive to canonical state):
    proto.reset()
    proto.recompute(comms.edges())
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple


class ProtoTopology:
    """
    Bounded, reversible, non-canonical proto-regional structure.

    Computes connected components of the committed-pair graph and surfaces each
    component of size ≥ 2 as a proto-region.  Entirely separate from the
    canonical topology — resetting or discarding a ProtoTopology object has zero
    effect on substrate state.

    Parameters
    ----------
    None — ProtoTopology has no configuration parameters.  Its output is
    determined solely by the committed edges passed to evaluate_edges() or
    recompute().
    """

    def __init__(self) -> None:
        self._regions: List[FrozenSet[str]] = []
        self._node_to_region: Dict[str, FrozenSet[str]] = {}

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_edges(self, committed_edges: Iterable[Tuple[Any, Any]]) -> None:
        """
        Build proto-regions from the given committed pair edges.

        Clears any previous state first, then runs a BFS connected-component
        search over the undirected committed-pair graph.  Components of size ≥ 2
        are recorded as proto-regions; isolated nodes (no committed neighbors) are
        excluded.

        Parameters
        ----------
        committed_edges : iterable of (id_i, id_j) pairs
            Use TopologyCommitments.edges() as the source.  Each element may be
            any hashable pair; both orderings are treated identically.

        This method is idempotent: calling it twice with the same input produces
        the same result.  It is fully deterministic.
        """
        # Build undirected adjacency from committed edges
        adj: Dict[str, Set[str]] = defaultdict(set)
        for id_i, id_j in committed_edges:
            a, b = str(id_i), str(id_j)
            adj[a].add(b)
            adj[b].add(a)

        # BFS connected-component search
        visited: Set[str] = set()
        regions: List[FrozenSet[str]] = []

        for start in sorted(adj):          # sorted for determinism
            if start in visited:
                continue
            # BFS
            component: Set[str] = set()
            queue: deque[str] = deque([start])
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                component.add(node)
                for neighbor in adj[node]:
                    if neighbor not in visited:
                        queue.append(neighbor)
            if len(component) >= 2:
                region = frozenset(component)
                regions.append(region)

        # Build reverse lookup
        node_to_region: Dict[str, FrozenSet[str]] = {}
        for region in regions:
            for node in region:
                node_to_region[node] = region

        self._regions = regions
        self._node_to_region = node_to_region

    # ------------------------------------------------------------------
    # Query surface
    # ------------------------------------------------------------------

    def regions(self) -> List[FrozenSet[str]]:
        """
        Return list of current proto-regions.

        Each proto-region is a frozenset of node-id strings with |region| ≥ 2.
        The list is sorted by the lexicographically smallest member of each
        region for deterministic ordering.
        """
        return sorted(self._regions, key=lambda r: min(r))

    def region_of(self, node_id: Any) -> Optional[FrozenSet[str]]:
        """
        Return the proto-region containing node_id, or None if not in any region.

        Symmetric: region_of(i) and region_of(j) return the same frozenset
        when (i, j) were connected in the committed-pair graph.
        """
        return self._node_to_region.get(str(node_id))

    def contains_node(self, node_id: Any) -> bool:
        """Return True if node_id participates in any proto-region."""
        return str(node_id) in self._node_to_region

    def region_count(self) -> int:
        """Number of current proto-regions."""
        return len(self._regions)

    def node_count(self) -> int:
        """Total number of nodes participating in any proto-region."""
        return len(self._node_to_region)

    # ------------------------------------------------------------------
    # Reset / recompute
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Clear all proto-regions.

        Clearing has zero effect on canonical gate or graph state.
        """
        self._regions = []
        self._node_to_region = {}

    def recompute(self, committed_edges: Iterable[Tuple[Any, Any]]) -> None:
        """
        Rebuild proto-regions from scratch.

        Equivalent to reset() followed by evaluate_edges(committed_edges).
        Deterministic: result depends only on the supplied edge set.
        """
        self.evaluate_edges(committed_edges)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> FrozenSet[FrozenSet[str]]:
        """Return immutable snapshot of current proto-region set."""
        return frozenset(self._regions)
