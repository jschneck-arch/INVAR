"""
invar.adapters.redteam.feedback
=================================
Structured suggestion engine derived from RedTeamObserver signals.

FeedbackEngine converts observed signals into Suggestion objects — structured,
evidence-backed findings for a human operator.  Nothing is executed, inferred
beyond metrics, or mutated.  The operator decides; the engine only proposes.

Suggestion types:
    "reuse"         — gate identity appears across N+ execution windows
    "high_activity" — cycle has high normalized incoming causal weight
    "anomaly"       — cycle has low normalized incoming causal weight
    "chain"         — a sequence of 3+ cycles connected by strong causal links

All suggestions are generated at construction time (eager, deterministic).
Suggestion IDs are SHA-256 digests of sorted evidence — same evidence always
produces the same ID and is deduplicated.

API:
    engine.suggestions()          → all Suggestion objects (sorted by confidence desc)
    engine.by_type(type_str)      → suggestions of one type
    engine.by_cycle(cycle_id)     → suggestions referencing a specific cycle

Constraints:
    - No Layer 0 modification
    - No Pearl modification
    - No execution, automation, or control
    - No free-text narration — evidence fields only (cycles, artifacts, confidence)
    - No inference beyond measured signal values
    - Fully discardable

Default thresholds (all configurable at construction):
    reuse_min_count        = 2     gates appearing in ≥ 2 windows
    high_activity_threshold = 0.7  activity ≥ 0.7 → high_activity suggestion
    low_activity_threshold  = 0.3  activity ≤ 0.3 → anomaly suggestion
    chain_threshold         = 0.5  link weight ≥ 0.5 for chain detection
    chain_min_length        = 3    minimum window count in a chain
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from invar.adapters.redteam.observer import RedTeamObserver

GateKey = Tuple[str, str, str]  # (workload_id, node_key, gate_id)


@dataclass(frozen=True)
class Suggestion:
    """
    Immutable structured finding derived from Invar signals.

    Fields contain only evidence — no free-text narration, no inferred intent,
    no domain speculation.
    """
    suggestion_id: str
    type: str
    cycle_id: Optional[str]
    supporting_cycles: Tuple[str, ...]
    supporting_artifacts: Tuple[GateKey, ...]
    confidence: float


def _make_id(*parts: str) -> str:
    """SHA-256 digest of sorted string parts, truncated to 16 hex chars."""
    key = "|".join(sorted(str(p) for p in parts))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class FeedbackEngine:
    """
    Suggestion engine: converts RedTeamObserver signals into operator findings.

    All suggestions are generated at construction and are immutable.
    """

    def __init__(
        self,
        observer: RedTeamObserver,
        reuse_min_count: int = 2,
        high_activity_threshold: float = 0.7,
        low_activity_threshold: float = 0.3,
        chain_threshold: float = 0.5,
        chain_min_length: int = 3,
    ) -> None:
        self._observer = observer
        seen_ids: set = set()
        all_suggestions: List[Suggestion] = []

        def _add(s: Suggestion) -> None:
            if s.suggestion_id not in seen_ids:
                seen_ids.add(s.suggestion_id)
                all_suggestions.append(s)

        cycle_ids = observer.cycle_ids

        # ------------------------------------------------------------------
        # TYPE 1: reuse — gate identity appears in N+ windows
        # ------------------------------------------------------------------
        gate_windows: Dict[GateKey, List[str]] = defaultdict(list)
        for cid in cycle_ids:
            seen_gk: FrozenSet[GateKey] = frozenset(
                (p.workload_id, p.node_key, p.gate_id)
                for p in observer._windows.get(cid)
            )
            for gk in seen_gk:
                gate_windows[gk].append(cid)

        total_windows = max(len(cycle_ids), 1)
        for gk, cycles in sorted(gate_windows.items()):
            if len(cycles) >= reuse_min_count:
                sid = _make_id("reuse", str(gk), *cycles)
                _add(Suggestion(
                    suggestion_id=sid,
                    type="reuse",
                    cycle_id=None,
                    supporting_cycles=tuple(sorted(cycles)),
                    supporting_artifacts=(gk,),
                    confidence=min(1.0, len(cycles) / total_windows),
                ))

        # ------------------------------------------------------------------
        # TYPE 2: high_activity — activity >= threshold
        # ------------------------------------------------------------------
        for cid in cycle_ids:
            act = observer.activity(cid)
            if act >= high_activity_threshold:
                sid = _make_id("high_activity", cid)
                _add(Suggestion(
                    suggestion_id=sid,
                    type="high_activity",
                    cycle_id=cid,
                    supporting_cycles=(cid,),
                    supporting_artifacts=(),
                    confidence=act,
                ))

        # ------------------------------------------------------------------
        # TYPE 3: anomaly — activity <= threshold
        # ------------------------------------------------------------------
        for cid in cycle_ids:
            act = observer.activity(cid)
            if act <= low_activity_threshold:
                sid = _make_id("anomaly", cid)
                _add(Suggestion(
                    suggestion_id=sid,
                    type="anomaly",
                    cycle_id=cid,
                    supporting_cycles=(cid,),
                    supporting_artifacts=(),
                    confidence=min(1.0, 1.0 - act),
                ))

        # ------------------------------------------------------------------
        # TYPE 4: chain — sequence of N+ windows via strong causal links
        # ------------------------------------------------------------------
        strong = observer.strong_links(chain_threshold)
        chains = _find_chains(strong, chain_min_length)
        for path, weights in chains:
            avg_weight = sum(weights) / len(weights) if weights else 0.0
            sid = _make_id("chain", *path)
            _add(Suggestion(
                suggestion_id=sid,
                type="chain",
                cycle_id=None,
                supporting_cycles=tuple(path),
                supporting_artifacts=(),
                confidence=min(1.0, avg_weight),
            ))

        # Sort by confidence descending, then suggestion_id for tie-breaking
        self._suggestions: List[Suggestion] = sorted(
            all_suggestions,
            key=lambda s: (-s.confidence, s.suggestion_id),
        )

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def suggestions(self) -> List[Suggestion]:
        """Return all suggestions sorted by confidence descending."""
        return list(self._suggestions)

    def by_type(self, type_str: str) -> List[Suggestion]:
        """Return all suggestions of the given type."""
        return [s for s in self._suggestions if s.type == type_str]

    def by_cycle(self, cycle_id: str) -> List[Suggestion]:
        """Return all suggestions that reference cycle_id."""
        return [s for s in self._suggestions if cycle_id in s.supporting_cycles]

    def with_ack(self, store: "AcknowledgmentStore") -> List[Tuple[Suggestion, Optional["Acknowledgment"]]]:
        """
        Return each suggestion paired with its operator acknowledgment (or None).

        Read-only join between the suggestion list and an AcknowledgmentStore.
        Order matches suggestions() (sorted by confidence desc).  The store
        is not modified.
        """
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore  # noqa: F401
        return [(s, store.get(s.suggestion_id)) for s in self._suggestions]


# ---------------------------------------------------------------------------
# Chain detection
# ---------------------------------------------------------------------------

def _find_chains(
    strong_links: List[Tuple[str, str, float]],
    min_length: int,
) -> List[Tuple[List[str], List[float]]]:
    """
    Find all maximal paths of length >= min_length in the strong-link DAG.

    Returns list of (path, weights) where path is a list of cycle_ids and
    weights is the list of edge weights along the path.

    Paths are deterministic: nodes visited in sorted order where there is a
    choice.  Cycles in the graph are avoided via visited tracking.
    """
    if not strong_links:
        return []

    # Build adjacency: node → sorted list of (successor, weight)
    adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    all_nodes: set = set()
    for a, b, w in strong_links:
        adj[a].append((b, w))
        all_nodes.add(a)
        all_nodes.add(b)

    # Sort adjacency lists for determinism
    for node in adj:
        adj[node].sort(key=lambda x: x[0])

    # Find source nodes (no incoming strong edges)
    has_incoming: set = {b for _, b, _ in strong_links}
    sources = sorted(all_nodes - has_incoming)

    results: List[Tuple[List[str], List[float]]] = []

    for src in sources:
        # DFS — stack holds (node, path_so_far, weights_so_far, visited_set)
        stack = [(src, [src], [], frozenset([src]))]
        while stack:
            node, path, weights, visited = stack.pop()
            nexts = [(n, w) for n, w in adj.get(node, []) if n not in visited]
            if nexts:
                for nxt, w in reversed(nexts):  # reversed so sorted order is DFS-left-first
                    stack.append((nxt, path + [nxt], weights + [w], visited | {nxt}))
            else:
                # Maximal path — record if long enough
                if len(path) >= min_length:
                    results.append((path, weights))

    return results
