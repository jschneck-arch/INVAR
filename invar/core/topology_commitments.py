"""
invar.core.topology_commitments
================================
Non-canonical bounded proto-topological commitment surface — Stage 19.

TopologyCommitments surfaces pairs whose current emergence AND normalized trace
AND candidate membership all simultaneously meet stricter explicit thresholds.
The resulting set is a durable (but resettable) proposal surface only: no
canonical graph weight is written, no gate state is modified, no Pearl is
created, no support is injected.

Commitment rule (all three conditions must hold simultaneously):

    (i, j) ∈ K  ⟺  E_ij ≥ θ_E^commit  ∧  τ̂_ij ≥ θ_τ^commit  ∧  I_ij = 1

Where:
    E_ij   = emergence_weight(gate_i, gate_j, t)    ∈ [0, 1]  — current coherence
    τ̂_ij   = TopologyTrace.normalized(i, j)         ∈ [0, 1]  — historical trace
    I_ij   = TopologyCandidates.contains(i, j)      ∈ {0, 1}  — candidate membership
    θ_E^commit  = theta_e   — commitment emergence threshold  (stricter than candidate)
    θ_τ^commit  = theta_tau — commitment trace threshold      (stricter than candidate)

All three signals must exceed their respective thresholds simultaneously.
Candidate membership is a hard gate: a pair cannot commit without being a candidate.

Safety properties:
    - Entirely non-canonical: no write-back to canonical graph, Gate, or Pearl
    - Deterministic: same inputs always produce same committed set
    - Reversible: reset() / recompute() clear proposals without substrate effect
    - Symmetric: (i,j) ∈ K ⟺ (j,i) ∈ K  (pair key is canonical-ordered)
    - Dormant by default: theta_e=1.0, theta_tau=1.0 → at-maximum signals only
    - Bounded: committed set size ≤ number of pairs evaluated
    - Gate.step() NOT modified; phi_R, phi_B, energy(), p() NOT touched

Relationship to earlier stages:
    Stage 12: emergence_weight()              — current coherence signal
    Stage 15: TopologyTrace                   — bounded historical trace
    Stage 16: effective_weight() / normalized — transient weight modulation
    Stage 17: TopologyCandidates              — candidate identification
    Stage 18: kappa_candidate in effective_weight() — candidate causal influence
    Stage 19: TopologyCommitments             — proto-topological commitment
                                               (this module)
"""
from __future__ import annotations

from typing import Any, FrozenSet, List, Optional, Set, Tuple


def _pair_key(id_i: Any, id_j: Any) -> Tuple[str, str]:
    """Canonical symmetric pair key — same result for (i,j) and (j,i)."""
    a, b = str(id_i), str(id_j)
    return (a, b) if a <= b else (b, a)


class TopologyCommitments:
    """
    Bounded, reversible, non-canonical proto-topological commitment set.

    Surfaces gate-pair commitments whose current emergence AND normalized trace
    AND candidate membership all meet explicit (stricter-than-candidate) thresholds.
    Acts as a durable proposal surface only — entirely separate from canonical state.

    Parameters
    ----------
    theta_e : float
        Commitment threshold on current emergence E_ij ∈ [0, 1].
        Should be strictly greater than the corresponding TopologyCandidates threshold.
        Default 1.0 — dormant (only at-maximum signals qualify).
    theta_tau : float
        Commitment threshold on normalized trace τ̂_ij ∈ [0, 1].
        Should be strictly greater than the corresponding TopologyCandidates threshold.
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
        self._committed: Set[Tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Commitment evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        id_i: Any,
        id_j: Any,
        e_ij: float,
        tau_hat: float,
        i_ij: float,
    ) -> bool:
        """
        Evaluate pair (i, j) and update commitment membership.

        Adds pair to committed set iff:
            E_ij ≥ θ_E  AND  τ̂_ij ≥ θ_τ  AND  I_ij == 1

        Removes pair from committed set if it no longer qualifies.

        Parameters
        ----------
        id_i, id_j : gate identifiers (any hashable)
        e_ij       : current emergence ∈ [0, 1]; use emergence_weight()
        tau_hat    : normalized trace τ̂_ij ∈ [0, 1]; use TopologyTrace.normalized()
        i_ij       : candidate membership flag ∈ {0.0, 1.0}; use float(cands.contains(i, j))

        Returns True if pair is now committed, False otherwise.
        """
        key = _pair_key(id_i, id_j)
        qualifies = (
            (e_ij >= self.theta_e)
            and (tau_hat >= self.theta_tau)
            and (i_ij == 1.0)
        )
        if qualifies:
            self._committed.add(key)
        else:
            self._committed.discard(key)
        return qualifies

    # ------------------------------------------------------------------
    # Query surface
    # ------------------------------------------------------------------

    def contains(self, id_i: Any, id_j: Any) -> bool:
        """Return True if (i, j) is currently a committed edge. Symmetric."""
        return _pair_key(id_i, id_j) in self._committed

    def edges(self) -> List[Tuple[str, str]]:
        """Return list of committed pairs in canonical (sorted) order."""
        return sorted(self._committed)

    def count(self) -> int:
        """Return number of current committed pairs."""
        return len(self._committed)

    # ------------------------------------------------------------------
    # Reset / recompute
    # ------------------------------------------------------------------

    def reset(
        self,
        id_i: Optional[Any] = None,
        id_j: Optional[Any] = None,
    ) -> None:
        """
        Clear commitment set.

        reset()        — clear all commitments
        reset(i, j)    — remove one specific pair

        Clearing has zero effect on canonical gate or graph state.
        """
        if id_i is None:
            self._committed.clear()
        else:
            self._committed.discard(_pair_key(id_i, id_j))

    def recompute(
        self,
        pairs: List[Tuple[Any, Any, float, float, float]],
    ) -> None:
        """
        Rebuild commitment set from scratch.

        All existing commitments are cleared first.  Deterministic: result depends
        only on current signal values and thresholds.

        Parameters
        ----------
        pairs : list of (id_i, id_j, e_ij, tau_hat, i_ij)
        """
        self._committed.clear()
        for id_i, id_j, e_ij, tau_hat, i_ij in pairs:
            self.evaluate(id_i, id_j, e_ij, tau_hat, i_ij)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> FrozenSet[Tuple[str, str]]:
        """Return immutable snapshot of current commitment set."""
        return frozenset(self._committed)
