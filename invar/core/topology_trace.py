"""
invar.core.topology_trace
=========================
Non-canonical bounded topology trace memory for gate pairs — Stages 15–16.

TopologyTrace accumulates relationship evidence over time without mutating
canonical graph state. It is a parallel structure maintained by callers,
not part of gate dynamics (Gate.step() is not modified by this module).

Trace update equation (forward Euler per pair per time step):
    τ_ij += dt * (η_τ · E_ij − λ_τ · τ_ij)
    τ_ij  = max(0.0, τ_ij)

Where:
    E_ij = emergence_weight(gate_i, gate_j, t)   — from invar.core.gate
    η_τ  = eta_tau   — accumulation rate (0.0 = dormant)
    λ_τ  = lambda_tau — decay rate (> 0 for stability)

Steady state:  τ* = η_τ · E_ij / λ_τ
Upper bound:   τ* ≤ η_τ / λ_τ   (since E_ij ≤ 1)
Symmetric:     τ_ij = τ_ji   (symmetric key scheme)
Reversible:    trace.reset() clears without affecting canonical state

Stage 16 — controlled trace influence:
    τ̂_ij = τ_ij / τ_max ∈ [0, 1]   where τ_max = η_τ / λ_τ
    w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij)

    normalized(i, j)  — returns τ̂_ij (0.0 if eta_tau=0)
    effective_weight() — module-level helper; dormant when all κ=0

Stage 18 — controlled candidate influence:
    I_ij ∈ {0, 1}  — candidate membership from TopologyCandidates
    w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij + κ_C · I_ij)

    effective_weight(..., i_ij=0.0, kappa_candidate=0.0)
    With kappa_candidate=0.0 (default): Stage 16 behavior preserved exactly.

Stage 20 — controlled commitment influence:
    K_ij ∈ {0, 1}  — commitment membership from TopologyCommitments
    w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij + κ_C · I_ij + κ_K · K_ij)

    effective_weight(..., k_ij=0.0, kappa_commitment=0.0)
    With kappa_commitment=0.0 (default): Stage 19 behavior preserved exactly.

    SAFETY CONSTRAINT: κ_K << κ_C << κ_τ  (commitment must never dominate weighting)
        trace = memory driver (largest weight signal)
        candidate = structural confirmation (moderate)
        commitment = reinforcement only (weakest non-zero signal)

Stage 21 — controlled stabilization regulation:
    R_ij_lock = K_ij · τ̂_ij ∈ [0, 1]  — over-stabilization risk signal
    w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock)

    regulation_signal(k_ij, tau_hat) -> float  — helper; returns K_ij · τ̂_ij ∈ [0, 1]
    effective_weight(..., r_ij_lock=0.0, kappa_regulate=0.0)
    With kappa_regulate=0.0 (default): Stage 20 behavior preserved exactly.

    SAFETY CONSTRAINT: κ_R < κ_K < κ_C < κ_τ  (regulation is the weakest signal)
        trace    = memory driver (largest)
        candidate = structural confirmation
        commitment = reinforcement
        regulation = counter-pressure only (smallest; never dominates)

Stage 24 — controlled boundary influence:
    B_ij ∈ {0, 1}  — same-region flag from CanonicalBoundary.same_region()
    w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B)

    effective_weight(..., b_ij=0.0, kappa_boundary=0.0)
    With kappa_boundary=0.0 (default): Stage 23 behavior preserved exactly.

    SAFETY CONSTRAINT: κ_B << κ_R < κ_K < κ_C < κ_τ  (boundary is the weakest signal)
        trace     = memory driver (largest)
        candidate = structural confirmation
        commitment = reinforcement
        regulation = counter-pressure
        boundary  = context only (absolute minimum; never dominates)

Stage 25 — final saturation control / global safety envelope:
    excess_ij = max(0, M_raw − 1)   where M_raw = 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B
    M_sat = M_raw                                      if excess_ij = 0  (M_raw ≤ 1)
    M_sat = 1 + excess_ij / (1 + σ · excess_ij)       if excess_ij > 0  (M_raw > 1)
    w_ij_eff = w_ij · max(0, M_sat)

    Where σ = sigma_saturate ≥ 0.

    effective_weight(..., sigma_saturate=0.0)
    With sigma_saturate=0.0 (default): Stage 24 behavior preserved exactly.

    Saturation compresses only the reinforcement above unity (excess_ij > 0).
    The attenuation region (M_raw ≤ 1) is passed through unchanged.

    Properties:
        - Monotone for all σ ≥ 0: larger M_raw → larger M_sat (ordering always preserved)
        - Identity when dormant (σ=0): M_sat = 1 + excess = M_raw → Stage 24 bit-identical
        - Identity below unity: M_raw ≤ 1 → M_sat = M_raw (no compression of attenuation)
        - Bounded above: M_sat < M_raw for M_raw > 1 and σ > 0
        - Asymptote: as σ → ∞, M_sat → 1 from above (topology influence never nullified)
        - Smooth: no discontinuity; continuous at M_raw = 1
        - Deterministic: no hidden state, no memory

    SIGNAL ORDERING: κ_B << κ_R < κ_K < κ_C < κ_τ
    Saturation compresses the aggregate excess; individual signal ordering is preserved.
    Topology influence is compressed but never nullified for M_raw > 1.

Usage:
    from invar.core.gate import emergence_weight
    from invar.core.topology_trace import TopologyTrace, effective_weight
    from invar.core.topology_candidates import TopologyCandidates
    from invar.core.topology_commitments import TopologyCommitments

    trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
    cands = TopologyCandidates(theta_e=0.4, theta_tau=0.4)
    comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)

    # Per time step, for each relevant pair:
    e_ij = emergence_weight(gate_i, gate_j, t)
    trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)

    # Read accumulated trace:
    tau = trace.get(gate_i.gate_id, gate_j.gate_id)

    # Stage 16–25: compute effective interaction weight (transient, not stored):
    tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
    cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)
    i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
    comms.evaluate(gate_i.gate_id, gate_j.gate_id,
                   e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)
    k_ij = float(comms.contains(gate_i.gate_id, gate_j.gate_id))
    r_lock = regulation_signal(k_ij, tau_hat)
    w_eff = effective_weight(w_ij, e_ij, tau_hat,
                             kappa_e=0.1, kappa_tau=0.05,
                             i_ij=i_ij, kappa_candidate=0.02,
                             k_ij=k_ij, kappa_commitment=0.005,
                             r_ij_lock=r_lock, kappa_regulate=0.001,
                             sigma_saturate=0.5)

Non-canonical guarantee:
    Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified.
    Canonical graph weights are never read or modified.
    Discarding a TopologyTrace object has zero effect on substrate state.
    No Pearl is created or modified.
    effective_weight() is computed transiently — never written back.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _pair_key(id_i: Any, id_j: Any) -> Tuple:
    """Symmetric pair key: same result for (i,j) and (j,i)."""
    a, b = str(id_i), str(id_j)
    return (a, b) if a <= b else (b, a)


class TopologyTrace:
    """
    Bounded, reversible, non-canonical topology trace for gate pairs.

    Accumulates τ_ij — a decaying relationship memory driven by pairwise
    emergence signal E_ij. Entirely separate from canonical graph and gate state.

    Parameters
    ----------
    eta_tau : float
        Trace accumulation rate ≥ 0.  With eta_tau=0.0 (default), the trace
        never accumulates — dormant, Stage 14 behavior fully preserved.
    lambda_tau : float
        Trace decay rate > 0.  τ_ij decays to 0 without continued E_ij input.
        Provides stability guarantee: τ* = eta_tau · E_ij / lambda_tau < ∞.
    """

    def __init__(
        self,
        eta_tau: float = 0.0,
        lambda_tau: float = 0.1,
    ) -> None:
        if lambda_tau <= 0:
            raise ValueError("lambda_tau must be > 0 for trace stability")
        self.eta_tau = float(eta_tau)
        self.lambda_tau = float(lambda_tau)
        self._traces: Dict[Tuple, float] = {}

    def get(self, id_i: Any, id_j: Any) -> float:
        """
        Return current τ_ij for pair (i, j).

        Returns 0.0 if no step() has been called for this pair.
        Symmetric: get(i, j) == get(j, i).
        """
        return self._traces.get(_pair_key(id_i, id_j), 0.0)

    def step(
        self,
        id_i: Any,
        id_j: Any,
        e_ij: float,
        dt: float,
    ) -> None:
        """
        Advance topology trace for pair (i, j) by one forward-Euler step.

        τ_ij += dt * (η_τ · e_ij − λ_τ · τ_ij)
        τ_ij  = max(0.0, τ_ij)

        Parameters
        ----------
        id_i, id_j : gate identifiers (any hashable; gate_id strings work)
        e_ij       : pairwise emergence signal ∈ [0, 1]; use emergence_weight()
        dt         : time step > 0
        """
        key = _pair_key(id_i, id_j)
        tau = self._traces.get(key, 0.0)
        tau += dt * (self.eta_tau * e_ij - self.lambda_tau * tau)
        self._traces[key] = max(0.0, tau)

    def reset(
        self,
        id_i: Optional[Any] = None,
        id_j: Optional[Any] = None,
    ) -> None:
        """
        Clear topology trace.

        reset()           — clear all pair traces
        reset(i, j)       — clear trace for one pair

        Clearing has zero effect on canonical gate or graph state.
        """
        if id_i is None:
            self._traces.clear()
        else:
            self._traces.pop(_pair_key(id_i, id_j), None)

    def pairs(self) -> list:
        """Return list of (id_i, id_j) tuples for all stored pairs (canonical order)."""
        return list(self._traces.keys())

    @property
    def steady_state_bound(self) -> float:
        """
        Upper bound on τ* for any pair: η_τ / λ_τ.

        Since E_ij ≤ 1, no pair trace can exceed this value at steady state.
        """
        return self.eta_tau / self.lambda_tau

    def normalized(self, id_i: Any, id_j: Any) -> float:
        """
        Return τ̂_ij = τ_ij / τ_max ∈ [0, 1].

        τ_max = η_τ / λ_τ (steady_state_bound).
        Returns 0.0 if eta_tau = 0 (dormant trace — no meaningful normalization).
        Symmetric: normalized(i, j) == normalized(j, i).
        """
        if self.eta_tau == 0.0:
            return 0.0
        tau_max = self.steady_state_bound
        return min(1.0, self.get(id_i, id_j) / tau_max)


def regulation_signal(k_ij: float, tau_hat: float) -> float:
    """
    Stage 21: compute over-stabilization risk signal R_ij_lock ∈ [0, 1].

    R_ij_lock = K_ij · τ̂_ij

    Non-zero only when the pair is simultaneously committed (K_ij = 1) and has high
    normalized trace memory (τ̂_ij near 1).  Reflects how deeply locked a relationship
    has become.  Used as the subtracted regulation term in effective_weight().

    Parameters
    ----------
    k_ij    : commitment flag K_ij ∈ {0.0, 1.0}; from float(TopologyCommitments.contains())
    tau_hat : normalized trace τ̂_ij ∈ [0, 1]; from TopologyTrace.normalized()

    Returns R_lock ∈ [0, 1].  Deterministic, no hidden state.
    """
    return k_ij * tau_hat


def effective_weight(
    w_ij: float,
    e_ij: float,
    tau_hat: float,
    kappa_e: float = 0.0,
    kappa_tau: float = 0.0,
    i_ij: float = 0.0,
    kappa_candidate: float = 0.0,
    k_ij: float = 0.0,
    kappa_commitment: float = 0.0,
    r_ij_lock: float = 0.0,
    kappa_regulate: float = 0.0,
    b_ij: float = 0.0,
    kappa_boundary: float = 0.0,
    sigma_saturate: float = 0.0,
) -> float:
    """
    Stages 16 + 18 + 20 + 21 + 24 + 25: effective interaction weight — transient, never stored.

    Stage 25 (final saturation control):

        excess = max(0, M_raw − 1)
        M_sat  = M_raw                           if excess = 0  (M_raw ≤ 1, pass-through)
        M_sat  = 1 + excess / (1 + σ·excess)    if excess > 0  (M_raw > 1, compressed)
        w_ij_eff = w_ij · max(0, M_sat)

    When σ=0 (default): M_sat = M_raw — bit-identical to Stage 24.
    When M_raw ≤ 1: no compression (attenuation passes through unchanged).
    When M_raw > 1: M_sat ∈ (1, M_raw) — compressed but always above unity.
    Monotone for all σ ≥ 0: larger M_raw → larger M_sat (signal ordering preserved).

    Parameters
    ----------
    w_ij            : canonical edge weight (read-only)
    e_ij            : pairwise emergence signal ∈ [0, 1]; from emergence_weight()
    tau_hat         : normalized topology trace τ̂_ij ∈ [0, 1]; from TopologyTrace.normalized()
    kappa_e         : emergence modulation coefficient (default 0.0 — dormant)
    kappa_tau       : trace modulation coefficient (default 0.0 — dormant)
    i_ij            : candidate membership flag I_ij ∈ {0.0, 1.0}; from TopologyCandidates.contains()
                      (default 0.0 — dormant, Stage 16 behavior preserved exactly)
    kappa_candidate : candidate influence coefficient κ_C (default 0.0 — dormant)
    k_ij            : commitment membership flag K_ij ∈ {0.0, 1.0}; from TopologyCommitments.contains()
                      (default 0.0 — dormant, Stage 19 behavior preserved exactly)
    kappa_commitment: commitment influence coefficient κ_K (default 0.0 — dormant)
                      MUST satisfy κ_K << κ_C << κ_τ — commitment reinforces only, never dominates
    r_ij_lock       : over-stabilization risk signal R_lock ∈ [0, 1]; use regulation_signal()
                      (default 0.0 — dormant, Stage 20 behavior preserved exactly)
    kappa_regulate  : regulation coefficient κ_R (default 0.0 — dormant)
                      MUST satisfy κ_R < κ_K — regulation tempers only, never overwhelms
    b_ij            : same-region boundary flag B_ij ∈ {0.0, 1.0}; use float(boundary.same_region(i,j))
                      (default 0.0 — dormant, Stage 23 behavior preserved exactly)
    kappa_boundary  : boundary influence coefficient κ_B (default 0.0 — dormant)
                      MUST satisfy κ_B << κ_R — boundary is context only, absolute minimum signal
    sigma_saturate  : saturation coefficient σ ≥ 0 (default 0.0 — dormant, Stage 24 preserved)
                      Compresses aggregate reinforcement above M_raw=1; does not affect attenuation.
                      Does not modify φ_R, φ_B, energy(), p(), or any canonical state.

    SAFETY COEFFICIENT ORDERING (caller responsibility):
        κ_B << κ_R < κ_K < κ_C < κ_τ
        boundary < regulation < commitment < candidate < trace
    Saturation compresses aggregate; individual signal ordering is preserved.

    With all κ = 0.0 and σ = 0.0 (defaults), returns w_ij exactly (bit-identical to prior stages).
    Result is always ≥ 0 for non-negative w_ij (multiplier clamped to ≥ 0).
    Canonical graph weights are never modified; output is transient.
    """
    m_raw = (
        1.0
        + kappa_e * e_ij
        + kappa_tau * tau_hat
        + kappa_candidate * i_ij
        + kappa_commitment * k_ij
        - kappa_regulate * r_ij_lock
        + kappa_boundary * b_ij
    )
    if sigma_saturate == 0.0:
        multiplier = m_raw
    else:
        excess = m_raw - 1.0
        if excess <= 0.0:
            multiplier = m_raw
        else:
            multiplier = 1.0 + excess / (1.0 + sigma_saturate * excess)
    return w_ij * max(0.0, multiplier)
