"""
skg.core.narrative
==================
Narrative state N_t = (M_t, I_t, R_t) and the observation weight W_t(g).

Narrative is the mechanism by which past history, current intent, and
observed outcomes bias the observation functional J(Ω) toward future-useful
slices of transition space.

    N_t = (M_t, I_t, R_t)

        M_t(g): memory weight   — importance of gate g in recent history
        I_t(g): intent weight   — operator-specified future-relevance of gate g
        R_t(g): outcome weight  — feedback: did observing g lead to useful action?

    W_{t+1}(g) = γM·M_t(g) + γI·I_t(g) + γR·R_t(g)   [narrative update rule]

W_t(g) enters the observation functional as the narrative utility term:

    N_t(Ω) = Σ_{g∈Ω} W_t(g) · H_t(g)

High W_t(g) means: observing this gate would be narratively valuable.
High H_t(g) means: the gate is uncertain. The product prioritizes
uncertain gates that are narratively relevant.

Narrative does not replace physics. It feeds the observation functional
through W_t(g). The physics (entropy gradient) still governs everything else.

Decay: memory decays exponentially. Intent and outcome are operator-set.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_DEFAULT_GAMMA_M = 0.5   # memory weight
_DEFAULT_GAMMA_I = 0.3   # intent weight
_DEFAULT_GAMMA_R = 0.2   # outcome weight
_MEMORY_DECAY = 0.95     # per-step memory decay factor


@dataclass
class NarrativeWeights:
    """W_t(g) for a single gate at one time step."""
    gate_id: str
    memory: float = 0.0    # M_t(g)
    intent: float = 0.0    # I_t(g)
    outcome: float = 0.0   # R_t(g)
    gamma_M: float = _DEFAULT_GAMMA_M
    gamma_I: float = _DEFAULT_GAMMA_I
    gamma_R: float = _DEFAULT_GAMMA_R

    @property
    def W(self) -> float:
        """W_t(g) = γM·M_t + γI·I_t + γR·R_t"""
        return self.gamma_M * self.memory + self.gamma_I * self.intent + self.gamma_R * self.outcome


class NarrativeState:
    """
    The narrative state N_t = (M_t, I_t, R_t) for all gates.

    Provides W_t(g) for each gate_id, which biases the observation
    functional toward historically, intentionally, and outcomically
    relevant transitions.
    """

    def __init__(
        self,
        gamma_M: float = _DEFAULT_GAMMA_M,
        gamma_I: float = _DEFAULT_GAMMA_I,
        gamma_R: float = _DEFAULT_GAMMA_R,
        memory_decay: float = _MEMORY_DECAY,
    ) -> None:
        self._gamma_M = gamma_M
        self._gamma_I = gamma_I
        self._gamma_R = gamma_R
        self._memory_decay = memory_decay
        self._weights: Dict[str, NarrativeWeights] = {}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def W(self, gate_id: str) -> float:
        """W_t(g) — total narrative weight for a gate. Default 0."""
        w = self._weights.get(gate_id)
        return w.W if w is not None else 0.0

    def narrative_utility(self, gate_id: str, H_g: float) -> float:
        """W_t(g) · H_t(g) — utility contribution of observing gate g."""
        return self.W(gate_id) * H_g

    def all_weights(self) -> Dict[str, float]:
        """All gate_id → W_t(g) pairs with nonzero weight."""
        return {gid: w.W for gid, w in self._weights.items() if w.W > 1e-12}

    # ------------------------------------------------------------------
    # Update: memory (from observation history)
    # ------------------------------------------------------------------

    def observe(self, gate_id: str, delta_H: float) -> None:
        """
        Record an observation event. Updates M_t(g).

        A confirming observation (ΔH < 0) reduces memory weight —
        the gate is getting resolved. A contradicting observation (ΔH > 0)
        raises memory weight — the gate is getting more interesting.

        |ΔH| is the magnitude of the entropy change.
        """
        w = self._get_or_create(gate_id)
        # Memory: recent observation with significant ΔH raises weight
        w.memory = min(1.0, w.memory + abs(delta_H) * 0.5)

    def step_memory_decay(self) -> None:
        """Apply per-step memory decay to all gates."""
        for w in self._weights.values():
            w.memory *= self._memory_decay

    # ------------------------------------------------------------------
    # Update: intent (operator-set)
    # ------------------------------------------------------------------

    def set_intent(self, gate_id: str, value: float) -> None:
        """
        Set I_t(g) — operator-specified future relevance.

        Value ∈ [0, 1]. Call this when the operator specifies a workload
        or gate as high-priority (e.g., "focus on this CVE").
        """
        w = self._get_or_create(gate_id)
        w.intent = max(0.0, min(1.0, value))

    def set_intent_workload(self, workload_id: str, value: float) -> None:
        """Set intent for all gates with matching workload_id prefix."""
        for gid, w in self._weights.items():
            if gid.startswith(workload_id):
                w.intent = max(0.0, min(1.0, value))

    def clear_intent(self) -> None:
        """Reset all intent weights to zero."""
        for w in self._weights.values():
            w.intent = 0.0

    # ------------------------------------------------------------------
    # Update: outcome (feedback from action)
    # ------------------------------------------------------------------

    def record_outcome(self, gate_id: str, value: float) -> None:
        """
        Record R_t(g) — outcome feedback after using an observation for action.

        Positive value: the observation of this gate led to useful action.
        Negative value: the observation was misleading or wasteful.
        Value ∈ [-1, 1] (clamped to [0, 1] for W computation).
        """
        w = self._get_or_create(gate_id)
        w.outcome = max(0.0, min(1.0, value))

    # ------------------------------------------------------------------
    # Narrative update rule (full step)
    # ------------------------------------------------------------------

    def step(
        self,
        memory_updates: Optional[Dict[str, float]] = None,
        intent_updates: Optional[Dict[str, float]] = None,
        outcome_updates: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Apply one narrative update step:
            W_{t+1}(g) = γM·M_t(g) + γI·I_t(g) + γR·R_t(g)

        with memory_decay applied to M_t before weighting.

        Updates are |ΔH| values for memory, operator values for intent/outcome.
        """
        self.step_memory_decay()

        if memory_updates:
            for gid, delta_h in memory_updates.items():
                self.observe(gid, delta_h)

        if intent_updates:
            for gid, val in intent_updates.items():
                self.set_intent(gid, val)

        if outcome_updates:
            for gid, val in outcome_updates.items():
                self.record_outcome(gid, val)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(self, gate_id: str) -> NarrativeWeights:
        if gate_id not in self._weights:
            self._weights[gate_id] = NarrativeWeights(
                gate_id=gate_id,
                gamma_M=self._gamma_M,
                gamma_I=self._gamma_I,
                gamma_R=self._gamma_R,
            )
        return self._weights[gate_id]
