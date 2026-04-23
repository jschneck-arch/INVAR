"""
invar.adapters.redteam.acknowledgment
=======================================
Append-only operator acknowledgment store for FeedbackEngine suggestions.

AcknowledgmentStore records operator classifications of Suggestion objects.
Each classification (Acknowledgment) is immutable and append-only: once a
suggestion is acknowledged, the decision cannot be overwritten or deleted.
This makes the store an auditable log of operator judgment.

Valid decisions: "valid" | "irrelevant" | "investigate"

No explanation field, no narrative, no reasoning stored — only:
    suggestion_id  →  decision  +  timestamp

The store does NOT modify Invar, does NOT trigger actions, does NOT feed back
into Layer 0 physics, and does NOT affect FeedbackEngine or observer state.

API:
    store.record(ack)              → append an Acknowledgment (raises on duplicate)
    store.get(suggestion_id)       → Optional[Acknowledgment]
    store.all()                    → all Acknowledgments in record order
    store.by_decision(decision)    → filtered list

FeedbackEngine integration (read-only join):
    engine.with_ack(store)         → [(Suggestion, Optional[Acknowledgment])]

Constraints:
    - Append-only: no overwrite, no deletion
    - Records are frozen (immutable)
    - No Invar state modification
    - No automation or feedback loops
    - Deterministic: same record sequence → same store state
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

VALID_DECISIONS = frozenset({"valid", "irrelevant", "investigate"})


@dataclass(frozen=True)
class Acknowledgment:
    """
    Immutable operator classification of a single Suggestion.

    Fields carry only the decision reference — no explanation, no narrative.
    """
    suggestion_id: str
    decision: str    # "valid" | "irrelevant" | "investigate"
    ts: float        # Unix timestamp of the acknowledgment


class AcknowledgmentStore:
    """
    Append-only audit log of operator acknowledgments.

    Each suggestion_id can be acknowledged at most once.  Records are
    immutable after insertion.  No Invar state is touched.
    """

    def __init__(self) -> None:
        self._log: List[Acknowledgment] = []
        self._index: Dict[str, Acknowledgment] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, ack: Acknowledgment) -> None:
        """
        Append an Acknowledgment to the store.

        Raises
        ------
        ValueError
            If ack.decision is not one of the valid decisions.
        ValueError
            If ack.suggestion_id has already been acknowledged (no overwrite).
        """
        if ack.decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{ack.decision}'. "
                f"Must be one of: {sorted(VALID_DECISIONS)}"
            )
        if ack.suggestion_id in self._index:
            raise ValueError(
                f"suggestion_id '{ack.suggestion_id}' already acknowledged "
                f"(decision='{self._index[ack.suggestion_id].decision}'). "
                "AcknowledgmentStore is append-only."
            )
        self._log.append(ack)
        self._index[ack.suggestion_id] = ack

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, suggestion_id: str) -> Optional[Acknowledgment]:
        """
        Return the Acknowledgment for suggestion_id, or None if unacknowledged.
        """
        return self._index.get(suggestion_id)

    def all(self) -> List[Acknowledgment]:
        """Return all Acknowledgments in record order (independent copy)."""
        return list(self._log)

    def by_decision(self, decision: str) -> List[Acknowledgment]:
        """Return all Acknowledgments with the given decision."""
        return [a for a in self._log if a.decision == decision]

    def __len__(self) -> int:
        """Number of recorded acknowledgments."""
        return len(self._log)
