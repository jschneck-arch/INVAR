"""
invar.adapters.redteam.relationship_graph
==========================================
Red team domain relationship graph — read-only, adapter-local.

RelationshipGraph derives directed cycle relationships and multi-hop attack
pattern matches from proto-causal links and domain primitive classifications.
All outputs are computed at construction from existing adapter-layer objects.
Nothing is executed, modified, or stored as new canonical state.

CycleRelationship types (adapter-local):
    "continuation"      — same primitive in both cycles (continued operation)
    "stage_transition"  — known primitive-pair transition (e.g. cred → lateral)
    "unclassified"      — proto-causal link exists but no known pattern

Known stage transitions (labeled):
    credential_to_lateral, lateral_to_execution, discovery_to_lateral,
    discovery_to_execution, execution_to_persistence, execution_to_collection,
    execution_to_c2, collection_to_c2, credential_to_execution, persistence_to_c2

Named attack patterns (3-hop or 2-hop primitive sequences):
    credential_lateral_exec   — CREDENTIAL_ACCESS → LATERAL_MOVEMENT → EXECUTION
    discovery_lateral_exec    — DISCOVERY → LATERAL_MOVEMENT → EXECUTION
    exec_persist_c2           — EXECUTION → PERSISTENCE → COMMAND_AND_CONTROL
    cred_exec_collect         — CREDENTIAL_ACCESS → EXECUTION → COLLECTION
    collect_to_c2             — COLLECTION → COMMAND_AND_CONTROL

API:
    graph.cycle_relationships()         → all CycleRelationship objects
    graph.relationships_from(cycle_id)  → outgoing relationships
    graph.relationships_to(cycle_id)    → incoming relationships
    graph.pattern_matches()             → detected PatternMatch objects
    graph.pivot_cycles()                → cycles that relay (source and dest)
    graph.artifact_reuse_map()          → gate_key → [cycle_ids] for reused gates

Constraints:
    - No Layer 0 modification
    - No mutation of any input layer
    - Domain labels and relationships are adapter-local only
    - Deterministic: same observer + domain_model → same outputs
    - Discardable: zero side-effects
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from invar.adapters.redteam.domain_model import OperationPrimitive, RedTeamDomainModel
from invar.adapters.redteam.observer import RedTeamObserver

GateKey = Tuple[str, str, str]


# ---------------------------------------------------------------------------
# Relationship and pattern type constants
# ---------------------------------------------------------------------------

class RelationshipType:
    """Adapter-local cycle relationship classification constants."""
    CONTINUATION     = "continuation"
    STAGE_TRANSITION = "stage_transition"
    UNCLASSIFIED     = "unclassified"


# ---------------------------------------------------------------------------
# Known directed primitive transitions
# ---------------------------------------------------------------------------

_STAGE_TRANSITIONS: Dict[Tuple[str, str], str] = {
    (OperationPrimitive.CREDENTIAL_ACCESS,  OperationPrimitive.LATERAL_MOVEMENT):    "credential_to_lateral",
    (OperationPrimitive.LATERAL_MOVEMENT,   OperationPrimitive.EXECUTION):            "lateral_to_execution",
    (OperationPrimitive.DISCOVERY,          OperationPrimitive.LATERAL_MOVEMENT):     "discovery_to_lateral",
    (OperationPrimitive.DISCOVERY,          OperationPrimitive.EXECUTION):            "discovery_to_execution",
    (OperationPrimitive.EXECUTION,          OperationPrimitive.PERSISTENCE):          "execution_to_persistence",
    (OperationPrimitive.EXECUTION,          OperationPrimitive.COLLECTION):           "execution_to_collection",
    (OperationPrimitive.EXECUTION,          OperationPrimitive.COMMAND_AND_CONTROL):  "execution_to_c2",
    (OperationPrimitive.COLLECTION,         OperationPrimitive.COMMAND_AND_CONTROL):  "collection_to_c2",
    (OperationPrimitive.CREDENTIAL_ACCESS,  OperationPrimitive.EXECUTION):            "credential_to_execution",
    (OperationPrimitive.PERSISTENCE,        OperationPrimitive.COMMAND_AND_CONTROL):  "persistence_to_c2",
}

# Named multi-hop attack patterns: name → ordered tuple of OperationPrimitive values
_ATTACK_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "collect_to_c2":           (OperationPrimitive.COLLECTION,         OperationPrimitive.COMMAND_AND_CONTROL),
    "cred_exec_collect":       (OperationPrimitive.CREDENTIAL_ACCESS,  OperationPrimitive.EXECUTION,       OperationPrimitive.COLLECTION),
    "credential_lateral_exec": (OperationPrimitive.CREDENTIAL_ACCESS,  OperationPrimitive.LATERAL_MOVEMENT, OperationPrimitive.EXECUTION),
    "discovery_lateral_exec":  (OperationPrimitive.DISCOVERY,          OperationPrimitive.LATERAL_MOVEMENT, OperationPrimitive.EXECUTION),
    "exec_persist_c2":         (OperationPrimitive.EXECUTION,          OperationPrimitive.PERSISTENCE,      OperationPrimitive.COMMAND_AND_CONTROL),
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CycleRelationship:
    """
    Immutable directed relationship between two causally-linked cycles.

    Derived from proto-causal links and domain primitive classification.
    Never stored as canonical truth.
    """
    from_cycle:        str
    to_cycle:          str
    from_primitive:    str   # OperationPrimitive of from_cycle
    to_primitive:      str   # OperationPrimitive of to_cycle
    relationship_type: str   # RelationshipType constant
    transition_label:  Optional[str]  # e.g. "credential_to_lateral" or None
    weight:            float           # proto-causal link weight
    shared_gate_count: int             # number of shared gate keys


@dataclass(frozen=True)
class PatternMatch:
    """
    Immutable match of a named attack pattern in the cycle graph.

    cycle_path is the sequence of cycle IDs matching the pattern.
    primitives mirrors the pattern definition.
    avg_weight is the mean proto-causal link weight along the path.
    """
    pattern_name: str
    cycle_path:   Tuple[str, ...]
    primitives:   Tuple[str, ...]
    avg_weight:   float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_relationship(
    prim_a: str,
    prim_b: str,
) -> Tuple[str, Optional[str]]:
    """Return (relationship_type, transition_label) for a primitive pair."""
    if (prim_a == prim_b
            and prim_a != OperationPrimitive.UNCLASSIFIED
            and prim_a != OperationPrimitive.MULTI_STAGE):
        return RelationshipType.CONTINUATION, None
    label = _STAGE_TRANSITIONS.get((prim_a, prim_b))
    if label is not None:
        return RelationshipType.STAGE_TRANSITION, label
    return RelationshipType.UNCLASSIFIED, None


def _find_pattern_matches(
    cycle_ids: List[str],
    adj: Dict[str, List[Tuple[str, float]]],
    primitives: Dict[str, str],
) -> List[PatternMatch]:
    """
    Find all path-matches of named attack patterns in the directed cycle graph.

    Uses DFS with frozenset visited tracking for cycle safety.  Paths are
    explored in adjacency-list order (sorted for determinism).  Results are
    deduplicated and sorted by (-avg_weight, pattern_name, cycle_path).
    """
    results: List[PatternMatch] = []
    seen: set = set()

    for pattern_name, pattern_prims in sorted(_ATTACK_PATTERNS.items()):
        n = len(pattern_prims)
        for src in cycle_ids:
            if primitives.get(src) != pattern_prims[0]:
                continue
            # DFS stack: (node, path, weights, visited)
            stack = [(src, (src,), (), frozenset([src]))]
            while stack:
                node, path, weights, visited = stack.pop()
                depth = len(path)
                if depth == n:
                    key = (pattern_name, path)
                    if key not in seen:
                        seen.add(key)
                        avg_w = sum(weights) / len(weights) if weights else 0.0
                        results.append(PatternMatch(
                            pattern_name=pattern_name,
                            cycle_path=path,
                            primitives=pattern_prims,
                            avg_weight=avg_w,
                        ))
                    continue
                next_prim = pattern_prims[depth]
                for nxt, w in reversed(adj.get(node, [])):
                    if nxt not in visited and primitives.get(nxt) == next_prim:
                        stack.append((nxt, path + (nxt,), weights + (w,), visited | {nxt}))

    return sorted(results, key=lambda pm: (-pm.avg_weight, pm.pattern_name, pm.cycle_path))


# ---------------------------------------------------------------------------
# Relationship graph
# ---------------------------------------------------------------------------

class RelationshipGraph:
    """
    Read-only directed graph of cycle relationships and attack pattern matches.

    All data is derived at construction from RedTeamObserver (for proto-causal
    links and gate inventories) and RedTeamDomainModel (for primitive
    classifications).  Nothing is executed or stored as new canonical state.
    """

    def __init__(
        self,
        observer: RedTeamObserver,
        domain_model: RedTeamDomainModel,
    ) -> None:
        cycle_ids = observer.cycle_ids

        # Primitive for each cycle
        prims: Dict[str, str] = {
            cid: domain_model.cycle_primitive(cid) for cid in cycle_ids
        }

        # Build adjacency list (sorted for determinism)
        adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        for a, b, w in observer._causal.weighted_links():
            adj[a].append((b, w))
        for node in adj:
            adj[node].sort(key=lambda x: x[0])

        # Build cycle relationships
        all_rels: List[CycleRelationship] = []
        from_index: Dict[str, List[CycleRelationship]] = defaultdict(list)
        to_index:   Dict[str, List[CycleRelationship]] = defaultdict(list)

        for a, b, w in sorted(observer._causal.weighted_links(), key=lambda x: (x[0], x[1])):
            prim_a = prims.get(a, OperationPrimitive.UNCLASSIFIED)
            prim_b = prims.get(b, OperationPrimitive.UNCLASSIFIED)
            rel_type, label = _classify_relationship(prim_a, prim_b)
            rel = CycleRelationship(
                from_cycle=a,
                to_cycle=b,
                from_primitive=prim_a,
                to_primitive=prim_b,
                relationship_type=rel_type,
                transition_label=label,
                weight=w,
                shared_gate_count=len(observer._causal.shared_gates(a, b)),
            )
            all_rels.append(rel)
            from_index[a].append(rel)
            to_index[b].append(rel)

        self._relationships: List[CycleRelationship] = all_rels
        self._from_index: Dict[str, List[CycleRelationship]] = dict(from_index)
        self._to_index:   Dict[str, List[CycleRelationship]] = dict(to_index)

        # Pattern matches
        self._pattern_matches = _find_pattern_matches(cycle_ids, dict(adj), prims)

        # Pivot cycles: cycles that are both a source and a destination
        self._pivot_cycles: List[str] = sorted(
            set(from_index.keys()) & set(to_index.keys())
        )

        # Artifact reuse map: gate_key → sorted cycle_ids (2+ occurrences only)
        gate_cycles: Dict[GateKey, List[str]] = defaultdict(list)
        for cid in cycle_ids:
            seen_keys: set = set()
            for p in (observer._windows.get(cid) or []):
                gk: GateKey = (p.workload_id, p.node_key, p.gate_id)
                if gk not in seen_keys:
                    seen_keys.add(gk)
                    gate_cycles[gk].append(cid)
        self._reuse_map: Dict[GateKey, List[str]] = {
            gk: sorted(cycles)
            for gk, cycles in sorted(gate_cycles.items())
            if len(cycles) >= 2
        }

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def cycle_relationships(self) -> List[CycleRelationship]:
        """Return all directed cycle relationships (independent copy)."""
        return list(self._relationships)

    def relationships_from(self, cycle_id: str) -> List[CycleRelationship]:
        """Return all relationships where cycle_id is the source."""
        return list(self._from_index.get(cycle_id, []))

    def relationships_to(self, cycle_id: str) -> List[CycleRelationship]:
        """Return all relationships where cycle_id is the destination."""
        return list(self._to_index.get(cycle_id, []))

    def pattern_matches(self) -> List[PatternMatch]:
        """
        Return all detected named attack pattern matches.

        Sorted by avg_weight descending, then pattern_name, then cycle_path.
        """
        return list(self._pattern_matches)

    def pivot_cycles(self) -> List[str]:
        """
        Return cycle IDs that appear as both relationship source and destination.

        These are relay nodes in the cycle graph — operationally significant as
        pivot or handoff points between attack stages.
        """
        return list(self._pivot_cycles)

    def artifact_reuse_map(self) -> Dict[GateKey, List[str]]:
        """
        Return gate keys that appear in two or more cycles.

        Maps each reused gate key to a sorted list of cycle IDs.
        Returns an independent copy.
        """
        return {gk: list(cycles) for gk, cycles in self._reuse_map.items()}
