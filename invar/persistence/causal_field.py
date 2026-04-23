"""
invar.persistence.causal_field
================================
Transient, non-canonical propagation field derived from weighted proto-causal
links.

CausalField converts proto-causal link weights into a per-window influence
signal.  For each execution window, incoming link weights are summed to produce
a raw influence score; raw scores are then normalized to [0, 1] so the window
with the highest accumulated incoming influence receives value 1.0.

    raw(W)  = Σ weight(A → W)  for all A linking into W
    value(W) = raw(W) / max(raw)   if max(raw) > 0
    value(W) = 0.0                  otherwise

Windows with no incoming links receive value 0.0.  A window at the head of the
causal chain (nothing points to it) always has value 0.0 regardless of its
outgoing weights.

API:
    field.value(cycle_id)   → normalized influence ∈ [0.0, 1.0]
    field.all()             → dict mapping cycle_id → value for all windows

Safety:
    - No Pearl fields modified
    - No Layer 0 physics touched
    - Non-canonical: discarding this object has zero substrate effect
    - No mutations to ProtoCausality, ExecutionWindows, or their Pearls
    - Deterministic: same input → same field

Usage:
    from invar.persistence.execution_window import ExecutionWindows
    from invar.persistence.proto_causality import ProtoCausality
    from invar.persistence.causal_field import CausalField

    ew = ExecutionWindows.build(archive.pearls)
    causal = ProtoCausality.build(ew)
    field = CausalField.build(causal, ew)

    for cid, v in sorted(field.all().items(), key=lambda x: -x[1]):
        print(cid, f"influence={v:.3f}")
"""
from __future__ import annotations

from typing import Dict, List

from invar.persistence.execution_window import ExecutionWindows
from invar.persistence.proto_causality import ProtoCausality


class CausalField:
    """
    Normalized per-window propagation field derived from proto-causal weights.

    Each window's value is the sum of incoming link weights, normalized by the
    maximum raw value across all windows.
    """

    def __init__(
        self, causal: ProtoCausality, windows: ExecutionWindows
    ) -> None:
        cycle_ids: List[str] = windows.cycle_ids

        # Accumulate raw incoming influence per window
        raw: Dict[str, float] = {cid: 0.0 for cid in cycle_ids}
        for a, b, w in causal.weighted_links():
            if b in raw:
                raw[b] += w

        # Normalize to [0, 1]
        max_raw = max(raw.values()) if raw else 0.0
        if max_raw > 0.0:
            self._values: Dict[str, float] = {
                cid: raw[cid] / max_raw for cid in cycle_ids
            }
        else:
            self._values = {cid: 0.0 for cid in cycle_ids}

    @classmethod
    def build(
        cls, causal: ProtoCausality, windows: ExecutionWindows
    ) -> "CausalField":
        """Construct a CausalField from a ProtoCausality and ExecutionWindows."""
        return cls(causal, windows)

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def value(self, cycle_id: str) -> float:
        """
        Return the normalized influence of cycle_id ∈ [0.0, 1.0].

        Returns 0.0 if cycle_id is not in the field.
        """
        return self._values.get(cycle_id, 0.0)

    def all(self) -> Dict[str, float]:
        """
        Return a copy of the full influence map: {cycle_id → value}.

        Mutating the returned dict does not affect internal state.
        """
        return dict(self._values)
