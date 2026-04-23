"""
invar.core.canonical_boundary
=============================
Bounded canonical-facing advisory projection of proto-topology — Stage 23.

CanonicalBoundary projects non-canonical proto-regions from ProtoTopology into
a deterministic advisory surface that canonical-layer consumers may query.  It
introduces canonical *visibility* of topology without canonical *mutation* of
any truth state.

Key principle:

    The canonical boundary is a view, not a mutation.

    Proto-topology remains non-canonical.  The boundary exposes structural
    advisory information to canonical-layer consumers but does not:
        - modify phi_R, phi_B
        - change energy(), p(), or collapse logic
        - inject support into any gate
        - mutate the canonical graph
        - create Pearls or emit narration

Region labeling scheme:

    Each proto-region is assigned a deterministic label equal to the
    lexicographically smallest node-id string in that region.  This is stable
    as long as the minimum member of a region is unchanged.

    label(R) = min(R)    where R is a frozenset of str node-ids

Safety properties:
    - Entirely non-canonical: no write-back to canonical graph, Gate, or Pearl
    - Deterministic: same ProtoTopology input → same advisory projection
    - Reversible: reset() / recompute() clear projection without substrate effect
    - Advisory only: projected region ids are labels, not canonical identities
    - Gate.step() NOT modified; phi_R, phi_B, energy(), p() NOT touched

Relationship to earlier stages:
    Stage 15: TopologyTrace          — bounded historical coherence memory
    Stage 17: TopologyCandidates     — candidate pair identification
    Stage 19: TopologyCommitments    — committed pair surface
    Stage 20: kappa_commitment       — commitment causal influence on weights
    Stage 21: regulation_signal()    — over-stabilization counter-pressure
    Stage 22: ProtoTopology          — regional structure from committed pairs
    Stage 23: CanonicalBoundary      — canonical-facing advisory projection
                                       (this module)

Usage:
    from invar.core.proto_topology import ProtoTopology
    from invar.core.canonical_boundary import CanonicalBoundary

    proto = ProtoTopology()
    proto.evaluate_edges(comms.edges())

    boundary = CanonicalBoundary()
    boundary.project(proto)

    # Advisory queries (read-only; no canonical mutation):
    boundary.region_of("gate_id")         # str label or None
    boundary.same_region("g1", "g2")      # bool
    boundary.region_sizes()               # dict {label: int}
    boundary.region_ids()                 # sorted list of labels
    boundary.nodes_in_region("g1")        # frozenset of node-ids or None
    boundary.snapshot()                   # immutable Advisory snapshot

    # Reset / rebuild (non-destructive to canonical state):
    boundary.reset()
    boundary.recompute(proto)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .proto_topology import ProtoTopology


# ---------------------------------------------------------------------------
# Advisory snapshot — immutable record of a single projection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AdvisorySnapshot:
    """
    Immutable snapshot of a CanonicalBoundary projection.

    Fields
    ------
    node_labels : mapping of node-id → region label (str)
    region_sizes : mapping of region label → region size (int)
    region_members : mapping of region label → frozenset of node-ids

    All fields are immutable.  This snapshot is decoupled from the live
    CanonicalBoundary — later mutations of the boundary do not affect it.
    """
    node_labels: FrozenSet[tuple]       # frozenset of (node_id, label) pairs
    region_sizes: FrozenSet[tuple]      # frozenset of (label, size) pairs
    region_members: FrozenSet[tuple]    # frozenset of (label, frozenset) pairs

    def to_dicts(self):
        """Convenience: unpack into three plain dicts for inspection."""
        return (
            dict(self.node_labels),
            dict(self.region_sizes),
            {label: members for label, members in self.region_members},
        )


# ---------------------------------------------------------------------------
# CanonicalBoundary
# ---------------------------------------------------------------------------

class CanonicalBoundary:
    """
    Bounded canonical-facing advisory projection of proto-topology.

    Projects ProtoTopology proto-regions into a deterministic advisory surface
    that canonical-layer consumers may query without canonical state being
    mutated.  This is canonical visibility only, not canonical mutation.

    Region label scheme:
        label(R) = min(R)   — lexicographically smallest node-id in region R.

    No configuration parameters — projection is determined entirely by the
    ProtoTopology passed to project() or recompute().
    """

    def __init__(self) -> None:
        self._node_to_label: Dict[str, str] = {}      # node_id → region label
        self._label_to_members: Dict[str, FrozenSet[str]] = {}  # label → members

    # ------------------------------------------------------------------
    # Projection
    # ------------------------------------------------------------------

    def project(self, proto: "ProtoTopology") -> None:
        """
        Project proto-topology regions into the canonical advisory boundary.

        Clears any previous projection first.  Region labels are assigned as
        min(region) — the lexicographically smallest node-id string in each
        region.  Deterministic: same proto-topology input → same output.

        Parameters
        ----------
        proto : ProtoTopology
            Source of non-canonical proto-regions.  Its regions() list is
            consumed read-only; no state in proto is modified.
        """
        node_to_label: Dict[str, str] = {}
        label_to_members: Dict[str, FrozenSet[str]] = {}

        for region in proto.regions():
            label = min(region)               # deterministic, stable label
            label_to_members[label] = region
            for node in region:
                node_to_label[node] = label

        self._node_to_label = node_to_label
        self._label_to_members = label_to_members

    # ------------------------------------------------------------------
    # Advisory query surface (read-only; never mutates canonical state)
    # ------------------------------------------------------------------

    def region_of(self, node_id: Any) -> Optional[str]:
        """
        Return the advisory region label for node_id, or None if not projected.

        The label is advisory only — it is not a canonical identity.
        """
        return self._node_to_label.get(str(node_id))

    def same_region(self, id_i: Any, id_j: Any) -> bool:
        """
        Return True if id_i and id_j share the same advisory proto-region.

        Symmetric: same_region(i, j) == same_region(j, i).
        Returns False if either node is not in any projected region.
        """
        label_i = self._node_to_label.get(str(id_i))
        if label_i is None:
            return False
        return label_i == self._node_to_label.get(str(id_j))

    def region_sizes(self) -> Dict[str, int]:
        """
        Return {region_label: size} for all projected regions.

        Returned dict is a copy — modifying it does not affect the boundary.
        """
        return {label: len(members) for label, members in self._label_to_members.items()}

    def region_ids(self) -> List[str]:
        """Return sorted list of projected region labels."""
        return sorted(self._label_to_members)

    def nodes_in_region(self, node_id: Any) -> Optional[FrozenSet[str]]:
        """
        Return the full frozenset of node-ids in the same region as node_id.

        Returns None if node_id is not in any projected region.
        """
        label = self._node_to_label.get(str(node_id))
        if label is None:
            return None
        return self._label_to_members[label]

    def contains_node(self, node_id: Any) -> bool:
        """Return True if node_id is in any projected region."""
        return str(node_id) in self._node_to_label

    def region_count(self) -> int:
        """Number of projected regions."""
        return len(self._label_to_members)

    def node_count(self) -> int:
        """Total number of nodes covered by projected regions."""
        return len(self._node_to_label)

    # ------------------------------------------------------------------
    # Reset / recompute
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Clear the advisory projection.

        Clearing has zero effect on canonical gate or graph state.
        """
        self._node_to_label = {}
        self._label_to_members = {}

    def recompute(self, proto: "ProtoTopology") -> None:
        """
        Rebuild advisory projection from scratch.

        Equivalent to reset() followed by project(proto).  Deterministic.
        """
        self.project(proto)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> AdvisorySnapshot:
        """
        Return an immutable snapshot of the current advisory projection.

        The snapshot is decoupled from the live boundary — subsequent reset()
        or recompute() calls do not affect the returned snapshot.
        """
        return AdvisorySnapshot(
            node_labels=frozenset(self._node_to_label.items()),
            region_sizes=frozenset(
                (label, len(members))
                for label, members in self._label_to_members.items()
            ),
            region_members=frozenset(
                (label, members)
                for label, members in self._label_to_members.items()
            ),
        )
