"""
invar.adapters.redteam.action_proposal
========================================
Design-only controlled action interface — proposes but never executes.

ActionProposalEngine derives ProposedAction objects from FeedbackEngine
suggestions filtered by AcknowledgmentStore state.  A proposed action
represents what operational step could address a suggestion.  It is NOT
executed, NOT triggered, and NOT acted upon automatically — ever.

Operator flow:
    Suggestion → (operator acknowledges) → ProposedAction → operator decides
                                                           → external system

Proposal eligibility:
    Only suggestions acknowledged as "valid" or "investigate" receive a
    ProposedAction.  "open" and "reviewed-irrelevant" suggestions are excluded.

Action types (parallel to Suggestion types):
    "examine_reuse"         — from "reuse" suggestions
    "examine_high_activity" — from "high_activity" suggestions
    "examine_anomaly"       — from "anomaly" suggestions
    "trace_chain"           — from "chain" suggestions

ProposedAction fields:
    proposal_id     SHA-256 of (suggestion_id + action_type), 16 hex chars
    suggestion_id   reference to originating Suggestion
    action_type     declarative type string (never imperative)
    target          primary cycle_id or gate-key string from the Suggestion
    parameters      sorted tuple of (key, value) string pairs; .params() → dict
    confidence      inherited from source Suggestion

API:
    engine.proposals()              → all ProposedActions (confidence desc)
    engine.for_suggestion(sid)      → Optional[ProposedAction]
    engine.by_type(action_type)     → list filtered by action_type

Constraints:
    - No execution, no triggering, no tool invocation
    - No Layer 0 modification
    - No Suggestion or Acknowledgment mutation
    - Fully derived: same engine + store → same proposals
    - Discardable: zero side-effects on construction or destruction
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
from invar.adapters.redteam.feedback import FeedbackEngine, Suggestion

# Suggestion type → action type
_SUGGESTION_TO_ACTION: Dict[str, str] = {
    "reuse":          "examine_reuse",
    "high_activity":  "examine_high_activity",
    "anomaly":        "examine_anomaly",
    "chain":          "trace_chain",
}

# Acknowledgment decisions that make a suggestion eligible for a proposal
_ELIGIBLE_DECISIONS = frozenset({"valid", "investigate"})


def _make_id(*parts: str) -> str:
    key = "|".join(sorted(str(p) for p in parts))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class ProposedAction:
    """
    Immutable declarative action proposal derived from a Suggestion.

    Never executed automatically.  Operator decides whether and how to act.
    Parameters are stored as sorted (key, value) string pairs; use .params()
    for dict access.
    """
    proposal_id: str
    suggestion_id: str
    action_type: str
    target: str
    parameters: Tuple[Tuple[str, str], ...]
    confidence: float

    def params(self) -> Dict[str, str]:
        """Return parameters as a plain dict (independent copy)."""
        return dict(self.parameters)


def _build_action(suggestion: Suggestion) -> ProposedAction:
    """Derive a ProposedAction from a Suggestion."""
    action_type = _SUGGESTION_TO_ACTION.get(suggestion.type, "examine_unknown")

    if suggestion.type == "reuse":
        gk = suggestion.supporting_artifacts[0] if suggestion.supporting_artifacts else ("", "", "")
        target = "|".join(str(x) for x in gk)
        raw: Dict[str, str] = {
            "cycles": ",".join(suggestion.supporting_cycles),
            "count":  str(len(suggestion.supporting_cycles)),
        }
    elif suggestion.type in ("high_activity", "anomaly"):
        target = suggestion.cycle_id or ""
        raw = {
            "cycle_id":   suggestion.cycle_id or "",
            "confidence": f"{suggestion.confidence:.6f}",
        }
    elif suggestion.type == "chain":
        target = suggestion.supporting_cycles[0] if suggestion.supporting_cycles else ""
        raw = {
            "path":       ",".join(suggestion.supporting_cycles),
            "length":     str(len(suggestion.supporting_cycles)),
            "avg_weight": f"{suggestion.confidence:.6f}",
        }
    else:
        target = suggestion.cycle_id or ""
        raw = {}

    return ProposedAction(
        proposal_id=_make_id(suggestion.suggestion_id, action_type),
        suggestion_id=suggestion.suggestion_id,
        action_type=action_type,
        target=target,
        parameters=tuple(sorted(raw.items())),
        confidence=suggestion.confidence,
    )


class ActionProposalEngine:
    """
    Design-only action proposal engine: derives ProposedActions from eligible
    suggestions.

    Eligible suggestions are those acknowledged as "valid" or "investigate".
    All proposals are generated at construction and are immutable.
    Nothing is executed or triggered.
    """

    def __init__(
        self,
        engine: FeedbackEngine,
        store: AcknowledgmentStore,
    ) -> None:
        proposals: List[ProposedAction] = []
        index: Dict[str, ProposedAction] = {}

        for suggestion in engine.suggestions():
            ack = store.get(suggestion.suggestion_id)
            if ack is not None and ack.decision in _ELIGIBLE_DECISIONS:
                action = _build_action(suggestion)
                proposals.append(action)
                index[suggestion.suggestion_id] = action

        self._proposals: List[ProposedAction] = sorted(
            proposals,
            key=lambda a: (-a.confidence, a.proposal_id),
        )
        self._index = index

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def proposals(self) -> List[ProposedAction]:
        """Return all ProposedActions sorted by confidence descending."""
        return list(self._proposals)

    def for_suggestion(self, suggestion_id: str) -> Optional[ProposedAction]:
        """Return the ProposedAction for a suggestion, or None if not eligible."""
        return self._index.get(suggestion_id)

    def by_type(self, action_type: str) -> List[ProposedAction]:
        """Return all ProposedActions of the given action type."""
        return [a for a in self._proposals if a.action_type == action_type]
