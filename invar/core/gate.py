"""
skg.core.gate
=============
Gate physics — the atomic unit of field energy.

A gate is a binary question about a specific (workload, node) pair:
is this condition realized (R) or blocked (B)? Until sufficient support
accumulates to collapse the superposition, the gate is in state U —
the absence of collapse, not a third basis state.

The energy of a gate in state U is its binary Shannon entropy over the
support vector (φ_R, φ_B), as derived in Work 5 Definition 1:

    p(g)  = φ_R / (φ_R + φ_B + ε)
    H(g)  = -p·log₂(p) - (1-p)·log₂(1-p)

Maximum energy (H=1 bit) when φ_R = φ_B = 0 (no observations).
Zero energy when either φ_R or φ_B reaches the collapse threshold.

Collapsed gates (R or B) carry zero energy.

All decay is applied at read time. The stored support contributions are
immutable (φ₀ values preserved). H(g) is a function of time.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .envelope import DecayClass, SupportContribution, coherence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPSILON = 1e-10           # prevents log(0) and division by zero
COLLAPSE_THRESHOLD = 0.7   # φ_R or φ_B must reach this to collapse a gate


# ---------------------------------------------------------------------------
# Gate state
# ---------------------------------------------------------------------------

class GateState(str, Enum):
    U = "U"   # superposition — neither confirmed nor blocked
    R = "R"   # realized — condition confirmed
    B = "B"   # blocked   — condition blocked/negated


# ---------------------------------------------------------------------------
# Gate energy (core physics)
# ---------------------------------------------------------------------------

def binary_entropy(p: float) -> float:
    """
    H_binary(p) = -p·log₂(p) - (1-p)·log₂(1-p)

    Returns bits in [0, 1].
    p is clamped to (_EPSILON, 1-_EPSILON) to avoid log(0).
    """
    p = max(_EPSILON, min(1.0 - _EPSILON, p))
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def gate_p(phi_R: float, phi_B: float) -> float:
    """
    Realization probability from support vector.

        p = φ_R / (φ_R + φ_B)   when φ_R + φ_B > 0
        p = 0.5                   when φ_R = φ_B = 0  (maximum superposition)

    The zero-observation prior is 0.5: no evidence → maximum uncertainty.
    At collapse: p → 1.0 (R) or p → 0.0 (B).

    Note: the formula φ_R/(φ_R+φ_B+ε) in Work 5 Definition 1 has a typo —
    it gives p=0 at zero observations, not p=0.5. The correct formulation
    uses the explicit prior.
    """
    total = phi_R + phi_B
    if total < _EPSILON:
        return 0.5  # no observations → maximum superposition prior
    return phi_R / total


def gate_energy(phi_R: float, phi_B: float, state: GateState = GateState.U) -> float:
    """
    H(g): energy of a gate from its support vector.

    Collapsed gates (R or B) carry zero energy.
    Unresolved gates carry H_binary(p(g)).

    This is Definition 1 of Work 5.
    """
    if state != GateState.U:
        return 0.0
    p = gate_p(phi_R, phi_B)
    return binary_entropy(p)


def gate_phase(phi_R: float, phi_B: float) -> float:
    """
    θ(g) = (1 - p(g)) · π

    Phase encoding for Kuramoto coupling and fiber tensor computation.
    At superposition (p=0.5): θ = π/2.
    At R-collapse (p→1): θ → 0.
    At B-collapse (p→0): θ → π.
    """
    p = gate_p(phi_R, phi_B)
    return (1.0 - p) * math.pi


# ---------------------------------------------------------------------------
# Contradiction signal (Stage 9)
# ---------------------------------------------------------------------------

def contradiction_signal(
    gate: "Gate",
    neighbors: "List[Gate]",
    t: Optional[float] = None,
) -> float:
    """
    C_i = (1/|N|) · Σ_{j∈N} |sin(θᵢ⁽⁰⁾ − θⱼ⁽⁰⁾)|

    Bounded phase-mismatch signal ∈ [0, 1].

    Returns 0.0 when neighbors is empty (isolated gate has no contradiction).
    θ⁽⁰⁾ = gate_phase(phi_R, phi_B) — support-derived anchor only.
    Deterministic: pure function of support state at time t.
    """
    if not neighbors:
        return 0.0
    theta_i = gate.phase(t)
    total = sum(abs(math.sin(theta_i - nb.phase(t))) for nb in neighbors)
    return total / len(neighbors)


def resonance_signal(
    gate: "Gate",
    neighbors: "List[Gate]",
    t: Optional[float] = None,
) -> float:
    """
    R_i = (1/|N|) · Σ_{j∈N} cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)

    Bounded phase-alignment signal ∈ [-1, 1].

    Returns 0.0 when neighbors is empty (isolated gate has no resonance).
    θ⁽⁰⁾ = gate_phase(phi_R, phi_B) — support-derived anchor only, NOT evolved theta.
    Using the anchor (not dynamic theta) prevents feedback: rho*R_i drives theta,
    which would otherwise feed back into R_i in subsequent steps, risking runaway.
    Deterministic: pure function of support state at time t.

    Interpretation:
      R_i =  1.0 → perfect alignment (all neighbors share same anchor phase)
      R_i =  0.0 → orthogonal phases (π/2 apart on average)
      R_i = -1.0 → anti-aligned (all neighbors π away)
    """
    if not neighbors:
        return 0.0
    theta_i = gate.phase(t)
    total = sum(math.cos(nb.phase(t) - theta_i) for nb in neighbors)
    return total / len(neighbors)


# ---------------------------------------------------------------------------
# Emergence weight (Stage 12)
# ---------------------------------------------------------------------------

def emergence_weight(
    gate_i: "Gate",
    gate_j: "Gate",
    t: Optional[float] = None,
) -> float:
    """
    E_ij = min(1, ā_ij · max(0, R_ij))

    Bounded amplitude-alignment enhancement factor ∈ [0, 1].

    ā_ij = (aᵢ + aⱼ) / 2         — mean amplitude of the pair
    R_ij = cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)   — pairwise cosine alignment ∈ [-1, 1]
    E_ij = min(1, ā_ij · max(0, R_ij))

    Properties:
      - E_ij ∈ [0, 1]: min provides ceiling; max(0,…) clips anti-alignment to zero
      - E_ij = 0 when R_ij ≤ 0 (anti-aligned or orthogonal — no enhancement)
      - E_ij = 0 when either gate has a=0 (quiescent pair — no enhancement)
      - E_ij → 1 when both gates are maximally aligned and amplified
      - Symmetric: E_ij = E_ji (ā and cos are both symmetric)
      - Deterministic: pure function of support state and amplitude at time t
      - Reversible: not written back to canonical state; read-only query

    Callers apply the effective weight:
        w_ij_eff = w_ij * (1 + gate.kappa_emergence * emergence_weight(gate_i, gate_j, t))

    With kappa_emergence=0.0 (default): w_ij_eff = w_ij (canonical weight unchanged).
    """
    a_mean = (gate_i.a + gate_j.a) / 2.0
    r_ij = math.cos(gate_j.phase(t) - gate_i.phase(t))
    return min(1.0, a_mean * max(0.0, r_ij))


# ---------------------------------------------------------------------------
# Local emergence summary (Stage 13)
# ---------------------------------------------------------------------------

def local_emergence_summary(
    gate: "Gate",
    neighbors: "List[Gate]",
    t: Optional[float] = None,
) -> float:
    """
    Ē_i = (1/|N|) · Σ_{j∈N} emergence_weight(gate, j, t)

    Bounded neighborhood mean of pairwise emergence factors ∈ [0, 1].

    Returns 0.0 when neighbors is empty (isolated gate has no emergence context).
    Deterministic: pure function of support state and amplitudes at time t.
    Local: depends only on this gate's direct neighbors.

    Used by callers to pre-compute e_bar before passing it to step():
        e_bar = local_emergence_summary(gate, neighbors, t)
        gate.step(dt, r_i=r_i, e_bar=e_bar, ...)
    """
    if not neighbors:
        return 0.0
    total = sum(emergence_weight(gate, nb, t) for nb in neighbors)
    return total / len(neighbors)


# ---------------------------------------------------------------------------
# Gate — stateful object tracking support contributions
# ---------------------------------------------------------------------------

@dataclass
class Gate:
    """
    A single gate: binary question with accumulated support.

    gate_id and workload_id are opaque strings. The substrate does not
    interpret them — they are custody identifiers only.

    Support contributions are immutable once appended. Decay is applied
    at read time via SupportContribution.current_phi_R/B().
    """
    gate_id:     str
    workload_id: str
    node_key:    str

    _contributions: List[SupportContribution] = field(
        default_factory=list, repr=False
    )
    _state: GateState = GateState.U

    # Collapse is substrate-mediated — the gate does not assign its own state.
    _collapse_ts: Optional[float] = None

    # Layer 0 base-state restoration fields (ET-G1B Option C).
    # Set only by _restore_from_pearl_snapshot(). Zero by default (no base).
    # When _base_ts is set, accumulated() adds the decayed base support on top of
    # any live contributions. Single state model — base and contributions are additive.
    _base_phi_R: float = field(default=0.0, repr=False)
    _base_phi_B: float = field(default=0.0, repr=False)
    _base_ts: Optional[float] = field(default=None, repr=False)

    # Layer 0 Oscillation Addendum — dynamical extension fields.
    # Stage 1: dormant storage only. No existing output is affected.
    # Stage 2: step() evolves theta via (omega + coupling + memory) dynamics.
    # Stage 3: weighted_phase() multiplies by a (a=1.0 → identical output).
    # Stage 4: functional extension (E_osc, P_res) uses these values.
    # Stage 5: theta feeds into weighted_phase() live path.
    #          theta is the MEMORY PHASE OFFSET (θᵐᵉᵐ), not the full phase.
    #          Full dynamic phase: θ⁽⁰⁾(t) + theta  (anchor + offset).
    #          Default theta=0.0 → offset is zero → output identical to pre-Stage-5.
    # Stage 6: mu now evolves via bounded exponential decay + optional explicit input.
    #          dμ/dt = c_in − lambda_mu·μ   (passed to step() as c_in, default 0.0)
    #          Default mu=0, c_in=0 → identical to Stage 5 behavior (no change).
    # Stage 7: amplitude `a` evolves when alpha > 0 (dormant when alpha=0.0).
    #          da/dt = alpha·H(g) − xi·a   (H(g) drives amplitude; xi damps it)
    #          Steady state: a* = alpha·H(g)/xi  (finite and bounded for xi > 0)
    #          Default alpha=0.0 → step() never touches a → a=1.0 unchanged.
    # Stage 8: β·μ term added to amplitude equation (dormant when beta=0.0).
    #          da/dt = alpha·H(g) + beta·μ − xi·a
    #          Steady state: a* = (alpha·H + beta·μ*) / xi
    #          Forward Euler: mu snapshot taken before any updates (mu_n).
    #          Default beta=0.0 → Stage 7 behavior unchanged.
    # Stage 9: cross-gate contradiction coupling (dormant when gamma=0.0).
    #          dμ/dt = c_in + gamma·C_i − lambda_mu·μ
    #          C_i is a bounded phase-mismatch signal [0,1] passed to step() as c_i.
    #          Computed externally via contradiction_signal(gate, neighbors, t).
    #          Default gamma=0.0 → Stage 8 behavior unchanged.
    # Stage 10: bounded resonance coupling (dormant when rho=0.0).
    #           dθᵐᵉᵐ/dt = ω + coupling_term + μ + ρ·R_i
    #           R_i is a bounded alignment signal [-1,1] passed to step() as r_i.
    #           Computed externally via resonance_signal(gate, neighbors, t).
    #           Uses support-anchor θ⁽⁰⁾ (not evolved theta) — avoids feedback runaway.
    #           Default rho=0.0 → Stage 9 behavior unchanged.
    # Stage 11: bounded persistence reward (dormant when epsilon_persist=0.0).
    #           ξ_eff = ξ / max(1e-6, 1 + ε_p · P_i)  where P_i = min(1, a·H(g))
    #           P_i ∈ [0,1] — local score; high amplitude × high entropy → slower decay.
    #           Computed internally in step() — no external signal needed.
    #           Only active when alpha != 0.0 (amplitude block is live).
    #           Default epsilon_persist=0.0 → ξ_eff = ξ → Stage 10 behavior unchanged.
    # Stage 12: controlled topology emergence (dormant when kappa_emergence=0.0).
    #           w_ij_eff = w_ij · (1 + κ · E_ij)
    #           E_ij = min(1, ā_ij · max(0, R_ij))  ā_ij = (a_i + a_j)/2  R_ij = cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)
    #           E_ij ∈ [0,1] — bounded; reversible (not written back); non-canonical.
    #           Computed externally via emergence_weight(gate_i, gate_j, t).
    #           Callers apply: w_eff = w * (1 + gate.kappa_emergence * emergence_weight(...)).
    #           Default kappa_emergence=0.0 → w_ij_eff = w_ij → Stage 11 behavior unchanged.
    # Stage 13: controlled feedback coupling (dormant when delta_feedback=0.0).
    #           ρ_eff = ρ · (1 + δ · Ē_i)  where Ē_i = local_emergence_summary(gate, neighbors, t)
    #           Ē_i ∈ [0,1] — neighborhood mean of pairwise E_ij; passed to step() as e_bar.
    #           ρ_eff is transient — computed in step(), not stored, not written back.
    #           High-emergence neighborhoods strengthen resonance channel; others unchanged.
    #           Default delta_feedback=0.0 → ρ_eff = ρ → Stage 12 behavior unchanged.
    # Stage 14: controlled stabilization / attractor bias (dormant when zeta_stabilize=0.0).
    #           ω_eff = ω / max(1e-9, 1 + ζ · Ē_i)  reuses e_bar from Stage 13.
    #           ω_eff is transient — computed in step(), not stored, not written back.
    #           High-emergence neighborhoods drift more slowly; coupling terms unchanged.
    #           Sign preserved: sign(ω_eff) = sign(ω) always. No hard locking possible.
    #           Default zeta_stabilize=0.0 → ω_eff = ω → Stage 13 behavior unchanged.
    theta: float = field(default=0.0, repr=False)           # memory phase offset θᵐᵉᵐ; 0.0 = no offset
    a: float = field(default=1.0, repr=False)               # oscillation amplitude; 1.0 = no change
    omega: float = field(default=0.0, repr=False)           # intrinsic angular frequency
    xi: float = field(default=0.01, repr=False)             # amplitude damping coefficient ≥ 0
    mu: float = field(default=0.0, repr=False)              # contradiction-memory term
    lambda_mu: float = field(default=0.1, repr=False)       # contradiction-memory decay rate ≥ 0
    alpha: float = field(default=0.0, repr=False)           # amplitude drive coefficient; 0.0 = dormant
    beta: float = field(default=0.0, repr=False)            # μ→a coupling coefficient; 0.0 = dormant
    gamma: float = field(default=0.0, repr=False)           # cross-gate contradiction sensitivity; 0.0 = dormant
    rho: float = field(default=0.0, repr=False)             # resonance coupling coefficient; 0.0 = dormant
    epsilon_persist: float = field(default=0.0, repr=False) # persistence reward coefficient; 0.0 = dormant
    kappa_emergence: float = field(default=0.0, repr=False) # topology emergence sensitivity; 0.0 = dormant
    delta_feedback: float = field(default=0.0, repr=False)  # feedback coupling coefficient; 0.0 = dormant
    zeta_stabilize: float = field(default=0.0, repr=False)  # stabilization coefficient; 0.0 = dormant

    def add_contribution(self, c: SupportContribution) -> None:
        """Append an immutable support contribution."""
        self._contributions.append(c)
        self._maybe_collapse()

    def accumulated(self, t: Optional[float] = None) -> Tuple[float, float]:
        """
        Return current (φ_R, φ_B) with decay applied to all contributions.

        Single state model: phi_total = phi_base(t) + Σ contribution_phi(t)

        phi_base decays from Pearl.ts using STRUCTURAL decay — the canonical
        base support from archive restoration. Future live contributions add on
        top and decay according to their own decay_class. Both evolve over time;
        there is no frozen override and no dual-mode switching.
        """
        if t is None:
            t = time.time()
        phi_R = sum(c.current_phi_R(t) for c in self._contributions)
        phi_B = sum(c.current_phi_B(t) for c in self._contributions)
        if self._base_ts is not None:
            phi_R += coherence(self._base_phi_R, DecayClass.STRUCTURAL, self._base_ts, t)
            phi_B += coherence(self._base_phi_B, DecayClass.STRUCTURAL, self._base_ts, t)
        return phi_R, phi_B

    def state(self, t: Optional[float] = None) -> GateState:
        """
        Current gate state, accounting for decoherence.

        A gate that was collapsed may drift back to U if its support
        decoheres below the threshold. The stored _state is not authoritative
        — the live accumulated() support is. Applies equally to live gates and
        restored gates (no special-casing — single state model).
        """
        if self._state != GateState.U:
            phi_R, phi_B = self.accumulated(t)
            if phi_R >= COLLAPSE_THRESHOLD:
                return GateState.R
            if phi_B >= COLLAPSE_THRESHOLD:
                return GateState.B
            # Support decohered below threshold — superposition reasserts
            return GateState.U
        return GateState.U

    def _restore_from_pearl_snapshot(
        self,
        phi_R: float,
        phi_B: float,
        state: GateState,
        ts: float,
    ) -> None:
        """
        Layer 0 Gate restoration surface. Authorized for invar/persistence/ only.

        Establishes a canonical base state from archived Pearl fields. This is NOT a
        frozen override — it sets the base layer of a single-state model:

            phi_total(t) = phi_base(t) + Σ contribution_phi(t)

        phi_base decays from ts using DecayClass.STRUCTURAL. Future live contributions
        (via add_contribution() / ingest()) add on top and are NOT ignored — there is
        no dual-state switching, no silent mutation, no snapshot override.

        Preconditions:
          - Gate must have no existing contributions (_contributions == []).
            Restoration targets only fresh, empty Gates.
          - phi_R and phi_B are non-negative (Pearl-native values are always valid).
          - state reflects gate state at Pearl.ts (used to initialise collapse tracking).

        Postconditions:
          - accumulated(t) = phi_base(t) + Σ c(t) — decays, evolves, additive. Not frozen.
          - state(t) computed from accumulated(t) via threshold — same as live gates.
          - _contributions remains empty — no SupportContribution created.
          - No Pearl is emitted. No listener notified. _seq not advanced.

        Known approximation: the base decays at STRUCTURAL rate regardless of original
        observation decay class (Pearl does not carry per-contribution decay_class).
        This is exact for STRUCTURAL observations; conservative for others.
        Documented in INVAR_CORE_CONTRACT.md §5.9 and INVAR_EXECUTION_TEMPORAL_CONTRACT.md §ET-G1B.

        Do not call from domain code, kernel code, sensor code, or any module outside
        invar/persistence/. See INVAR_CORE_CONTRACT.md §4.1, §5.9.
        """
        if self._contributions:
            raise ValueError(
                "Cannot restore into a gate that already has contributions. "
                "Restoration must target a fresh, empty Gate."
            )
        self._base_phi_R = phi_R
        self._base_phi_B = phi_B
        self._base_ts = ts
        # Initialise collapse tracking from Pearl state_after so state() knows
        # to recheck accumulated() on future queries (enables decoherence detection).
        if state != GateState.U:
            self._state = state
            self._collapse_ts = ts

    def energy(self, t: Optional[float] = None) -> float:
        """H(g): gate energy at time t. Definition 1 of Work 5."""
        s = self.state(t)
        if s != GateState.U:
            return 0.0
        phi_R, phi_B = self.accumulated(t)
        return gate_energy(phi_R, phi_B, GateState.U)

    def phase(self, t: Optional[float] = None) -> float:
        """θ(g) = (1-p)·π for Kuramoto coupling."""
        phi_R, phi_B = self.accumulated(t)
        return gate_phase(phi_R, phi_B)

    def weighted_phase(self, t: Optional[float] = None) -> complex:
        """
        H(g) · a · e^(i·(θ⁽⁰⁾(t) + θᵐᵉᵐ)) — H-weighted, amplitude-scaled, phase-dynamic contribution.

        Stage 5 activation: dynamic phase = support anchor + memory offset.
            θ_dynamic = phase(t) + self.theta
            phase(t)   = (1-p(t))·π  — support-derived anchor (unchanged)
            self.theta = memory offset evolved by step() (default 0.0)

        Safety: with theta=0.0 (default) and a=1.0 (default), output is
        bit-for-bit identical to the pre-Stage-5 H(g)·e^(iθ(g)).

        This is the unit for Ψᵢ = Σ H(g)·a·e^(i·θ_dynamic).
        Near-collapsed gates (H≈0) vanish from the state.
        """
        import cmath
        h = self.energy(t)
        if h < 1e-12:
            return complex(0.0)
        theta_dynamic = self.phase(t) + self.theta
        return h * self.a * cmath.exp(1j * theta_dynamic)

    def p(self, t: Optional[float] = None) -> float:
        """Realization probability p = φ_R/(φ_R+φ_B+ε) at time t."""
        phi_R, phi_B = self.accumulated(t)
        return gate_p(phi_R, phi_B)

    # ------------------------------------------------------------------
    # Layer 0 Oscillation Addendum — Stages 2/5/6/7/8/9/10: phase + memory + amplitude
    # ------------------------------------------------------------------

    def step(
        self,
        dt: float,
        coupling_term: float = 0.0,
        c_in: float = 0.0,
        c_i: float = 0.0,
        r_i: float = 0.0,
        e_bar: float = 0.0,
        t: Optional[float] = None,
    ) -> None:
        """
        Forward Euler step of phase offset, contradiction-memory, and amplitude.

        Stage 5 (phase, live):
            dθᵐᵉᵐ/dt = ω + coupling_term + μ

        Stage 6 (μ evolution, live):
            dμ/dt = c_in − lambda_mu · μ
            Steady state: μ* = c_in / lambda_mu.

        Stage 7 (amplitude, live when alpha > 0):
            da/dt = alpha · H(g) − xi · a
            Steady state: a* = alpha · H(g) / xi.

        Stage 8 (μ→a coupling, live when alpha > 0 and beta != 0):
            da/dt = alpha · H(g) + beta · μ − xi · a
            Steady state: a* = (alpha · H(g) + beta · μ*) / xi.

        Stage 9 (cross-gate contradiction coupling, live when gamma != 0):
            dμ/dt = c_in + gamma · c_i − lambda_mu · μ
            c_i is a pre-computed contradiction signal from neighbors ∈ [0, 1].
            Compute via: c_i = contradiction_signal(self, neighbors, t)
            Steady state: μ* = (c_in + gamma · c_i) / lambda_mu.

        Stage 10 (bounded resonance coupling, live when rho != 0):
            dθᵐᵉᵐ/dt = ω + coupling_term + μ + ρ · r_i
            r_i is a pre-computed resonance signal from neighbors ∈ [-1, 1].
            Compute via: r_i = resonance_signal(self, neighbors, t)
            Uses support-anchor θ⁽⁰⁾ (not evolved theta) — no feedback runaway.

        Stage 11 (bounded persistence reward, live when epsilon_persist != 0 and alpha != 0):
            ξ_eff = ξ / max(1e-6, 1 + ε_p · P_i)
            P_i = min(1, a · H(g))   [local persistence score ∈ [0, 1]]
            da/dt = alpha · H(g) + beta · μ − ξ_eff · a
            Coherent gates (high a, high H) decay more slowly.
            Computed internally — no new step() parameter needed.

        Stage 13 (controlled feedback coupling, live when delta_feedback != 0):
            ρ_eff = ρ · (1 + delta_feedback · e_bar)
            e_bar is a pre-computed local emergence summary ∈ [0, 1].
            Compute via: e_bar = local_emergence_summary(self, neighbors, t)
            ρ_eff is transient — computed here, not stored.
            High-emergence neighborhoods: ρ_eff > ρ (stronger resonance pull).
            Empty/quiescent neighborhoods: e_bar=0 → ρ_eff = ρ (no change).
            With delta_feedback=0.0 (default): ρ_eff = ρ (Stage 13 dormant).

        Stage 14 (controlled stabilization, live when zeta_stabilize != 0):
            ω_eff = ω / max(1e-9, 1 + zeta_stabilize · e_bar)
            e_bar is reused from Stage 13 — no new parameter needed.
            ω_eff is transient — computed here, not stored.
            High-emergence neighborhoods: |ω_eff| < |ω| (intrinsic drift reduced).
            Empty/quiescent neighborhoods: e_bar=0 → ω_eff = ω (no stabilization).
            Sign preserved: sign(ω_eff) = sign(ω) always — no polarity reversal.
            Coupling, μ, and resonance terms are unaffected — no hard locking.
            With zeta_stabilize=0.0 (default): ω_eff = ω (Stage 13 unchanged).

        Evaluation order (all derivatives use state at t_n — forward Euler):
          mu_n = snapshot of mu before any update
          1. rho_eff   = rho * (1 + delta_feedback * e_bar)        [transient Stage 13]
          2. omega_eff = omega / max(1e-9, 1 + zeta_stabilize * e_bar)  [transient Stage 14]
          3. theta += dt * (omega_eff + coupling_term + mu_n + rho_eff * r_i)
          4. mu   += dt * (c_in + gamma * c_i − lambda_mu * mu_n)
          5. [if alpha != 0]:
               h = energy(t)
               p_score = min(1, a * h)
               xi_eff = xi / max(1e-6, 1 + epsilon_persist * p_score)
               a += dt * (alpha * h + beta * mu_n − xi_eff * a)

        Using mu_n for theta and amplitude ensures causality: no field reads
        its own post-update value within the same step.

        coupling_term: external override for phase (default 0.0); distinct from r_i.
        c_in: explicit contradiction injection this step (default 0.0).
        c_i: pre-computed cross-gate contradiction signal ∈ [0, 1] (default 0.0).
             Compute via contradiction_signal() before calling step().
        r_i: pre-computed resonance signal ∈ [-1, 1] (default 0.0).
             Compute via resonance_signal() before calling step().
        e_bar: pre-computed local emergence summary ∈ [0, 1] (default 0.0).
               Compute via local_emergence_summary() before calling step().

        Invariants preserved:
          - all defaults → theta, mu, a unchanged (O3, O4, O1)
          - all fields evolve continuously in dt when non-default
          - no effect on phi_R, phi_B, energy(), p(), or collapse logic
          - phi_R, phi_B, _state, _collapse_ts are never touched by step()
        """
        # Snapshot mu before any updates (forward Euler — evaluate at t_n)
        mu_n = self.mu
        # Stage 13: transient effective resonance coefficient (dormant when delta_feedback=0)
        rho_eff = self.rho * (1.0 + self.delta_feedback * e_bar)
        # Stage 14: transient effective natural frequency — reduced drift for coherent gates
        omega_eff = self.omega / max(1e-9, 1.0 + self.zeta_stabilize * e_bar)
        # Phase evolution — uses both modulated coefficients
        self.theta += dt * (omega_eff + coupling_term + mu_n + rho_eff * r_i)
        # Contradiction-memory decay + explicit injection + cross-gate signal
        self.mu += dt * (c_in + self.gamma * c_i - self.lambda_mu * mu_n)
        # Amplitude evolution — dormant when alpha=0.0 (Stage 7 gate)
        if self.alpha != 0.0:
            h = self.energy(t)
            # Stage 11: persistence reward — reduce effective damping for coherent gates
            p_score = min(1.0, self.a * h)
            xi_eff = self.xi / max(1e-6, 1.0 + self.epsilon_persist * p_score)
            self.a += dt * (self.alpha * h + self.beta * mu_n - xi_eff * self.a)
            if self.a < 0.0:
                self.a = 0.0

    def _maybe_collapse(self, t: Optional[float] = None) -> None:
        """Check threshold; record collapse timestamp if crossed."""
        if t is None:
            t = time.time()
        phi_R, phi_B = self.accumulated(t)
        if phi_R >= COLLAPSE_THRESHOLD:
            self._state = GateState.R
            if self._collapse_ts is None:
                self._collapse_ts = t
        elif phi_B >= COLLAPSE_THRESHOLD:
            self._state = GateState.B
            if self._collapse_ts is None:
                self._collapse_ts = t
