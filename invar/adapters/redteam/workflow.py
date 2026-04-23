"""
invar.adapters.redteam.workflow
=================================
Read-only operator workflow view over FeedbackEngine suggestions and
AcknowledgmentStore decisions.

WorkflowView derives workflow state for each suggestion on demand from two
inputs (FeedbackEngine + AcknowledgmentStore) without storing new canonical
state, mutating either input, or triggering any action.

Workflow states (derived, not stored):
    "open"                 — no acknowledgment recorded
    "reviewed-valid"       — acknowledged with decision "valid"
    "reviewed-irrelevant"  — acknowledged with decision "irrelevant"
    "needs-investigation"  — acknowledged with decision "investigate"

Queue ordering (needs-investigation first, then open, then reviewed):
    1. needs-investigation   (highest priority)
    2. open
    3. reviewed-valid
    4. reviewed-irrelevant
    Within each tier: confidence descending, then suggestion_id ascending.

API:
    view.items()              → all suggestions as workflow dicts
    view.by_state(state)      → filtered workflow dicts for one state
    view.queue()              → all items in priority order
    view.counts()             → {state: count} for all four states

Constraints:
    - No new canonical state stored
    - No mutation of suggestions, acknowledgments, or Invar core
    - Deterministic: same engine + store → same outputs
    - Discardable: zero side-effects
"""
from __future__ import annotations

from typing import Dict, List, Optional

from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
from invar.adapters.redteam.feedback import FeedbackEngine, Suggestion

# Decision → workflow state
_DECISION_TO_STATE: Dict[str, str] = {
    "valid":       "reviewed-valid",
    "irrelevant":  "reviewed-irrelevant",
    "investigate": "needs-investigation",
}

# Priority order for queue() — lower number = higher priority
_STATE_PRIORITY: Dict[str, int] = {
    "needs-investigation": 0,
    "open":                1,
    "reviewed-valid":      2,
    "reviewed-irrelevant": 3,
}

_ALL_STATES = ("open", "reviewed-valid", "reviewed-irrelevant", "needs-investigation")

# Keys present in every workflow item dict
_ITEM_KEYS = ("suggestion_id", "type", "cycle_id", "confidence", "state")


class WorkflowView:
    """
    Read-only workflow organizer: derives operator queue from suggestions + acks.

    Constructed from a FeedbackEngine and an AcknowledgmentStore.  All output
    is computed on demand from those two sources — nothing is cached or persisted.
    """

    def __init__(
        self,
        engine: FeedbackEngine,
        store: AcknowledgmentStore,
    ) -> None:
        self._engine = engine
        self._store = store

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _state_of(self, suggestion: Suggestion) -> str:
        ack = self._store.get(suggestion.suggestion_id)
        if ack is None:
            return "open"
        return _DECISION_TO_STATE.get(ack.decision, "open")

    def _to_item(self, suggestion: Suggestion) -> Dict:
        return {
            "suggestion_id": suggestion.suggestion_id,
            "type":          suggestion.type,
            "cycle_id":      suggestion.cycle_id,
            "confidence":    suggestion.confidence,
            "state":         self._state_of(suggestion),
        }

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def items(self) -> List[Dict]:
        """
        Return all suggestions as workflow dicts in suggestion order.

        Each dict has keys: suggestion_id, type, cycle_id, confidence, state.
        Returns an independent copy — mutation does not affect internal state.
        """
        return [self._to_item(s) for s in self._engine.suggestions()]

    def by_state(self, state: str) -> List[Dict]:
        """
        Return workflow dicts filtered to a single state.

        Valid states: "open", "reviewed-valid", "reviewed-irrelevant",
        "needs-investigation".  Returns [] for an unrecognised state.
        Order matches items() (confidence-sorted) within the filtered set.
        """
        return [item for item in self.items() if item["state"] == state]

    def queue(self) -> List[Dict]:
        """
        Return all workflow items in priority order.

        Tier ordering (highest first):
            1. needs-investigation
            2. open
            3. reviewed-valid
            4. reviewed-irrelevant

        Within each tier: confidence descending, then suggestion_id ascending.
        """
        return sorted(
            self.items(),
            key=lambda item: (
                _STATE_PRIORITY.get(item["state"], 99),
                -item["confidence"],
                item["suggestion_id"],
            ),
        )

    def counts(self) -> Dict[str, int]:
        """
        Return the count of suggestions in each workflow state.

        All four states are always present in the result (count 0 if empty).
        """
        result: Dict[str, int] = {s: 0 for s in _ALL_STATES}
        for item in self.items():
            state = item["state"]
            result[state] = result.get(state, 0) + 1
        return result
