"""
invar.core.topology_candidates
==============================
Non-canonical bounded topology candidate consolidation — Stage 17.

TopologyCandidates surfaces pairs whose current emergence AND accumulated
normalized trace both exceed explicit thresholds.  The resulting set is a
proposal surface only: no canonical graph weight is written, no gate state
is modified, no Pearl is created, no support is injected.

Membership rule (both conditions must hold simultaneously):

    (i, j) ∈ C  ⟺  E_ij ≥ θ_E  ∧  τ̂_ij ≥ θ_τ

Where:
    E_ij   = emergence_weight(gate_i, gate_j, t)    ∈ [0, 1]
    τ̂_ij   = TopologyTrace.normalized(i, j)         ∈ [0, 1]
    θ_E    = theta_e    threshold on current emergence
    θ_τ    = theta_tau  threshold on normalized trace history

Safety properties:
    - Entirely non-canonical: no write-back to canonical graph, Gate, or Pearl
    - Deterministic: same inputs always produce same candidate set
    - Reversible: reset() / recompute() clear proposals without substrate effect
    - Symmetric: (i,j) ∈ C ⟺ (j,i) ∈ C  (pair key is canonical-ordered)
    - Dormant by default: with θ_E=1.0 or θ_τ=1.0, no pairs qualify unless at maximum
    - Bounded: candidate set size ≤ number of pairs evaluated
    - Gate.step() is NOT modified; phi_R, phi_B, energy(), p() are NOT touched

Non-canonical guarantee:
    Discarding or resetting a TopologyCandidates object has zero effect on
    canonical substrate state.  The candidate set encodes only which pairs
    have been observed to be both currently coherent and historically sustained.

Relationship to earlier stages:
    Stage 12: emergence_weight()              — current coherence signal
    Stage 15: TopologyTrace                   — bounded historical trace
    Stage 16: effective_weight() / normalized — transient weight modulation
    Stage 17: TopologyCandidates              — explicit candidate identification
                                               (this module)
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


def _pair_key(id_i: Any, id_j: Any) -> Tuple[str, str]:
    """Canonical symmetric pair key — same result for (i,j) and (j,i)."""
    a, b = str(id_i), str(id_j)
    return (a, b) if a <= b else (b, a)


class TopologyCandidates:
    """
    Bounded, reversible, non-canonical topology candidate set.

    Surfaces gate-pair candidates whose current emergence AND normalized trace
    history both meet explicit thresholds.  Acts as a proposal surface only.

    Parameters
    ----------
    theta_e : float
        Threshold on current emergence E_ij ∈ [0, 1].
        Pair qualifies only when E_ij ≥ theta_e.
        Default 1.0 — dormant (no pair can exceed 1.0, so no candidates).
    theta_tau : float
        Threshold on normalized trace τ̂_ij ∈ [0, 1].
        Pair qualifies only when τ̂_ij ≥ theta_tau.
        Default 1.0 — dormant.
    """

    def __init__(
        self,
        theta_e: float = 1.0,
        theta_tau: float = 1.0,
    ) -> None:
        if not (0.0 <= theta_e <= 1.0):
            raise ValueError(f"theta_e must be in [0, 1], got {theta_e}")
        if not (0.0 <= theta_tau <= 1.0):
            raise ValueError(f"theta_tau must be in [0, 1], got {theta_tau}")
        self.theta_e = float(theta_e)
        self.theta_tau = float(theta_tau)
        self._candidates: Set[Tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Candidate evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        id_i: Any,
        id_j: Any,
        e_ij: float,
        tau_hat: float,
    ) -> bool:
        """
        Evaluate pair (i, j) and update candidate membership.

        Adds pair to candidate set iff E_ij ≥ θ_E AND τ̂_ij ≥ θ_τ.
        Removes pair from candidate set if it no longer qualifies.

        Parameters
        ----------
        id_i, id_j : gate identifiers (any hashable)
        e_ij       : current emergence ∈ [0, 1]; use emergence_weight()
        tau_hat    : normalized trace τ̂_ij ∈ [0, 1]; use TopologyTrace.normalized()

        Returns True if pair is now a candidate, False otherwise.
        """
        key = _pair_key(id_i, id_j)
        qualifies = (e_ij >= self.theta_e) and (tau_hat >= self.theta_tau)
        if qualifies:
            self._candidates.add(key)
        else:
            self._candidates.discard(key)
        return qualifies

    # ------------------------------------------------------------------
    # Query surface
    # ------------------------------------------------------------------

    def contains(self, id_i: Any, id_j: Any) -> bool:
        """Return True if (i, j) is currently a candidate edge. Symmetric."""
        return _pair_key(id_i, id_j) in self._candidates

    def edges(self) -> List[Tuple[str, str]]:
        """Return list of candidate pairs in canonical (sorted) order."""
        return sorted(self._candidates)

    def count(self) -> int:
        """Return number of current candidate pairs."""
        return len(self._candidates)

    # ------------------------------------------------------------------
    # Reset / recompute
    # ------------------------------------------------------------------

    def reset(
        self,
        id_i: Optional[Any] = None,
        id_j: Optional[Any] = None,
    ) -> None:
        """
        Clear candidate set.

        reset()        — clear all candidates
        reset(i, j)    — remove one specific pair

        Clearing has zero effect on canonical gate or graph state.
        """
        if id_i is None:
            self._candidates.clear()
        else:
            self._candidates.discard(_pair_key(id_i, id_j))

    def recompute(
        self,
        pairs: List[Tuple[Any, Any, float, float]],
    ) -> None:
        """
        Rebuild candidate set from scratch using provided (id_i, id_j, e_ij, tau_hat) tuples.

        All existing candidates are cleared first.  Deterministic: result depends
        only on current signal values and thresholds.

        Parameters
        ----------
        pairs : list of (id_i, id_j, e_ij, tau_hat)
        """
        self._candidates.clear()
        for id_i, id_j, e_ij, tau_hat in pairs:
            self.evaluate(id_i, id_j, e_ij, tau_hat)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> FrozenSet[Tuple[str, str]]:
        """Return immutable snapshot of current candidate set."""
        return frozenset(self._candidates)
