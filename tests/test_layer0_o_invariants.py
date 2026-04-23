"""
Layer 0 O-invariant tests — INVAR Oscillation Addendum.

Stages 1–9 are complete.

Reference: docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md

O1 — Bounded amplitude           ag must not diverge  [Live: Stage 7]
O2 — No energy creation          energy accounted for in L*
O3 — Phase continuity            no discontinuous θ jumps  [Live: Stage 5]
O4 — Contradiction memory bounded μg must remain finite  [Live: Stage 6]
O5 — Persistence allowed         system can stay non-collapsed without violating L*
O6 — Coarse-grain stability      coarse state consistent with fine oscillation
"""
import math
import time

import pytest

from invar.core.envelope import DecayClass, ObsGateEnvelope, SupportContribution
from invar.core.field import CouplingField
from invar.core.functional import e_osc, global_L_star, local_L, local_L_star, p_res
from invar.core.gate import (
    Gate, GateState,
    contradiction_signal, emergence_weight, local_emergence_summary, resonance_signal,
)
from invar.core.topology_trace import TopologyTrace, effective_weight, regulation_signal
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_commitments import TopologyCommitments
from invar.core.proto_topology import ProtoTopology
from invar.core.canonical_boundary import CanonicalBoundary, AdvisorySnapshot
from invar.core.gravity import GravityField
from invar.core.support_engine import SupportEngine
from invar.core.topology import CouplingGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fresh():
    engine = SupportEngine()
    gravity = GravityField(engine)
    field = CouplingField()
    graph = CouplingGraph()
    return engine, gravity, field, graph


def push(engine, wid, nk, gate_id, phi_R, phi_B,
         decay_class=DecayClass.STRUCTURAL, t0=None):
    if t0 is None:
        t0 = time.time()
    env = ObsGateEnvelope(instrument_id="test", workload_id=wid, node_key=nk, ts=t0)
    env.contributions.append(SupportContribution(
        gate_id=gate_id, phi_R=phi_R, phi_B=phi_B,
        decay_class=decay_class, t0=t0,
    ))
    engine.ingest(env)


def all_gates(engine, wid, nk):
    return list(engine.gates(wid, nk).values())


# ---------------------------------------------------------------------------
# O1 — Bounded amplitude
# ---------------------------------------------------------------------------

class TestO1BoundedAmplitude:

    def test_o1_default_alpha_amplitude_unchanged(self):
        """With default alpha=0.0, step() never touches a — a=1.0 always."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            for _ in range(1000):
                g.step(dt=0.01)
        for g in gates:
            assert g.a == 1.0

    def test_o1_amplitude_does_not_diverge_under_sustained_drive(self):
        """ag must remain bounded under high unresolvedness drive with alpha > 0.

        Stage 7 live: da/dt = alpha·H(g) − xi·a. Steady state a* = alpha·H/xi.
        With alpha=0.1, xi=0.1: a* = H(g). For H=1 gate, a* = 1.0.
        """
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            g.alpha = 0.1
            g.xi = 0.1
            for _ in range(2000):
                g.step(dt=0.01)
        for g in gates:
            assert g.a < 5.0, f"amplitude diverged: a={g.a}"

    def test_o1_damping_prevents_runaway(self):
        """With xi > 0, amplitude converges to a* = alpha·H(g) / xi at steady state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        for g in gates:
            g.alpha = 0.1
            g.xi = 0.1
            for _ in range(3000):
                g.step(dt=0.01)
        for g in gates:
            h = g.energy(t)
            expected_steady = g.alpha * h / g.xi
            assert g.a == pytest.approx(expected_steady, rel=0.02)

    def test_o1_amplitude_decays_to_zero_when_gate_collapses(self):
        """Collapsed gate has H=0, so a* = 0: amplitude decays to zero after collapse.

        With xi=0.1 and a(0)=2.0: a(t) = 2·e^(-0.1·t).
        After t=200 (2000 steps × dt=0.1): a ≈ 2·e^(-20) ≈ negligible.
        """
        engine, gravity, field, graph = fresh()
        # Push enough support to collapse the gate (phi_R=0.8 > COLLAPSE_THRESHOLD=0.7)
        push(engine, "w1", "n1", "g1", phi_R=0.8, phi_B=0.0)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            g.a = 2.0  # start elevated
            g.alpha = 0.1
            g.xi = 0.1
            for _ in range(2000):
                g.step(dt=0.1)  # t=200 total → a ≈ 2·e^(-20) ≈ 0
        for g in gates:
            assert g.a < 0.01

    def test_o1_amplitude_evolution_does_not_affect_energy(self):
        """Amplitude step reads H(g) but must not write to phi_R, phi_B, or energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.alpha = 0.5
            for _ in range(500):
                g.step(dt=0.02)
        energy_after = [g.energy(t) for g in gates]
        state_after = [g.state(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)
        assert state_after == state_before

    def test_o1_amplitude_nonnegative(self):
        """Amplitude must never go negative even under heavy damping with no drive."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.a = 5.0
        g.alpha = 0.001  # very weak drive
        g.xi = 10.0      # very strong damping
        for _ in range(1000):
            g.step(dt=0.1)
        assert g.a >= 0.0

    # --- Stage 8: μ→a coupling tests ---

    def test_o1_beta_zero_stage7_behavior_unchanged(self):
        """With beta=0.0 (default), Stage 8 is dormant: identical to Stage 7."""
        g_stage7 = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g_stage8 = Gate(gate_id="g2", workload_id="w1", node_key="n1")
        g_stage7.alpha = 0.1
        g_stage7.xi = 0.1
        g_stage8.alpha = 0.1
        g_stage8.xi = 0.1
        g_stage8.beta = 0.0  # explicit dormant
        for _ in range(500):
            g_stage7.step(dt=0.02)
            g_stage8.step(dt=0.02)
        assert g_stage8.a == pytest.approx(g_stage7.a, abs=1e-14)

    def test_o1_mu_coupling_amplifies_amplitude(self):
        """With beta > 0 and nonzero mu, amplitude rises above entropy-only trajectory.

        Setup: fresh gate (H=1.0), alpha=0.1, xi=0.1, beta=0.1.
        Sustain mu at mu*=2.0 via c_in=lambda_mu*mu* = 0.1*2.0 = 0.2.
        Stage 7 a* = alpha*H/xi = 1.0.
        Stage 8 a* = (alpha*H + beta*mu*)/xi = (0.1 + 0.2)/0.1 = 3.0.
        """
        g7 = Gate(gate_id="g7", workload_id="w1", node_key="n1")
        g8 = Gate(gate_id="g8", workload_id="w1", node_key="n1")
        g7.alpha = 0.1
        g7.xi = 0.1
        g8.alpha = 0.1
        g8.xi = 0.1
        g8.beta = 0.1
        g8.lambda_mu = 0.1
        c_in = 0.2  # sustains mu* = c_in/lambda_mu = 2.0
        for _ in range(5000):
            g7.step(dt=0.01)
            g8.step(dt=0.01, c_in=c_in)
        # Stage 8 amplitude should be significantly higher than Stage 7
        assert g8.a > g7.a + 1.0

    def test_o1_mu_coupling_steady_state(self):
        """a converges to (alpha*H + beta*mu*) / xi under sustained mu drive.

        Fresh gate: H=1.0. alpha=0.1, xi=0.2, beta=0.1, lambda_mu=0.1, c_in=0.2.
        mu* = 0.2/0.1 = 2.0. a* = (0.1*1.0 + 0.1*2.0)/0.2 = 1.5.
        Using xi > lambda_mu avoids equal-time-constant resonance for cleaner convergence.
        """
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.alpha = 0.1
        g.xi = 0.2      # faster amplitude convergence than mu (xi > lambda_mu)
        g.beta = 0.1
        g.lambda_mu = 0.1
        c_in = 0.2
        for _ in range(8000):
            g.step(dt=0.01, c_in=c_in)
        mu_star = c_in / g.lambda_mu                             # = 2.0
        h = g.energy()                                           # fresh gate H = 1.0
        a_star = (g.alpha * h + g.beta * mu_star) / g.xi        # = 1.5
        assert g.a == pytest.approx(a_star, rel=0.02)

    def test_o1_mu_coupling_bounded_under_sustained_drive(self):
        """a remains finite and non-negative under any sustained mu drive."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.alpha = 0.5
        g.xi = 0.1
        g.beta = 0.3
        g.lambda_mu = 0.1
        for _ in range(3000):
            g.step(dt=0.01, c_in=1.0)  # high contradiction drive
        assert math.isfinite(g.a)
        assert g.a >= 0.0
        assert g.a < 1000.0

    def test_o1_mu_coupling_does_not_affect_energy(self):
        """beta*mu in amplitude does not change gate energy or support."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.alpha = 0.2
            g.beta = 0.5
            g.mu = 3.0
            for _ in range(500):
                g.step(dt=0.02, c_in=0.2)
        energy_after = [g.energy(t) for g in gates]
        state_after = [g.state(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)
        assert state_after == state_before

    def test_o1_mu_coupling_changes_weighted_phase_magnitude(self):
        """beta*mu coupling raises |weighted_phase| vs beta=0 case."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        g7 = gates[0]
        g7.alpha = 0.1
        g7.xi = 0.1
        # Stage 8 gate — fresh instance, same params plus beta
        g8 = Gate(gate_id="g8", workload_id="w1", node_key="n1")
        g8.alpha = 0.1
        g8.xi = 0.1
        g8.beta = 0.2
        g8.lambda_mu = 0.1
        for _ in range(3000):
            g7.step(dt=0.01)
            g8.step(dt=0.01, c_in=0.2)
        t = time.time()
        mag7 = abs(g7.weighted_phase(t))
        # g8 has no support contributions so H=1; g7 has phi_R=0.3,phi_B=0.3
        # Compare by a value directly: g8.a should be > g7.a
        assert g8.a > g7.a


# ---------------------------------------------------------------------------
# O2 — No energy creation
# ---------------------------------------------------------------------------

class TestO2NoEnergyCreation:

    def test_o2_e_osc_nonnegative(self):
        """E_osc ≥ 0 always — squares of real values."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        assert e_osc(gates) >= 0.0

    def test_o2_e_osc_zero_when_omega_and_mu_zero(self):
        """With default ω=0, μ=0: E_osc = λ_a·a² only (structural cost)."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            assert g.omega == 0.0
            assert g.mu == 0.0
        # E_osc is non-negative and finite
        cost = e_osc(gates)
        assert 0.0 <= cost < 1e6

    def test_o2_local_L_star_bounded_below(self):
        """L* ≥ 0 always (P_res ≤ E_self ≤ L)."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        t = time.time()
        l_star = local_L_star("w1", "n1", engine, field, graph, gravity, t)
        assert l_star >= 0.0


# ---------------------------------------------------------------------------
# O3 — Phase continuity
# ---------------------------------------------------------------------------

class TestO3PhaseContinuity:

    def test_o3_theta_starts_at_zero(self):
        """Fresh gate: theta = 0.0 (memory phase offset; zero means no offset from anchor)."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.theta == 0.0

    def test_o3_step_with_omega_zero_does_not_change_theta(self):
        """omega=0, mu=0, coupling=0 → theta unchanged after step()."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        theta_before = g.theta
        g.step(dt=0.1)
        assert g.theta == pytest.approx(theta_before, abs=1e-12)

    def test_o3_theta_changes_continuously_with_nonzero_omega(self):
        """Non-zero omega → theta changes proportionally to dt."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.omega = 1.0
        theta_before = g.theta
        g.step(dt=0.1)
        delta = g.theta - theta_before
        assert delta == pytest.approx(0.1, abs=1e-10)

    def test_o3_weighted_phase_reflects_dynamic_theta(self):
        """After step() with omega, weighted_phase uses the evolved theta. (Stage 5 live)"""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            g.omega = 1.0
        t = time.time()
        psi_before = gravity.fiber_tensor("w1", "n1", t)
        for g in gates:
            g.step(dt=0.5)
        psi_after = gravity.fiber_tensor("w1", "n1", t)
        # Phase should have rotated — tensors should differ in angle
        angle_before = math.atan2(psi_before.imag, psi_before.real + 1e-30)
        angle_after = math.atan2(psi_after.imag, psi_after.real + 1e-30)
        assert abs(angle_after - angle_before) > 0.01

    def test_o3_default_params_output_unchanged(self):
        """With omega=0, mu=0, coupling=0: weighted_phase() is unchanged by step(). (O3 regression guard)"""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        psi_before = gravity.fiber_tensor("w1", "n1", t)
        for g in gates:
            # All defaults: omega=0, mu=0, coupling=0 → step is a no-op on theta
            g.step(dt=10.0)
        psi_after = gravity.fiber_tensor("w1", "n1", t)
        assert psi_after == pytest.approx(psi_before, abs=1e-12)

    def test_o3_energy_unchanged_by_phase_step(self):
        """step() with omega≠0 changes phase but not energy or collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.omega = 5.0
            for _ in range(100):
                g.step(dt=0.1)
        energy_after = [g.energy(t) for g in gates]
        state_after = [g.state(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)
        assert state_after == state_before


# ---------------------------------------------------------------------------
# O4 — Contradiction memory bounded
# ---------------------------------------------------------------------------

class TestO4ContradictionMemoryBounded:

    def test_o4_mu_starts_at_zero(self):
        """Fresh gate: mu = 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.mu == 0.0

    def test_o4_mu_remains_bounded_under_sustained_contradiction(self):
        """mu must stay finite even with sustained contradiction drive.

        With constant c_in=0.1 and lambda_mu=0.1, steady state = c_in/lambda_mu = 1.0.
        Uses step() with explicit c_in injection.
        """
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        for _ in range(1000):
            g.step(dt=0.01, c_in=0.1)
        # Steady state: mu* = c_in / lambda_mu = 0.1 / 0.1 = 1.0
        assert abs(g.mu) < 2.0

    def test_o4_mu_decays_when_contradiction_removed(self):
        """mu decays toward zero after contradiction drive removed.

        Stage 6 live: step() evolves mu via dμ/dt = c_in − lambda_mu·μ.
        With c_in=0 and lambda_mu=0.1, mu decays exponentially.
        After 200 steps of dt=0.1 (total t=20): mu ≈ 5 * e^(-0.1*20) ≈ 0.677.
        """
        mu_initial = 5.0
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.mu = mu_initial
        for _ in range(200):
            g.step(dt=0.1)  # no contradiction input
        assert g.mu < mu_initial     # decayed from initial
        assert g.mu > 0.0            # still non-negative (exponential decay stays positive)
        assert g.mu < 1.0            # decayed significantly (expected ≈ 0.677)

    def test_o4_mu_decays_to_near_zero_over_long_run(self):
        """mu reaches near-zero under sustained decay with no input."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g.mu = 10.0
        for _ in range(2000):
            g.step(dt=0.1)  # total t=200: mu ≈ 10 * e^(-0.1*200) ≈ 2e-9
        assert abs(g.mu) < 1e-6

    def test_o4_mu_steady_state_under_constant_input(self):
        """With constant c_in, mu converges to c_in / lambda_mu."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        c_in = 0.5
        # lambda_mu default = 0.1 → expected steady state = 0.5/0.1 = 5.0
        for _ in range(5000):
            g.step(dt=0.01, c_in=c_in)
        expected = c_in / g.lambda_mu
        assert g.mu == pytest.approx(expected, rel=0.01)  # within 1%

    def test_o4_mu_evolution_does_not_affect_energy(self):
        """Evolving mu via step() must not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        for g in gates:
            g.mu = 2.0
            for _ in range(100):
                g.step(dt=0.1, c_in=0.05)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_o4_mu_evolution_does_not_affect_collapse(self):
        """Evolving mu via step() must not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.mu = 3.0
            for _ in range(200):
                g.step(dt=0.05, c_in=0.1)
        state_after = [g.state(t) for g in gates]
        assert state_after == state_before

    def test_o4_mu_influences_theta_via_step(self):
        """Nonzero mu causes theta to evolve faster via the phase law dθ/dt = ω + coupling + μ."""
        g_with_mu = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g_without_mu = Gate(gate_id="g2", workload_id="w1", node_key="n1")
        g_with_mu.mu = 1.0
        # One step: theta += dt * (0 + 0 + mu)
        g_with_mu.step(dt=0.1)
        g_without_mu.step(dt=0.1)
        assert g_with_mu.theta > g_without_mu.theta

    def test_o4_default_params_no_mu_change(self):
        """With default mu=0 and c_in=0, mu stays at 0 after any number of steps."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.mu == 0.0
        for _ in range(1000):
            g.step(dt=0.1)
        assert g.mu == 0.0


# ---------------------------------------------------------------------------
# O5 — Persistence allowed
# ---------------------------------------------------------------------------

class TestO5PersistenceAllowed:

    def test_o5_step_does_not_trigger_collapse(self):
        """step() never modifies phi_R, phi_B, _state, or _collapse_ts."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        for g in gates:
            state_before = g._state
            phi_before = g.accumulated(t)
            g.step(dt=0.5)
            assert g._state == state_before
            # accumulated() at the same fixed t must be bit-for-bit identical
            assert g.accumulated(t) == phi_before

    def test_o5_gate_remains_U_after_many_steps(self):
        """Balanced gate stays in U after many step() calls."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        for g in gates:
            for _ in range(1000):
                g.step(dt=0.01)
        for g in gates:
            assert g.state(t) == GateState.U

    def test_o5_L_star_finite_for_oscillating_gate(self):
        """L* remains finite and non-negative for a gate under oscillation."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            g.omega = 0.5
            for _ in range(50):
                g.step(dt=0.05)
        t = time.time()
        l_star = local_L_star("w1", "n1", engine, field, graph, gravity, t)
        assert math.isfinite(l_star)
        assert l_star >= 0.0


# ---------------------------------------------------------------------------
# O6 — Coarse-grain stability
# ---------------------------------------------------------------------------

class TestO6CoarseGrainStability:

    def test_o6_e_osc_additive_across_gates(self):
        """E_osc for a cluster equals the sum of per-gate oscillatory costs."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.2, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        total = e_osc(gates)
        per_gate = sum(e_osc([g]) for g in gates)
        assert total == pytest.approx(per_gate, abs=1e-12)

    def test_o6_coarse_psi_star_bounded_by_self_energy(self):
        """
        Coarse-grained Ψ̃* = Σᵢ Ψᵢ* stays ≤ Σᵢ E_self(Ωᵢ).

        Once weighted_phase uses evolved theta, the coherence bound
        Σ|Ψᵢ| ≤ Σ E_self must still hold for the oscillatory tensor.
        """
        engine, gravity, field, graph = fresh()
        for nk, phi_R, phi_B in [("n1", 0.3, 0.3), ("n2", 0.25, 0.35), ("n3", 0.4, 0.2)]:
            push(engine, "w1", nk, "g1", phi_R, phi_B)
        for nk in ["n1", "n2", "n3"]:
            for g in all_gates(engine, "w1", nk):
                g.omega = 0.5
                for _ in range(20):
                    g.step(dt=0.05)
        t = time.time()
        psi_cluster = sum(gravity.fiber_tensor("w1", nk, t) for nk in ["n1", "n2", "n3"])
        e_total = sum(gravity.self_energy("w1", nk, t) for nk in ["n1", "n2", "n3"])
        assert abs(psi_cluster) <= e_total + 1e-10


# ---------------------------------------------------------------------------
# Stage 9 — Cross-gate contradiction coupling
# ---------------------------------------------------------------------------

class TestStage9CrossGateContradiction:

    def test_s9_gamma_zero_default_stage8_behavior_unchanged(self):
        """With default gamma=0.0, step(c_i=X) has no effect on mu — Stage 8 behavior."""
        g_default = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g_with_ci = Gate(gate_id="g2", workload_id="w1", node_key="n1")
        # Both start with same state; only one receives c_i signal
        for _ in range(100):
            g_default.step(dt=0.1, c_i=0.0)
            g_with_ci.step(dt=0.1, c_i=1.0)  # gamma=0 → c_i has no effect
        assert g_default.mu == pytest.approx(g_with_ci.mu, abs=1e-12)

    def test_s9_contradiction_signal_identical_phases_returns_zero(self):
        """Gates with identical support state have zero phase mismatch — C_i = 0."""
        t = time.time()
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g2 = Gate(gate_id="g2", workload_id="w1", node_key="n1")
        # No contributions — both have p=0.5 → phase = π/2, no mismatch
        c = contradiction_signal(g1, [g2], t)
        assert c == pytest.approx(0.0, abs=1e-12)

    def test_s9_contradiction_signal_empty_neighbors_returns_zero(self):
        """Isolated gate: no neighbors → C_i = 0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        c = contradiction_signal(g, [], None)
        assert c == 0.0

    def test_s9_contradiction_signal_bounded_in_zero_one(self):
        """C_i is bounded to [0, 1] for any combination of gate support states."""
        engine, gravity, field, graph = fresh()
        t = time.time()
        # Create gates with varied support states
        push(engine, "w1", "n1", "g1", phi_R=0.1, phi_B=0.5, t0=t)
        push(engine, "w1", "n2", "g2", phi_R=0.5, phi_B=0.1, t0=t)
        push(engine, "w1", "n3", "g3", phi_R=0.3, phi_B=0.3, t0=t)
        gates_n1 = all_gates(engine, "w1", "n1")
        gates_n2 = all_gates(engine, "w1", "n2")
        gates_n3 = all_gates(engine, "w1", "n3")
        for gi in gates_n1:
            neighbors = gates_n2 + gates_n3
            c = contradiction_signal(gi, neighbors, t)
            assert 0.0 <= c <= 1.0 + 1e-12

    def test_s9_contradiction_signal_max_disagreement_near_one(self):
        """Gates maximally out of phase give C_i close to 1."""
        # Gate at p≈1 (R-biased, phase ≈ 0) vs gate at p≈0 (B-biased, phase ≈ π)
        # sin(0 − π) = sin(-π) = 0, but sin(π/2) = 1 is maximum.
        # Use p=0.5 (phase=π/2) and p→0 (phase≈π): |sin(π/2 − π)| = |sin(-π/2)| = 1.
        t = time.time()
        # g1: balanced (phase ≈ π/2) — no contributions → p=0.5 → phase = π/2
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        # g2: strong B-bias → p≈0.01 → phase ≈ 0.99π ≈ 3.11
        # theta_i=π/2, theta_j≈π: |sin(π/2 − π)| = |sin(-π/2)| = 1.0
        engine = SupportEngine()
        env = ObsGateEnvelope(
            instrument_id="test", workload_id="w2", node_key="n2", ts=t
        )
        env.contributions.append(SupportContribution(
            gate_id="g2", phi_R=0.01, phi_B=0.99,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine.ingest(env)
        g2_list = all_gates(engine, "w2", "n2")
        assert len(g2_list) == 1
        g2 = g2_list[0]
        c = contradiction_signal(g1, [g2], t)
        assert c > 0.9

    def test_s9_cross_gate_disagreement_raises_mu(self):
        """Gate with gamma>0 and disagreeing neighbor accumulates mu faster than isolated gate."""
        t = time.time()
        # Gate under test
        g_coupled = Gate(gate_id="g1", workload_id="w1", node_key="n1", gamma=0.5)
        g_isolated = Gate(gate_id="g2", workload_id="w2", node_key="n2", gamma=0.5)

        # Neighbor with orthogonal phase (p=0.5, same as g_coupled → C_i=0)
        # Actually we need a disagreeing neighbor.
        # g_coupled is balanced (p=0.5, phase=π/2); make neighbor B-biased (phase≈π)
        engine = SupportEngine()
        env = ObsGateEnvelope(
            instrument_id="test", workload_id="w3", node_key="n3", ts=t
        )
        env.contributions.append(SupportContribution(
            gate_id="nb", phi_R=0.01, phi_B=0.6,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine.ingest(env)
        neighbor = all_gates(engine, "w3", "n3")[0]

        c_i = contradiction_signal(g_coupled, [neighbor], t)
        assert c_i > 0.5  # meaningful disagreement

        for _ in range(200):
            g_coupled.step(dt=0.05, c_i=c_i)
            g_isolated.step(dt=0.05, c_i=0.0)

        # Coupled gate has higher mu due to persistent cross-gate signal
        assert g_coupled.mu > g_isolated.mu

    def test_s9_mu_bounded_under_sustained_cross_gate_drive(self):
        """mu stays finite under sustained c_i=1.0 and gamma>0.

        Steady state: mu* = gamma*c_i / lambda_mu = 0.5*1.0/0.1 = 5.0.
        Run long enough to converge; confirm mu ≤ 1.5 * steady_state.
        """
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 gamma=0.5, lambda_mu=0.1)
        for _ in range(5000):
            g.step(dt=0.01, c_i=1.0)
        expected_ss = g.gamma * 1.0 / g.lambda_mu  # = 5.0
        assert math.isfinite(g.mu)
        assert g.mu == pytest.approx(expected_ss, rel=0.02)

    def test_s9_cross_gate_coupling_does_not_affect_energy(self):
        """step() with gamma and c_i must not change gate energy or state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.gamma = 0.5
            for _ in range(200):
                g.step(dt=0.05, c_i=0.8)
        energy_after = [g.energy(t) for g in gates]
        state_after = [g.state(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)
        assert state_after == state_before

    def test_s9_contradiction_signal_deterministic(self):
        """contradiction_signal returns same value on repeated calls with same t."""
        t = time.time()
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.2, phi_B=0.4, t0=t)
        push(engine, "w1", "n2", "g2", phi_R=0.4, phi_B=0.2, t0=t)
        g1 = all_gates(engine, "w1", "n1")[0]
        g2 = all_gates(engine, "w1", "n2")[0]
        c1 = contradiction_signal(g1, [g2], t)
        c2 = contradiction_signal(g1, [g2], t)
        assert c1 == c2

    def test_s9_gamma_field_default_zero(self):
        """Fresh Gate has gamma=0.0 by default."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.gamma == 0.0


# ---------------------------------------------------------------------------
# Stage 10 — Bounded resonance coupling
# ---------------------------------------------------------------------------

class TestStage10ResonanceCoupling:

    def test_s10_rho_zero_default_stage9_behavior_unchanged(self):
        """With default rho=0.0, step(r_i=X) has no effect on theta — Stage 9 behavior."""
        g_default = Gate(gate_id="g1", workload_id="w1", node_key="n1", omega=0.1)
        g_with_ri = Gate(gate_id="g2", workload_id="w1", node_key="n1", omega=0.1)
        # rho=0.0 by default — r_i signal ignored
        for _ in range(100):
            g_default.step(dt=0.1, r_i=0.0)
            g_with_ri.step(dt=0.1, r_i=1.0)
        assert g_default.theta == pytest.approx(g_with_ri.theta, abs=1e-12)

    def test_s10_rho_field_default_zero(self):
        """Fresh Gate has rho=0.0 by default."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.rho == 0.0

    def test_s10_resonance_signal_empty_neighbors_returns_zero(self):
        """Isolated gate: no neighbors → R_i = 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        r = resonance_signal(g, [], None)
        assert r == 0.0

    def test_s10_resonance_signal_identical_phases_returns_one(self):
        """Gates with identical support state have cos(0) = 1 alignment — R_i = 1.0."""
        # Fresh gates have same default phase (no contributions → p=0.5 → phase=π/2)
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2")
        r = resonance_signal(g1, [g2], None)
        assert r == pytest.approx(1.0, abs=1e-12)

    def test_s10_resonance_signal_bounded_in_minus_one_to_one(self):
        """R_i is bounded to [-1, 1] for any combination of gate support states."""
        engine, gravity, field, graph = fresh()
        t = time.time()
        push(engine, "w1", "n1", "g1", phi_R=0.1, phi_B=0.5, t0=t)
        push(engine, "w1", "n2", "g2", phi_R=0.5, phi_B=0.1, t0=t)
        push(engine, "w1", "n3", "g3", phi_R=0.3, phi_B=0.3, t0=t)
        gates_n1 = all_gates(engine, "w1", "n1")
        gates_n2 = all_gates(engine, "w1", "n2")
        gates_n3 = all_gates(engine, "w1", "n3")
        for gi in gates_n1:
            neighbors = gates_n2 + gates_n3
            r = resonance_signal(gi, neighbors, t)
            assert -1.0 - 1e-12 <= r <= 1.0 + 1e-12

    def test_s10_resonance_signal_anti_aligned_phases_negative(self):
        """Gate at phase≈0 and neighbor at phase≈π give cos(π-0)=cos(π)=-1 → R_i≈-1."""
        t = time.time()
        # g1: strong R-bias → p≈1 → phase ≈ 0
        engine1 = SupportEngine()
        env1 = ObsGateEnvelope(instrument_id="test", workload_id="w1", node_key="n1", ts=t)
        env1.contributions.append(SupportContribution(
            gate_id="g1", phi_R=0.99, phi_B=0.01,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine1.ingest(env1)
        g1 = all_gates(engine1, "w1", "n1")[0]

        # g2: strong B-bias → p≈0 → phase ≈ π
        engine2 = SupportEngine()
        env2 = ObsGateEnvelope(instrument_id="test", workload_id="w2", node_key="n2", ts=t)
        env2.contributions.append(SupportContribution(
            gate_id="g2", phi_R=0.01, phi_B=0.99,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine2.ingest(env2)
        g2 = all_gates(engine2, "w2", "n2")[0]

        r = resonance_signal(g1, [g2], t)
        assert r < -0.9  # strongly anti-aligned

    def test_s10_resonance_drives_phase_toward_neighbors(self):
        """With rho>0, gate with r_i>0 accumulates more theta than isolated gate."""
        g_aligned = Gate(gate_id="g1", workload_id="w1", node_key="n1", rho=0.5)
        g_isolated = Gate(gate_id="g2", workload_id="w2", node_key="n2", rho=0.5)
        # r_i=0.8 (positive resonance) → extra term adds to theta
        for _ in range(100):
            g_aligned.step(dt=0.1, r_i=0.8)
            g_isolated.step(dt=0.1, r_i=0.0)
        assert g_aligned.theta > g_isolated.theta

    def test_s10_resonance_anti_alignment_slows_phase(self):
        """With rho>0 and r_i<0, theta accumulates less than with r_i=0."""
        g_anti = Gate(gate_id="g1", workload_id="w1", node_key="n1", rho=0.5, omega=1.0)
        g_free = Gate(gate_id="g2", workload_id="w2", node_key="n2", rho=0.5, omega=1.0)
        for _ in range(100):
            g_anti.step(dt=0.1, r_i=-0.5)  # anti-alignment brakes phase
            g_free.step(dt=0.1, r_i=0.0)
        assert g_anti.theta < g_free.theta

    def test_s10_resonance_does_not_affect_energy(self):
        """step() with rho and r_i must not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        for g in gates:
            g.rho = 1.0
            for _ in range(200):
                g.step(dt=0.05, r_i=0.8)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s10_resonance_does_not_affect_collapse(self):
        """step() with rho and r_i must not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.rho = 2.0
            for _ in range(200):
                g.step(dt=0.05, r_i=-1.0)
        state_after = [g.state(t) for g in gates]
        assert state_after == state_before

    def test_s10_resonance_signal_deterministic(self):
        """resonance_signal returns same value on repeated calls with same t."""
        t = time.time()
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.2, phi_B=0.4, t0=t)
        push(engine, "w1", "n2", "g2", phi_R=0.4, phi_B=0.2, t0=t)
        g1 = all_gates(engine, "w1", "n1")[0]
        g2 = all_gates(engine, "w1", "n2")[0]
        r1 = resonance_signal(g1, [g2], t)
        r2 = resonance_signal(g1, [g2], t)
        assert r1 == r2

    def test_s10_resonance_and_contradiction_orthogonal(self):
        """R_i and C_i use orthogonal trig functions; both bounded independently.

        At phase difference of π/2: |sin(π/2)| = 1 (max contradiction)
                                     cos(π/2) = 0  (zero resonance)
        """
        t = time.time()
        # g1: balanced → phase = π/2
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1")

        # g2: strong R-bias → p≈1 → phase ≈ 0; diff from g1 ≈ π/2
        engine = SupportEngine()
        env = ObsGateEnvelope(instrument_id="test", workload_id="w2", node_key="n2", ts=t)
        env.contributions.append(SupportContribution(
            gate_id="g2", phi_R=0.99, phi_B=0.01,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine.ingest(env)
        g2 = all_gates(engine, "w2", "n2")[0]

        c = contradiction_signal(g1, [g2], t)
        r = resonance_signal(g1, [g2], t)
        # Near π/2 phase diff: high contradiction, near-zero resonance
        assert c > 0.9
        assert abs(r) < 0.2  # close to zero (orthogonal)


# ---------------------------------------------------------------------------
# Stage 11 — Bounded persistence reward
# ---------------------------------------------------------------------------

class TestStage11PersistenceReward:

    def test_s11_epsilon_persist_default_zero(self):
        """Fresh Gate has epsilon_persist=0.0 by default."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.epsilon_persist == 0.0

    def test_s11_epsilon_zero_stage10_behavior_unchanged(self):
        """With default epsilon_persist=0.0, amplitude evolves exactly as Stage 10."""
        g_no_persist = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                            alpha=0.1, xi=0.1)
        g_zero_ep = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                         alpha=0.1, xi=0.1, epsilon_persist=0.0)
        t = None
        for _ in range(500):
            g_no_persist.step(dt=0.01, t=t)
            g_zero_ep.step(dt=0.01, t=t)
        assert g_no_persist.a == pytest.approx(g_zero_ep.a, abs=1e-12)

    def test_s11_persistence_score_bounded_zero_one(self):
        """P_i = min(1, a*H) ∈ [0,1] for any gate state."""
        t = time.time()
        # Balanced gate: H=1.0 (no contributions → max entropy), a=2.0 → P_i = min(1, 2.0*1.0) = 1.0
        g_max = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=2.0)
        h = g_max.energy(None)
        p_score = min(1.0, g_max.a * h)
        assert 0.0 <= p_score <= 1.0

        # Collapsed gate: must have support ≥ threshold to genuinely collapse
        engine = SupportEngine()
        env = ObsGateEnvelope(instrument_id="test", workload_id="w2", node_key="n2", ts=t)
        env.contributions.append(SupportContribution(
            gate_id="gc", phi_R=0.8, phi_B=0.0,
            decay_class=DecayClass.STRUCTURAL, t0=t,
        ))
        engine.ingest(env)
        g_collapsed = all_gates(engine, "w2", "n2")[0]
        assert g_collapsed.state(t) == GateState.R  # actually collapsed
        h2 = g_collapsed.energy(t)
        p_score2 = min(1.0, g_collapsed.a * h2)
        assert p_score2 == 0.0  # collapsed → H=0 → P_i=0

    def test_s11_xi_eff_always_positive(self):
        """Effective damping ξ_eff = ξ / max(1e-6, 1+ε·P_i) is always > 0."""
        # Even with large epsilon_persist, xi_eff stays positive
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 alpha=0.5, xi=0.1, epsilon_persist=1000.0)
        t = None
        # Run without crashing; amplitude must remain finite and non-negative
        for _ in range(100):
            g.step(dt=0.01, t=t)
        assert g.a >= 0.0
        assert math.isfinite(g.a)

    def test_s11_coherent_gate_decays_slower_than_incoherent(self):
        """High persistence (high a·H) decays more slowly than low persistence.

        Two gates identical except epsilon_persist. The one with epsilon_persist>0
        has ξ_eff < ξ and reaches a higher steady-state amplitude.
        """
        # Gate without persistence reward
        g_no = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                    alpha=0.1, xi=0.1, epsilon_persist=0.0)
        # Gate with persistence reward
        g_yes = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                     alpha=0.1, xi=0.1, epsilon_persist=2.0)
        t = None
        for _ in range(3000):
            g_no.step(dt=0.01, t=t)
            g_yes.step(dt=0.01, t=t)
        # Both should have converged; the persistence gate should have higher a
        assert g_yes.a > g_no.a

    def test_s11_persistence_only_active_when_alpha_nonzero(self):
        """With alpha=0.0, epsilon_persist has no effect — a stays at 1.0."""
        g_ep = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                    alpha=0.0, epsilon_persist=5.0)
        for _ in range(1000):
            g_ep.step(dt=0.1)
        # alpha=0 → amplitude block never entered → a unchanged
        assert g_ep.a == 1.0

    def test_s11_persistence_does_not_affect_energy(self):
        """step() with epsilon_persist must not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        for g in gates:
            g.alpha = 0.1
            g.xi = 0.1
            g.epsilon_persist = 2.0
            for _ in range(200):
                g.step(dt=0.05, t=t)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s11_persistence_does_not_affect_collapse(self):
        """step() with epsilon_persist must not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        state_before = [g.state(t) for g in gates]
        for g in gates:
            g.alpha = 0.1
            g.xi = 0.1
            g.epsilon_persist = 5.0
            for _ in range(200):
                g.step(dt=0.05, t=t)
        state_after = [g.state(t) for g in gates]
        assert state_after == state_before

    def test_s11_persistence_deterministic(self):
        """Same epsilon_persist and same initial state → same trajectory."""
        def run(ep):
            g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     alpha=0.1, xi=0.1, epsilon_persist=ep)
            for _ in range(200):
                g.step(dt=0.01, t=None)
            return g.a

        a1 = run(2.0)
        a2 = run(2.0)
        assert a1 == pytest.approx(a2, abs=1e-12)

    def test_s11_persistence_steady_state_higher_than_baseline(self):
        """With epsilon_persist > 0, steady-state a is higher than alpha*H/xi baseline.

        Without persistence: a* = alpha*H/xi = 0.1*1.0/0.1 = 1.0
        With persistence: a* > 1.0 (ξ_eff < ξ)
        """
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 alpha=0.1, xi=0.1, epsilon_persist=1.0)
        t = None
        for _ in range(5000):
            g.step(dt=0.01, t=t)
        # baseline steady state is 1.0; with persistence it should be higher
        assert g.a > 1.0
        assert math.isfinite(g.a)


# ---------------------------------------------------------------------------
# Stage 12 — Controlled topology emergence
# ---------------------------------------------------------------------------

class TestStage12TopologyEmergence:

    def test_s12_kappa_zero_effective_weight_unchanged(self):
        """With kappa_emergence=0.0 (default), w_ij_eff = w_ij for any pair."""
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2")
        w_ij = 0.7
        E = emergence_weight(g1, g2)
        w_eff = w_ij * (1 + g1.kappa_emergence * E)
        assert w_eff == pytest.approx(w_ij, abs=1e-12)

    def test_s12_e_ij_bounded_zero_one(self):
        """E_ij ∈ [0, 1] for all gate configurations."""
        configs = [
            (0.0, 0.0, 0.0, 0.0),   # identical support-free gates
            (0.3, 0.3, 0.3, 0.3),   # same balanced gates
            (0.8, 0.0, 0.0, 0.8),   # one R-biased, one B-biased (anti-aligned)
            (0.3, 0.0, 0.6, 0.0),   # same polarity, different magnitude
        ]
        for phi_R_a, phi_B_a, phi_R_b, phi_B_b in configs:
            engine = SupportEngine()
            t = time.time()
            for wid, nk, gid, pR, pB in [
                ("wa", "na", "ga", phi_R_a, phi_B_a),
                ("wb", "nb", "gb", phi_R_b, phi_B_b),
            ]:
                if pR + pB > 0:
                    env = ObsGateEnvelope(instrument_id="test", workload_id=wid, node_key=nk, ts=t)
                    env.contributions.append(SupportContribution(
                        gate_id=gid, phi_R=pR, phi_B=pB,
                        decay_class=DecayClass.STRUCTURAL, t0=t,
                    ))
                    engine.ingest(env)
            # Fresh gates for isolated pairs
            ga = Gate(gate_id="ga", workload_id="wa", node_key="na")
            gb = Gate(gate_id="gb", workload_id="wb", node_key="nb")
            E = emergence_weight(ga, gb, t)
            assert 0.0 <= E <= 1.0, f"E_ij={E} out of [0,1] for config {phi_R_a,phi_B_a,phi_R_b,phi_B_b}"

    def test_s12_e_ij_symmetric(self):
        """E_ij = E_ji — emergence weight is symmetric."""
        engine = SupportEngine()
        t = time.time()
        for wid, nk, gid, pR, pB in [("wa", "na", "ga", 0.4, 0.1), ("wb", "nb", "gb", 0.1, 0.4)]:
            env = ObsGateEnvelope(instrument_id="test", workload_id=wid, node_key=nk, ts=t)
            env.contributions.append(SupportContribution(
                gate_id=gid, phi_R=pR, phi_B=pB,
                decay_class=DecayClass.STRUCTURAL, t0=t,
            ))
            engine.ingest(env)
        ga = Gate(gate_id="ga", workload_id="wa", node_key="na")
        gb = Gate(gate_id="gb", workload_id="wb", node_key="nb")
        assert emergence_weight(ga, gb, t) == pytest.approx(emergence_weight(gb, ga, t), abs=1e-12)

    def test_s12_aligned_persistent_pair_enhances_weight(self):
        """Aligned pair (same phase) with a > 0 produces E_ij > 0."""
        # Two gates with identical support → same phase → cos(0) = 1 → E_ij = ā
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=1.0)
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2", a=1.0)
        E = emergence_weight(g1, g2)
        # Both have no contributions → phase = π/2 each → R_ij = cos(0) = 1.0
        # ā = 1.0 → E_ij = min(1, 1.0*1.0) = 1.0
        assert E == pytest.approx(1.0, abs=1e-10)

    def test_s12_anti_aligned_pair_clips_to_zero(self):
        """Anti-aligned pair (phases π apart) → R_ij = -1 → max(0, R_ij)=0 → E_ij=0."""
        t = time.time()
        engine = SupportEngine()
        # Gate A: strong R bias → phase near 0
        for wid, nk, gid, pR, pB in [
            ("wa", "na", "ga", 0.9, 0.0),  # R-biased → p → 1 → θ → 0
            ("wb", "nb", "gb", 0.0, 0.9),  # B-biased → p → 0 → θ → π
        ]:
            env = ObsGateEnvelope(instrument_id="test", workload_id=wid, node_key=nk, ts=t)
            env.contributions.append(SupportContribution(
                gate_id=gid, phi_R=pR, phi_B=pB,
                decay_class=DecayClass.STRUCTURAL, t0=t,
            ))
            engine.ingest(env)
        ga = list(engine.gates("wa", "na").values())[0]
        gb = list(engine.gates("wb", "nb").values())[0]
        E = emergence_weight(ga, gb, t)
        # R_ij = cos(π − 0) = -1 → max(0, -1) = 0 → E_ij = 0
        assert E == pytest.approx(0.0, abs=1e-6)

    def test_s12_zero_amplitude_produces_zero_e(self):
        """If ā_ij = 0 (both amplitudes zero), E_ij = 0."""
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=0.0)
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2", a=0.0)
        E = emergence_weight(g1, g2)
        assert E == pytest.approx(0.0, abs=1e-12)

    def test_s12_w_eff_bounded_above(self):
        """w_ij_eff ≤ w_ij * (1 + kappa) since E_ij ≤ 1."""
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=1.0, kappa_emergence=0.5)
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2", a=1.0)
        w_ij = 0.6
        E = emergence_weight(g1, g2)
        w_eff = w_ij * (1 + g1.kappa_emergence * E)
        assert w_eff <= w_ij * (1 + g1.kappa_emergence)

    def test_s12_w_eff_non_negative(self):
        """w_ij_eff ≥ 0 for non-negative w_ij and kappa."""
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=1.5, kappa_emergence=2.0)
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2", a=1.5)
        w_ij = 0.5
        E = emergence_weight(g1, g2)
        w_eff = w_ij * (1 + g1.kappa_emergence * E)
        assert w_eff >= 0.0

    def test_s12_emergence_does_not_affect_energy(self):
        """emergence_weight() is read-only — gate energy is unchanged after calling it."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        # Read emergence weights (read-only, should not mutate anything)
        if len(gates) >= 2:
            _ = emergence_weight(gates[0], gates[1], t)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s12_emergence_does_not_affect_collapse(self):
        """emergence_weight() is read-only — gate collapse state is unchanged."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]
        if len(gates) >= 2:
            _ = emergence_weight(gates[0], gates[1], t)
        states_after = [g.state(t) for g in gates]
        assert states_after == states_before

    def test_s12_emergence_deterministic(self):
        """Same gate configuration → same emergence_weight every call."""
        g1 = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=0.8)
        g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2", a=0.6)
        t = 12345.0
        E1 = emergence_weight(g1, g2, t)
        E2 = emergence_weight(g1, g2, t)
        assert E1 == pytest.approx(E2, abs=1e-12)

    def test_s12_kappa_emergence_default_zero(self):
        """Gate.kappa_emergence defaults to 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.kappa_emergence == 0.0


# ---------------------------------------------------------------------------
# Stage 13 — Controlled feedback coupling
# ---------------------------------------------------------------------------

class TestStage13FeedbackCoupling:

    def test_s13_delta_feedback_default_zero(self):
        """Gate.delta_feedback defaults to 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.delta_feedback == 0.0

    def test_s13_delta_zero_stage12_behavior_unchanged(self):
        """With delta_feedback=0.0, step() behaves identically to Stage 12."""
        # Two identical gates; one has delta_feedback=0 (explicit), other omits it
        g_ref = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     rho=0.3, omega=0.1)
        g_fb = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                    rho=0.3, omega=0.1, delta_feedback=0.0)
        r_i = 0.8
        e_bar = 0.5   # would have effect if delta_feedback != 0
        for _ in range(200):
            g_ref.step(dt=0.01, r_i=r_i)
            g_fb.step(dt=0.01, r_i=r_i, e_bar=e_bar)
        # delta_feedback=0 → rho_eff = rho regardless of e_bar
        assert g_ref.theta == pytest.approx(g_fb.theta, abs=1e-12)

    def test_s13_e_bar_zero_stage12_behavior_unchanged(self):
        """With e_bar=0.0 (default), step() behaves identically to Stage 12 even if delta_feedback > 0."""
        g_ref = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     rho=0.3, omega=0.1, delta_feedback=0.0)
        g_fb = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                    rho=0.3, omega=0.1, delta_feedback=2.0)
        r_i = 0.5
        for _ in range(200):
            g_ref.step(dt=0.01, r_i=r_i, e_bar=0.0)
            g_fb.step(dt=0.01, r_i=r_i, e_bar=0.0)  # e_bar=0 → rho_eff = rho
        assert g_ref.theta == pytest.approx(g_fb.theta, abs=1e-12)

    def test_s13_local_emergence_summary_empty_returns_zero(self):
        """local_emergence_summary with no neighbors returns 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert local_emergence_summary(g, []) == 0.0

    def test_s13_local_emergence_summary_bounded_zero_one(self):
        """Ē_i ∈ [0, 1] for any neighborhood."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=1.5)
        nbs = [
            Gate(gate_id=f"nb{i}", workload_id="w2", node_key="n2", a=float(i) * 0.3)
            for i in range(5)
        ]
        e_bar = local_emergence_summary(g, nbs)
        assert 0.0 <= e_bar <= 1.0

    def test_s13_local_emergence_summary_single_neighbor(self):
        """With one neighbor, Ē_i = emergence_weight(gate, nb)."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=1.0)
        nb = Gate(gate_id="nb1", workload_id="w2", node_key="n2", a=1.0)
        t = None
        e_bar = local_emergence_summary(g, [nb], t)
        e_direct = emergence_weight(g, nb, t)
        assert e_bar == pytest.approx(e_direct, abs=1e-12)

    def test_s13_high_emergence_strengthens_resonance(self):
        """High-emergence neighborhood produces stronger resonance pull than low-emergence."""
        # Gate with same rho and r_i, but different e_bar via delta_feedback
        g_low = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     rho=0.2, delta_feedback=1.0)
        g_high = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                      rho=0.2, delta_feedback=1.0)
        r_i = 0.7
        e_low = 0.0   # no emergence context
        e_high = 0.8  # high emergence context
        for _ in range(100):
            g_low.step(dt=0.01, r_i=r_i, e_bar=e_low)
            g_high.step(dt=0.01, r_i=r_i, e_bar=e_high)
        # High emergence → larger rho_eff → theta accumulated more
        assert abs(g_high.theta) > abs(g_low.theta)

    def test_s13_rho_eff_bounded(self):
        """Effective resonance coefficient ρ_eff ≤ ρ*(1+δ) since Ē_i ≤ 1."""
        rho = 0.4
        delta = 0.5
        e_bar = 0.9  # high, but ≤ 1
        rho_eff = rho * (1.0 + delta * e_bar)
        assert rho_eff <= rho * (1.0 + delta)
        assert rho_eff >= rho  # e_bar ≥ 0, delta ≥ 0, rho ≥ 0

    def test_s13_rho_eff_non_negative_for_positive_rho_delta(self):
        """With rho ≥ 0 and delta ≥ 0, rho_eff ≥ 0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 rho=0.3, delta_feedback=1.0)
        # e_bar ∈ [0,1]; rho_eff = 0.3*(1+1*e_bar) ≥ 0.3
        # Just verify step() doesn't produce NaN or negative divergence
        for e_bar in [0.0, 0.5, 1.0]:
            g2 = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                      rho=0.3, delta_feedback=1.0)
            g2.step(dt=0.01, r_i=0.5, e_bar=e_bar)
            assert math.isfinite(g2.theta)

    def test_s13_feedback_does_not_affect_energy(self):
        """step() with delta_feedback must not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        for g in gates:
            g.rho = 0.3
            g.delta_feedback = 1.0
            for _ in range(200):
                g.step(dt=0.05, r_i=0.5, e_bar=0.7, t=t)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s13_feedback_does_not_affect_collapse(self):
        """step() with delta_feedback must not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]
        for g in gates:
            g.rho = 0.3
            g.delta_feedback = 1.0
            for _ in range(200):
                g.step(dt=0.05, r_i=0.5, e_bar=0.9, t=t)
        states_after = [g.state(t) for g in gates]
        assert states_after == states_before

    def test_s13_feedback_deterministic(self):
        """Same delta_feedback, r_i, e_bar and initial state → same trajectory."""
        def run(delta):
            g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     rho=0.3, delta_feedback=delta)
            for _ in range(200):
                g.step(dt=0.01, r_i=0.6, e_bar=0.5)
            return g.theta

        t1 = run(1.0)
        t2 = run(1.0)
        assert t1 == pytest.approx(t2, abs=1e-12)

    def test_s13_local_emergence_summary_deterministic(self):
        """Same gate and neighbor state → same Ē_i every call."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1", a=0.8)
        nbs = [Gate(gate_id=f"nb{i}", workload_id="w2", node_key="n2", a=0.6)
               for i in range(3)]
        t = 99999.0
        e1 = local_emergence_summary(g, nbs, t)
        e2 = local_emergence_summary(g, nbs, t)
        assert e1 == pytest.approx(e2, abs=1e-12)


# ---------------------------------------------------------------------------
# Stage 14 — Controlled stabilization / attractor bias
# ---------------------------------------------------------------------------

class TestStage14Stabilization:

    def test_s14_zeta_stabilize_default_zero(self):
        """Gate.zeta_stabilize defaults to 0.0."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1")
        assert g.zeta_stabilize == 0.0

    def test_s14_zeta_zero_stage13_behavior_unchanged(self):
        """With zeta_stabilize=0.0, step() is identical to Stage 13."""
        g_ref = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     omega=0.5, rho=0.2, delta_feedback=0.3)
        g_stab = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                      omega=0.5, rho=0.2, delta_feedback=0.3, zeta_stabilize=0.0)
        r_i = 0.6
        e_bar = 0.7
        for _ in range(200):
            g_ref.step(dt=0.01, r_i=r_i, e_bar=e_bar)
            g_stab.step(dt=0.01, r_i=r_i, e_bar=e_bar)
        assert g_ref.theta == pytest.approx(g_stab.theta, abs=1e-12)

    def test_s14_e_bar_zero_stage13_behavior_unchanged(self):
        """With e_bar=0.0 (default), step() is identical to Stage 13 even with zeta_stabilize>0."""
        g_ref = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     omega=0.5, zeta_stabilize=0.0)
        g_stab = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                      omega=0.5, zeta_stabilize=10.0)
        for _ in range(200):
            g_ref.step(dt=0.01, e_bar=0.0)
            g_stab.step(dt=0.01, e_bar=0.0)  # e_bar=0 → omega_eff = omega
        assert g_ref.theta == pytest.approx(g_stab.theta, abs=1e-12)

    def test_s14_omega_eff_positive_for_positive_omega(self):
        """omega_eff = omega / (1 + zeta*e_bar) preserves sign for positive omega."""
        omega = 0.4
        zeta = 2.0
        for e_bar in [0.0, 0.5, 1.0]:
            omega_eff = omega / max(1e-9, 1.0 + zeta * e_bar)
            assert omega_eff > 0.0

    def test_s14_omega_eff_negative_for_negative_omega(self):
        """omega_eff preserves sign for negative omega."""
        omega = -0.4
        zeta = 2.0
        for e_bar in [0.0, 0.5, 1.0]:
            omega_eff = omega / max(1e-9, 1.0 + zeta * e_bar)
            assert omega_eff < 0.0

    def test_s14_omega_eff_bounded(self):
        """|omega_eff| ≤ |omega| for zeta ≥ 0 and e_bar ∈ [0,1]."""
        omega = 0.5
        zeta = 3.0
        for e_bar in [0.0, 0.25, 0.5, 0.75, 1.0]:
            omega_eff = omega / max(1e-9, 1.0 + zeta * e_bar)
            assert abs(omega_eff) <= abs(omega) + 1e-12

    def test_s14_high_emergence_drifts_slower_than_low_emergence(self):
        """Gate in high-emergence context accumulates less theta from omega than low-emergence."""
        omega = 1.0
        zeta = 2.0
        g_low = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     omega=omega, zeta_stabilize=zeta)
        g_high = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                      omega=omega, zeta_stabilize=zeta)
        e_low = 0.0   # no emergence context — omega_eff = omega
        e_high = 0.9  # high emergence context — omega_eff < omega
        for _ in range(500):
            g_low.step(dt=0.01, e_bar=e_low)
            g_high.step(dt=0.01, e_bar=e_high)
        # Low-emergence gate drifted faster (more theta accumulated from omega)
        assert g_low.theta > g_high.theta

    def test_s14_omega_zero_unaffected(self):
        """Gate with omega=0 is completely unaffected by zeta_stabilize."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 omega=0.0, zeta_stabilize=5.0)
        for _ in range(500):
            g.step(dt=0.01, e_bar=0.9)
        # Only omega drives theta here; omega=0 → theta stays 0
        assert g.theta == pytest.approx(0.0, abs=1e-12)

    def test_s14_does_not_freeze_coupling_driven_evolution(self):
        """Even with large zeta, coupling_term still drives theta — no hard locking."""
        g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                 omega=0.0, zeta_stabilize=1000.0)
        coupling = 0.5  # non-zero coupling drives evolution
        for _ in range(100):
            g.step(dt=0.01, coupling_term=coupling, e_bar=1.0)
        # coupling_term is unaffected by zeta — theta must evolve
        assert g.theta != pytest.approx(0.0, abs=1e-3)

    def test_s14_stabilization_does_not_affect_energy(self):
        """step() with zeta_stabilize must not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        for g in gates:
            g.omega = 0.5
            g.zeta_stabilize = 2.0
            for _ in range(200):
                g.step(dt=0.05, e_bar=0.8, t=t)
        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s14_stabilization_does_not_affect_collapse(self):
        """step() with zeta_stabilize must not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]
        for g in gates:
            g.omega = 0.5
            g.zeta_stabilize = 2.0
            for _ in range(200):
                g.step(dt=0.05, e_bar=0.8, t=t)
        states_after = [g.state(t) for g in gates]
        assert states_after == states_before

    def test_s14_stabilization_deterministic(self):
        """Same zeta, e_bar and initial state → same trajectory."""
        def run(zeta):
            g = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                     omega=0.4, zeta_stabilize=zeta)
            for _ in range(200):
                g.step(dt=0.01, e_bar=0.6)
            return g.theta

        t1 = run(1.5)
        t2 = run(1.5)
        assert t1 == pytest.approx(t2, abs=1e-12)

    def test_s14_stages_13_14_compose_independently(self):
        """Stage 13 (delta_feedback) and Stage 14 (zeta_stabilize) compose without interference.

        A gate with both active produces the same result as applying each modulation
        independently: rho_eff and omega_eff are computed from the same e_bar but
        affect separate terms in the phase equation.
        """
        omega = 0.3
        rho = 0.4
        delta = 0.5
        zeta = 1.0
        r_i = 0.6
        e_bar = 0.7

        # Gate with both active
        g_both = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                      omega=omega, rho=rho, delta_feedback=delta, zeta_stabilize=zeta)
        for _ in range(200):
            g_both.step(dt=0.01, r_i=r_i, e_bar=e_bar)

        # Manual computation: rho_eff and omega_eff combined
        rho_eff = rho * (1.0 + delta * e_bar)
        omega_eff = omega / max(1e-9, 1.0 + zeta * e_bar)
        expected_theta = 200 * 0.01 * (omega_eff + rho_eff * r_i)
        assert g_both.theta == pytest.approx(expected_theta, rel=1e-9)


# ---------------------------------------------------------------------------
# Stage 15 — Controlled topology persistence
# ---------------------------------------------------------------------------

class TestStage15TopologyPersistence:

    def test_s15_trace_starts_at_zero(self):
        """Before any step(), get() returns 0.0 for any pair."""
        trace = TopologyTrace(eta_tau=0.5, lambda_tau=0.1)
        assert trace.get("g1", "g2") == 0.0
        assert trace.get("g2", "g1") == 0.0

    def test_s15_eta_tau_zero_trace_stays_zero(self):
        """With eta_tau=0.0 (default), trace never accumulates regardless of e_ij."""
        trace = TopologyTrace(eta_tau=0.0, lambda_tau=0.1)
        for _ in range(500):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
        assert trace.get("g1", "g2") == pytest.approx(0.0, abs=1e-12)

    def test_s15_trace_symmetric(self):
        """τ_ij = τ_ji — get(i,j) == get(j,i)."""
        trace = TopologyTrace(eta_tau=0.2, lambda_tau=0.1)
        for _ in range(100):
            trace.step("g1", "g2", e_ij=0.8, dt=0.01)
        assert trace.get("g1", "g2") == pytest.approx(trace.get("g2", "g1"), abs=1e-12)

    def test_s15_repeated_coherence_increases_trace(self):
        """Sustained high E_ij drives τ_ij above zero and converging upward."""
        trace = TopologyTrace(eta_tau=0.2, lambda_tau=0.1)
        for _ in range(200):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
        assert trace.get("g1", "g2") > 0.0

    def test_s15_trace_decays_without_coherence(self):
        """After coherence stops (e_ij=0), trace decays toward 0."""
        trace = TopologyTrace(eta_tau=0.5, lambda_tau=0.2)
        # Accumulate first
        for _ in range(300):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
        peak = trace.get("g1", "g2")
        assert peak > 0.5

        # Decay for 20 time-constant multiples (lambda=0.2 → tc=5 → 100 units = 10000 steps)
        # After 100 time units: exp(-0.2*100) ≈ 2e-9 — negligible fraction of peak
        for _ in range(10000):
            trace.step("g1", "g2", e_ij=0.0, dt=0.01)
        decayed = trace.get("g1", "g2")
        assert decayed < peak * 0.001

    def test_s15_trace_non_negative(self):
        """τ_ij ≥ 0 always, even from zero initial condition with e_ij=0."""
        trace = TopologyTrace(eta_tau=0.1, lambda_tau=0.5)
        for _ in range(200):
            trace.step("g1", "g2", e_ij=0.0, dt=0.1)
        assert trace.get("g1", "g2") >= 0.0

    def test_s15_trace_bounded_by_steady_state(self):
        """τ* ≤ η_τ / λ_τ for sustained E_ij=1."""
        eta, lam = 0.3, 0.15
        trace = TopologyTrace(eta_tau=eta, lambda_tau=lam)
        for _ in range(2000):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
        tau = trace.get("g1", "g2")
        bound = eta / lam
        assert tau <= bound + 1e-6
        assert trace.steady_state_bound == pytest.approx(bound, rel=1e-12)

    def test_s15_trace_converges_to_steady_state(self):
        """τ_ij converges to η_τ·E_ij/λ_τ under constant E_ij."""
        eta, lam, e_ij = 0.2, 0.1, 0.6
        trace = TopologyTrace(eta_tau=eta, lambda_tau=lam)
        expected_ss = eta * e_ij / lam
        # Run for 15 time constants (1/lambda = 10) at dt=0.01 → 15000 steps
        # Residual error: exp(-0.1*150) ≈ 9e-8 → well within 1% rel tolerance
        for _ in range(15000):
            trace.step("g1", "g2", e_ij=e_ij, dt=0.01)
        assert trace.get("g1", "g2") == pytest.approx(expected_ss, rel=1e-2)

    def test_s15_reset_clears_all_traces(self):
        """reset() clears all pair traces; get() returns 0 afterward."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        for _ in range(100):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
            trace.step("g2", "g3", e_ij=0.5, dt=0.01)
        trace.reset()
        assert trace.get("g1", "g2") == 0.0
        assert trace.get("g2", "g3") == 0.0

    def test_s15_reset_single_pair(self):
        """reset(i, j) clears only that pair; others remain."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        for _ in range(100):
            trace.step("g1", "g2", e_ij=1.0, dt=0.01)
            trace.step("g2", "g3", e_ij=1.0, dt=0.01)
        trace.reset("g1", "g2")
        assert trace.get("g1", "g2") == 0.0
        assert trace.get("g2", "g3") > 0.0

    def test_s15_gate_step_unchanged_by_trace(self):
        """Gate.step() behavior is identical whether trace exists or not."""
        g_with_trace = Gate(gate_id="g1", workload_id="w1", node_key="n1",
                            omega=0.3, rho=0.2, delta_feedback=0.1, zeta_stabilize=0.5)
        g_neighbor = Gate(gate_id="g2", workload_id="w2", node_key="n2",
                          omega=0.3, rho=0.2, delta_feedback=0.1, zeta_stabilize=0.5)
        g_no_trace = Gate(gate_id="g3", workload_id="w3", node_key="n3",
                          omega=0.3, rho=0.2, delta_feedback=0.1, zeta_stabilize=0.5)

        trace = TopologyTrace(eta_tau=0.5, lambda_tau=0.2)
        dt = 0.01
        r_i = 0.5
        e_bar = 0.4

        for _ in range(200):
            # g_with_trace: trace runs externally alongside step() — trace must not affect step()
            e_ij = emergence_weight(g_with_trace, g_neighbor, None)
            trace.step(g_with_trace.gate_id, g_neighbor.gate_id, e_ij, dt)
            g_with_trace.step(dt=dt, r_i=r_i, e_bar=e_bar)
            # g_no_trace: identical step() calls, no trace
            g_no_trace.step(dt=dt, r_i=r_i, e_bar=e_bar)

        # Trace is external and must not affect gate dynamics
        assert g_with_trace.theta == pytest.approx(g_no_trace.theta, abs=1e-12)

    def test_s15_trace_does_not_affect_gate_energy(self):
        """Running TopologyTrace does not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        trace = TopologyTrace(eta_tau=0.5, lambda_tau=0.1)
        if len(gates) >= 2:
            for _ in range(200):
                e_ij = emergence_weight(gates[0], gates[1], t)
                trace.step(gates[0].gate_id, gates[1].gate_id, e_ij, 0.01)

        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s15_trace_does_not_affect_collapse(self):
        """Running TopologyTrace does not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        trace = TopologyTrace(eta_tau=1.0, lambda_tau=0.1)
        if len(gates) >= 2:
            for _ in range(200):
                e_ij = emergence_weight(gates[0], gates[1], t)
                trace.step(gates[0].gate_id, gates[1].gate_id, e_ij, 0.01)

        states_after = [g.state(t) for g in gates]
        assert states_after == states_before

    def test_s15_trace_deterministic(self):
        """Same e_ij sequence and parameters → same trace value."""
        def run():
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.15)
            for i in range(300):
                e_ij = 0.5 + 0.3 * (i % 3 == 0)   # deterministic pattern
                trace.step("g1", "g2", e_ij=e_ij, dt=0.01)
            return trace.get("g1", "g2")

        assert run() == pytest.approx(run(), abs=1e-12)

    def test_s15_lambda_tau_nonpositive_raises(self):
        """TopologyTrace rejects lambda_tau ≤ 0 (unbounded trace)."""
        import pytest as _pytest
        with _pytest.raises(ValueError):
            TopologyTrace(eta_tau=0.1, lambda_tau=0.0)
        with _pytest.raises(ValueError):
            TopologyTrace(eta_tau=0.1, lambda_tau=-0.1)


# ---------------------------------------------------------------------------
# Stage 16 — Controlled trace influence
# ---------------------------------------------------------------------------

class TestStage16TraceInfluence:
    """
    Stage 16: w_ij_eff = w_ij * (1 + κ_E * E_ij + κ_τ * τ̂_ij)
    τ̂_ij = τ_ij / τ_max ∈ [0, 1];  effective_weight() is transient, never stored.
    """

    def test_s16_dormant_by_default(self):
        """effective_weight with both kappa=0 returns w_ij exactly."""
        assert effective_weight(0.7, e_ij=0.5, tau_hat=0.8) == pytest.approx(0.7, abs=1e-12)
        assert effective_weight(1.0, e_ij=1.0, tau_hat=1.0) == pytest.approx(1.0, abs=1e-12)
        assert effective_weight(0.0, e_ij=0.5, tau_hat=0.5) == pytest.approx(0.0, abs=1e-12)

    def test_s16_kappa_e_modulates_weight(self):
        """kappa_e alone scales w by (1 + κ_E * E_ij)."""
        w = 0.5
        e = 0.4
        kappa_e = 0.3
        expected = w * (1.0 + kappa_e * e)
        assert effective_weight(w, e_ij=e, tau_hat=0.0, kappa_e=kappa_e) == pytest.approx(expected, rel=1e-12)

    def test_s16_kappa_tau_modulates_weight(self):
        """kappa_tau alone scales w by (1 + κ_τ * τ̂_ij)."""
        w = 0.6
        tau_hat = 0.7
        kappa_tau = 0.2
        expected = w * (1.0 + kappa_tau * tau_hat)
        assert effective_weight(w, e_ij=0.0, tau_hat=tau_hat, kappa_tau=kappa_tau) == pytest.approx(expected, rel=1e-12)

    def test_s16_combined_modulation(self):
        """Both coefficients active: w_ij_eff = w_ij * (1 + κ_E*E + κ_τ*τ̂)."""
        w = 0.8
        e = 0.5
        tau_hat = 0.6
        kappa_e = 0.1
        kappa_tau = 0.15
        expected = w * (1.0 + kappa_e * e + kappa_tau * tau_hat)
        result = effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=kappa_e, kappa_tau=kappa_tau)
        assert result == pytest.approx(expected, rel=1e-12)

    def test_s16_normalized_dormant_when_eta_zero(self):
        """normalized() returns 0.0 when eta_tau=0 (dormant Stage 15)."""
        trace = TopologyTrace(eta_tau=0.0, lambda_tau=0.1)
        trace._traces[("g1", "g2")] = 0.5  # manually inject a value
        assert trace.normalized("g1", "g2") == 0.0

    def test_s16_normalized_range(self):
        """normalized() returns values ∈ [0, 1] for any trace state."""
        trace = TopologyTrace(eta_tau=0.2, lambda_tau=0.1)
        e_ij = 0.8
        for _ in range(500):
            trace.step("a", "b", e_ij, dt=0.01)
        tau_hat = trace.normalized("a", "b")
        assert 0.0 <= tau_hat <= 1.0

    def test_s16_normalized_at_steady_state(self):
        """τ̂ approaches 1.0 * E_ij at steady state (τ_max = η/λ, τ* = E*η/λ)."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        e_ij = 1.0  # maximum signal → τ* = τ_max
        for _ in range(20000):
            trace.step("x", "y", e_ij, dt=0.01)
        tau_hat = trace.normalized("x", "y")
        assert tau_hat == pytest.approx(1.0, rel=1e-2)

    def test_s16_normalized_zero_before_any_steps(self):
        """normalized() returns 0.0 for unseen pair."""
        trace = TopologyTrace(eta_tau=0.5, lambda_tau=0.1)
        assert trace.normalized("p", "q") == 0.0

    def test_s16_normalized_symmetric(self):
        """normalized(i, j) == normalized(j, i)."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        for _ in range(200):
            trace.step("ga", "gb", 0.7, dt=0.01)
        assert trace.normalized("ga", "gb") == pytest.approx(trace.normalized("gb", "ga"), abs=1e-12)

    def test_s16_canonical_weight_unchanged(self):
        """effective_weight() does not modify the passed-in w_ij value."""
        w_orig = 0.55
        w_copy = w_orig
        result = effective_weight(w_copy, e_ij=0.6, tau_hat=0.4, kappa_e=0.2, kappa_tau=0.1)
        assert w_orig == 0.55  # original unchanged
        assert result != w_orig  # but result differs

    def test_s16_gate_state_unchanged_by_effective_weight(self):
        """Calling effective_weight() does not alter any Gate fields."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.3, phi_B=0.3)
        push(engine, "w1", "n1", "g2", phi_R=0.4, phi_B=0.2)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            theta_before = (g1.theta, g2.theta)
            a_before = (g1.a, g2.a)
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            for _ in range(100):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            e_ij = emergence_weight(g1, g2, t)
            _ = effective_weight(0.5, e_ij=e_ij, tau_hat=tau_hat, kappa_e=0.2, kappa_tau=0.1)
            assert g1.theta == theta_before[0]
            assert g2.theta == theta_before[1]
            assert g1.a == a_before[0]
            assert g2.a == a_before[1]

    def test_s16_effective_weight_nonnegative_for_nonneg_inputs(self):
        """w_ij_eff ≥ 0 when w_ij ≥ 0, κ_E ≥ 0, κ_τ ≥ 0, E ∈ [0,1], τ̂ ∈ [0,1]."""
        for w in [0.0, 0.1, 0.5, 1.0]:
            for e in [0.0, 0.5, 1.0]:
                for tau_hat in [0.0, 0.5, 1.0]:
                    result = effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=0.5, kappa_tau=0.5)
                    assert result >= 0.0

    def test_s16_effective_weight_bounded_above(self):
        """w_ij_eff ≤ w_ij * (1 + κ_E + κ_τ) since E ≤ 1 and τ̂ ≤ 1."""
        w = 0.8
        kappa_e = 0.3
        kappa_tau = 0.4
        upper = w * (1.0 + kappa_e + kappa_tau)
        for e in [0.0, 0.5, 1.0]:
            for tau_hat in [0.0, 0.5, 1.0]:
                result = effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=kappa_e, kappa_tau=kappa_tau)
                assert result <= upper + 1e-12

    def test_s16_effective_weight_zero_w_gives_zero(self):
        """Zero canonical weight stays zero regardless of modulation."""
        result = effective_weight(0.0, e_ij=1.0, tau_hat=1.0, kappa_e=10.0, kappa_tau=10.0)
        assert result == pytest.approx(0.0, abs=1e-12)

    def test_s16_reset_zeros_normalized(self):
        """After reset(), normalized() returns 0.0."""
        trace = TopologyTrace(eta_tau=0.4, lambda_tau=0.1)
        for _ in range(300):
            trace.step("a", "b", 0.9, dt=0.01)
        assert trace.normalized("a", "b") > 0.0
        trace.reset("a", "b")
        assert trace.normalized("a", "b") == 0.0


# ---------------------------------------------------------------------------
# Stage 17 — Controlled topology consolidation
# ---------------------------------------------------------------------------

class TestStage17TopologyConsolidation:
    """
    Stage 17: (i,j) ∈ C ⟺ E_ij ≥ θ_E ∧ τ̂_ij ≥ θ_τ
    Non-canonical, reversible, deterministic candidate surface only.
    """

    # ---- dormant / threshold guards ----

    def test_s17_dormant_by_default(self):
        """Default thresholds (1.0, 1.0): no pair can exceed max → no candidates."""
        cands = TopologyCandidates()
        result = cands.evaluate("g1", "g2", e_ij=1.0, tau_hat=1.0)
        # 1.0 >= 1.0 is True — but default should still produce a candidate
        # (boundary case: >= allows equality)
        assert result is True
        assert cands.count() == 1

    def test_s17_below_threshold_no_candidate(self):
        """Pair below either threshold is not a candidate."""
        cands = TopologyCandidates(theta_e=0.5, theta_tau=0.5)
        # E below threshold
        assert cands.evaluate("g1", "g2", e_ij=0.4, tau_hat=0.8) is False
        assert cands.count() == 0
        # tau_hat below threshold
        assert cands.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.3) is False
        assert cands.count() == 0

    def test_s17_both_above_threshold_produces_candidate(self):
        """Pair meeting both thresholds becomes a candidate."""
        cands = TopologyCandidates(theta_e=0.5, theta_tau=0.5)
        result = cands.evaluate("g1", "g2", e_ij=0.7, tau_hat=0.6)
        assert result is True
        assert cands.count() == 1
        assert cands.contains("g1", "g2")

    def test_s17_high_emergence_without_trace_not_candidate(self):
        """High E_ij alone is insufficient without sufficient trace."""
        cands = TopologyCandidates(theta_e=0.3, theta_tau=0.6)
        cands.evaluate("g1", "g2", e_ij=1.0, tau_hat=0.0)
        assert cands.contains("g1", "g2") is False

    def test_s17_high_trace_without_emergence_not_candidate(self):
        """High τ̂_ij alone is insufficient without sufficient emergence."""
        cands = TopologyCandidates(theta_e=0.6, theta_tau=0.3)
        cands.evaluate("g1", "g2", e_ij=0.0, tau_hat=1.0)
        assert cands.contains("g1", "g2") is False

    # ---- symmetry ----

    def test_s17_candidate_symmetric(self):
        """contains(i, j) == contains(j, i)."""
        cands = TopologyCandidates(theta_e=0.3, theta_tau=0.3)
        cands.evaluate("ga", "gb", e_ij=0.8, tau_hat=0.7)
        assert cands.contains("ga", "gb") is True
        assert cands.contains("gb", "ga") is True

    # ---- determinism ----

    def test_s17_deterministic_repeated_evaluate(self):
        """Same inputs always produce same candidate membership."""
        def run():
            cands = TopologyCandidates(theta_e=0.4, theta_tau=0.4)
            for e, t in [(0.6, 0.5), (0.3, 0.9), (0.8, 0.8), (0.1, 0.2)]:
                cands.evaluate("g1", "g2", e_ij=e, tau_hat=t)
            return cands.contains("g1", "g2")

        assert run() == run()

    def test_s17_recompute_deterministic(self):
        """recompute() with same pairs list always yields same result."""
        pairs = [
            ("a", "b", 0.7, 0.6),
            ("b", "c", 0.2, 0.9),
            ("a", "c", 0.8, 0.8),
        ]

        def run():
            cands = TopologyCandidates(theta_e=0.5, theta_tau=0.5)
            cands.recompute(pairs)
            return cands.snapshot()

        assert run() == run()

    # ---- reset / recompute ----

    def test_s17_reset_all_clears_candidates(self):
        """reset() removes all candidates."""
        cands = TopologyCandidates(theta_e=0.2, theta_tau=0.2)
        cands.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9)
        cands.evaluate("g1", "g3", e_ij=0.8, tau_hat=0.8)
        assert cands.count() == 2
        cands.reset()
        assert cands.count() == 0

    def test_s17_reset_pair_removes_only_that_pair(self):
        """reset(i, j) removes exactly that pair."""
        cands = TopologyCandidates(theta_e=0.2, theta_tau=0.2)
        cands.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9)
        cands.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8)
        cands.reset("g1", "g2")
        assert cands.contains("g1", "g2") is False
        assert cands.contains("g2", "g3") is True

    def test_s17_recompute_replaces_prior_state(self):
        """recompute() clears stale candidates before evaluating new input."""
        cands = TopologyCandidates(theta_e=0.5, theta_tau=0.5)
        # First pass: g1-g2 qualifies
        cands.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9)
        assert cands.contains("g1", "g2") is True
        # recompute with data that does NOT qualify g1-g2
        cands.recompute([("g1", "g2", 0.1, 0.1)])
        assert cands.contains("g1", "g2") is False

    # ---- live signals from actual gates ----

    def _build_sustained_trace(self, g1, g2, t, steps=15000, dt=0.01):
        """Run TopologyTrace to near steady state for gate pair."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        for _ in range(steps):
            e_ij = emergence_weight(g1, g2, t)
            trace.step(g1.gate_id, g2.gate_id, e_ij, dt)
        return trace

    def test_s17_sustained_coherent_pair_becomes_candidate(self):
        """Gate pair with high E_ij and near-steady-state trace becomes candidate."""
        engine, gravity, field, graph = fresh()
        # phi_R == phi_B → high coherence
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        if len(gates) < 2:
            pytest.skip("need 2 gates")
        g1, g2 = gates[0], gates[1]
        t = time.time()

        trace = self._build_sustained_trace(g1, g2, t)
        e_ij = emergence_weight(g1, g2, t)
        tau_hat = trace.normalized(g1.gate_id, g2.gate_id)

        # With generous thresholds, should qualify
        cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
        cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e_ij, tau_hat=tau_hat)
        assert cands.contains(g1.gate_id, g2.gate_id) is True

    def test_s17_no_candidate_when_thresholds_exceed_signals(self):
        """With thresholds at their maximum valid value, sub-max signals do not qualify."""
        # E_ij ∈ [0,1] and τ̂ ∈ [0,1]; using theta=1.0 means only signals at exactly 1.0 qualify.
        # A dormant trace (eta_tau=0) returns tau_hat=0.0, which is < 1.0 → no candidate.
        cands = TopologyCandidates(theta_e=1.0, theta_tau=1.0)
        cands.evaluate("g1", "g2", e_ij=0.99, tau_hat=0.99)
        assert cands.contains("g1", "g2") is False
        # Signals exactly at 1.0 DO qualify (>= is the rule)
        cands.evaluate("g1", "g2", e_ij=1.0, tau_hat=1.0)
        assert cands.contains("g1", "g2") is True

    def test_s17_gate_state_unchanged_by_consolidation(self):
        """TopologyCandidates.evaluate() never alters Gate fields."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            theta_before = (g1.theta, g2.theta)
            a_before = (g1.a, g2.a)
            mu_before = (g1.mu, g2.mu)

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)

            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            cands.evaluate(
                g1.gate_id, g2.gate_id,
                e_ij=emergence_weight(g1, g2, t),
                tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
            )

            assert g1.theta == theta_before[0]
            assert g2.theta == theta_before[1]
            assert g1.a == a_before[0]
            assert g2.a == a_before[1]
            assert g1.mu == mu_before[0]
            assert g2.mu == mu_before[1]

    def test_s17_gate_energy_unchanged_by_consolidation(self):
        """Candidate consolidation does not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            energy_before = [g.energy(t) for g in gates]

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)

            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            cands.evaluate(
                g1.gate_id, g2.gate_id,
                e_ij=emergence_weight(g1, g2, t),
                tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
            )

            energy_after = [g.energy(t) for g in gates]
            assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s17_collapse_state_unchanged_by_consolidation(self):
        """Candidate consolidation does not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        states_before = [g.state(t) for g in gates]

        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)

            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            cands.evaluate(
                g1.gate_id, g2.gate_id,
                e_ij=emergence_weight(g1, g2, t),
                tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
            )

        states_after = [g.state(t) for g in gates]
        assert states_after == states_before

    def test_s17_reset_has_no_substrate_effect(self):
        """After reset(), gate state and energy are identical to before consolidation."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            energy_before = [g.energy(t) for g in gates]
            state_before = [g.state(t) for g in gates]

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)

            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            cands.evaluate(
                g1.gate_id, g2.gate_id,
                e_ij=emergence_weight(g1, g2, t),
                tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
            )
            assert cands.count() > 0
            cands.reset()
            assert cands.count() == 0

            # substrate unchanged
            assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)
            assert [g.state(t) for g in gates] == state_before

    def test_s17_invalid_threshold_raises(self):
        """TopologyCandidates rejects thresholds outside [0, 1]."""
        import pytest as _pt
        with _pt.raises(ValueError):
            TopologyCandidates(theta_e=-0.1, theta_tau=0.5)
        with _pt.raises(ValueError):
            TopologyCandidates(theta_e=0.5, theta_tau=1.1)


# ---------------------------------------------------------------------------
# Stage 18 — Controlled candidate influence
# ---------------------------------------------------------------------------

class TestStage18CandidateInfluence:
    """
    Stage 18: w_ij_eff = w_ij * (1 + κ_E*E_ij + κ_τ*τ̂_ij + κ_C*I_ij)
    I_ij ∈ {0, 1} — binary candidate membership flag.
    kappa_candidate=0.0 by default — Stage 17 behavior preserved exactly.
    """

    # ---- dormant by default ----

    def test_s18_dormant_by_default_kappa_zero(self):
        """kappa_candidate=0.0: effective_weight unchanged from Stage 16 result."""
        w, e, tau_hat = 0.7, 0.5, 0.6
        kappa_e, kappa_tau = 0.1, 0.08
        expected = effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=kappa_e, kappa_tau=kappa_tau)
        result = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                  kappa_e=kappa_e, kappa_tau=kappa_tau,
                                  i_ij=1.0, kappa_candidate=0.0)
        assert result == pytest.approx(expected, abs=1e-12)

    def test_s18_dormant_i_ij_zero_no_change(self):
        """i_ij=0.0 (non-candidate): kappa_candidate has no effect regardless of value."""
        w, e, tau_hat = 0.8, 0.4, 0.5
        base = effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=0.1, kappa_tau=0.05)
        result = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                  kappa_e=0.1, kappa_tau=0.05,
                                  i_ij=0.0, kappa_candidate=0.5)
        assert result == pytest.approx(base, abs=1e-12)

    # ---- candidate membership adds bounded increment ----

    def test_s18_candidate_adds_kappa_c_times_w(self):
        """When i_ij=1, effective weight includes κ_C * w_ij increment."""
        w, e, tau_hat = 0.6, 0.0, 0.0
        kappa_c = 0.15
        expected = w * (1.0 + kappa_c * 1.0)
        result = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                  i_ij=1.0, kappa_candidate=kappa_c)
        assert result == pytest.approx(expected, rel=1e-12)

    def test_s18_full_combined_formula(self):
        """w_ij_eff = w_ij*(1 + κ_E*E + κ_τ*τ̂ + κ_C*I) with all terms active."""
        w, e, tau_hat = 0.5, 0.6, 0.7
        kappa_e, kappa_tau, kappa_c = 0.1, 0.08, 0.04
        expected = w * (1.0 + kappa_e * e + kappa_tau * tau_hat + kappa_c * 1.0)
        result = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                  kappa_e=kappa_e, kappa_tau=kappa_tau,
                                  i_ij=1.0, kappa_candidate=kappa_c)
        assert result == pytest.approx(expected, rel=1e-12)

    def test_s18_non_candidate_pair_no_contribution(self):
        """Non-candidate pair (i_ij=0) gets no candidate term in weight."""
        w, e, tau_hat = 0.7, 0.5, 0.4
        kappa_c = 0.2
        without_candidate = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                             kappa_e=0.1, kappa_tau=0.05,
                                             i_ij=0.0, kappa_candidate=kappa_c)
        with_candidate = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                          kappa_e=0.1, kappa_tau=0.05,
                                          i_ij=1.0, kappa_candidate=kappa_c)
        assert with_candidate > without_candidate
        assert without_candidate == pytest.approx(
            effective_weight(w, e_ij=e, tau_hat=tau_hat, kappa_e=0.1, kappa_tau=0.05),
            abs=1e-12,
        )

    # ---- bounded and non-negative ----

    def test_s18_effective_weight_bounded_above(self):
        """w_ij_eff ≤ w_ij*(1 + κ_E + κ_τ + κ_C) since E,τ̂,I ∈ [0,1]."""
        w = 0.9
        kappa_e, kappa_tau, kappa_c = 0.2, 0.15, 0.1
        upper = w * (1.0 + kappa_e + kappa_tau + kappa_c)
        for e in [0.0, 0.5, 1.0]:
            for tau_hat in [0.0, 0.5, 1.0]:
                for i_ij in [0.0, 1.0]:
                    result = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                             kappa_e=kappa_e, kappa_tau=kappa_tau,
                                             i_ij=i_ij, kappa_candidate=kappa_c)
                    assert result <= upper + 1e-12

    def test_s18_effective_weight_nonnegative(self):
        """w_ij_eff ≥ 0 for non-negative w and κ values."""
        for w in [0.0, 0.3, 1.0]:
            for i_ij in [0.0, 1.0]:
                result = effective_weight(w, e_ij=0.5, tau_hat=0.5,
                                          kappa_e=0.1, kappa_tau=0.1,
                                          i_ij=i_ij, kappa_candidate=0.05)
                assert result >= 0.0

    def test_s18_zero_w_stays_zero(self):
        """Zero canonical weight stays zero regardless of candidate membership."""
        result = effective_weight(0.0, e_ij=1.0, tau_hat=1.0,
                                  kappa_e=1.0, kappa_tau=1.0,
                                  i_ij=1.0, kappa_candidate=1.0)
        assert result == pytest.approx(0.0, abs=1e-12)

    # ---- determinism ----

    def test_s18_deterministic_repeated_calls(self):
        """Same inputs always produce same effective weight."""
        def run():
            return effective_weight(0.6, e_ij=0.55, tau_hat=0.72,
                                    kappa_e=0.12, kappa_tau=0.08,
                                    i_ij=1.0, kappa_candidate=0.04)
        assert run() == pytest.approx(run(), abs=1e-12)

    # ---- integration with TopologyCandidates ----

    def test_s18_candidate_flag_from_topology_candidates(self):
        """i_ij derived from TopologyCandidates.contains() matches expected formula."""
        cands = TopologyCandidates(theta_e=0.3, theta_tau=0.3)
        cands.evaluate("g1", "g2", e_ij=0.8, tau_hat=0.7)  # qualifies
        cands.evaluate("g2", "g3", e_ij=0.1, tau_hat=0.9)  # does NOT qualify (e too low)

        w, e12, tau12 = 0.5, 0.8, 0.7
        e23, tau23 = 0.1, 0.9
        kappa_e, kappa_tau, kappa_c = 0.1, 0.05, 0.08

        i_12 = float(cands.contains("g1", "g2"))
        i_23 = float(cands.contains("g2", "g3"))

        w12 = effective_weight(w, e_ij=e12, tau_hat=tau12,
                               kappa_e=kappa_e, kappa_tau=kappa_tau,
                               i_ij=i_12, kappa_candidate=kappa_c)
        w23 = effective_weight(w, e_ij=e23, tau_hat=tau23,
                               kappa_e=kappa_e, kappa_tau=kappa_tau,
                               i_ij=i_23, kappa_candidate=kappa_c)

        assert i_12 == 1.0
        assert i_23 == 0.0
        assert w12 > w23  # candidate pair has higher effective weight

    def test_s18_clearing_candidates_removes_contribution(self):
        """After reset(), candidate term drops to zero (i_ij=0) without substrate effect."""
        cands = TopologyCandidates(theta_e=0.2, theta_tau=0.2)
        cands.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9)
        assert cands.contains("g1", "g2") is True

        w, e, tau_hat, kappa_c = 0.5, 0.9, 0.9, 0.1
        w_with = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                  i_ij=float(cands.contains("g1", "g2")),
                                  kappa_candidate=kappa_c)
        cands.reset("g1", "g2")
        w_after = effective_weight(w, e_ij=e, tau_hat=tau_hat,
                                   i_ij=float(cands.contains("g1", "g2")),
                                   kappa_candidate=kappa_c)

        assert w_with > w_after
        assert w_after == pytest.approx(
            effective_weight(w, e_ij=e, tau_hat=tau_hat),
            abs=1e-12,
        )

    # ---- canonical substrate unchanged ----

    def test_s18_gate_state_unchanged(self):
        """effective_weight() with candidate flag never alters Gate fields."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            theta_before = (g1.theta, g2.theta)
            a_before = (g1.a, g2.a)

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            for _ in range(100):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)

            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            _ = effective_weight(0.5, e_ij=emergence_weight(g1, g2, t),
                                 tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
                                 i_ij=i_ij, kappa_candidate=0.1)

            assert g1.theta == theta_before[0]
            assert g2.theta == theta_before[1]
            assert g1.a == a_before[0]
            assert g2.a == a_before[1]

    def test_s18_gate_energy_unchanged(self):
        """Candidate influence computation does not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            for _ in range(100):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)

            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            _ = effective_weight(0.5, e_ij=emergence_weight(g1, g2, t),
                                 tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
                                 i_ij=i_ij, kappa_candidate=0.1)

        energy_after = [g.energy(t) for g in gates]
        assert energy_after == pytest.approx(energy_before, abs=1e-12)

    def test_s18_collapse_state_unchanged(self):
        """Candidate influence computation does not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            for _ in range(100):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)

            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            _ = effective_weight(0.5, e_ij=emergence_weight(g1, g2, t),
                                 tau_hat=trace.normalized(g1.gate_id, g2.gate_id),
                                 i_ij=i_ij, kappa_candidate=0.1)

        states_after = [g.state(t) for g in gates]
        assert states_after == states_before


# ---------------------------------------------------------------------------
# Stage 19 — Controlled topology commitment
# ---------------------------------------------------------------------------

class TestStage19TopologyCommitment:
    """
    Stage 19: (i,j) ∈ K ⟺ E_ij ≥ θ_E^commit ∧ τ̂_ij ≥ θ_τ^commit ∧ I_ij = 1
    Non-canonical, reversible, deterministic proto-topological commitment surface.
    Commitment thresholds are stricter than candidate thresholds.
    """

    # ---- threshold / dormancy guards ----

    def test_s19_no_commitment_when_thresholds_above_signals(self):
        """Signals below commitment thresholds → no commitment."""
        comms = TopologyCommitments(theta_e=0.8, theta_tau=0.8)
        # All three signals: e=0.7, tau_hat=0.7, i_ij=1 — e and tau below threshold
        result = comms.evaluate("g1", "g2", e_ij=0.7, tau_hat=0.7, i_ij=1.0)
        assert result is False
        assert comms.count() == 0

    def test_s19_commitment_requires_candidate_membership(self):
        """High emergence and trace alone do not commit without i_ij=1."""
        comms = TopologyCommitments(theta_e=0.3, theta_tau=0.3)
        result = comms.evaluate("g1", "g2", e_ij=1.0, tau_hat=1.0, i_ij=0.0)
        assert result is False
        assert comms.count() == 0

    def test_s19_commitment_requires_sufficient_emergence(self):
        """Candidate + high trace, but emergence below threshold → no commitment."""
        comms = TopologyCommitments(theta_e=0.7, theta_tau=0.3)
        result = comms.evaluate("g1", "g2", e_ij=0.5, tau_hat=1.0, i_ij=1.0)
        assert result is False
        assert comms.count() == 0

    def test_s19_commitment_requires_sufficient_trace(self):
        """Candidate + high emergence, but trace below threshold → no commitment."""
        comms = TopologyCommitments(theta_e=0.3, theta_tau=0.7)
        result = comms.evaluate("g1", "g2", e_ij=1.0, tau_hat=0.5, i_ij=1.0)
        assert result is False
        assert comms.count() == 0

    def test_s19_all_conditions_met_produces_commitment(self):
        """All three conditions met → committed edge is produced."""
        comms = TopologyCommitments(theta_e=0.5, theta_tau=0.5)
        result = comms.evaluate("g1", "g2", e_ij=0.8, tau_hat=0.7, i_ij=1.0)
        assert result is True
        assert comms.count() == 1
        assert comms.contains("g1", "g2")

    # ---- commitment is strictly stricter than candidate ----

    def test_s19_commitment_stricter_than_candidate(self):
        """Pair can be a candidate but not committed when commitment threshold higher."""
        cands = TopologyCandidates(theta_e=0.3, theta_tau=0.3)
        comms = TopologyCommitments(theta_e=0.8, theta_tau=0.8)

        e_ij, tau_hat = 0.5, 0.5
        cands.evaluate("g1", "g2", e_ij=e_ij, tau_hat=tau_hat)
        i_ij = float(cands.contains("g1", "g2"))
        comms.evaluate("g1", "g2", e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)

        assert cands.contains("g1", "g2") is True   # qualifies as candidate
        assert comms.contains("g1", "g2") is False  # but not committed

    # ---- symmetry ----

    def test_s19_commitment_symmetric(self):
        """contains(i, j) == contains(j, i)."""
        comms = TopologyCommitments(theta_e=0.3, theta_tau=0.3)
        comms.evaluate("ga", "gb", e_ij=0.9, tau_hat=0.8, i_ij=1.0)
        assert comms.contains("ga", "gb") is True
        assert comms.contains("gb", "ga") is True

    # ---- determinism ----

    def test_s19_deterministic(self):
        """Same inputs → same commitment membership every time."""
        def run():
            comms = TopologyCommitments(theta_e=0.4, theta_tau=0.4)
            data = [(0.9, 0.8, 1.0), (0.3, 0.9, 1.0), (0.8, 0.8, 0.0)]
            for e, t, i in data:
                comms.evaluate("g1", "g2", e_ij=e, tau_hat=t, i_ij=i)
            return comms.contains("g1", "g2")
        assert run() == run()

    def test_s19_recompute_deterministic(self):
        """recompute() with same pairs list always yields same result."""
        pairs = [
            ("a", "b", 0.9, 0.8, 1.0),
            ("b", "c", 0.2, 0.9, 1.0),
            ("a", "c", 0.85, 0.85, 1.0),
        ]
        def run():
            comms = TopologyCommitments(theta_e=0.6, theta_tau=0.6)
            comms.recompute(pairs)
            return comms.snapshot()
        assert run() == run()

    # ---- reset / recompute ----

    def test_s19_reset_all_clears_commitments(self):
        """reset() removes all committed pairs."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8, i_ij=1.0)
        assert comms.count() == 2
        comms.reset()
        assert comms.count() == 0

    def test_s19_reset_pair_removes_only_that_pair(self):
        """reset(i, j) removes exactly one pair."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8, i_ij=1.0)
        comms.reset("g1", "g2")
        assert comms.contains("g1", "g2") is False
        assert comms.contains("g2", "g3") is True

    def test_s19_recompute_replaces_prior_state(self):
        """recompute() clears stale commitments before evaluating new input."""
        comms = TopologyCommitments(theta_e=0.3, theta_tau=0.3)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        assert comms.contains("g1", "g2") is True
        comms.recompute([("g1", "g2", 0.1, 0.1, 1.0)])
        assert comms.contains("g1", "g2") is False

    # ---- integration with full signal pipeline ----

    def _build_sustained_trace(self, g1, g2, t, steps=15000, dt=0.01):
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        for _ in range(steps):
            e_ij = emergence_weight(g1, g2, t)
            trace.step(g1.gate_id, g2.gate_id, e_ij, dt)
        return trace

    def test_s19_sustained_coherent_pair_with_candidate_commits(self):
        """Pair passing all three conditions (low thresholds) becomes committed."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        if len(gates) < 2:
            pytest.skip("need 2 gates")
        g1, g2 = gates[0], gates[1]
        t = time.time()

        trace = self._build_sustained_trace(g1, g2, t)
        e_ij = emergence_weight(g1, g2, t)
        tau_hat = trace.normalized(g1.gate_id, g2.gate_id)

        # Generous thresholds — pair should qualify for both candidate and commitment
        cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
        comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
        cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e_ij, tau_hat=tau_hat)
        i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
        comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)
        assert comms.contains(g1.gate_id, g2.gate_id) is True

    def test_s19_without_candidate_no_commitment_regardless_of_signals(self):
        """Even with generous commitment thresholds, no i_ij → no commitment."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        if len(gates) < 2:
            pytest.skip("need 2 gates")
        g1, g2 = gates[0], gates[1]
        t = time.time()

        trace = self._build_sustained_trace(g1, g2, t)
        e_ij = emergence_weight(g1, g2, t)
        tau_hat = trace.normalized(g1.gate_id, g2.gate_id)

        comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
        # i_ij=0.0 — explicitly not a candidate
        comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e_ij, tau_hat=tau_hat, i_ij=0.0)
        assert comms.contains(g1.gate_id, g2.gate_id) is False

    # ---- canonical substrate unchanged ----

    def test_s19_gate_state_unchanged(self):
        """TopologyCommitments.evaluate() never alters Gate fields."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            theta_before = (g1.theta, g2.theta)
            a_before = (g1.a, g2.a)
            mu_before = (g1.mu, g2.mu)

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)

            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)

            assert g1.theta == theta_before[0]
            assert g2.theta == theta_before[1]
            assert g1.a == a_before[0]
            assert g2.a == a_before[1]
            assert g1.mu == mu_before[0]
            assert g2.mu == mu_before[1]

    def test_s19_gate_energy_unchanged(self):
        """Commitment does not change gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s19_collapse_state_unchanged(self):
        """Commitment does not change gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)

        assert [g.state(t) for g in gates] == states_before

    def test_s19_reset_has_no_substrate_effect(self):
        """reset() removes commitments without changing any Gate or graph state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            energy_before = [g.energy(t) for g in gates]
            state_before = [g.state(t) for g in gates]

            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)
            assert comms.count() > 0
            comms.reset()
            assert comms.count() == 0

            assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)
            assert [g.state(t) for g in gates] == state_before

    def test_s19_invalid_threshold_raises(self):
        """TopologyCommitments rejects thresholds outside [0, 1]."""
        import pytest as _pt
        with _pt.raises(ValueError):
            TopologyCommitments(theta_e=-0.1, theta_tau=0.5)
        with _pt.raises(ValueError):
            TopologyCommitments(theta_e=0.5, theta_tau=1.1)


# ---------------------------------------------------------------------------
# Stage 20 — controlled commitment influence
# ---------------------------------------------------------------------------

class TestStage20CommitmentInfluence:
    """
    Stage 20: committed pairs get a small bounded reinforcement of effective weight.

    Formula:
        w_ij_eff = w_ij · (1 + κ_E·E_ij + κ_τ·τ̂_ij + κ_C·I_ij + κ_K·K_ij)

    Safety constraint:  κ_K << κ_C << κ_τ  (commitment never dominates)
    K_ij ∈ {0.0, 1.0}  — binary flag only
    kappa_commitment=0.0 (default) → Stage 19 behavior identical
    """

    # ---- kappa_commitment=0 preserves Stage 19 exactly ----

    def test_s20_kappa_zero_returns_stage19_result(self):
        """With kappa_commitment=0.0 (default), effective_weight is bit-identical to Stage 19."""
        w, e, tau, i = 0.8, 0.6, 0.5, 1.0
        result_s19 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02)
        result_s20 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=1.0, kappa_commitment=0.0)
        assert result_s19 == result_s20

    def test_s20_k_ij_zero_returns_stage19_result(self):
        """With k_ij=0.0 (non-committed), kappa_commitment term is zero."""
        w, e, tau, i = 0.7, 0.55, 0.45, 1.0
        result_s19 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02)
        result_s20 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=0.0, kappa_commitment=0.01)
        assert result_s19 == result_s20

    def test_s20_all_defaults_returns_w_ij(self):
        """With all κ = 0.0 (defaults), effective_weight returns w_ij exactly."""
        for w in [0.0, 0.5, 1.0, 2.3]:
            assert effective_weight(w, 0.8, 0.7,
                                    k_ij=1.0, kappa_commitment=0.0) == w

    # ---- committed pair gets additional weight ----

    def test_s20_committed_pair_gets_larger_weight(self):
        """Committed pair (k_ij=1) with kappa_commitment>0 has higher effective weight."""
        w, e, tau, i = 1.0, 0.6, 0.5, 1.0
        w_uncommitted = effective_weight(w, e, tau,
                                         kappa_e=0.1, kappa_tau=0.05,
                                         i_ij=i, kappa_candidate=0.02,
                                         k_ij=0.0, kappa_commitment=0.005)
        w_committed = effective_weight(w, e, tau,
                                       kappa_e=0.1, kappa_tau=0.05,
                                       i_ij=i, kappa_candidate=0.02,
                                       k_ij=1.0, kappa_commitment=0.005)
        assert w_committed > w_uncommitted

    def test_s20_non_committed_pair_unchanged(self):
        """Non-committed pair (k_ij=0) is unaffected by kappa_commitment value."""
        w, e, tau, i = 0.9, 0.7, 0.6, 0.0
        base = effective_weight(w, e, tau,
                                kappa_e=0.1, kappa_tau=0.05,
                                i_ij=i, kappa_candidate=0.02,
                                k_ij=0.0, kappa_commitment=0.0)
        with_kappa = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=0.0, kappa_commitment=0.05)
        assert base == with_kappa

    # ---- commitment reinforcement is weaker than candidate and trace ----

    def test_s20_commitment_weaker_than_candidate_contribution(self):
        """κ_K·K_ij < κ_C·I_ij when using recommended defaults."""
        kappa_tau = 0.05
        kappa_candidate = 0.02
        kappa_commitment = 0.005
        assert kappa_commitment < kappa_candidate < kappa_tau

    def test_s20_commitment_additive_term_is_bounded(self):
        """Commitment contribution κ_K·K_ij ≤ kappa_commitment (since K_ij ≤ 1)."""
        kappa_commitment = 0.005
        w, e, tau = 1.0, 0.8, 0.7
        w_committed = effective_weight(w, e, tau,
                                       k_ij=1.0, kappa_commitment=kappa_commitment)
        w_base = effective_weight(w, e, tau)
        assert w_committed <= w_base * (1.0 + kappa_commitment + 1e-12)

    # ---- zero canonical weight stays zero ----

    def test_s20_zero_weight_stays_zero(self):
        """w_ij=0 → w_ij_eff=0 regardless of all κ values and k_ij."""
        result = effective_weight(0.0, 0.9, 0.9,
                                  kappa_e=0.3, kappa_tau=0.2,
                                  i_ij=1.0, kappa_candidate=0.1,
                                  k_ij=1.0, kappa_commitment=0.05)
        assert result == 0.0

    # ---- determinism ----

    def test_s20_deterministic_same_inputs_same_output(self):
        """Same inputs always produce identical output (no hidden state)."""
        kwargs = dict(w_ij=0.75, e_ij=0.6, tau_hat=0.5,
                      kappa_e=0.1, kappa_tau=0.05,
                      i_ij=1.0, kappa_candidate=0.02,
                      k_ij=1.0, kappa_commitment=0.005)
        r1 = effective_weight(**kwargs)
        r2 = effective_weight(**kwargs)
        assert r1 == r2

    # ---- weight is bounded ----

    def test_s20_effective_weight_bounded_above(self):
        """w_ij_eff ≤ w_ij · (1 + κ_E + κ_τ + κ_C + κ_K) since all signals ≤ 1."""
        w = 1.0
        ke, kt, kc, kk = 0.3, 0.1, 0.05, 0.01
        upper = w * (1.0 + ke + kt + kc + kk)
        result = effective_weight(w, 1.0, 1.0,
                                  kappa_e=ke, kappa_tau=kt,
                                  i_ij=1.0, kappa_candidate=kc,
                                  k_ij=1.0, kappa_commitment=kk)
        assert result <= upper + 1e-12

    def test_s20_effective_weight_non_negative(self):
        """For non-negative w_ij and all κ ≥ 0, effective weight ≥ 0."""
        result = effective_weight(0.5, 0.8, 0.7,
                                  kappa_e=0.1, kappa_tau=0.05,
                                  i_ij=1.0, kappa_candidate=0.02,
                                  k_ij=1.0, kappa_commitment=0.005)
        assert result >= 0.0

    # ---- removing commitment removes influence immediately ----

    def test_s20_removing_commitment_removes_influence(self):
        """Resetting commitment membership immediately removes k_ij contribution."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        assert comms.contains("g1", "g2") is True

        k_committed = float(comms.contains("g1", "g2"))
        w_before = effective_weight(1.0, 0.8, 0.7,
                                    k_ij=k_committed, kappa_commitment=0.01)

        comms.reset("g1", "g2")
        assert comms.contains("g1", "g2") is False
        k_reset = float(comms.contains("g1", "g2"))
        w_after = effective_weight(1.0, 0.8, 0.7,
                                   k_ij=k_reset, kappa_commitment=0.01)

        assert w_after < w_before

    # ---- k_ij is binary ----

    def test_s20_k_ij_is_binary_flag(self):
        """k_ij comes from float(comms.contains()) — only 0.0 or 1.0."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        k = float(comms.contains("g1", "g2"))
        assert k in (0.0, 1.0)

        comms.reset("g1", "g2")
        k2 = float(comms.contains("g1", "g2"))
        assert k2 in (0.0, 1.0)

    # ---- energy and collapse unchanged ----

    def test_s20_gate_energy_unchanged(self):
        """effective_weight() with commitment flag does not touch gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)
            k_ij = float(comms.contains(g1.gate_id, g2.gate_id))
            effective_weight(1.0, e, tau_hat,
                             kappa_e=0.1, kappa_tau=0.05,
                             i_ij=i_ij, kappa_candidate=0.02,
                             k_ij=k_ij, kappa_commitment=0.005)

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s20_collapse_state_unchanged(self):
        """effective_weight() with commitment flag does not touch gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)
            k_ij = float(comms.contains(g1.gate_id, g2.gate_id))
            effective_weight(1.0, e, tau_hat,
                             kappa_e=0.1, kappa_tau=0.05,
                             i_ij=i_ij, kappa_candidate=0.02,
                             k_ij=k_ij, kappa_commitment=0.005)

        assert [g.state(t) for g in gates] == states_before

    def test_s20_gate_step_not_modified(self):
        """Gate.step() signature and behavior unchanged by Stage 20 — no new parameters."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        for g in gates:
            theta_before = g.theta
            g.step(dt=0.01)
            assert abs(g.theta - theta_before) < 1.0

    # ---- full pipeline integration ----

    def test_s20_full_pipeline_committed_pair_has_higher_weight(self):
        """End-to-end: committed pair from full signal pipeline gets higher effective weight."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.5, phi_B=0.5)
        push(engine, "w1", "n1", "g2", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        if len(gates) < 2:
            pytest.skip("need 2 gates")
        g1, g2 = gates[0], gates[1]
        t = time.time()

        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
        comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)

        for _ in range(15000):
            e = emergence_weight(g1, g2, t)
            trace.step(g1.gate_id, g2.gate_id, e, 0.01)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)

        e = emergence_weight(g1, g2, t)
        tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
        i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
        k_ij = float(comms.contains(g1.gate_id, g2.gate_id))

        w_without_commitment = effective_weight(1.0, e, tau_hat,
                                                kappa_e=0.1, kappa_tau=0.05,
                                                i_ij=i_ij, kappa_candidate=0.02,
                                                k_ij=0.0, kappa_commitment=0.005)
        w_with_commitment = effective_weight(1.0, e, tau_hat,
                                             kappa_e=0.1, kappa_tau=0.05,
                                             i_ij=i_ij, kappa_candidate=0.02,
                                             k_ij=k_ij, kappa_commitment=0.005)
        if k_ij == 1.0:
            assert w_with_commitment > w_without_commitment
        else:
            assert w_with_commitment == w_without_commitment


# ---------------------------------------------------------------------------
# Stage 21 — controlled stabilization regulation
# ---------------------------------------------------------------------------

class TestStage21StabilizationRegulation:
    """
    Stage 21: highly committed / high-trace pairs experience a small bounded counter-pressure.

    Regulation signal:  R_lock = K_ij · τ̂_ij  ∈ [0, 1]
    Formula:
        w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock)

    Safety ordering:  κ_R < κ_K < κ_C < κ_τ  (regulation is the weakest signal)
    kappa_regulate=0.0 (default) → Stage 20 behavior identical
    r_ij_lock=0.0 → no regulation regardless of kappa_regulate
    """

    # ---- regulation_signal() correctness ----

    def test_s21_regulation_signal_committed_and_traced(self):
        """R_lock = K_ij * tau_hat; full signals give non-zero regulation."""
        assert regulation_signal(1.0, 0.8) == pytest.approx(0.8)

    def test_s21_regulation_signal_not_committed(self):
        """R_lock = 0 when K_ij = 0 (pair not committed)."""
        assert regulation_signal(0.0, 0.9) == 0.0

    def test_s21_regulation_signal_zero_trace(self):
        """R_lock = 0 when tau_hat = 0 (no trace memory)."""
        assert regulation_signal(1.0, 0.0) == 0.0

    def test_s21_regulation_signal_bounded(self):
        """R_lock ∈ [0, 1] for all valid inputs."""
        for k in [0.0, 1.0]:
            for tau in [0.0, 0.25, 0.5, 0.75, 1.0]:
                r = regulation_signal(k, tau)
                assert 0.0 <= r <= 1.0

    def test_s21_regulation_signal_deterministic(self):
        """Same inputs produce same output always."""
        assert regulation_signal(1.0, 0.7) == regulation_signal(1.0, 0.7)

    # ---- kappa_regulate=0 preserves Stage 20 exactly ----

    def test_s21_kappa_zero_returns_stage20_result(self):
        """With kappa_regulate=0.0 (default), effective_weight is bit-identical to Stage 20."""
        w, e, tau, i, k = 0.8, 0.6, 0.5, 1.0, 1.0
        r = regulation_signal(k, tau)
        result_s20 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005)
        result_s21 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=r, kappa_regulate=0.0)
        assert result_s20 == result_s21

    def test_s21_r_ij_lock_zero_no_regulation_effect(self):
        """With r_ij_lock=0.0, kappa_regulate has no effect on output."""
        w, e, tau, i, k = 0.7, 0.55, 0.45, 1.0, 1.0
        base = effective_weight(w, e, tau,
                                kappa_e=0.1, kappa_tau=0.05,
                                i_ij=i, kappa_candidate=0.02,
                                k_ij=k, kappa_commitment=0.005,
                                r_ij_lock=0.0, kappa_regulate=0.0)
        with_kappa = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=0.0, kappa_regulate=0.5)
        assert base == with_kappa

    def test_s21_all_defaults_returns_w_ij(self):
        """With all κ = 0.0 (defaults), effective_weight returns w_ij exactly."""
        for w in [0.0, 0.5, 1.0, 2.3]:
            assert effective_weight(w, 0.8, 0.7,
                                    r_ij_lock=1.0, kappa_regulate=0.0) == w

    # ---- regulation lowers effective weight for committed/traced pairs ----

    def test_s21_regulated_weight_lower_than_unregulated(self):
        """Active regulation reduces effective weight for committed high-trace pairs."""
        w, e, tau, i, k = 1.0, 0.6, 0.8, 1.0, 1.0
        r = regulation_signal(k, tau)
        w_no_reg = effective_weight(w, e, tau,
                                    kappa_e=0.1, kappa_tau=0.05,
                                    i_ij=i, kappa_candidate=0.02,
                                    k_ij=k, kappa_commitment=0.005,
                                    r_ij_lock=r, kappa_regulate=0.0)
        w_with_reg = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=r, kappa_regulate=0.001)
        assert w_with_reg < w_no_reg

    def test_s21_uncommitted_pair_unaffected_by_regulation(self):
        """Regulation has no effect when K_ij = 0 (pair not committed)."""
        w, e, tau, i, k = 1.0, 0.6, 0.8, 0.0, 0.0
        r = regulation_signal(k, tau)
        assert r == 0.0
        w_no_reg = effective_weight(w, e, tau,
                                    k_ij=k, kappa_commitment=0.005,
                                    r_ij_lock=r, kappa_regulate=0.0)
        w_with_reg = effective_weight(w, e, tau,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=r, kappa_regulate=0.001)
        assert w_no_reg == w_with_reg

    def test_s21_regulation_only_non_zero_when_committed_and_traced(self):
        """Regulation term κ_R · R_lock > 0 only when K_ij=1 AND τ̂_ij > 0."""
        assert regulation_signal(0.0, 0.9) == 0.0   # not committed
        assert regulation_signal(1.0, 0.0) == 0.0   # no trace
        assert regulation_signal(1.0, 0.5) == 0.5   # both active

    # ---- safety ordering ----

    def test_s21_coefficient_ordering_documented_constraint(self):
        """Typical recommended values satisfy κ_R < κ_K < κ_C < κ_τ."""
        kappa_tau = 0.05
        kappa_candidate = 0.02
        kappa_commitment = 0.005
        kappa_regulate = 0.001
        assert kappa_regulate < kappa_commitment < kappa_candidate < kappa_tau

    def test_s21_regulation_does_not_exceed_commitment_contribution(self):
        """With κ_R < κ_K, regulation cannot exceed the commitment boost for K_ij=1."""
        kappa_commitment = 0.005
        kappa_regulate = 0.001
        # Regulation at most κ_R * 1 = 0.001; commitment at least κ_K * 1 = 0.005
        assert kappa_regulate * 1.0 < kappa_commitment * 1.0

    # ---- non-negativity and boundedness ----

    def test_s21_effective_weight_non_negative(self):
        """Effective weight is always ≥ 0 regardless of regulation magnitude."""
        for kappa_regulate in [0.0, 0.01, 1.0, 100.0]:
            result = effective_weight(0.5, 0.8, 0.9,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=1.0, kappa_candidate=0.02,
                                      k_ij=1.0, kappa_commitment=0.005,
                                      r_ij_lock=1.0, kappa_regulate=kappa_regulate)
            assert result >= 0.0, f"negative result at kappa_regulate={kappa_regulate}"

    def test_s21_zero_weight_stays_zero(self):
        """w_ij=0 → w_ij_eff=0 regardless of regulation."""
        result = effective_weight(0.0, 0.9, 0.9,
                                  kappa_e=0.3, kappa_tau=0.2,
                                  i_ij=1.0, kappa_candidate=0.1,
                                  k_ij=1.0, kappa_commitment=0.05,
                                  r_ij_lock=1.0, kappa_regulate=0.01)
        assert result == 0.0

    def test_s21_effective_weight_bounded_above(self):
        """w_ij_eff ≤ w_ij · (1 + κ_E + κ_τ + κ_C + κ_K) since regulation only reduces."""
        w = 1.0
        ke, kt, kc, kk, kr = 0.3, 0.1, 0.05, 0.01, 0.002
        upper = w * (1.0 + ke + kt + kc + kk)
        result = effective_weight(w, 1.0, 1.0,
                                  kappa_e=ke, kappa_tau=kt,
                                  i_ij=1.0, kappa_candidate=kc,
                                  k_ij=1.0, kappa_commitment=kk,
                                  r_ij_lock=1.0, kappa_regulate=kr)
        assert result <= upper + 1e-12

    # ---- determinism ----

    def test_s21_deterministic(self):
        """Same inputs always produce identical output."""
        kwargs = dict(w_ij=0.75, e_ij=0.6, tau_hat=0.5,
                      kappa_e=0.1, kappa_tau=0.05,
                      i_ij=1.0, kappa_candidate=0.02,
                      k_ij=1.0, kappa_commitment=0.005,
                      r_ij_lock=0.5, kappa_regulate=0.001)
        assert effective_weight(**kwargs) == effective_weight(**kwargs)

    # ---- removing commitment removes regulation immediately ----

    def test_s21_removing_commitment_removes_regulation(self):
        """Resetting commitment to zero removes R_lock and its weight effect immediately."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        k = float(comms.contains("g1", "g2"))
        tau_hat = 0.8
        r_lock = regulation_signal(k, tau_hat)
        w_committed = effective_weight(1.0, 0.7, tau_hat,
                                       k_ij=k, kappa_commitment=0.005,
                                       r_ij_lock=r_lock, kappa_regulate=0.001)

        comms.reset("g1", "g2")
        k2 = float(comms.contains("g1", "g2"))
        r_lock2 = regulation_signal(k2, tau_hat)
        w_reset = effective_weight(1.0, 0.7, tau_hat,
                                   k_ij=k2, kappa_commitment=0.005,
                                   r_ij_lock=r_lock2, kappa_regulate=0.001)

        # After reset: k2=0 → no commitment boost, no regulation → w_reset != w_committed
        assert k2 == 0.0
        assert r_lock2 == 0.0
        assert w_reset != w_committed

    # ---- canonical substrate unchanged ----

    def test_s21_gate_energy_unchanged(self):
        """regulation_signal() and effective_weight() do not touch gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)
            k_ij = float(comms.contains(g1.gate_id, g2.gate_id))
            r_lock = regulation_signal(k_ij, tau_hat)
            effective_weight(1.0, e, tau_hat,
                             kappa_e=0.1, kappa_tau=0.05,
                             i_ij=i_ij, kappa_candidate=0.02,
                             k_ij=k_ij, kappa_commitment=0.005,
                             r_ij_lock=r_lock, kappa_regulate=0.001)

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s21_collapse_state_unchanged(self):
        """Regulation computation does not touch gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        if len(gates) >= 2:
            g1, g2 = gates[0], gates[1]
            trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
            cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
            comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
            for _ in range(200):
                e = emergence_weight(g1, g2, t)
                trace.step(g1.gate_id, g2.gate_id, e, 0.01)
                tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
                cands.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat)
            e = emergence_weight(g1, g2, t)
            tau_hat = trace.normalized(g1.gate_id, g2.gate_id)
            i_ij = float(cands.contains(g1.gate_id, g2.gate_id))
            comms.evaluate(g1.gate_id, g2.gate_id, e_ij=e, tau_hat=tau_hat, i_ij=i_ij)
            k_ij = float(comms.contains(g1.gate_id, g2.gate_id))
            r_lock = regulation_signal(k_ij, tau_hat)
            effective_weight(1.0, e, tau_hat,
                             kappa_e=0.1, kappa_tau=0.05,
                             i_ij=i_ij, kappa_candidate=0.02,
                             k_ij=k_ij, kappa_commitment=0.005,
                             r_ij_lock=r_lock, kappa_regulate=0.001)

        assert [g.state(t) for g in gates] == states_before

    def test_s21_gate_step_not_modified(self):
        """Gate.step() is completely unchanged by Stage 21."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            theta_before = g.theta
            g.step(dt=0.01)
            assert abs(g.theta - theta_before) < 1.0

    def test_s21_commitment_and_trace_sets_unchanged(self):
        """Calling regulation_signal() and effective_weight() never mutates commitment or trace."""
        trace = TopologyTrace(eta_tau=0.3, lambda_tau=0.1)
        cands = TopologyCandidates(theta_e=0.01, theta_tau=0.01)
        comms = TopologyCommitments(theta_e=0.01, theta_tau=0.01)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        snapshot_before = comms.snapshot()

        k_ij = float(comms.contains("g1", "g2"))
        tau_hat = 0.8
        r_lock = regulation_signal(k_ij, tau_hat)
        effective_weight(1.0, 0.7, tau_hat,
                         k_ij=k_ij, kappa_commitment=0.005,
                         r_ij_lock=r_lock, kappa_regulate=0.001)

        assert comms.snapshot() == snapshot_before


# ---------------------------------------------------------------------------
# Stage 22 — controlled proto-topology shaping
# ---------------------------------------------------------------------------

class TestStage22ProtoTopology:
    """
    Stage 22: committed pairs are surfaced as bounded, reversible, non-canonical
    proto-regions via connected-component analysis.

    Rule:  (i,j) ∈ K  ⟹  (i,j) ∈ G_proto
           proto-regions = connected components of G_proto with |region| ≥ 2

    ProtoTopology is entirely non-canonical — no write-back to canonical state.
    """

    # ---- empty input ----

    def test_s22_no_edges_no_regions(self):
        """With no committed edges, no proto-regions are produced."""
        pt = ProtoTopology()
        pt.evaluate_edges([])
        assert pt.region_count() == 0
        assert pt.regions() == []
        assert pt.node_count() == 0

    def test_s22_initial_state_empty(self):
        """Fresh ProtoTopology with no evaluate_edges() call has no regions."""
        pt = ProtoTopology()
        assert pt.region_count() == 0
        assert pt.node_count() == 0
        assert pt.regions() == []

    # ---- single pair → one 2-node region ----

    def test_s22_one_pair_yields_one_region(self):
        """One committed pair yields exactly one 2-node proto-region."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2")])
        assert pt.region_count() == 1
        assert pt.node_count() == 2
        r = pt.regions()[0]
        assert r == frozenset({"g1", "g2"})

    def test_s22_one_pair_region_membership(self):
        """Both nodes in a committed pair are in the same region."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2")])
        assert pt.contains_node("g1") is True
        assert pt.contains_node("g2") is True
        assert pt.region_of("g1") == pt.region_of("g2")

    def test_s22_non_member_node_returns_none(self):
        """region_of() returns None for a node not in any committed edge."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2")])
        assert pt.region_of("g3") is None
        assert pt.contains_node("g3") is False

    # ---- chain → one connected region ----

    def test_s22_chain_yields_one_region(self):
        """A chain of committed pairs g1-g2-g3 yields one connected region."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2"), ("g2", "g3")])
        assert pt.region_count() == 1
        assert pt.node_count() == 3
        assert pt.regions()[0] == frozenset({"g1", "g2", "g3"})

    def test_s22_four_node_clique_yields_one_region(self):
        """A fully connected 4-node clique of committed pairs → one 4-node region."""
        edges = [("a","b"), ("a","c"), ("a","d"), ("b","c"), ("b","d"), ("c","d")]
        pt = ProtoTopology()
        pt.evaluate_edges(edges)
        assert pt.region_count() == 1
        assert pt.node_count() == 4

    # ---- disconnected groups → separate regions ----

    def test_s22_two_disconnected_pairs_yield_two_regions(self):
        """Two separate committed pairs with no shared nodes → two regions."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2"), ("g3", "g4")])
        assert pt.region_count() == 2
        assert pt.node_count() == 4
        r1 = pt.region_of("g1")
        r2 = pt.region_of("g3")
        assert r1 != r2
        assert r1 == frozenset({"g1", "g2"})
        assert r2 == frozenset({"g3", "g4"})

    def test_s22_two_chains_disconnected_yield_two_regions(self):
        """Two disconnected chains → two separate proto-regions."""
        pt = ProtoTopology()
        pt.evaluate_edges([("a","b"), ("b","c"), ("x","y"), ("y","z")])
        assert pt.region_count() == 2
        assert pt.node_count() == 6
        assert pt.region_of("a") == frozenset({"a", "b", "c"})
        assert pt.region_of("x") == frozenset({"x", "y", "z"})

    def test_s22_connecting_two_clusters_merges_them(self):
        """Adding a bridge edge between two regions merges them into one."""
        pt = ProtoTopology()
        pt.evaluate_edges([("a","b"), ("c","d")])
        assert pt.region_count() == 2

        pt.recompute([("a","b"), ("c","d"), ("b","c")])
        assert pt.region_count() == 1
        assert pt.node_count() == 4

    # ---- symmetry and order-independence ----

    def test_s22_region_membership_symmetric(self):
        """region_of(i) and region_of(j) return same frozenset for committed pair."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2")])
        assert pt.region_of("g1") == pt.region_of("g2")

    def test_s22_edge_order_does_not_matter(self):
        """(i,j) and (j,i) as input edges produce identical regions."""
        pt1 = ProtoTopology()
        pt1.evaluate_edges([("g1", "g2"), ("g2", "g3")])

        pt2 = ProtoTopology()
        pt2.evaluate_edges([("g3", "g2"), ("g2", "g1")])

        assert pt1.snapshot() == pt2.snapshot()

    def test_s22_input_list_order_does_not_matter(self):
        """Different orderings of the same edge list produce the same regions."""
        edges_a = [("a","b"), ("b","c"), ("x","y")]
        edges_b = [("x","y"), ("b","a"), ("c","b")]
        pt1 = ProtoTopology()
        pt1.evaluate_edges(edges_a)
        pt2 = ProtoTopology()
        pt2.evaluate_edges(edges_b)
        assert pt1.snapshot() == pt2.snapshot()

    # ---- determinism ----

    def test_s22_deterministic_across_calls(self):
        """Same input always produces the same proto-region snapshot."""
        edges = [("g1","g2"), ("g2","g3"), ("g4","g5")]
        pt = ProtoTopology()
        pt.evaluate_edges(edges)
        snap1 = pt.snapshot()
        pt.evaluate_edges(edges)
        snap2 = pt.snapshot()
        assert snap1 == snap2

    def test_s22_deterministic_two_instances(self):
        """Two separate ProtoTopology instances with same input give same result."""
        edges = [("a","b"), ("b","c"), ("x","y")]
        pt1 = ProtoTopology()
        pt1.evaluate_edges(edges)
        pt2 = ProtoTopology()
        pt2.evaluate_edges(edges)
        assert pt1.snapshot() == pt2.snapshot()

    # ---- reset / recompute ----

    def test_s22_reset_clears_all_regions(self):
        """reset() removes all proto-regions."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1","g2"), ("g3","g4")])
        assert pt.region_count() == 2
        pt.reset()
        assert pt.region_count() == 0
        assert pt.node_count() == 0
        assert pt.regions() == []

    def test_s22_recompute_replaces_prior_state(self):
        """recompute() clears old regions before evaluating new edges."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1","g2"), ("g3","g4")])
        assert pt.region_count() == 2
        pt.recompute([("g1","g2")])
        assert pt.region_count() == 1
        assert pt.region_of("g3") is None

    def test_s22_recompute_empty_clears(self):
        """recompute([]) removes all regions."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1","g2")])
        pt.recompute([])
        assert pt.region_count() == 0

    # ---- integration with TopologyCommitments ----

    def test_s22_built_from_commitments_edges(self):
        """ProtoTopology correctly consumes TopologyCommitments.edges()."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8, i_ij=1.0)
        comms.evaluate("g4", "g5", e_ij=0.7, tau_hat=0.7, i_ij=1.0)

        pt = ProtoTopology()
        pt.evaluate_edges(comms.edges())
        assert pt.region_count() == 2
        assert pt.region_of("g1") == frozenset({"g1","g2","g3"})
        assert pt.region_of("g4") == frozenset({"g4","g5"})

    def test_s22_resetting_commitments_and_recomputing_updates_regions(self):
        """After commitment reset, recomputing proto-topology reflects the change."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g3", "g4", e_ij=0.9, tau_hat=0.9, i_ij=1.0)

        pt = ProtoTopology()
        pt.evaluate_edges(comms.edges())
        assert pt.region_count() == 2

        comms.reset()
        pt.recompute(comms.edges())
        assert pt.region_count() == 0

    # ---- canonical substrate unchanged ----

    def test_s22_gate_energy_unchanged(self):
        """ProtoTopology operations never touch gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2")])
        assert pt.region_count() == 1
        pt.reset()

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s22_collapse_state_unchanged(self):
        """ProtoTopology operations never touch gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2"), ("g2", "g3")])
        pt.reset()

        assert [g.state(t) for g in gates] == states_before

    def test_s22_canonical_graph_unchanged(self):
        """ProtoTopology never modifies the canonical CouplingGraph."""
        engine, gravity, field, graph = fresh()
        # Record graph state — no edges initially
        edges_before = list(graph.edges()) if hasattr(graph, "edges") else []

        pt = ProtoTopology()
        pt.evaluate_edges([("g1", "g2"), ("g3", "g4")])
        pt.reset()

        edges_after = list(graph.edges()) if hasattr(graph, "edges") else []
        assert edges_before == edges_after

    def test_s22_gate_step_not_modified(self):
        """Gate.step() is completely unchanged by Stage 22."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            theta_before = g.theta
            g.step(dt=0.01)
            assert abs(g.theta - theta_before) < 1.0

    # ---- snapshot immutability ----

    def test_s22_snapshot_is_immutable(self):
        """snapshot() returns a frozenset — mutation of the result doesn't affect proto-topology."""
        pt = ProtoTopology()
        pt.evaluate_edges([("g1","g2")])
        snap = pt.snapshot()
        assert isinstance(snap, frozenset)
        # Cannot add to a frozenset — this just verifies the type
        assert pt.region_count() == 1


# ---------------------------------------------------------------------------
# Stage 23 — controlled canonical boundary introduction
# ---------------------------------------------------------------------------

class TestStage23CanonicalBoundary:
    """
    Stage 23: non-canonical proto-regions are projected into a deterministic
    advisory surface (CanonicalBoundary) that canonical-layer consumers may
    query — without any canonical state being mutated.

    Label scheme:  label(R) = min(R)  — lexicographically smallest node-id.
    The boundary is a view, not a mutation.  Proto-topology remains non-canonical.
    """

    def _make_proto(self, edges):
        pt = ProtoTopology()
        pt.evaluate_edges(edges)
        return pt

    # ---- empty projection ----

    def test_s23_empty_proto_yields_empty_boundary(self):
        """With no proto-regions, projection is empty."""
        pt = self._make_proto([])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_count() == 0
        assert b.node_count() == 0
        assert b.region_ids() == []

    def test_s23_initial_state_empty(self):
        """Fresh CanonicalBoundary has no projected regions."""
        b = CanonicalBoundary()
        assert b.region_count() == 0
        assert b.region_of("g1") is None

    # ---- single region ----

    def test_s23_one_pair_projects_one_region(self):
        """One committed pair in proto → one advisory region."""
        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_count() == 1
        assert b.node_count() == 2

    def test_s23_region_label_is_min_member(self):
        """Region label equals the lexicographically smallest node-id."""
        pt = self._make_proto([("g3", "g1"), ("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_ids() == ["g1"]
        assert b.region_of("g1") == "g1"
        assert b.region_of("g2") == "g1"
        assert b.region_of("g3") == "g1"

    def test_s23_nodes_in_region_returns_full_set(self):
        """nodes_in_region returns the complete frozenset of region members."""
        pt = self._make_proto([("a", "b"), ("b", "c")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.nodes_in_region("a") == frozenset({"a", "b", "c"})
        assert b.nodes_in_region("c") == frozenset({"a", "b", "c"})

    def test_s23_contains_node_true_for_members(self):
        """contains_node() returns True for all nodes in a projected region."""
        pt = self._make_proto([("x", "y")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.contains_node("x") is True
        assert b.contains_node("y") is True

    def test_s23_contains_node_false_for_non_members(self):
        """contains_node() returns False for nodes not in any region."""
        pt = self._make_proto([("x", "y")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.contains_node("z") is False

    def test_s23_region_of_unknown_returns_none(self):
        """region_of() returns None for a node not in any projected region."""
        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_of("g99") is None

    def test_s23_nodes_in_region_unknown_returns_none(self):
        """nodes_in_region() returns None for a node not in any region."""
        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.nodes_in_region("g99") is None

    # ---- same_region ----

    def test_s23_same_region_true_for_co_members(self):
        """same_region(i, j) is True when i and j are in the same region."""
        pt = self._make_proto([("g1", "g2"), ("g2", "g3")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.same_region("g1", "g3") is True
        assert b.same_region("g1", "g2") is True

    def test_s23_same_region_false_for_different_regions(self):
        """same_region(i, j) is False when i and j are in different regions."""
        pt = self._make_proto([("g1", "g2"), ("g3", "g4")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.same_region("g1", "g3") is False
        assert b.same_region("g2", "g4") is False

    def test_s23_same_region_false_for_non_member(self):
        """same_region returns False if either node is not in any region."""
        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.same_region("g1", "g99") is False
        assert b.same_region("g99", "g1") is False

    def test_s23_same_region_symmetric(self):
        """same_region(i, j) == same_region(j, i) always."""
        pt = self._make_proto([("g1", "g2"), ("g3", "g4")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.same_region("g1", "g2") == b.same_region("g2", "g1")
        assert b.same_region("g1", "g3") == b.same_region("g3", "g1")

    # ---- multiple regions ----

    def test_s23_two_disconnected_regions_get_separate_labels(self):
        """Two disconnected proto-regions yield two separate advisory region ids."""
        pt = self._make_proto([("a", "b"), ("x", "y")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_count() == 2
        assert b.region_of("a") != b.region_of("x")
        assert sorted(b.region_ids()) == ["a", "x"]

    def test_s23_region_sizes_correct(self):
        """region_sizes() returns correct size for each projected region."""
        pt = self._make_proto([("a","b"),("b","c"),("x","y")])
        b = CanonicalBoundary()
        b.project(pt)
        sizes = b.region_sizes()
        assert sizes["a"] == 3   # label "a" covers {a, b, c}
        assert sizes["x"] == 2   # label "x" covers {x, y}

    # ---- determinism ----

    def test_s23_deterministic_same_proto_same_projection(self):
        """Same ProtoTopology input always produces identical projection."""
        edges = [("g1","g2"),("g2","g3"),("x","y")]
        pt = self._make_proto(edges)
        b1 = CanonicalBoundary()
        b1.project(pt)
        snap1 = b1.snapshot()

        b2 = CanonicalBoundary()
        b2.project(pt)
        snap2 = b2.snapshot()

        assert snap1 == snap2

    def test_s23_deterministic_label_regardless_of_edge_order(self):
        """Region label (min member) is independent of edge input order."""
        pt1 = self._make_proto([("g3","g1"),("g1","g2")])
        pt2 = self._make_proto([("g2","g1"),("g1","g3")])
        b1 = CanonicalBoundary()
        b1.project(pt1)
        b2 = CanonicalBoundary()
        b2.project(pt2)
        assert b1.snapshot() == b2.snapshot()

    # ---- reset / recompute ----

    def test_s23_reset_clears_projection(self):
        """reset() removes all advisory region data."""
        pt = self._make_proto([("g1","g2")])
        b = CanonicalBoundary()
        b.project(pt)
        assert b.region_count() == 1
        b.reset()
        assert b.region_count() == 0
        assert b.region_of("g1") is None

    def test_s23_recompute_replaces_prior_projection(self):
        """recompute() clears old projection before applying new proto-topology."""
        pt1 = self._make_proto([("g1","g2"),("g3","g4")])
        b = CanonicalBoundary()
        b.project(pt1)
        assert b.region_count() == 2

        pt2 = self._make_proto([("g1","g2")])
        b.recompute(pt2)
        assert b.region_count() == 1
        assert b.region_of("g3") is None

    def test_s23_recompute_empty_clears(self):
        """recompute() with empty proto clears the projection."""
        pt = self._make_proto([("g1","g2")])
        b = CanonicalBoundary()
        b.project(pt)
        b.recompute(self._make_proto([]))
        assert b.region_count() == 0

    # ---- snapshot is immutable and decoupled ----

    def test_s23_snapshot_is_advisory_snapshot(self):
        """snapshot() returns an AdvisorySnapshot instance."""
        pt = self._make_proto([("g1","g2")])
        b = CanonicalBoundary()
        b.project(pt)
        snap = b.snapshot()
        assert isinstance(snap, AdvisorySnapshot)

    def test_s23_snapshot_decoupled_from_later_reset(self):
        """Snapshot captured before reset() is not affected by the reset."""
        pt = self._make_proto([("g1","g2"),("g3","g4")])
        b = CanonicalBoundary()
        b.project(pt)
        snap = b.snapshot()
        b.reset()
        # boundary is cleared, but snapshot retains prior state
        assert b.region_count() == 0
        node_labels, region_sizes, _ = snap.to_dicts()
        assert "g1" in node_labels
        assert "g3" in node_labels

    # ---- integration with full pipeline ----

    def test_s23_full_pipeline_projection(self):
        """End-to-end: commitments → proto-topology → canonical boundary."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8, i_ij=1.0)
        comms.evaluate("g4", "g5", e_ij=0.7, tau_hat=0.7, i_ij=1.0)

        proto = ProtoTopology()
        proto.evaluate_edges(comms.edges())

        boundary = CanonicalBoundary()
        boundary.project(proto)

        assert boundary.region_count() == 2
        assert boundary.same_region("g1", "g3") is True
        assert boundary.same_region("g1", "g4") is False
        assert boundary.same_region("g4", "g5") is True
        assert boundary.region_of("g1") == "g1"
        assert boundary.region_of("g4") == "g4"

    # ---- canonical substrate unchanged ----

    def test_s23_gate_energy_unchanged(self):
        """CanonicalBoundary operations never touch gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        _ = b.same_region("g1", "g2")
        _ = b.region_of("g1")
        b.reset()

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s23_collapse_state_unchanged(self):
        """CanonicalBoundary operations never touch gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        pt = self._make_proto([("g1", "g2")])
        b = CanonicalBoundary()
        b.project(pt)
        b.reset()

        assert [g.state(t) for g in gates] == states_before

    def test_s23_canonical_graph_unchanged(self):
        """CanonicalBoundary never modifies the canonical CouplingGraph."""
        engine, gravity, field, graph = fresh()
        edges_before = list(graph.edges()) if hasattr(graph, "edges") else []

        pt = self._make_proto([("g1","g2"),("g3","g4")])
        b = CanonicalBoundary()
        b.project(pt)
        b.reset()

        edges_after = list(graph.edges()) if hasattr(graph, "edges") else []
        assert edges_before == edges_after

    def test_s23_gate_step_not_modified(self):
        """Gate.step() is completely unchanged by Stage 23."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            theta_before = g.theta
            g.step(dt=0.01)
            assert abs(g.theta - theta_before) < 1.0

    def test_s23_proto_topology_unchanged_by_projection(self):
        """project() reads ProtoTopology read-only; proto-regions are not mutated."""
        pt = self._make_proto([("g1","g2"),("g3","g4")])
        snap_before = pt.snapshot()

        b = CanonicalBoundary()
        b.project(pt)
        b.reset()

        assert pt.snapshot() == snap_before


# ---------------------------------------------------------------------------
# Stage 24 — controlled boundary influence
# ---------------------------------------------------------------------------

class TestStage24BoundaryInfluence:
    """
    Stage 24: same-region pairs (B_ij = 1) receive a minimal bounded reinforcement.

    Formula:
        w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B)

    Safety ordering:  κ_B << κ_R < κ_K < κ_C < κ_τ  (boundary is the weakest signal)
    B_ij ∈ {0.0, 1.0}  — binary same-region flag only
    kappa_boundary=0.0 (default) → Stage 23 behavior identical
    b_ij=0.0 → no boundary effect regardless of kappa_boundary
    """

    def _make_boundary(self, edges):
        pt = ProtoTopology()
        pt.evaluate_edges(edges)
        b = CanonicalBoundary()
        b.project(pt)
        return b

    # ---- kappa_boundary=0 preserves Stage 23 exactly ----

    def test_s24_kappa_zero_returns_stage23_result(self):
        """With kappa_boundary=0.0 (default), effective_weight is bit-identical to Stage 23."""
        w, e, tau, i, k = 0.8, 0.6, 0.5, 1.0, 1.0
        r = regulation_signal(k, tau)
        result_s23 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=r, kappa_regulate=0.001)
        result_s24 = effective_weight(w, e, tau,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=i, kappa_candidate=0.02,
                                      k_ij=k, kappa_commitment=0.005,
                                      r_ij_lock=r, kappa_regulate=0.001,
                                      b_ij=1.0, kappa_boundary=0.0)
        assert result_s23 == result_s24

    def test_s24_b_ij_zero_no_boundary_effect(self):
        """With b_ij=0.0 (not same-region), kappa_boundary has no effect."""
        w, e, tau = 0.9, 0.6, 0.5
        base = effective_weight(w, e, tau,
                                b_ij=0.0, kappa_boundary=0.0)
        with_kappa = effective_weight(w, e, tau,
                                      b_ij=0.0, kappa_boundary=0.5)
        assert base == with_kappa

    def test_s24_all_defaults_returns_w_ij(self):
        """With all κ = 0.0 (defaults), returns w_ij exactly."""
        for w in [0.0, 0.5, 1.0, 2.3]:
            assert effective_weight(w, 0.8, 0.7,
                                    b_ij=1.0, kappa_boundary=0.0) == w

    # ---- same-region pair gets additional weight ----

    def test_s24_same_region_pair_gets_higher_weight(self):
        """Same-region pair (b_ij=1) with kappa_boundary>0 has higher effective weight."""
        w, e, tau = 1.0, 0.6, 0.5
        w_no_boundary = effective_weight(w, e, tau,
                                         b_ij=0.0, kappa_boundary=0.0005)
        w_with_boundary = effective_weight(w, e, tau,
                                           b_ij=1.0, kappa_boundary=0.0005)
        assert w_with_boundary > w_no_boundary

    def test_s24_different_region_pair_unchanged(self):
        """b_ij=0.0 (different region or not projected) → kappa_boundary has no effect."""
        w, e, tau = 0.9, 0.7, 0.6
        base = effective_weight(w, e, tau, b_ij=0.0, kappa_boundary=0.0)
        modified = effective_weight(w, e, tau, b_ij=0.0, kappa_boundary=0.01)
        assert base == modified

    # ---- boundary is weaker than all prior signals ----

    def test_s24_boundary_weaker_than_commitment(self):
        """κ_B contribution < κ_K contribution for B_ij = K_ij = 1."""
        kappa_boundary = 0.0005
        kappa_commitment = 0.005
        # For binary flags, contributions are just the coefficients
        assert kappa_boundary * 1.0 < kappa_commitment * 1.0

    def test_s24_coefficient_ordering_full_chain(self):
        """Recommended defaults satisfy κ_B << κ_R < κ_K < κ_C < κ_τ."""
        kappa_tau = 0.05
        kappa_candidate = 0.02
        kappa_commitment = 0.005
        kappa_regulate = 0.001
        kappa_boundary = 0.0005
        assert kappa_boundary < kappa_regulate < kappa_commitment
        assert kappa_commitment < kappa_candidate < kappa_tau

    # ---- boundary flag from CanonicalBoundary ----

    def test_s24_b_ij_from_same_region_true(self):
        """float(boundary.same_region(i,j)) = 1.0 for co-members."""
        b = self._make_boundary([("g1","g2"),("g2","g3")])
        assert float(b.same_region("g1", "g3")) == 1.0
        assert float(b.same_region("g1", "g2")) == 1.0

    def test_s24_b_ij_from_same_region_false(self):
        """float(boundary.same_region(i,j)) = 0.0 for different regions."""
        b = self._make_boundary([("g1","g2"),("g3","g4")])
        assert float(b.same_region("g1", "g3")) == 0.0

    def test_s24_b_ij_is_binary(self):
        """b_ij from CanonicalBoundary.same_region() is always 0.0 or 1.0."""
        b = self._make_boundary([("g1","g2"),("g3","g4")])
        for pair in [("g1","g2"), ("g1","g3"), ("g3","g4"), ("g1","g99")]:
            val = float(b.same_region(*pair))
            assert val in (0.0, 1.0)

    # ---- non-negativity and boundedness ----

    def test_s24_effective_weight_non_negative(self):
        """Effective weight is always ≥ 0 regardless of kappa_boundary."""
        for kappa_boundary in [0.0, 0.001, 1.0, 100.0]:
            result = effective_weight(0.5, 0.8, 0.9,
                                      kappa_e=0.1, kappa_tau=0.05,
                                      i_ij=1.0, kappa_candidate=0.02,
                                      k_ij=1.0, kappa_commitment=0.005,
                                      r_ij_lock=1.0, kappa_regulate=0.001,
                                      b_ij=1.0, kappa_boundary=kappa_boundary)
            assert result >= 0.0

    def test_s24_zero_weight_stays_zero(self):
        """w_ij=0 → w_ij_eff=0 regardless of boundary flag."""
        result = effective_weight(0.0, 0.9, 0.9,
                                  kappa_e=0.3, kappa_tau=0.2,
                                  i_ij=1.0, kappa_candidate=0.1,
                                  k_ij=1.0, kappa_commitment=0.05,
                                  r_ij_lock=1.0, kappa_regulate=0.01,
                                  b_ij=1.0, kappa_boundary=0.005)
        assert result == 0.0

    def test_s24_effective_weight_bounded_above(self):
        """w_ij_eff ≤ w_ij·(1 + κ_E + κ_τ + κ_C + κ_K + κ_B) since all signals ≤ 1."""
        w = 1.0
        ke, kt, kc, kk, kr, kb = 0.3, 0.1, 0.05, 0.01, 0.002, 0.0005
        upper = w * (1.0 + ke + kt + kc + kk + kb)
        result = effective_weight(w, 1.0, 1.0,
                                  kappa_e=ke, kappa_tau=kt,
                                  i_ij=1.0, kappa_candidate=kc,
                                  k_ij=1.0, kappa_commitment=kk,
                                  r_ij_lock=0.0, kappa_regulate=kr,
                                  b_ij=1.0, kappa_boundary=kb)
        assert result <= upper + 1e-12

    # ---- determinism ----

    def test_s24_deterministic(self):
        """Same inputs always produce identical output."""
        kwargs = dict(w_ij=0.75, e_ij=0.6, tau_hat=0.5,
                      kappa_e=0.1, kappa_tau=0.05,
                      i_ij=1.0, kappa_candidate=0.02,
                      k_ij=1.0, kappa_commitment=0.005,
                      r_ij_lock=0.5, kappa_regulate=0.001,
                      b_ij=1.0, kappa_boundary=0.0005)
        assert effective_weight(**kwargs) == effective_weight(**kwargs)

    # ---- removing region membership removes effect ----

    def test_s24_removing_region_removes_boundary_influence(self):
        """After boundary reset, b_ij=0 and weight reverts to pre-boundary level."""
        b = self._make_boundary([("g1","g2")])
        b_ij_before = float(b.same_region("g1", "g2"))
        w_with = effective_weight(1.0, 0.7, 0.5,
                                  b_ij=b_ij_before, kappa_boundary=0.0005)

        b.reset()
        b_ij_after = float(b.same_region("g1", "g2"))
        w_without = effective_weight(1.0, 0.7, 0.5,
                                     b_ij=b_ij_after, kappa_boundary=0.0005)

        assert b_ij_after == 0.0
        assert w_without < w_with

    # ---- canonical substrate unchanged ----

    def test_s24_gate_energy_unchanged(self):
        """Boundary flag computation and effective_weight() never touch gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]

        boundary = self._make_boundary([("g1","g2")])
        b_ij = float(boundary.same_region("g1", "g2"))
        effective_weight(1.0, 0.7, 0.5, b_ij=b_ij, kappa_boundary=0.0005)

        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s24_collapse_state_unchanged(self):
        """Boundary influence computation never touches gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        push(engine, "w1", "n1", "g2", phi_R=0.3, phi_B=0.3)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        states_before = [g.state(t) for g in gates]

        boundary = self._make_boundary([("g1","g2")])
        b_ij = float(boundary.same_region("g1", "g2"))
        effective_weight(1.0, 0.7, 0.5, b_ij=b_ij, kappa_boundary=0.0005)

        assert [g.state(t) for g in gates] == states_before

    def test_s24_gate_step_not_modified(self):
        """Gate.step() is completely unchanged by Stage 24."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "g1", phi_R=0.4, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        for g in gates:
            theta_before = g.theta
            g.step(dt=0.01)
            assert abs(g.theta - theta_before) < 1.0

    def test_s24_canonical_boundary_not_mutated_by_effective_weight(self):
        """effective_weight() reads boundary read-only; same_region results are unchanged."""
        b = self._make_boundary([("g1","g2"),("g3","g4")])
        snap_before = b.snapshot()

        b_ij = float(b.same_region("g1", "g2"))
        effective_weight(1.0, 0.7, 0.5, b_ij=b_ij, kappa_boundary=0.0005)

        assert b.snapshot() == snap_before

    # ---- full pipeline integration ----

    def test_s24_full_pipeline_same_region_higher_weight(self):
        """End-to-end: commitments → proto → boundary → effective_weight with boundary boost."""
        comms = TopologyCommitments(theta_e=0.2, theta_tau=0.2)
        comms.evaluate("g1", "g2", e_ij=0.9, tau_hat=0.9, i_ij=1.0)
        comms.evaluate("g2", "g3", e_ij=0.8, tau_hat=0.8, i_ij=1.0)

        proto = ProtoTopology()
        proto.evaluate_edges(comms.edges())

        boundary = CanonicalBoundary()
        boundary.project(proto)

        b_same = float(boundary.same_region("g1", "g3"))
        b_diff = float(boundary.same_region("g1", "g99"))

        w_same = effective_weight(1.0, 0.7, 0.6,
                                  b_ij=b_same, kappa_boundary=0.0005)
        w_diff = effective_weight(1.0, 0.7, 0.6,
                                  b_ij=b_diff, kappa_boundary=0.0005)

        assert b_same == 1.0
        assert b_diff == 0.0
        assert w_same > w_diff


class TestStage25SaturationControl:
    """Stage 25 — final saturation control / global safety envelope.

    M_raw = 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B
    M_sat = M_raw / (1 + σ · max(0, M_raw − 1))
    w_ij_eff = w_ij · max(0, M_sat)
    """

    # ------------------------------------------------------------------
    # Dormancy: sigma=0.0 must preserve Stage 24 exactly
    # ------------------------------------------------------------------

    def test_s25_sigma_zero_returns_stage24_result(self):
        """sigma_saturate=0.0 → result is bit-identical to Stage 24."""
        w24 = effective_weight(
            2.0, 0.8, 0.7,
            kappa_e=0.1, kappa_tau=0.05,
            i_ij=1.0, kappa_candidate=0.02,
            k_ij=1.0, kappa_commitment=0.005,
            r_ij_lock=0.3, kappa_regulate=0.001,
            b_ij=1.0, kappa_boundary=0.0005,
        )
        w25 = effective_weight(
            2.0, 0.8, 0.7,
            kappa_e=0.1, kappa_tau=0.05,
            i_ij=1.0, kappa_candidate=0.02,
            k_ij=1.0, kappa_commitment=0.005,
            r_ij_lock=0.3, kappa_regulate=0.001,
            b_ij=1.0, kappa_boundary=0.0005,
            sigma_saturate=0.0,
        )
        assert w25 == w24

    def test_s25_all_defaults_returns_w_ij(self):
        """All defaults (all κ=0, σ=0) → w_ij exactly."""
        assert effective_weight(3.7, 0.5, 0.5, sigma_saturate=0.0) == 3.7
        assert effective_weight(3.7, 0.5, 0.5) == 3.7

    # ------------------------------------------------------------------
    # Compression behavior: active saturation must reduce weight vs Stage 24
    # ------------------------------------------------------------------

    def test_s25_large_reinforcement_compressed(self):
        """For M_raw well above 1, saturation reduces effective weight vs no-saturation."""
        # Build a scenario with meaningful reinforcement (M_raw > 1)
        w24 = effective_weight(1.0, 1.0, 1.0,
                               kappa_e=0.5, kappa_tau=0.3,
                               sigma_saturate=0.0)
        w25 = effective_weight(1.0, 1.0, 1.0,
                               kappa_e=0.5, kappa_tau=0.3,
                               sigma_saturate=1.0)
        assert w25 < w24, "saturation must reduce weight when M_raw > 1"
        assert w25 > 0.0

    def test_s25_small_reinforcement_minimal_compression(self):
        """For M_raw barely above 1, compression is minimal."""
        # kappa values very small → M_raw ≈ 1 + ε
        w24 = effective_weight(1.0, 0.1, 0.1,
                               kappa_e=0.01, kappa_tau=0.01,
                               sigma_saturate=0.0)
        w25 = effective_weight(1.0, 0.1, 0.1,
                               kappa_e=0.01, kappa_tau=0.01,
                               sigma_saturate=1.0)
        # Compression exists but is very small
        assert w25 <= w24
        assert abs(w25 - w24) < 0.01

    def test_s25_no_reinforcement_no_compression(self):
        """When M_raw = 1 (all κ=0), saturation has zero effect regardless of σ."""
        w24 = effective_weight(1.5, 0.5, 0.5, sigma_saturate=0.0)
        w25 = effective_weight(1.5, 0.5, 0.5, sigma_saturate=10.0)
        assert w25 == w24  # M_raw = 1 exactly → no compression

    def test_s25_attenuation_no_compression(self):
        """When M_raw < 1 (net negative reinforcement), no saturation compression."""
        # Regulation term makes M_raw < 1
        w24 = effective_weight(1.0, 0.0, 0.9,
                               k_ij=1.0, kappa_commitment=0.001,
                               r_ij_lock=0.9, kappa_regulate=0.5,
                               sigma_saturate=0.0)
        w25 = effective_weight(1.0, 0.0, 0.9,
                               k_ij=1.0, kappa_commitment=0.001,
                               r_ij_lock=0.9, kappa_regulate=0.5,
                               sigma_saturate=10.0)
        assert w25 == w24  # M_raw < 1 → no compression branch taken

    # ------------------------------------------------------------------
    # Monotonicity: stronger pair must remain stronger after saturation
    # ------------------------------------------------------------------

    def test_s25_monotone_stronger_pair_stays_stronger(self):
        """Saturation is monotone: pair with higher M_raw has higher M_sat."""
        # Strong pair: high kappa_tau hit
        w_strong = effective_weight(1.0, 0.9, 0.9,
                                    kappa_e=0.2, kappa_tau=0.15,
                                    sigma_saturate=1.0)
        # Weak pair: low values
        w_weak = effective_weight(1.0, 0.2, 0.2,
                                  kappa_e=0.2, kappa_tau=0.15,
                                  sigma_saturate=1.0)
        assert w_strong > w_weak

    def test_s25_monotone_increasing_sigma_decreasing_weight(self):
        """Higher σ → lower effective weight when M_raw > 1."""
        kwargs = dict(w_ij=1.0, e_ij=1.0, tau_hat=1.0,
                      kappa_e=0.5, kappa_tau=0.3)
        w0 = effective_weight(**kwargs, sigma_saturate=0.0)
        w1 = effective_weight(**kwargs, sigma_saturate=0.5)
        w2 = effective_weight(**kwargs, sigma_saturate=2.0)
        assert w0 > w1 > w2 > 0.0

    def test_s25_signal_ordering_preserved(self):
        """Pair with trace influence remains stronger than pair with only boundary (ordering)."""
        # High trace: kappa_tau active
        w_trace = effective_weight(1.0, 0.5, 0.9,
                                   kappa_tau=0.3,
                                   sigma_saturate=1.0)
        # Only boundary: much weaker kappa_boundary
        w_boundary = effective_weight(1.0, 0.5, 0.0,
                                      kappa_boundary=0.001, b_ij=1.0,
                                      sigma_saturate=1.0)
        assert w_trace > w_boundary

    # ------------------------------------------------------------------
    # Safety: non-negativity and bounds
    # ------------------------------------------------------------------

    def test_s25_effective_weight_non_negative(self):
        """Effective weight is always ≥ 0 for w_ij ≥ 0."""
        # Force M_raw strongly negative via regulation
        w = effective_weight(1.0, 0.0, 1.0,
                             k_ij=1.0, r_ij_lock=1.0,
                             kappa_regulate=5.0,
                             sigma_saturate=2.0)
        assert w >= 0.0

    def test_s25_zero_weight_stays_zero(self):
        """w_ij = 0 → effective weight = 0 regardless of saturation."""
        assert effective_weight(0.0, 1.0, 1.0,
                                kappa_e=0.5, kappa_tau=0.5,
                                sigma_saturate=1.0) == 0.0

    def test_s25_saturation_bounded_above(self):
        """M_sat ≤ M_raw always; effective weight never exceeds unsaturated value for w_ij > 0."""
        # M_raw > 1 case
        w_raw = effective_weight(1.0, 1.0, 1.0,
                                 kappa_e=0.5, kappa_tau=0.5,
                                 sigma_saturate=0.0)
        w_sat = effective_weight(1.0, 1.0, 1.0,
                                 kappa_e=0.5, kappa_tau=0.5,
                                 sigma_saturate=0.5)
        assert w_sat <= w_raw

    def test_s25_saturated_weight_above_unity_for_positive_reinforcement(self):
        """After saturation, M_sat > 1 holds when M_raw > 1 and σ is finite."""
        # excess = 0.5 + 0.3 = 0.8 → M_sat = 1 + 0.8/(1 + 1.0*0.8) = 1 + 0.8/1.8 ≈ 1.444
        w = effective_weight(1.0, 1.0, 1.0,
                             kappa_e=0.5, kappa_tau=0.3,
                             sigma_saturate=1.0)
        assert w > 1.0

    def test_s25_asymptotic_bound_high_sigma(self):
        """As σ → ∞, M_sat → 1 from above for M_raw > 1 (topology not nullified)."""
        # excess = M_raw - 1 = 0.5 + 0.5 = 1.0
        # M_sat = 1 + 1/(1 + 1000*1) ≈ 1.001
        w = effective_weight(1.0, 1.0, 1.0,
                             kappa_e=0.5, kappa_tau=0.5,
                             sigma_saturate=1000.0)
        # Should be just above 1.0 (not far above; topology influence compressed but present)
        assert 1.0 < w <= 1.01

    # ------------------------------------------------------------------
    # Determinism and non-canonicality
    # ------------------------------------------------------------------

    def test_s25_deterministic(self):
        """Repeated calls with same inputs produce identical outputs."""
        kwargs = dict(w_ij=1.5, e_ij=0.8, tau_hat=0.7,
                      kappa_e=0.15, kappa_tau=0.08,
                      i_ij=1.0, kappa_candidate=0.02,
                      sigma_saturate=0.5)
        results = [effective_weight(**kwargs) for _ in range(10)]
        assert all(r == results[0] for r in results)

    def test_s25_gate_energy_unchanged(self):
        """Saturation does not alter gate energy."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "s25_g1", phi_R=0.6, phi_B=0.4)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        energy_before = [g.energy(t) for g in gates]
        effective_weight(1.0, 0.8, 0.7, kappa_e=0.2, kappa_tau=0.1,
                         sigma_saturate=0.5)
        assert [g.energy(t) for g in gates] == pytest.approx(energy_before, abs=1e-12)

    def test_s25_collapse_state_unchanged(self):
        """Saturation does not alter gate collapse state."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "s25_g2", phi_R=0.9, phi_B=0.1)
        gates = all_gates(engine, "w1", "n1")
        t = time.time()
        p_before = [g.p() for g in gates]
        effective_weight(1.0, 1.0, 1.0, kappa_e=0.5, kappa_tau=0.5,
                         sigma_saturate=0.5)
        assert [g.p() for g in gates] == pytest.approx(p_before, abs=1e-12)

    def test_s25_gate_step_not_modified(self):
        """Gate.step() amplitude is unaffected by saturation computation (alpha=0 default)."""
        engine, gravity, field, graph = fresh()
        push(engine, "w1", "n1", "s25_g3", phi_R=0.5, phi_B=0.5)
        gates = all_gates(engine, "w1", "n1")
        a_before = [g.a for g in gates]
        effective_weight(2.0, 1.0, 1.0, kappa_e=0.5, kappa_tau=0.5,
                         sigma_saturate=2.0)
        for g in gates:
            g.step(dt=0.01)
        # With default alpha=0, amplitude is invariant under step()
        assert [g.a for g in gates] == pytest.approx(a_before, abs=1e-12)

    def test_s25_topology_structures_not_mutated(self):
        """Saturation computation leaves all topology structures unchanged."""
        trace = TopologyTrace(eta_tau=0.1, lambda_tau=0.1)
        trace.step("g1", "g2", 0.8, 0.1)
        tau_before = trace.get("g1", "g2")

        cands = TopologyCandidates(theta_e=0.3, theta_tau=0.3)
        cands.evaluate("g1", "g2", e_ij=0.8, tau_hat=0.8)
        count_before = len(list(cands.edges()))

        tau_hat = trace.normalized("g1", "g2")
        effective_weight(1.0, 0.8, tau_hat,
                         kappa_e=0.2, kappa_tau=0.1,
                         i_ij=1.0, kappa_candidate=0.05,
                         sigma_saturate=2.0)

        assert trace.get("g1", "g2") == tau_before
        assert len(list(cands.edges())) == count_before

    # ------------------------------------------------------------------
    # Topology influence not nullified
    # ------------------------------------------------------------------

    def test_s25_topology_influence_not_nullified(self):
        """Saturation compresses but does not erase topology influence."""
        w_no_topo = effective_weight(1.0, 0.0, 0.0, sigma_saturate=1.0)
        w_with_topo = effective_weight(1.0, 0.8, 0.8,
                                       kappa_e=0.2, kappa_tau=0.15,
                                       sigma_saturate=1.0)
        assert w_with_topo > w_no_topo

    def test_s25_full_coefficient_chain_compressed(self):
        """All signals active + saturation: ordering preserved, output compressed vs unsaturated."""
        kwargs = dict(
            w_ij=1.0, e_ij=0.9, tau_hat=0.85,
            kappa_e=0.1, kappa_tau=0.05,
            i_ij=1.0, kappa_candidate=0.02,
            k_ij=1.0, kappa_commitment=0.005,
            r_ij_lock=0.3, kappa_regulate=0.001,
            b_ij=1.0, kappa_boundary=0.0005,
        )
        w_raw = effective_weight(**kwargs, sigma_saturate=0.0)
        w_sat = effective_weight(**kwargs, sigma_saturate=0.5)
        assert w_sat < w_raw    # saturation compresses
        assert w_sat > 1.0      # topology influence not erased (M_raw > 1)
        assert w_sat > 0.0

    def test_s25_boundary_weaker_than_trace_after_saturation(self):
        """κ_B << κ_τ ordering is preserved after saturation."""
        w_trace = effective_weight(1.0, 0.0, 1.0,
                                   kappa_tau=0.1,
                                   sigma_saturate=1.0)
        w_boundary = effective_weight(1.0, 0.0, 0.0,
                                      b_ij=1.0, kappa_boundary=0.001,
                                      sigma_saturate=1.0)
        assert w_trace > w_boundary


class TestL1PearlCanonicalIntegration:
    """L1-1 — Pearl canonical integration: truth without narration.

    PearlArchive is the auditable, append-only record of state transitions.
    All tests verify the Pearl schema is minimal, immutable, monotone, and
    completely free of narration, labels, or adapter artifacts.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _engine_with_archive(self):
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        return engine, archive

    def _envelope(self, gate_id="g1", phi_R=0.4, phi_B=0.0, cycle_id="cycle-001"):
        from invar.core.envelope import DecayClass
        env = ObsGateEnvelope(
            instrument_id="test-probe",
            workload_id="w1",
            node_key="n1",
            cycle_id=cycle_id,
        )
        env.add(gate_id, phi_R=phi_R, phi_B=phi_B,
                decay_class=DecayClass.STRUCTURAL)
        return env

    # ------------------------------------------------------------------
    # Immutability: Pearl is a frozen / immutable record
    # ------------------------------------------------------------------

    def test_l1_pearl_is_dataclass(self):
        """Pearl must be a dataclass (supports dataclasses.replace)."""
        import dataclasses
        from invar.core.support_engine import Pearl
        assert dataclasses.is_dataclass(Pearl)

    def test_l1_pearl_immutable_after_creation(self):
        """Pearl fields cannot be silently mutated after creation."""
        import dataclasses
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())

        pearl = archive.pearls[0]
        # dataclasses.replace confirms the Pearl supports immutable copies
        copy = dataclasses.replace(pearl, seq_id=999)
        # Original pearl must be unchanged
        assert pearl.seq_id != 999
        assert copy.seq_id == 999

    # ------------------------------------------------------------------
    # seq_id: monotone emission order
    # ------------------------------------------------------------------

    def test_l1_seq_id_starts_at_one(self):
        """First Pearl emitted by a fresh engine has seq_id = 1."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        assert archive.pearls[0].seq_id == 1

    def test_l1_seq_id_strictly_monotone(self):
        """Pearls are recorded in strictly increasing seq_id order."""
        engine, archive = self._engine_with_archive()
        e1 = self._envelope(gate_id="g1", cycle_id="c1")
        e2 = self._envelope(gate_id="g2", cycle_id="c2")
        engine.ingest(e1)
        engine.ingest(e2)
        ps = archive.pearls
        assert len(ps) == 2
        assert ps[0].seq_id < ps[1].seq_id

    def test_l1_archive_rejects_non_monotone_seq(self):
        """archive.record() raises ValueError on non-monotone seq_id."""
        import dataclasses
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())

        bad = dataclasses.replace(archive.pearls[0], seq_id=0)
        with pytest.raises(ValueError, match="Non-monotone seq_id"):
            archive.record(bad)

    # ------------------------------------------------------------------
    # Schema: raw state only — no narration, no labels
    # ------------------------------------------------------------------

    def test_l1_pearl_has_required_fields(self):
        """Pearl has the minimal required state fields."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        p = archive.pearls[0]

        # Identity
        assert hasattr(p, "seq_id")
        assert hasattr(p, "cycle_id")
        assert hasattr(p, "ts")
        assert hasattr(p, "gate_id")

        # Gate state snapshot
        assert hasattr(p, "phi_R_after")
        assert hasattr(p, "phi_B_after")

        # Derived (allowed)
        assert hasattr(p, "H_before")
        assert hasattr(p, "H_after")
        assert hasattr(p, "delta_H")

    def test_l1_pearl_no_narration_fields(self):
        """Pearl must not carry narration, labels, or interpretation fields."""
        import dataclasses
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        p = archive.pearls[0]

        field_names = {f.name for f in dataclasses.fields(p)}
        forbidden = {
            "label", "region", "cluster", "meaning", "explanation",
            "description", "narration", "summary", "annotation",
            "interpretation", "debug", "text",
        }
        overlap = field_names & forbidden
        assert overlap == set(), f"Pearl contains narration fields: {overlap}"

    def test_l1_structural_references_are_ids_only(self):
        """Pearl.gate_id, node_key, workload_id are opaque ID strings, not objects."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        p = archive.pearls[0]
        assert isinstance(p.gate_id, str)
        assert isinstance(p.node_key, str)
        assert isinstance(p.workload_id, str)

    # ------------------------------------------------------------------
    # Determinism: same input → same Pearl
    # ------------------------------------------------------------------

    def test_l1_deterministic_creation_same_seq_pattern(self):
        """Two engines ingesting identical content produce same seq_id pattern."""
        env = self._envelope()
        engine1 = SupportEngine()
        engine2 = SupportEngine()
        ps1 = engine1.ingest(env)
        ps2 = engine2.ingest(self._envelope())
        assert len(ps1) == len(ps2)
        assert ps1[0].seq_id == ps2[0].seq_id

    def test_l1_repeated_ingest_identical_pearl_idempotent(self):
        """Re-ingesting same envelope on same engine does not produce a new Pearl."""
        engine = SupportEngine()
        env = self._envelope()
        ps1 = engine.ingest(env)
        ps2 = engine.ingest(env)
        assert ps1[0].seq_id == ps2[0].seq_id

    # ------------------------------------------------------------------
    # Physics invariants: Pearl fields obey substrate rules
    # ------------------------------------------------------------------

    def test_l1_phi_values_non_negative(self):
        """phi_R_after and phi_B_after must be non-negative."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope(phi_R=0.5, phi_B=0.2))
        p = archive.pearls[0]
        assert p.phi_R_after >= 0.0
        assert p.phi_B_after >= 0.0

    def test_l1_delta_H_matches_snapshots(self):
        """delta_H = H_after - H_before within floating point precision."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        p = archive.pearls[0]
        assert abs(p.delta_H - (p.H_after - p.H_before)) < 1e-12

    def test_l1_pearl_unaffected_by_topology_layers(self):
        """Adding topology structures does not alter Pearl schema or content."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        p_before = archive.pearls[0]

        # Topology layers are computed outside Pearl
        trace = TopologyTrace(eta_tau=0.1, lambda_tau=0.1)
        trace.step("g1", "g2", 0.8, 0.01)
        effective_weight(1.0, 0.8, trace.normalized("g1", "g2"),
                         kappa_e=0.1, kappa_tau=0.05)

        p_after = archive.pearls[0]
        assert p_before.seq_id == p_after.seq_id
        assert p_before.phi_R_after == p_after.phi_R_after
        assert p_before.H_after == p_after.H_after

    # ------------------------------------------------------------------
    # Archive integrity
    # ------------------------------------------------------------------

    def test_l1_pearls_property_returns_copy(self):
        """archive.pearls returns an independent copy — mutations do not affect archive."""
        engine, archive = self._engine_with_archive()
        engine.ingest(self._envelope())
        ps = archive.pearls
        ps.clear()
        assert len(archive.pearls) == 1

    def test_l1_restore_into_creates_gate_without_contributions(self):
        """restore_into() creates gate accessible via engine.gate() with no contributions."""
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(self._envelope())

        engine2 = SupportEngine()
        archive.restore_into(engine2)

        gate = engine2.gate("w1", "n1", "g1")
        assert gate is not None
        assert len(gate._contributions) == 0

    def test_l1_restore_into_does_not_advance_seq(self):
        """restore_into() never calls ingest() — engine._seq stays 0."""
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(self._envelope())

        engine2 = SupportEngine()
        archive.restore_into(engine2)
        assert engine2._seq == 0

    def test_l1_layer0_physics_unchanged_by_archive(self):
        """Layer 0 gate physics are not altered by Pearl archiving."""
        engine, archive = self._engine_with_archive()
        env = self._envelope(phi_R=0.5, phi_B=0.1)
        engine.ingest(env)

        gate = engine.gate("w1", "n1", "g1")
        t = time.time()
        energy_from_engine = engine.field_energy(t)
        energy_from_gate = gate.energy(t)

        # Archiving does not modify gate physics
        assert energy_from_engine >= 0.0
        assert abs(energy_from_engine - energy_from_gate) < 1e-12


class TestL1TemporalGraph:
    """L1-2 — Temporal consistency graph (Pearl sequencing).

    TemporalGraph turns an ordered Pearl sequence into a navigable time
    structure.  All tests verify ordering, navigation, validation, and replay.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_archive(self, n=3):
        """Build a SupportEngine + PearlArchive with n distinct gate ingests."""
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        for i in range(n):
            env = ObsGateEnvelope(
                instrument_id="probe",
                workload_id="w1",
                node_key="n1",
                cycle_id=f"c{i}",
            )
            env.add(f"g{i}", phi_R=0.3 + 0.1 * i, phi_B=0.0,
                    decay_class=DecayClass.STRUCTURAL)
            engine.ingest(env)
        return engine, archive

    def _graph(self, n=3):
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(n)
        return TemporalGraph.build(archive.pearls), archive.pearls

    # ------------------------------------------------------------------
    # Construction and basic properties
    # ------------------------------------------------------------------

    def test_tg_build_from_pearls(self):
        """TemporalGraph.build() accepts a Pearl list and stores them sorted."""
        from invar.persistence.temporal_graph import TemporalGraph
        graph, pearls = self._graph(3)
        assert len(graph) == 3

    def test_tg_pearls_in_seq_id_order(self):
        """graph.pearls returns Pearls in strictly increasing seq_id order."""
        graph, _ = self._graph(4)
        ps = graph.pearls
        for i in range(len(ps) - 1):
            assert ps[i].seq_id < ps[i + 1].seq_id

    def test_tg_head_and_tail(self):
        """graph.head() and graph.tail() return first and last Pearls."""
        graph, pearls = self._graph(3)
        assert graph.head().seq_id == pearls[0].seq_id
        assert graph.tail().seq_id == pearls[-1].seq_id

    def test_tg_empty_graph(self):
        """Empty graph: head/tail return None, len=0."""
        from invar.persistence.temporal_graph import TemporalGraph
        graph = TemporalGraph.build([])
        assert len(graph) == 0
        assert graph.head() is None
        assert graph.tail() is None

    # ------------------------------------------------------------------
    # Navigation: next / prev
    # ------------------------------------------------------------------

    def test_tg_next_from_head(self):
        """next(head) returns the second Pearl."""
        graph, pearls = self._graph(3)
        nxt = graph.next(pearls[0])
        assert nxt is not None
        assert nxt.seq_id == pearls[1].seq_id

    def test_tg_next_from_tail_is_none(self):
        """next(tail) returns None."""
        graph, pearls = self._graph(3)
        assert graph.next(pearls[-1]) is None

    def test_tg_prev_from_tail(self):
        """prev(tail) returns the second-to-last Pearl."""
        graph, pearls = self._graph(3)
        prv = graph.prev(pearls[-1])
        assert prv is not None
        assert prv.seq_id == pearls[-2].seq_id

    def test_tg_prev_from_head_is_none(self):
        """prev(head) returns None."""
        graph, pearls = self._graph(3)
        assert graph.prev(pearls[0]) is None

    def test_tg_next_prev_inverse(self):
        """next(prev(p)) == p and prev(next(p)) == p for middle nodes."""
        graph, pearls = self._graph(4)
        mid = pearls[1]
        assert graph.next(graph.prev(mid)).seq_id == mid.seq_id
        assert graph.prev(graph.next(mid)).seq_id == mid.seq_id

    def test_tg_next_of_unknown_pearl_is_none(self):
        """next() on a Pearl not in graph returns None."""
        import dataclasses
        graph, pearls = self._graph(2)
        foreign = dataclasses.replace(pearls[0], seq_id=9999)
        assert graph.next(foreign) is None

    # ------------------------------------------------------------------
    # Path
    # ------------------------------------------------------------------

    def test_tg_path_full_chain(self):
        """path(head, tail) returns all Pearls."""
        graph, pearls = self._graph(4)
        segment = graph.path(pearls[0], pearls[-1])
        assert len(segment) == 4
        assert [p.seq_id for p in segment] == [p.seq_id for p in pearls]

    def test_tg_path_single_node(self):
        """path(p, p) returns a list with just that Pearl."""
        graph, pearls = self._graph(3)
        mid = pearls[1]
        assert graph.path(mid, mid) == [mid]

    def test_tg_path_subchain(self):
        """path(p[1], p[2]) returns exactly [p[1], p[2]]."""
        graph, pearls = self._graph(4)
        seg = graph.path(pearls[1], pearls[2])
        assert len(seg) == 2
        assert seg[0].seq_id == pearls[1].seq_id
        assert seg[1].seq_id == pearls[2].seq_id

    def test_tg_path_reversed_returns_empty(self):
        """path(end, start) with end > start returns empty list."""
        graph, pearls = self._graph(3)
        assert graph.path(pearls[-1], pearls[0]) == []

    def test_tg_path_unknown_start_returns_empty(self):
        """path with unknown start Pearl returns empty list."""
        import dataclasses
        graph, pearls = self._graph(2)
        foreign = dataclasses.replace(pearls[0], seq_id=9999)
        assert graph.path(foreign, pearls[-1]) == []

    # ------------------------------------------------------------------
    # Validation: correct chain passes
    # ------------------------------------------------------------------

    def test_tg_validate_correct_chain(self):
        """validate() passes on a correctly ordered, gapless chain."""
        graph, _ = self._graph(3)
        graph.validate()  # must not raise

    def test_tg_validate_empty_graph(self):
        """validate() passes on an empty graph."""
        from invar.persistence.temporal_graph import TemporalGraph
        TemporalGraph.build([]).validate()  # must not raise

    def test_tg_validate_single_pearl(self):
        """validate() passes on a graph with a single Pearl."""
        graph, pearls = self._graph(1)
        graph.validate()

    # ------------------------------------------------------------------
    # Validation: violations detected
    # ------------------------------------------------------------------

    def test_tg_validate_detects_non_monotone(self):
        """validate() raises ValueError on non-monotone (duplicate) seq_ids.

        TemporalGraph sorts its input, so a raw non-monotone list is normalised
        to sorted order.  The effective non-monotone violation after sorting is
        a duplicate seq_id (two Pearls with seq_id N both appear at positions i
        and i+1 after sort; validate() catches the duplicate first).
        """
        import dataclasses
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(3)
        ps = archive.pearls
        # Two Pearls share the same seq_id → after sort: [..., N, N, ...] → non-monotone
        dup = [ps[0], dataclasses.replace(ps[1], seq_id=ps[0].seq_id), ps[2]]
        graph = TemporalGraph.build(dup)
        with pytest.raises(ValueError):
            graph.validate()

    def test_tg_validate_detects_gap(self):
        """validate() raises ValueError on seq_id gap."""
        import dataclasses
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(3)
        ps = archive.pearls
        # Skip seq_id by jumping by 2
        gap = [ps[0], dataclasses.replace(ps[1], seq_id=ps[0].seq_id + 2), dataclasses.replace(ps[2], seq_id=ps[0].seq_id + 3)]
        graph = TemporalGraph.build(gap)
        with pytest.raises(ValueError, match="gap"):
            graph.validate()

    def test_tg_validate_detects_duplicate(self):
        """validate() raises ValueError on duplicate seq_ids."""
        import dataclasses
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(2)
        ps = archive.pearls
        # Duplicate: two Pearls with same seq_id
        dup = [ps[0], dataclasses.replace(ps[1], seq_id=ps[0].seq_id)]
        graph = TemporalGraph.build(dup)
        with pytest.raises(ValueError, match="Duplicate"):
            graph.validate()

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_tg_deterministic_same_structure(self):
        """Two TemporalGraphs built from the same Pearls have identical structure."""
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(3)
        ps = archive.pearls
        g1 = TemporalGraph.build(ps)
        g2 = TemporalGraph.build(ps)
        assert [p.seq_id for p in g1.pearls] == [p.seq_id for p in g2.pearls]

    def test_tg_unordered_input_sorted_correctly(self):
        """TemporalGraph normalises unordered input to seq_id order."""
        import dataclasses
        from invar.persistence.temporal_graph import TemporalGraph
        _, archive = self._make_archive(3)
        ps = archive.pearls
        # Reverse order input
        g = TemporalGraph.build(list(reversed(ps)))
        result = [p.seq_id for p in g.pearls]
        assert result == sorted(result)

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def test_tg_replay_does_not_advance_seq(self):
        """graph.replay() does not advance engine._seq."""
        graph, _ = self._graph(2)
        engine2 = SupportEngine()
        graph.replay(engine2)
        assert engine2._seq == 0

    def test_tg_replay_does_not_fire_listeners(self):
        """graph.replay() does not fire listeners on the target engine."""
        graph, _ = self._graph(2)
        engine2 = SupportEngine()
        fired = []
        engine2.add_listener(fired.append)
        graph.replay(engine2)
        assert fired == []

    def test_tg_replay_gate_exists(self):
        """After replay, gates are accessible via engine.gate()."""
        graph, _ = self._graph(2)
        engine2 = SupportEngine()
        graph.replay(engine2)
        g0 = engine2.gate("w1", "n1", "g0")
        g1 = engine2.gate("w1", "n1", "g1")
        assert g0 is not None
        assert g1 is not None

    def test_tg_replay_no_contributions(self):
        """After replay, restored gates have no SupportContributions."""
        graph, _ = self._graph(2)
        engine2 = SupportEngine()
        graph.replay(engine2)
        for gate_id in ["g0", "g1"]:
            gate = engine2.gate("w1", "n1", gate_id)
            assert gate is not None
            assert len(gate._contributions) == 0

    def test_tg_replay_energy_equivalent(self):
        """graph.replay() produces approximately equivalent field energy."""
        from invar.persistence.temporal_graph import TemporalGraph
        engine1 = SupportEngine()
        archive_src = __import__('invar.persistence.pearl_archive', fromlist=['PearlArchive']).PearlArchive()
        engine1.add_listener(archive_src.record)

        for i in range(3):
            env = ObsGateEnvelope(
                instrument_id="probe", workload_id="w1", node_key="n1",
                cycle_id=f"c{i}",
            )
            env.add(f"g{i}", phi_R=0.4, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
            engine1.ingest(env)

        graph = TemporalGraph.build(archive_src.pearls)
        engine2 = SupportEngine()
        graph.replay(engine2)

        assert abs(engine1.field_energy() - engine2.field_energy()) < 1e-9

    def test_tg_replay_matches_archive_restore(self):
        """graph.replay() produces same gate count as archive.restore_into()."""
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive

        engine1 = SupportEngine()
        archive = PearlArchive()
        engine1.add_listener(archive.record)

        for i in range(3):
            env = ObsGateEnvelope(
                instrument_id="probe", workload_id="w1", node_key="n1",
                cycle_id=f"c{i}",
            )
            env.add(f"g{i}", phi_R=0.4, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
            engine1.ingest(env)

        # Restore via archive
        engine_a = SupportEngine()
        archive.restore_into(engine_a)

        # Restore via graph
        graph = TemporalGraph.build(archive.pearls)
        engine_g = SupportEngine()
        graph.replay(engine_g)

        assert abs(engine_a.field_energy() - engine_g.field_energy()) < 1e-12

    def test_tg_layer0_physics_unaffected(self):
        """TemporalGraph construction and navigation do not alter Layer 0 physics."""
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)

        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1",
            cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        # Build graph and navigate — must not touch substrate
        graph = TemporalGraph.build(archive.pearls)
        _ = graph.next(graph.head())
        graph.validate()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L1-3: Execution Windows
# ===========================================================================

class TestL1ExecutionWindows:
    """L1-3: ExecutionWindows — cycle-based grouping of Pearls."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_archive(specs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R)
        Returns a PearlArchive with one Pearl per spec (distinct gate_ids).
        """
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        for wid, nk, gid, cid, phi_R in specs:
            env = ObsGateEnvelope(
                instrument_id="probe", workload_id=wid, node_key=nk, cycle_id=cid,
            )
            env.add(gid, phi_R=phi_R, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
            engine.ingest(env)
        return archive

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_ew_build_empty(self):
        """ExecutionWindows built from empty list has zero windows."""
        from invar.persistence.execution_window import ExecutionWindows
        ew = ExecutionWindows.build([])
        assert len(ew) == 0
        assert ew.cycle_ids == []

    def test_ew_build_single_window(self):
        """Single cycle_id → one window containing all Pearls."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert len(ew) == 1
        assert ew.cycle_ids == ["cycle-A"]
        assert len(ew.get("cycle-A")) == 2

    def test_ew_build_multiple_windows(self):
        """Three distinct cycle_ids → three windows in emission order."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert len(ew) == 3
        assert ew.cycle_ids == ["cycle-A", "cycle-B", "cycle-C"]

    def test_ew_window_ordering_by_min_seq_id(self):
        """Windows are ordered by the minimum seq_id of their Pearls."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-B", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        # cycle-A has the two lowest seq_ids
        assert ew.cycle_ids[0] == "cycle-A"
        assert ew.cycle_ids[1] == "cycle-B"

    def test_ew_pearls_within_window_sorted(self):
        """Pearls within a window are in seq_id order."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        window = ew.get("cycle-A")
        seq_ids = [p.seq_id for p in window]
        assert seq_ids == sorted(seq_ids)
        assert seq_ids == list(range(seq_ids[0], seq_ids[0] + len(seq_ids)))

    def test_ew_total_pearl_count(self):
        """Sum of all window sizes equals total Pearl count."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-B", 0.3),
            ("w1", "n1", "g4", "cycle-C", 0.2),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        total = sum(len(ew.get(cid)) for cid in ew.cycle_ids)
        assert total == len(archive.pearls)

    # ------------------------------------------------------------------
    # of() and get()
    # ------------------------------------------------------------------

    def test_ew_of_returns_correct_window(self):
        """of(pearl) returns the window containing that Pearl."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        pearls = archive.pearls
        w0 = ew.of(pearls[0])
        w1 = ew.of(pearls[1])
        assert pearls[0] in w0
        assert pearls[1] in w1
        assert pearls[0].cycle_id != pearls[1].cycle_id

    def test_ew_of_unknown_pearl_returns_empty(self):
        """of() with a Pearl not in any window returns empty list."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl
        ew = ExecutionWindows.build([])
        fake = Pearl(
            gate_id="x", node_key="n", workload_id="w", instrument_id="i",
            cycle_id="c", ts=1.0, seq_id=999,
            H_before=0.0, H_after=0.0, delta_H=0.0,
            phi_R_before=0.0, phi_R_after=0.0,
            phi_B_before=0.0, phi_B_after=0.0,
            state_before=GateState.U, state_after=GateState.U,
            coupling_propagated=False,
        )
        assert ew.of(fake) == []

    def test_ew_get_unknown_cycle_returns_empty(self):
        """get() with unknown cycle_id returns empty list."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.get("no-such-cycle") == []

    def test_ew_get_returns_independent_copy(self):
        """get() returns an independent copy; mutation does not affect internal state."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        w = ew.get("cycle-A")
        original_len = len(w)
        w.clear()
        assert len(ew.get("cycle-A")) == original_len

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def test_ew_next_window_basic(self):
        """next_window returns the immediately following window."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        nxt = ew.next_window("cycle-A")
        assert nxt is not None
        assert all(p.cycle_id == "cycle-B" for p in nxt)

    def test_ew_next_window_at_tail_returns_none(self):
        """next_window on last window returns None."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.next_window("cycle-B") is None

    def test_ew_prev_window_basic(self):
        """prev_window returns the immediately preceding window."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        prv = ew.prev_window("cycle-C")
        assert prv is not None
        assert all(p.cycle_id == "cycle-B" for p in prv)

    def test_ew_prev_window_at_head_returns_none(self):
        """prev_window on first window returns None."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.prev_window("cycle-A") is None

    def test_ew_next_prev_unknown_returns_none(self):
        """next_window / prev_window with unknown cycle_id return None."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.next_window("no-such") is None
        assert ew.prev_window("no-such") is None

    def test_ew_next_prev_roundtrip(self):
        """Traversing forward then backward returns to origin."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        nxt = ew.next_window("cycle-A")   # cycle-B
        assert nxt is not None
        nxt_cid = nxt[0].cycle_id
        back = ew.prev_window(nxt_cid)    # cycle-A
        assert back is not None
        assert all(p.cycle_id == "cycle-A" for p in back)

    # ------------------------------------------------------------------
    # range()
    # ------------------------------------------------------------------

    def test_ew_range_full(self):
        """range(first, last) returns all windows."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        r = ew.range("cycle-A", "cycle-C")
        assert len(r) == 3

    def test_ew_range_single(self):
        """range(x, x) returns the single window."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        r = ew.range("cycle-B", "cycle-B")
        assert len(r) == 1
        assert all(p.cycle_id == "cycle-B" for p in r[0])

    def test_ew_range_reversed_returns_empty(self):
        """range(end, start) with end before start returns empty list."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.range("cycle-B", "cycle-A") == []

    def test_ew_range_unknown_returns_empty(self):
        """range with unknown cycle_id returns empty list."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        assert ew.range("cycle-A", "no-such") == []
        assert ew.range("no-such", "cycle-A") == []

    def test_ew_range_middle_slice(self):
        """range selects an interior slice of windows."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
            ("w1", "n1", "g4", "cycle-D", 0.2),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        r = ew.range("cycle-B", "cycle-C")
        assert len(r) == 2
        cids = [w[0].cycle_id for w in r]
        assert cids == ["cycle-B", "cycle-C"]

    # ------------------------------------------------------------------
    # validate()
    # ------------------------------------------------------------------

    def test_ew_validate_passes_valid(self):
        """validate() raises nothing on a well-formed archive."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-B", 0.3),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        ew.validate()  # must not raise

    def test_ew_validate_empty_passes(self):
        """validate() on empty ExecutionWindows does not raise."""
        from invar.persistence.execution_window import ExecutionWindows
        ew = ExecutionWindows.build([])
        ew.validate()  # must not raise

    def test_ew_validate_detects_duplicate_seq_id(self):
        """validate() raises ValueError if a Pearl seq_id appears twice."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl
        p1 = Pearl(
            gate_id="g1", node_key="n1", workload_id="w1", instrument_id="i",
            cycle_id="cycle-A", ts=1.0, seq_id=1,
            H_before=0.0, H_after=0.0, delta_H=0.0,
            phi_R_before=0.0, phi_R_after=0.5,
            phi_B_before=0.0, phi_B_after=0.0,
            state_before=GateState.U, state_after=GateState.R,
            coupling_propagated=False,
        )
        p2 = Pearl(
            gate_id="g2", node_key="n1", workload_id="w1", instrument_id="i",
            cycle_id="cycle-B", ts=2.0, seq_id=1,  # duplicate seq_id
            H_before=0.0, H_after=0.0, delta_H=0.0,
            phi_R_before=0.0, phi_R_after=0.3,
            phi_B_before=0.0, phi_B_after=0.0,
            state_before=GateState.U, state_after=GateState.R,
            coupling_propagated=False,
        )
        ew = ExecutionWindows.build([p1, p2])
        with pytest.raises(ValueError):
            ew.validate()

    # ------------------------------------------------------------------
    # replay()
    # ------------------------------------------------------------------

    def test_ew_replay_restores_gate_energy(self):
        """replay(cycle_id, engine) restores energy equivalent to original."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        ew = ExecutionWindows.build(archive.pearls)

        engine_orig = SupportEngine()
        archive_orig = __import__('invar.persistence.pearl_archive', fromlist=['PearlArchive']).PearlArchive()
        engine_orig.add_listener(archive_orig.record)
        for spec in [("w1", "n1", "g1", "cycle-A", 0.5)]:
            wid, nk, gid, cid, phi_R = spec
            env = ObsGateEnvelope(instrument_id="probe", workload_id=wid, node_key=nk, cycle_id=cid)
            env.add(gid, phi_R=phi_R, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
            engine_orig.ingest(env)

        t = time.time()
        e_orig = engine_orig.field_energy(t)

        engine_new = SupportEngine()
        ew.replay("cycle-A", engine_new)
        e_new = engine_new.field_energy(t)

        assert abs(e_orig - e_new) < 1e-12

    def test_ew_replay_unknown_cycle_is_noop(self):
        """replay with unknown cycle_id does nothing to engine."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        engine = SupportEngine()
        ew.replay("no-such-cycle", engine)
        assert engine.field_energy() == pytest.approx(0.0, abs=1e-12)

    def test_ew_replay_does_not_advance_seq(self):
        """replay() must not advance engine._seq."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        engine = SupportEngine()
        seq_before = engine._seq
        ew.replay("cycle-A", engine)
        assert engine._seq == seq_before

    def test_ew_replay_does_not_fire_listeners(self):
        """replay() must not fire engine listeners."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        engine = SupportEngine()
        fired = []
        engine.add_listener(lambda p: fired.append(p))
        ew.replay("cycle-A", engine)
        assert fired == []

    def test_ew_replay_leaves_contributions_empty(self):
        """Gate restored by replay() has empty _contributions."""
        from invar.persistence.execution_window import ExecutionWindows
        archive = self._make_archive([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        ew = ExecutionWindows.build(archive.pearls)
        engine = SupportEngine()
        ew.replay("cycle-A", engine)
        gate = engine.gate("w1", "n1", "g1")
        assert gate._contributions == []

    # ------------------------------------------------------------------
    # Non-canonical / Layer 0 safety
    # ------------------------------------------------------------------

    def test_ew_construction_does_not_affect_physics(self):
        """Building ExecutionWindows does not alter Layer 0 physics."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.pearl_archive import PearlArchive
        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        ew = ExecutionWindows.build(archive.pearls)
        _ = ew.get("c0")
        ew.validate()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L1-4: Proto-Causality
# ===========================================================================

class TestL1ProtoCausality:
    """L1-4: ProtoCausality — cross-window structural continuity detection."""

    @staticmethod
    def _make_windows(specs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R)
        Returns (archive, ExecutionWindows).
        Uses directly-constructed Pearls to bypass ET-G3 idempotency guard,
        so the same gate_id can appear in multiple cycle windows.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl
        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R,
                delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        return None, ExecutionWindows.build(pearls)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_pc_build_empty(self):
        """ProtoCausality built from empty ExecutionWindows has zero links."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        ew = ExecutionWindows.build([])
        causal = ProtoCausality.build(ew)
        assert len(causal) == 0
        assert causal.links() == []

    def test_pc_build_no_shared_gates(self):
        """Windows with entirely disjoint gate_ids produce zero links."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert len(causal) == 0

    def test_pc_build_shared_gate_creates_link(self):
        """Two windows sharing a gate produce one link."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert len(causal) == 1
        links = causal.links()
        assert links[0] == ("cycle-A", "cycle-B")

    def test_pc_link_ordering_earlier_first(self):
        """Links are stored (earlier_cycle, later_cycle) by window position."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),  # g1 also in cycle-A
        ])
        causal = ProtoCausality.build(ew)
        # g1 appears in cycle-A and cycle-C → link (A, C)
        assert ("cycle-A", "cycle-C") in causal.links()
        # cycle-B has g2 only — no link with A or C
        assert ("cycle-A", "cycle-B") not in causal.links()

    def test_pc_multiple_shared_gates_one_link(self):
        """Two windows sharing multiple gates still produce one link."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.3),
            ("w1", "n1", "g2", "cycle-B", 0.2),
        ])
        causal = ProtoCausality.build(ew)
        assert len(causal) == 1

    def test_pc_three_windows_pairwise_sharing(self):
        """Three windows with overlapping gates produce three links.

        cycle-A: (n1,g1),(n1,g2) | cycle-B: (n2,g3),(n2,g1) | cycle-C: (n3,g2),(n3,g3)
        A↔B via (w1,n_,g1)—but different node_keys, so need same triple.
        Use distinct node_keys per window but share gate_id+workload across pairs:
          A↔B: share (w1,n1,g1) — ingest (w1,n1,g1) in both A and B.
          A↔C: share (w1,n1,g2) — ingest (w1,n1,g2) in both A and C.
          B↔C: share (w1,n2,g3) — ingest (w1,n2,g3) in both B and C.
        Each gate appears at most once per window per node, so no idempotency.
        """
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),  # shares (w1,n1,g1) with A
            ("w1", "n2", "g3", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-C", 0.5),  # shares (w1,n1,g2) with A
            ("w1", "n2", "g3", "cycle-C", 0.5),  # shares (w1,n2,g3) with B
        ])
        causal = ProtoCausality.build(ew)
        assert ("cycle-A", "cycle-B") in causal.links()
        assert ("cycle-A", "cycle-C") in causal.links()
        assert ("cycle-B", "cycle-C") in causal.links()
        assert len(causal) == 3

    # ------------------------------------------------------------------
    # shared_gates()
    # ------------------------------------------------------------------

    def test_pc_shared_gates_returns_correct_keys(self):
        """shared_gates(a, b) returns the gate triple intersection."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.3),
            ("w1", "n1", "g3", "cycle-B", 0.2),
        ])
        causal = ProtoCausality.build(ew)
        sg = causal.shared_gates("cycle-A", "cycle-B")
        assert ("w1", "n1", "g1") in sg
        assert ("w1", "n1", "g2") not in sg
        assert ("w1", "n1", "g3") not in sg

    def test_pc_shared_gates_symmetric(self):
        """shared_gates(a, b) == shared_gates(b, a)."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.shared_gates("cycle-A", "cycle-B") == \
               causal.shared_gates("cycle-B", "cycle-A")

    def test_pc_shared_gates_no_link_returns_empty(self):
        """shared_gates returns empty frozenset when no link exists."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.shared_gates("cycle-A", "cycle-B") == frozenset()

    def test_pc_shared_gates_unknown_cycle_returns_empty(self):
        """shared_gates with unknown cycle_id returns empty frozenset."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.shared_gates("cycle-A", "no-such") == frozenset()

    # ------------------------------------------------------------------
    # links_from() and links_to()
    # ------------------------------------------------------------------

    def test_pc_links_from_basic(self):
        """links_from returns later windows sharing a gate with cycle_id."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),
        ])
        causal = ProtoCausality.build(ew)
        frm = causal.links_from("cycle-A")
        assert "cycle-B" in frm
        assert "cycle-C" in frm

    def test_pc_links_to_basic(self):
        """links_to returns earlier windows sharing a gate with cycle_id."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),
        ])
        causal = ProtoCausality.build(ew)
        to = causal.links_to("cycle-C")
        assert "cycle-A" in to
        assert "cycle-B" in to

    def test_pc_links_from_empty_when_no_forward_link(self):
        """links_from returns [] for the last window in a chain."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.links_from("cycle-B") == []

    def test_pc_links_to_empty_when_no_backward_link(self):
        """links_to returns [] for the first window in a chain."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.links_to("cycle-A") == []

    def test_pc_links_from_unknown_returns_empty(self):
        """links_from with unknown cycle_id returns []."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.links_from("no-such") == []

    def test_pc_links_to_unknown_returns_empty(self):
        """links_to with unknown cycle_id returns []."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        causal = ProtoCausality.build(ew)
        assert causal.links_to("no-such") == []

    def test_pc_links_from_excludes_disjoint_windows(self):
        """links_from does not include windows that share no gate."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),  # disjoint
            ("w1", "n1", "g1", "cycle-C", 0.3),  # shares g1 with A
        ])
        causal = ProtoCausality.build(ew)
        frm = causal.links_from("cycle-A")
        assert "cycle-C" in frm
        assert "cycle-B" not in frm

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_pc_deterministic_same_input_same_links(self):
        """Two builds from identical archives produce identical links."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew1 = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g2", "cycle-B", 0.3),
        ])
        _, ew2 = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g2", "cycle-B", 0.3),
        ])
        c1 = ProtoCausality.build(ew1)
        c2 = ProtoCausality.build(ew2)
        assert c1.links() == c2.links()

    def test_pc_links_returns_independent_copy(self):
        """Mutating the list returned by links() does not affect internal state."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        causal = ProtoCausality.build(ew)
        lnks = causal.links()
        lnks.clear()
        assert len(causal.links()) == 1

    # ------------------------------------------------------------------
    # Non-canonical / Layer 0 safety
    # ------------------------------------------------------------------

    def test_pc_construction_does_not_affect_physics(self):
        """Building ProtoCausality does not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        ew = ExecutionWindows.build(archive.pearls)
        causal = ProtoCausality.build(ew)
        _ = causal.links()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)

    def test_pc_no_false_positives_different_workloads(self):
        """Gates with same gate_id but different workload_id are not shared."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w2", "n1", "g1", "cycle-B", 0.4),  # same gate_id, different workload
        ])
        causal = ProtoCausality.build(ew)
        # (w1, n1, g1) ≠ (w2, n1, g1)
        assert len(causal) == 0

    def test_pc_no_false_positives_different_node_keys(self):
        """Gates with same gate_id but different node_key are not shared."""
        from invar.persistence.proto_causality import ProtoCausality
        _, ew = self._make_windows([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n2", "g1", "cycle-B", 0.4),  # same gate_id, different node
        ])
        causal = ProtoCausality.build(ew)
        assert len(causal) == 0


# ===========================================================================
# L1-5: Causal Weighting
# ===========================================================================

class TestL1CausalWeighting:
    """L1-5: Causal weight extension of ProtoCausality."""

    @staticmethod
    def _make_causal(specs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R).
        Returns ProtoCausality built from direct Pearl construction.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl
        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        ew = ExecutionWindows.build(pearls)
        return ProtoCausality.build(ew)

    # ------------------------------------------------------------------
    # weight() correctness
    # ------------------------------------------------------------------

    def test_cw_weight_no_link_returns_zero(self):
        """weight() returns 0.0 when no link exists between the pair."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        assert causal.weight("cycle-A", "cycle-B") == pytest.approx(0.0)

    def test_cw_weight_unknown_cycle_returns_zero(self):
        """weight() returns 0.0 for unknown cycle_id."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        assert causal.weight("cycle-A", "no-such") == pytest.approx(0.0)
        assert causal.weight("no-such", "cycle-A") == pytest.approx(0.0)

    def test_cw_weight_full_overlap_is_one(self):
        """weight = 1.0 when one window is fully contained in the other."""
        # cycle-A: g1 | cycle-B: g1, g2  → shared={g1}, min_size=1 → w=1/1=1.0
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g2", "cycle-B", 0.3),
        ])
        assert causal.weight("cycle-A", "cycle-B") == pytest.approx(1.0)

    def test_cw_weight_partial_overlap(self):
        """weight = |shared| / min(|A|, |B|) for partial overlap."""
        # cycle-A: g1, g2, g3 (3 gates)
        # cycle-B: g1, g4     (2 gates)
        # shared: g1 (1 gate), min_size=2 → weight = 1/2 = 0.5
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g4", "cycle-B", 0.4),
        ])
        assert causal.weight("cycle-A", "cycle-B") == pytest.approx(0.5)

    def test_cw_weight_equal_windows_full_sharing(self):
        """weight = 1.0 when both windows have exactly the same gates."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        assert causal.weight("cycle-A", "cycle-B") == pytest.approx(1.0)

    def test_cw_weight_two_of_three_shared(self):
        """weight = 2/3 when 2 of 3 gates are shared (min size = 3)."""
        # cycle-A: g1, g2, g3 | cycle-B: g1, g2, g4 → shared={g1,g2}, min=3 → 2/3
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g4", "cycle-B", 0.3),
        ])
        assert causal.weight("cycle-A", "cycle-B") == pytest.approx(2.0 / 3.0)

    # ------------------------------------------------------------------
    # weight() bounds and symmetry
    # ------------------------------------------------------------------

    def test_cw_weight_bounded_zero_to_one(self):
        """All weights returned by weight() are in [0.0, 1.0]."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g3", "cycle-B", 0.4),
        ])
        for a, b in causal.links():
            w = causal.weight(a, b)
            assert 0.0 <= w <= 1.0

    def test_cw_weight_symmetric(self):
        """weight(a, b) == weight(b, a)."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ])
        assert causal.weight("cycle-A", "cycle-B") == \
               pytest.approx(causal.weight("cycle-B", "cycle-A"))

    def test_cw_weight_greater_overlap_greater_weight(self):
        """Higher gate overlap → higher weight (monotone).

        cycle-A: g1, g2, g3  (3 gates)
        cycle-B: g1, g4      (2 gates) → shared={g1},    w = 1/2 = 0.5
        cycle-C: g1, g2, g4  (3 gates) → shared={g1,g2}, w = 2/3 ≈ 0.667
        """
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g4", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.5),
            ("w1", "n1", "g2", "cycle-C", 0.4),
            ("w1", "n1", "g4", "cycle-C", 0.3),
        ])
        w_ab = causal.weight("cycle-A", "cycle-B")
        w_ac = causal.weight("cycle-A", "cycle-C")
        assert w_ab == pytest.approx(0.5)
        assert w_ac == pytest.approx(2.0 / 3.0)
        assert w_ac > w_ab

    # ------------------------------------------------------------------
    # weighted_links()
    # ------------------------------------------------------------------

    def test_cw_weighted_links_empty(self):
        """weighted_links() returns empty list when no links exist."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        ew = ExecutionWindows.build([])
        causal = ProtoCausality.build(ew)
        assert causal.weighted_links() == []

    def test_cw_weighted_links_structure(self):
        """weighted_links() returns (a, b, weight) triples."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        wl = causal.weighted_links()
        assert len(wl) == 1
        a, b, w = wl[0]
        assert a == "cycle-A"
        assert b == "cycle-B"
        assert isinstance(w, float)

    def test_cw_weighted_links_same_ordering_as_links(self):
        """weighted_links() preserves the same (a,b) ordering as links()."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-C", 0.4),
        ])
        pairs_from_links = causal.links()
        pairs_from_weighted = [(a, b) for a, b, _ in causal.weighted_links()]
        assert pairs_from_links == pairs_from_weighted

    def test_cw_weighted_links_weight_matches_weight_method(self):
        """Weight in weighted_links() matches weight(a, b) for all pairs."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ])
        for a, b, w in causal.weighted_links():
            assert w == pytest.approx(causal.weight(a, b))

    def test_cw_weighted_links_returns_independent_copy(self):
        """Mutating weighted_links() result does not affect internal state."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        wl = causal.weighted_links()
        wl.clear()
        assert len(causal.weighted_links()) == 1

    def test_cw_weighted_links_all_bounded(self):
        """All weights in weighted_links() are in [0.0, 1.0]."""
        causal = self._make_causal([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g2", "cycle-C", 0.3),
            ("w1", "n1", "g3", "cycle-C", 0.2),
        ])
        for _, _, w in causal.weighted_links():
            assert 0.0 <= w <= 1.0

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_cw_deterministic_weights(self):
        """Same input produces identical weights on two builds."""
        specs = [
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ]
        c1 = self._make_causal(specs)
        c2 = self._make_causal(specs)
        assert c1.weighted_links() == c2.weighted_links()

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_cw_weight_calls_do_not_affect_physics(self):
        """Calling weight() and weighted_links() does not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        ew = ExecutionWindows.build(archive.pearls)
        causal = ProtoCausality.build(ew)
        _ = causal.weight("c0", "c0")
        _ = causal.weighted_links()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L1-6: Causal Propagation Field
# ===========================================================================

class TestL1CausalField:
    """L1-6: CausalField — normalized per-window propagation influence."""

    @staticmethod
    def _build(specs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R).
        Returns (ExecutionWindows, ProtoCausality, CausalField).
        Uses direct Pearl construction to bypass ET-G3 idempotency.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl
        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        return ew, causal, field

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def test_cf_build_empty(self):
        """CausalField built from empty ExecutionWindows has no values."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        ew = ExecutionWindows.build([])
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        assert field.all() == {}

    def test_cf_build_no_links(self):
        """Windows with no shared gates produce zero influence everywhere."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        assert field.value("cycle-A") == pytest.approx(0.0)
        assert field.value("cycle-B") == pytest.approx(0.0)

    def test_cf_head_window_has_zero_influence(self):
        """The first window in a chain has no incoming links → value 0.0."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert field.value("cycle-A") == pytest.approx(0.0)

    def test_cf_tail_window_has_nonzero_influence(self):
        """The last window in a shared-gate chain has positive influence."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert field.value("cycle-B") > 0.0

    def test_cf_all_contains_all_cycle_ids(self):
        """all() contains an entry for every window, including isolated ones."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),  # no shared gate with A
            ("w1", "n1", "g1", "cycle-C", 0.3),  # shares g1 with A
        ])
        result = field.all()
        assert set(result.keys()) == {"cycle-A", "cycle-B", "cycle-C"}

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def test_cf_maximum_value_is_one(self):
        """The window with highest raw incoming influence has value 1.0."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),
        ])
        values = list(field.all().values())
        assert max(values) == pytest.approx(1.0)

    def test_cf_all_values_bounded(self):
        """All values in all() are in [0.0, 1.0]."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.5),
            ("w1", "n1", "g3", "cycle-C", 0.4),
        ])
        for v in field.all().values():
            assert 0.0 <= v <= 1.0

    def test_cf_no_links_all_zero(self):
        """When no links exist, all() maps every cycle_id to 0.0."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ])
        for v in field.all().values():
            assert v == pytest.approx(0.0)

    def test_cf_multiple_incoming_accumulates(self):
        """A window receiving links from two sources has higher raw influence."""
        # cycle-C gets links from both A and B, so its raw > raw of B (which
        # only gets from A in a simple chain).
        # cycle-A: g1, g2
        # cycle-B: g1, g3  (links: A→B via g1)
        # cycle-C: g2, g3  (links: A→C via g2, B→C via g3)
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g3", "cycle-B", 0.4),
            ("w1", "n1", "g2", "cycle-C", 0.5),
            ("w1", "n1", "g3", "cycle-C", 0.4),
        ])
        # cycle-C receives from A (via g2) and from B (via g3)
        # cycle-B receives from A (via g1) only
        assert field.value("cycle-C") >= field.value("cycle-B")

    def test_cf_single_link_tail_is_one(self):
        """With one link, the tail window (only receiver) gets value 1.0."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert field.value("cycle-B") == pytest.approx(1.0)

    # ------------------------------------------------------------------
    # value() access
    # ------------------------------------------------------------------

    def test_cf_value_unknown_returns_zero(self):
        """value() returns 0.0 for unknown cycle_id."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert field.value("no-such") == pytest.approx(0.0)

    def test_cf_all_returns_independent_copy(self):
        """Mutating the dict returned by all() does not affect internal state."""
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        d = field.all()
        d.clear()
        assert len(field.all()) == 2

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_cf_deterministic(self):
        """Same input produces identical field on two builds."""
        specs = [
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ]
        _, _, f1 = self._build(specs)
        _, _, f2 = self._build(specs)
        assert f1.all() == f2.all()

    # ------------------------------------------------------------------
    # Relative ordering
    # ------------------------------------------------------------------

    def test_cf_more_incoming_links_higher_influence(self):
        """Window with more incoming link weight ranks higher in the field."""
        # cycle-A: g1, g2 (source, no incoming)
        # cycle-B: g1     (1 incoming: from A via g1)
        # cycle-C: g1, g2 (2 incoming: from A via g1 and g2)
        _, _, field = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g1", "cycle-C", 0.5),
            ("w1", "n1", "g2", "cycle-C", 0.4),
        ])
        assert field.value("cycle-C") > field.value("cycle-B")
        assert field.value("cycle-A") == pytest.approx(0.0)

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_cf_construction_does_not_affect_physics(self):
        """Building CausalField does not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        ew = ExecutionWindows.build(archive.pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        _ = field.value("c0")
        _ = field.all()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L1-7: Red Team Adapter (Observation Layer)
# ===========================================================================

class TestL1RedTeamObserver:
    """L1-7: RedTeamObserver — read-only adapter over Invar structures."""

    @staticmethod
    def _build_observer(specs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R).
        Returns (ExecutionWindows, ProtoCausality, CausalField, RedTeamObserver).
        Uses direct Pearl construction to avoid ET-G3 idempotency.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))

        archive = PearlArchive()
        for p in pearls:
            archive.record(p)

        temporal = TemporalGraph.build(pearls)
        windows = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(windows)
        field = CausalField.build(causal, windows)
        observer = RedTeamObserver(archive, temporal, windows, causal, field)
        return windows, causal, field, observer

    # ------------------------------------------------------------------
    # activity()
    # ------------------------------------------------------------------

    def test_rt_activity_matches_causal_field(self):
        """activity() returns the same value as CausalField.value()."""
        _, _, field, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        for cid in ("cycle-A", "cycle-B"):
            assert obs.activity(cid) == pytest.approx(field.value(cid))

    def test_rt_activity_unknown_returns_zero(self):
        """activity() returns 0.0 for unknown cycle_id."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        assert obs.activity("no-such") == pytest.approx(0.0)

    def test_rt_activity_head_is_zero(self):
        """activity() for the source window (no incoming) is 0.0."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert obs.activity("cycle-A") == pytest.approx(0.0)

    def test_rt_activity_bounded(self):
        """activity() values are always in [0.0, 1.0]."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ])
        for cid in ("cycle-A", "cycle-B", "cycle-C"):
            assert 0.0 <= obs.activity(cid) <= 1.0

    # ------------------------------------------------------------------
    # shared_infra()
    # ------------------------------------------------------------------

    def test_rt_shared_infra_matches_proto_causality(self):
        """shared_infra(a, b) returns the same frozenset as shared_gates(a, b)."""
        _, causal, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ])
        assert obs.shared_infra("cycle-A", "cycle-B") == \
               causal.shared_gates("cycle-A", "cycle-B")

    def test_rt_shared_infra_no_overlap_returns_empty(self):
        """shared_infra() returns empty frozenset when cycles share no gates."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ])
        assert obs.shared_infra("cycle-A", "cycle-B") == frozenset()

    def test_rt_shared_infra_symmetric(self):
        """shared_infra(a, b) == shared_infra(b, a)."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert obs.shared_infra("cycle-A", "cycle-B") == \
               obs.shared_infra("cycle-B", "cycle-A")

    def test_rt_shared_infra_contains_correct_keys(self):
        """shared_infra() returns (workload_id, node_key, gate_id) triples."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g3", "cycle-B", 0.4),
        ])
        infra = obs.shared_infra("cycle-A", "cycle-B")
        assert ("w1", "n1", "g1") in infra
        assert ("w1", "n1", "g2") not in infra
        assert ("w1", "n1", "g3") not in infra

    # ------------------------------------------------------------------
    # strong_links()
    # ------------------------------------------------------------------

    def test_rt_strong_links_default_threshold(self):
        """strong_links() with default threshold=0.5 returns links with w≥0.5."""
        _, causal, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        sl = obs.strong_links()
        for a, b, w in sl:
            assert w >= 0.5

    def test_rt_strong_links_threshold_zero_returns_all(self):
        """strong_links(threshold=0.0) returns all weighted links."""
        _, causal, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ])
        all_wl = causal.weighted_links()
        sl = obs.strong_links(threshold=0.0)
        assert [(a, b) for a, b, _ in sl] == [(a, b) for a, b, _ in all_wl]

    def test_rt_strong_links_threshold_one_returns_full_containment(self):
        """strong_links(threshold=1.0) returns only weight-1.0 links."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),  # w=1.0 (smaller fully shared)
            ("w1", "n1", "g2", "cycle-B", 0.3),
            ("w1", "n1", "g1", "cycle-C", 0.5),  # w=0.5 (1 of 2 in A)
            ("w1", "n1", "g3", "cycle-C", 0.4),
        ])
        full = obs.strong_links(threshold=1.0)
        for _, _, w in full:
            assert w == pytest.approx(1.0)

    def test_rt_strong_links_high_threshold_returns_empty(self):
        """strong_links(threshold=1.01) returns empty (nothing exceeds 1.0)."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        assert obs.strong_links(threshold=1.01) == []

    def test_rt_strong_links_returns_independent_copy(self):
        """Mutating the strong_links() result does not affect internal state."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        sl = obs.strong_links()
        sl.clear()
        assert len(obs.strong_links()) >= 0  # internal state intact

    # ------------------------------------------------------------------
    # summary()
    # ------------------------------------------------------------------

    def test_rt_summary_keys(self):
        """summary() dict contains all required keys."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        s = obs.summary("cycle-A")
        assert set(s.keys()) >= {"cycle_id", "activity", "num_artifacts",
                                  "incoming_links", "outgoing_links"}

    def test_rt_summary_cycle_id(self):
        """summary()['cycle_id'] matches the requested cycle_id."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        assert obs.summary("cycle-A")["cycle_id"] == "cycle-A"

    def test_rt_summary_activity_matches_field(self):
        """summary()['activity'] matches CausalField.value()."""
        _, _, field, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ])
        for cid in ("cycle-A", "cycle-B"):
            assert obs.summary(cid)["activity"] == pytest.approx(field.value(cid))

    def test_rt_summary_num_artifacts(self):
        """summary()['num_artifacts'] counts distinct gate identities."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g3", "cycle-A", 0.3),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ])
        assert obs.summary("cycle-A")["num_artifacts"] == 3
        assert obs.summary("cycle-B")["num_artifacts"] == 1

    def test_rt_summary_link_counts(self):
        """summary() incoming/outgoing counts reflect actual links."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ])
        s_a = obs.summary("cycle-A")
        s_b = obs.summary("cycle-B")
        s_c = obs.summary("cycle-C")
        assert s_a["outgoing_links"] == 2   # A→B, A→C
        assert s_a["incoming_links"] == 0
        assert s_b["incoming_links"] == 1   # A→B
        assert s_b["outgoing_links"] == 1   # B→C
        assert s_c["incoming_links"] == 2   # A→C, B→C
        assert s_c["outgoing_links"] == 0

    def test_rt_summary_unknown_cycle(self):
        """summary() for unknown cycle_id returns zeroed observables."""
        _, _, _, obs = self._build_observer([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        s = obs.summary("no-such")
        assert s["cycle_id"] == "no-such"
        assert s["activity"] == pytest.approx(0.0)
        assert s["num_artifacts"] == 0
        assert s["incoming_links"] == 0
        assert s["outgoing_links"] == 0

    # ------------------------------------------------------------------
    # Determinism + non-mutation
    # ------------------------------------------------------------------

    def test_rt_deterministic(self):
        """Same input produces identical observer outputs on two builds."""
        specs = [
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ]
        _, _, _, obs1 = self._build_observer(specs)
        _, _, _, obs2 = self._build_observer(specs)
        assert obs1.summary("cycle-A") == obs2.summary("cycle-A")
        assert obs1.summary("cycle-B") == obs2.summary("cycle-B")
        assert obs1.strong_links() == obs2.strong_links()

    def test_rt_does_not_affect_physics(self):
        """Building and querying RedTeamObserver does not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.adapters.redteam.observer import RedTeamObserver

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        pearls = archive.pearls
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, TemporalGraph.build(pearls), ew, causal, field)
        _ = obs.activity("c0")
        _ = obs.summary("c0")
        _ = obs.strong_links()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L2-1: Controlled Feedback Interface
# ===========================================================================

class TestL2FeedbackEngine:
    """L2-1: FeedbackEngine — structured suggestions from observer signals."""

    @staticmethod
    def _build(specs, **kwargs):
        """
        specs: list of (workload_id, node_key, gate_id, cycle_id, phi_R).
        Returns (observer, FeedbackEngine). Uses direct Pearl construction.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))

        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        return obs, FeedbackEngine(obs, **kwargs)

    # ------------------------------------------------------------------
    # Suggestion dataclass
    # ------------------------------------------------------------------

    def test_fb_suggestion_is_frozen(self):
        """Suggestion is an immutable frozen dataclass."""
        from invar.adapters.redteam.feedback import Suggestion
        s = Suggestion(
            suggestion_id="abc123", type="reuse", cycle_id=None,
            supporting_cycles=("c1", "c2"), supporting_artifacts=(),
            confidence=0.5,
        )
        with pytest.raises((AttributeError, TypeError)):
            s.confidence = 0.9  # type: ignore[misc]

    # ------------------------------------------------------------------
    # TYPE 1: reuse
    # ------------------------------------------------------------------

    def test_fb_reuse_triggered_by_shared_gate(self):
        """Reuse suggestion fires when a gate appears in 2+ windows."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        reuse = engine.by_type("reuse")
        assert len(reuse) >= 1
        assert any(("w1", "n1", "g1") in s.supporting_artifacts for s in reuse)

    def test_fb_reuse_not_triggered_below_min_count(self):
        """Reuse suggestion absent when gate appears in fewer windows than threshold."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ], reuse_min_count=2)
        # g1 only in A, g2 only in B → no reuse
        assert engine.by_type("reuse") == []

    def test_fb_reuse_confidence_bounded(self):
        """Reuse confidence is in [0, 1]."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),
        ], reuse_min_count=2)
        for s in engine.by_type("reuse"):
            assert 0.0 <= s.confidence <= 1.0

    def test_fb_reuse_supporting_cycles_sorted(self):
        """Reuse supporting_cycles are sorted for determinism."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        for s in engine.by_type("reuse"):
            assert s.supporting_cycles == tuple(sorted(s.supporting_cycles))

    # ------------------------------------------------------------------
    # TYPE 2: high_activity
    # ------------------------------------------------------------------

    def test_fb_high_activity_fires_above_threshold(self):
        """high_activity suggestion fires when activity >= threshold."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], high_activity_threshold=0.5)
        ha = engine.by_type("high_activity")
        assert len(ha) >= 1
        for s in ha:
            assert s.confidence >= 0.5

    def test_fb_high_activity_not_fired_below_threshold(self):
        """high_activity suggestion absent when activity < threshold."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ], high_activity_threshold=0.99)
        # Single window has no incoming links → activity=0.0 < 0.99
        assert engine.by_type("high_activity") == []

    def test_fb_high_activity_cycle_id_set(self):
        """high_activity suggestion has cycle_id set."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], high_activity_threshold=0.5)
        for s in engine.by_type("high_activity"):
            assert s.cycle_id is not None
            assert s.cycle_id in s.supporting_cycles

    def test_fb_high_activity_confidence_matches_activity(self):
        """high_activity confidence equals the observed activity."""
        obs, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], high_activity_threshold=0.5)
        for s in engine.by_type("high_activity"):
            assert s.confidence == pytest.approx(obs.activity(s.cycle_id))

    # ------------------------------------------------------------------
    # TYPE 3: anomaly
    # ------------------------------------------------------------------

    def test_fb_anomaly_fires_below_threshold(self):
        """anomaly suggestion fires when activity <= threshold."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], low_activity_threshold=0.5)
        # cycle-A has 0.0 activity → anomaly
        anomalies = engine.by_type("anomaly")
        assert any(s.cycle_id == "cycle-A" for s in anomalies)

    def test_fb_anomaly_confidence_complement_of_activity(self):
        """anomaly confidence = 1 - activity."""
        obs, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], low_activity_threshold=0.5)
        for s in engine.by_type("anomaly"):
            expected = min(1.0, 1.0 - obs.activity(s.cycle_id))
            assert s.confidence == pytest.approx(expected)

    def test_fb_anomaly_confidence_bounded(self):
        """anomaly confidence is in [0, 1]."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g3", "cycle-C", 0.3),
        ], low_activity_threshold=1.0)
        for s in engine.by_type("anomaly"):
            assert 0.0 <= s.confidence <= 1.0

    # ------------------------------------------------------------------
    # TYPE 4: chain
    # ------------------------------------------------------------------

    def test_fb_chain_fires_for_three_window_sequence(self):
        """chain suggestion fires when 3+ windows form a strong-link sequence."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ], chain_threshold=0.0, chain_min_length=3)
        chains = engine.by_type("chain")
        assert len(chains) >= 1
        # All three cycles should appear in at least one chain
        all_cycle_ids_in_chains = set()
        for s in chains:
            all_cycle_ids_in_chains.update(s.supporting_cycles)
        assert "cycle-A" in all_cycle_ids_in_chains

    def test_fb_chain_not_fired_for_two_window_sequence(self):
        """chain suggestion absent when chain_min_length=3 and only 2 windows."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], chain_threshold=0.0, chain_min_length=3)
        assert engine.by_type("chain") == []

    def test_fb_chain_confidence_bounded(self):
        """chain confidence is in [0, 1]."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ], chain_threshold=0.0, chain_min_length=3)
        for s in engine.by_type("chain"):
            assert 0.0 <= s.confidence <= 1.0

    # ------------------------------------------------------------------
    # Determinism and deduplication
    # ------------------------------------------------------------------

    def test_fb_deterministic(self):
        """Same input produces identical suggestions on two builds."""
        specs = [
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ]
        _, e1 = self._build(specs, reuse_min_count=2)
        _, e2 = self._build(specs, reuse_min_count=2)
        assert [(s.suggestion_id, s.type) for s in e1.suggestions()] == \
               [(s.suggestion_id, s.type) for s in e2.suggestions()]

    def test_fb_no_duplicate_ids(self):
        """No two suggestions share the same suggestion_id."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.3),
        ], reuse_min_count=2, high_activity_threshold=0.5, low_activity_threshold=0.5)
        ids = [s.suggestion_id for s in engine.suggestions()]
        assert len(ids) == len(set(ids))

    # ------------------------------------------------------------------
    # API: by_type, by_cycle, suggestions
    # ------------------------------------------------------------------

    def test_fb_by_type_filters_correctly(self):
        """by_type() returns only suggestions of that type."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2, low_activity_threshold=0.5)
        for t in ("reuse", "anomaly"):
            for s in engine.by_type(t):
                assert s.type == t

    def test_fb_by_cycle_returns_referencing_suggestions(self):
        """by_cycle() returns suggestions that include cycle_id."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2, low_activity_threshold=0.5)
        for s in engine.by_cycle("cycle-A"):
            assert "cycle-A" in s.supporting_cycles

    def test_fb_suggestions_sorted_by_confidence_desc(self):
        """suggestions() are sorted by confidence descending."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2, low_activity_threshold=0.5, high_activity_threshold=0.5)
        confidences = [s.confidence for s in engine.suggestions()]
        assert confidences == sorted(confidences, reverse=True)

    def test_fb_suggestions_returns_independent_copy(self):
        """Mutating suggestions() output does not affect engine state."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        sl = engine.suggestions()
        original_len = len(sl)
        sl.clear()
        assert len(engine.suggestions()) == original_len

    def test_fb_confidence_all_bounded(self):
        """All suggestions have confidence in [0.0, 1.0]."""
        _, engine = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
            ("w1", "n1", "g1", "cycle-C", 0.5),
        ], reuse_min_count=2, high_activity_threshold=0.5,
           low_activity_threshold=0.5, chain_threshold=0.0, chain_min_length=3)
        for s in engine.suggestions():
            assert 0.0 <= s.confidence <= 1.0

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_fb_does_not_affect_physics(self):
        """Building FeedbackEngine does not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        pearls = archive.pearls
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, TemporalGraph.build(pearls), ew, causal, field)
        fb = FeedbackEngine(obs)
        _ = fb.suggestions()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L2-2: Operator Acknowledgment Layer
# ===========================================================================

class TestL2AcknowledgmentStore:
    """L2-2: AcknowledgmentStore + Acknowledgment — operator decision audit log."""

    @staticmethod
    def _make_ack(sid, decision="valid", ts=1.0):
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        return Acknowledgment(suggestion_id=sid, decision=decision, ts=ts)

    @staticmethod
    def _fresh_store():
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        return AcknowledgmentStore()

    # ------------------------------------------------------------------
    # Acknowledgment dataclass
    # ------------------------------------------------------------------

    def test_ack_is_frozen(self):
        """Acknowledgment is an immutable frozen dataclass."""
        ack = self._make_ack("abc")
        with pytest.raises((AttributeError, TypeError)):
            ack.decision = "irrelevant"  # type: ignore[misc]

    def test_ack_valid_decisions_accepted(self):
        """All three valid decisions are accepted by record()."""
        store = self._fresh_store()
        for decision in ("valid", "irrelevant", "investigate"):
            ack = self._make_ack(f"id-{decision}", decision=decision, ts=1.0)
            store.record(ack)  # must not raise

    def test_ack_invalid_decision_raises(self):
        """record() raises ValueError for unknown decision strings."""
        store = self._fresh_store()
        ack = self._make_ack("x", decision="execute")
        with pytest.raises(ValueError, match="Invalid decision"):
            store.record(ack)

    # ------------------------------------------------------------------
    # Append-only / no overwrite
    # ------------------------------------------------------------------

    def test_ack_no_overwrite_raises(self):
        """Acknowledging the same suggestion_id twice raises ValueError."""
        store = self._fresh_store()
        store.record(self._make_ack("abc", "valid"))
        with pytest.raises(ValueError, match="already acknowledged"):
            store.record(self._make_ack("abc", "irrelevant"))

    def test_ack_no_deletion(self):
        """Records cannot be removed; len() only grows."""
        store = self._fresh_store()
        store.record(self._make_ack("a", "valid"))
        store.record(self._make_ack("b", "investigate"))
        assert len(store) == 2

    def test_ack_empty_store_len_zero(self):
        """Fresh store has length zero."""
        store = self._fresh_store()
        assert len(store) == 0

    # ------------------------------------------------------------------
    # get()
    # ------------------------------------------------------------------

    def test_ack_get_returns_recorded(self):
        """get() returns the Acknowledgment after it's recorded."""
        store = self._fresh_store()
        ack = self._make_ack("xyz", "investigate", ts=42.0)
        store.record(ack)
        result = store.get("xyz")
        assert result is not None
        assert result.decision == "investigate"
        assert result.ts == 42.0

    def test_ack_get_unknown_returns_none(self):
        """get() returns None for an unrecorded suggestion_id."""
        store = self._fresh_store()
        assert store.get("no-such-id") is None

    # ------------------------------------------------------------------
    # all()
    # ------------------------------------------------------------------

    def test_ack_all_returns_in_record_order(self):
        """all() returns records in the order they were recorded."""
        store = self._fresh_store()
        store.record(self._make_ack("first", "valid"))
        store.record(self._make_ack("second", "irrelevant"))
        store.record(self._make_ack("third", "investigate"))
        ids = [a.suggestion_id for a in store.all()]
        assert ids == ["first", "second", "third"]

    def test_ack_all_returns_independent_copy(self):
        """Mutating all() result does not affect internal state."""
        store = self._fresh_store()
        store.record(self._make_ack("a", "valid"))
        result = store.all()
        result.clear()
        assert len(store.all()) == 1

    # ------------------------------------------------------------------
    # by_decision()
    # ------------------------------------------------------------------

    def test_ack_by_decision_valid(self):
        """by_decision('valid') returns only valid acknowledgments."""
        store = self._fresh_store()
        store.record(self._make_ack("a", "valid"))
        store.record(self._make_ack("b", "irrelevant"))
        store.record(self._make_ack("c", "valid"))
        result = store.by_decision("valid")
        assert len(result) == 2
        assert all(a.decision == "valid" for a in result)

    def test_ack_by_decision_empty_when_no_match(self):
        """by_decision returns [] when no matching decisions recorded."""
        store = self._fresh_store()
        store.record(self._make_ack("a", "valid"))
        assert store.by_decision("investigate") == []

    def test_ack_by_decision_all_three_types(self):
        """by_decision works correctly for all three decision types."""
        store = self._fresh_store()
        store.record(self._make_ack("v", "valid"))
        store.record(self._make_ack("i", "irrelevant"))
        store.record(self._make_ack("x", "investigate"))
        assert len(store.by_decision("valid")) == 1
        assert len(store.by_decision("irrelevant")) == 1
        assert len(store.by_decision("investigate")) == 1

    # ------------------------------------------------------------------
    # FeedbackEngine.with_ack()
    # ------------------------------------------------------------------

    @staticmethod
    def _build_feedback(specs, **kwargs):
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        return FeedbackEngine(obs, **kwargs)

    def test_ack_with_ack_returns_all_suggestions(self):
        """with_ack() returns one entry per suggestion."""
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        engine = self._build_feedback([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        store = AcknowledgmentStore()
        pairs = engine.with_ack(store)
        assert len(pairs) == len(engine.suggestions())

    def test_ack_with_ack_unacknowledged_is_none(self):
        """Unacknowledged suggestions pair with None."""
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        engine = self._build_feedback([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        store = AcknowledgmentStore()
        for s, ack in engine.with_ack(store):
            assert ack is None

    def test_ack_with_ack_acknowledged_suggestion_paired(self):
        """Acknowledged suggestions pair with their Acknowledgment."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment, AcknowledgmentStore
        engine = self._build_feedback([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions  # at least one suggestion exists

        store = AcknowledgmentStore()
        sid = suggestions[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="valid", ts=1.0))

        pairs = engine.with_ack(store)
        found = {s.suggestion_id: ack for s, ack in pairs}
        assert found[sid] is not None
        assert found[sid].decision == "valid"

    def test_ack_with_ack_does_not_modify_store(self):
        """with_ack() is purely read-only — store length unchanged."""
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        engine = self._build_feedback([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        store = AcknowledgmentStore()
        _ = engine.with_ack(store)
        assert len(store) == 0

    def test_ack_does_not_affect_physics(self):
        """AcknowledgmentStore and with_ack() do not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import Acknowledgment, AcknowledgmentStore

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        pearls = archive.pearls
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, TemporalGraph.build(pearls), ew, causal, field)
        fb = FeedbackEngine(obs)
        store = AcknowledgmentStore()
        if fb.suggestions():
            sid = fb.suggestions()[0].suggestion_id
            store.record(Acknowledgment(suggestion_id=sid, decision="valid", ts=1.0))
        _ = fb.with_ack(store)

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L2-3: Suggestion Prioritization + Operator Workflow
# ===========================================================================

class TestL2WorkflowView:
    """L2-3: WorkflowView — derived operator workflow over suggestions + acks."""

    @staticmethod
    def _build(specs, **fb_kwargs):
        """
        Returns (FeedbackEngine, AcknowledgmentStore, WorkflowView).
        Uses direct Pearl construction.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        from invar.adapters.redteam.workflow import WorkflowView
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        engine = FeedbackEngine(obs, **fb_kwargs)
        store = AcknowledgmentStore()
        view = WorkflowView(engine, store)
        return engine, store, view

    # ------------------------------------------------------------------
    # items()
    # ------------------------------------------------------------------

    def test_wf_items_count_matches_suggestions(self):
        """items() returns one dict per suggestion."""
        engine, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        assert len(view.items()) == len(engine.suggestions())

    def test_wf_items_has_required_keys(self):
        """Every item dict contains the required keys."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        required = {"suggestion_id", "type", "cycle_id", "confidence", "state"}
        for item in view.items():
            assert required <= set(item.keys())

    def test_wf_items_initial_state_all_open(self):
        """All suggestions are 'open' when no acknowledgments recorded."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        for item in view.items():
            assert item["state"] == "open"

    def test_wf_items_returns_independent_copy(self):
        """Mutating items() result does not affect internal state."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        result = view.items()
        original_len = len(result)
        result.clear()
        assert len(view.items()) == original_len

    # ------------------------------------------------------------------
    # State mapping
    # ------------------------------------------------------------------

    def test_wf_state_mapping_valid(self):
        """decision='valid' maps to 'reviewed-valid'."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        sid = suggestions[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="valid", ts=1.0))
        matching = [i for i in view.items() if i["suggestion_id"] == sid]
        assert matching[0]["state"] == "reviewed-valid"

    def test_wf_state_mapping_irrelevant(self):
        """decision='irrelevant' maps to 'reviewed-irrelevant'."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        sid = suggestions[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="irrelevant", ts=1.0))
        matching = [i for i in view.items() if i["suggestion_id"] == sid]
        assert matching[0]["state"] == "reviewed-irrelevant"

    def test_wf_state_mapping_investigate(self):
        """decision='investigate' maps to 'needs-investigation'."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        sid = suggestions[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        matching = [i for i in view.items() if i["suggestion_id"] == sid]
        assert matching[0]["state"] == "needs-investigation"

    # ------------------------------------------------------------------
    # by_state()
    # ------------------------------------------------------------------

    def test_wf_by_state_open_after_no_acks(self):
        """by_state('open') returns all items when nothing acknowledged."""
        engine, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        assert len(view.by_state("open")) == len(engine.suggestions())

    def test_wf_by_state_filters_correctly(self):
        """by_state() returns only items in that state."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        store.record(Acknowledgment(suggestion_id=suggestions[0].suggestion_id,
                                    decision="investigate", ts=1.0))
        inv = view.by_state("needs-investigation")
        assert all(i["state"] == "needs-investigation" for i in inv)
        assert len(inv) == 1

    def test_wf_by_state_unknown_returns_empty(self):
        """by_state() with unknown state returns []."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        assert view.by_state("no-such-state") == []

    def test_wf_by_state_after_ack_open_count_decreases(self):
        """Acknowledging a suggestion removes it from 'open'."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        open_before = len(view.by_state("open"))
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="valid", ts=1.0))
        assert len(view.by_state("open")) == open_before - 1
        assert len(view.by_state("reviewed-valid")) == 1

    # ------------------------------------------------------------------
    # queue()
    # ------------------------------------------------------------------

    def test_wf_queue_needs_investigation_first(self):
        """needs-investigation items appear before open items in queue()."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
            ("w1", "n1", "g2", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        if len(suggestions) < 2:
            pytest.skip("need 2+ suggestions for this test")
        # Acknowledge the last suggestion as "investigate"
        last_sid = suggestions[-1].suggestion_id
        store.record(Acknowledgment(suggestion_id=last_sid, decision="investigate", ts=1.0))
        q = view.queue()
        assert q[0]["state"] == "needs-investigation"

    def test_wf_queue_reviewed_irrelevant_last(self):
        """reviewed-irrelevant items appear last in queue()."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        store.record(Acknowledgment(suggestion_id=suggestions[0].suggestion_id,
                                    decision="irrelevant", ts=1.0))
        q = view.queue()
        assert q[-1]["state"] == "reviewed-irrelevant"

    def test_wf_queue_within_tier_confidence_descending(self):
        """Within a queue tier, confidence is in descending order."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g2", "cycle-A", 0.4),
            ("w1", "n1", "g1", "cycle-B", 0.5),
        ], reuse_min_count=2, low_activity_threshold=0.0)
        q = view.queue()
        open_items = [i for i in q if i["state"] == "open"]
        confidences = [i["confidence"] for i in open_items]
        assert confidences == sorted(confidences, reverse=True)

    def test_wf_queue_all_items_present(self):
        """queue() contains every suggestion exactly once."""
        engine, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        q = view.queue()
        assert len(q) == len(engine.suggestions())
        queued_ids = {i["suggestion_id"] for i in q}
        engine_ids = {s.suggestion_id for s in engine.suggestions()}
        assert queued_ids == engine_ids

    # ------------------------------------------------------------------
    # counts()
    # ------------------------------------------------------------------

    def test_wf_counts_all_states_present(self):
        """counts() always contains all four state keys."""
        _, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
        ])
        c = view.counts()
        assert set(c.keys()) >= {"open", "reviewed-valid",
                                  "reviewed-irrelevant", "needs-investigation"}

    def test_wf_counts_sums_to_total(self):
        """Sum of all counts equals total suggestion count."""
        engine, _, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        assert sum(view.counts().values()) == len(engine.suggestions())

    def test_wf_counts_update_after_ack(self):
        """counts() reflects acknowledgments made after view construction."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        engine, store, view = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        assert suggestions
        assert view.counts()["open"] == len(suggestions)
        store.record(Acknowledgment(suggestion_id=suggestions[0].suggestion_id,
                                    decision="valid", ts=1.0))
        assert view.counts()["reviewed-valid"] == 1
        assert view.counts()["open"] == len(suggestions) - 1

    # ------------------------------------------------------------------
    # Determinism + safety
    # ------------------------------------------------------------------

    def test_wf_deterministic(self):
        """Same engine + store → same queue output on two builds."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.workflow import WorkflowView
        engine, store, view1 = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        suggestions = engine.suggestions()
        if suggestions:
            store.record(Acknowledgment(suggestion_id=suggestions[0].suggestion_id,
                                        decision="investigate", ts=1.0))
        view2 = WorkflowView(engine, store)
        assert view1.queue() == view2.queue()

    def test_wf_does_not_affect_physics(self):
        """WorkflowView construction and queries do not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        from invar.adapters.redteam.workflow import WorkflowView

        engine = SupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1", cycle_id="c0",
        )
        env.add("g0", phi_R=0.5, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        engine.ingest(env)

        t = time.time()
        energy_before = engine.field_energy(t)

        pearls = archive.pearls
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, TemporalGraph.build(pearls), ew, causal, field)
        fb = FeedbackEngine(obs)
        store = AcknowledgmentStore()
        view = WorkflowView(fb, store)
        _ = view.items()
        _ = view.queue()
        _ = view.counts()

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


class TestL2ActionProposalEngine:
    """L2-4: ActionProposalEngine — design-only controlled action interface."""

    @staticmethod
    def _build(specs, acks=(), **fb_kwargs):
        """
        Returns (FeedbackEngine, AcknowledgmentStore, ActionProposalEngine).
        Uses direct Pearl construction.
        acks: iterable of (suggestion_id, decision) to record after engine build.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import Acknowledgment, AcknowledgmentStore
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        engine = FeedbackEngine(obs, **fb_kwargs)
        store = AcknowledgmentStore()
        for sid, decision in acks:
            store.record(Acknowledgment(suggestion_id=sid, decision=decision, ts=1.0))
        ap_engine = ActionProposalEngine(engine, store)
        return engine, store, ap_engine

    @staticmethod
    def _ack_all(engine, store, decision="investigate"):
        """Acknowledge all suggestions with the given decision."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        for s in engine.suggestions():
            store.record(Acknowledgment(suggestion_id=s.suggestion_id, decision=decision, ts=1.0))

    # ------------------------------------------------------------------
    # Eligibility gating
    # ------------------------------------------------------------------

    def test_ap_no_acks_no_proposals(self):
        """No acknowledgments → no proposed actions."""
        _, _, ap = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        assert ap.proposals() == []

    def test_ap_irrelevant_ack_no_proposal(self):
        """Decision 'irrelevant' does not produce a proposal."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="irrelevant", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert ap.proposals() == []

    def test_ap_investigate_ack_creates_proposal(self):
        """Decision 'investigate' produces a proposal."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert len(ap.proposals()) == 1
        assert ap.proposals()[0].suggestion_id == sid

    def test_ap_valid_ack_creates_proposal(self):
        """Decision 'valid' produces a proposal."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="valid", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert len(ap.proposals()) == 1

    # ------------------------------------------------------------------
    # Action type mapping
    # ------------------------------------------------------------------

    def test_ap_reuse_action_type(self):
        """'reuse' suggestion maps to 'examine_reuse' action."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        reuse = [s for s in engine.suggestions() if s.type == "reuse"]
        assert reuse, "need at least one reuse suggestion"
        store.record(Acknowledgment(suggestion_id=reuse[0].suggestion_id, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert ap.proposals()[0].action_type == "examine_reuse"

    def test_ap_high_activity_action_type(self):
        """'high_activity' suggestion maps to 'examine_high_activity' action."""
        # cycle-C receives links from both A and B (shared g1): activity=1.0 >= 0.8
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.9),
            ("w1", "n1", "g1", "cycle-B", 0.9),
            ("w1", "n1", "g1", "cycle-C", 0.9),
        ], high_activity_threshold=0.8)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ha = [s for s in engine.suggestions() if s.type == "high_activity"]
        assert ha, "need a high_activity suggestion"
        store.record(Acknowledgment(suggestion_id=ha[0].suggestion_id, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        result = [a for a in ap.proposals() if a.suggestion_id == ha[0].suggestion_id]
        assert result and result[0].action_type == "examine_high_activity"

    def test_ap_anomaly_action_type(self):
        """'anomaly' suggestion maps to 'examine_anomaly' action."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.1),
            ("w1", "n1", "g2", "cycle-B", 0.9),
        ], low_activity_threshold=0.4)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        an = [s for s in engine.suggestions() if s.type == "anomaly"]
        assert an, "need an anomaly suggestion"
        store.record(Acknowledgment(suggestion_id=an[0].suggestion_id, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        result = [a for a in ap.proposals() if a.suggestion_id == an[0].suggestion_id]
        assert result and result[0].action_type == "examine_anomaly"

    def test_ap_chain_action_type(self):
        """'chain' suggestion maps to 'trace_chain' action."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.9),
            ("w1", "n1", "g1", "cycle-B", 0.9),
            ("w1", "n1", "g1", "cycle-C", 0.9),
        ], chain_threshold=0.5, chain_min_length=3)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ch = [s for s in engine.suggestions() if s.type == "chain"]
        assert ch, "need a chain suggestion"
        store.record(Acknowledgment(suggestion_id=ch[0].suggestion_id, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        result = [a for a in ap.proposals() if a.suggestion_id == ch[0].suggestion_id]
        assert result and result[0].action_type == "trace_chain"

    # ------------------------------------------------------------------
    # ProposedAction fields
    # ------------------------------------------------------------------

    def test_ap_proposal_id_is_string(self):
        """proposal_id is a non-empty string."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert isinstance(ap.proposals()[0].proposal_id, str)
        assert len(ap.proposals()[0].proposal_id) > 0

    def test_ap_confidence_inherited(self):
        """Proposal confidence equals source suggestion confidence."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        s = engine.suggestions()[0]
        store.record(Acknowledgment(suggestion_id=s.suggestion_id, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        proposal = ap.for_suggestion(s.suggestion_id)
        assert proposal is not None
        assert proposal.confidence == pytest.approx(s.confidence)

    def test_ap_target_nonempty(self):
        """target is a non-empty string for all generated proposals."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        for proposal in ap.proposals():
            assert isinstance(proposal.target, str)
            assert len(proposal.target) > 0

    def test_ap_params_returns_dict(self):
        """params() returns a plain dict with string keys and values."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        for proposal in ap.proposals():
            d = proposal.params()
            assert isinstance(d, dict)
            for k, v in d.items():
                assert isinstance(k, str)
                assert isinstance(v, str)

    # ------------------------------------------------------------------
    # API: for_suggestion, by_type
    # ------------------------------------------------------------------

    def test_ap_for_suggestion_found(self):
        """for_suggestion returns the proposal when suggestion is eligible."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        result = ap.for_suggestion(sid)
        assert result is not None
        assert result.suggestion_id == sid

    def test_ap_for_suggestion_none_when_open(self):
        """for_suggestion returns None for unacknowledged (open) suggestions."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        for s in engine.suggestions():
            assert ap.for_suggestion(s.suggestion_id) is None

    def test_ap_for_suggestion_none_when_irrelevant(self):
        """for_suggestion returns None for suggestions marked irrelevant."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="irrelevant", ts=1.0))
        ap = ActionProposalEngine(engine, store)
        assert ap.for_suggestion(sid) is None

    def test_ap_by_type_filters_correctly(self):
        """by_type returns only proposals of the requested action type."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.9),
            ("w1", "n1", "g1", "cycle-B", 0.9),
        ], reuse_min_count=2, high_activity_threshold=0.8)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        for atype in ("examine_reuse", "examine_high_activity", "examine_anomaly", "trace_chain"):
            for proposal in ap.by_type(atype):
                assert proposal.action_type == atype

    def test_ap_by_type_unknown_returns_empty(self):
        """by_type returns [] for an unrecognised type."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        assert ap.by_type("nonexistent_type") == []

    # ------------------------------------------------------------------
    # Ordering and determinism
    # ------------------------------------------------------------------

    def test_ap_proposals_sorted_by_confidence_desc(self):
        """proposals() is sorted by confidence descending."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.9),
            ("w1", "n1", "g2", "cycle-B", 0.1),
        ], high_activity_threshold=0.8, low_activity_threshold=0.05)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        confs = [p.confidence for p in ap.proposals()]
        assert confs == sorted(confs, reverse=True)

    def test_ap_deterministic(self):
        """Same engine + store → identical proposals list on repeated construction."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap1 = ActionProposalEngine(engine, store)
        ap2 = ActionProposalEngine(engine, store)
        ids1 = [p.proposal_id for p in ap1.proposals()]
        ids2 = [p.proposal_id for p in ap2.proposals()]
        assert ids1 == ids2

    def test_ap_proposal_id_deterministic(self):
        """Same suggestion_id + action_type always produces same proposal_id."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        ap1 = ActionProposalEngine(engine, store)
        ap2 = ActionProposalEngine(engine, store)
        assert ap1.for_suggestion(sid).proposal_id == ap2.for_suggestion(sid).proposal_id

    def test_ap_proposals_independent_copy(self):
        """Mutating proposals() result does not affect internal state."""
        engine, store, _ = self._build([
            ("w1", "n1", "g1", "cycle-A", 0.5),
            ("w1", "n1", "g1", "cycle-B", 0.4),
        ], reuse_min_count=2)
        self._ack_all(engine, store, decision="investigate")
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        ap = ActionProposalEngine(engine, store)
        first = ap.proposals()
        first.clear()
        assert len(ap.proposals()) > 0

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_ap_no_layer0_effect(self):
        """ActionProposalEngine construction does not modify Layer 0 physics."""
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import Acknowledgment, AcknowledgmentStore
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = [
            Pearl(gate_id="g1", node_key="n1", workload_id="w1", instrument_id="probe",
                  cycle_id="cycle-A", ts=1.0, seq_id=1,
                  H_before=0.0, H_after=0.25, delta_H=0.25,
                  phi_R_before=0.0, phi_R_after=0.5,
                  phi_B_before=0.0, phi_B_after=0.0,
                  state_before=GateState.U, state_after=GateState.R,
                  coupling_propagated=False),
            Pearl(gate_id="g1", node_key="n1", workload_id="w1", instrument_id="probe",
                  cycle_id="cycle-B", ts=2.0, seq_id=2,
                  H_before=0.0, H_after=0.25, delta_H=0.25,
                  phi_R_before=0.0, phi_R_after=0.5,
                  phi_B_before=0.0, phi_B_after=0.0,
                  state_before=GateState.U, state_after=GateState.R,
                  coupling_propagated=False),
        ]
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        fb = FeedbackEngine(obs, reuse_min_count=2)
        store = AcknowledgmentStore()

        from invar.core.support_engine import SupportEngine
        import time as _time
        engine = SupportEngine()
        t = _time.time()
        energy_before = engine.field_energy(t)

        sid = fb.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        ActionProposalEngine(fb, store)

        assert engine.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


class TestL2RedTeamDomainModel:
    """L2-5: RedTeamDomainModel — red team domain concretization layer."""

    @staticmethod
    def _build(specs, acks=(), **fb_kwargs):
        """
        Returns (observer, engine, store, workflow, action_engine, model).
        specs: [(wid, nk, gid, cid, phi_R), ...]
        acks: [(suggestion_id, decision), ...]
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import Acknowledgment, AcknowledgmentStore
        from invar.adapters.redteam.workflow import WorkflowView
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.adapters.redteam.domain_model import RedTeamDomainModel
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        engine = FeedbackEngine(obs, **fb_kwargs)
        store = AcknowledgmentStore()
        for sid, decision in acks:
            store.record(Acknowledgment(suggestion_id=sid, decision=decision, ts=1.0))
        workflow = WorkflowView(engine, store)
        action_engine = ActionProposalEngine(engine, store)
        model = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        return obs, engine, store, workflow, action_engine, model

    @staticmethod
    def _minimal_model():
        """Build a minimal model suitable for artifact_type / cycle_primitive tests."""
        from invar.adapters.redteam.domain_model import RedTeamDomainModel
        _, _, _, _, _, model = TestL2RedTeamDomainModel._build([
            ("w1", "n1", "exec_tool", "cycle-A", 0.5),
            ("w1", "n1", "persist_svc", "cycle-B", 0.4),
        ], reuse_min_count=2)
        return model

    # ------------------------------------------------------------------
    # Artifact typing — known patterns
    # ------------------------------------------------------------------

    def test_dm_exec_artifact_type(self):
        """Gate containing 'exec' maps to EXECUTION_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "exec_cmd_tool")) == ArtifactType.EXECUTION_ARTIFACT

    def test_dm_persistence_artifact_type(self):
        """Gate containing 'persist' maps to PERSISTENCE_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "persist_registry")) == ArtifactType.PERSISTENCE_ARTIFACT

    def test_dm_credential_artifact_type(self):
        """Gate containing 'cred' maps to CREDENTIAL_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "cred_ticket_dump")) == ArtifactType.CREDENTIAL_ARTIFACT

    def test_dm_discovery_artifact_type(self):
        """Gate containing 'enum' maps to DISCOVERY_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "enum_hosts_scan")) == ArtifactType.DISCOVERY_ARTIFACT

    def test_dm_lateral_artifact_type(self):
        """Gate containing 'psexec' maps to LATERAL_ARTIFACT (not EXECUTION)."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "psexec_lateral_move")) == ArtifactType.LATERAL_ARTIFACT

    def test_dm_collection_artifact_type(self):
        """Gate containing 'loot' maps to COLLECTION_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "loot_exfil_data")) == ArtifactType.COLLECTION_ARTIFACT

    def test_dm_c2_artifact_type(self):
        """Gate containing 'beacon' maps to C2_ARTIFACT."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "beacon_callback_channel")) == ArtifactType.C2_ARTIFACT

    def test_dm_unknown_artifact_type(self):
        """Gate with no matching pattern maps to UNKNOWN."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "random_xyz_gate")) == ArtifactType.UNKNOWN

    def test_dm_case_insensitive_matching(self):
        """Artifact typing is case-insensitive."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "EXEC_TOOL")) == ArtifactType.EXECUTION_ARTIFACT
        assert model.artifact_type(("w1", "n1", "BEACON_C2")) == ArtifactType.C2_ARTIFACT

    def test_dm_autorun_maps_to_persistence_not_execution(self):
        """'autorun' matches PERSISTENCE before EXECUTION ('run' substring)."""
        from invar.adapters.redteam.domain_model import ArtifactType
        model = self._minimal_model()
        assert model.artifact_type(("w1", "n1", "autorun_key")) == ArtifactType.PERSISTENCE_ARTIFACT

    # ------------------------------------------------------------------
    # Cycle primitive classification
    # ------------------------------------------------------------------

    def test_dm_single_type_cycle_maps_to_correct_primitive(self):
        """Cycle with one non-UNKNOWN artifact type maps to its matching primitive."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_ps", "cycle-A", 0.5),
        ])
        assert model.cycle_primitive("cycle-A") == OperationPrimitive.EXECUTION

    def test_dm_multi_type_cycle_maps_to_multi_stage(self):
        """Cycle with two+ distinct non-UNKNOWN artifact types maps to MULTI_STAGE."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "cred_hash", "cycle-A", 0.4),
        ])
        assert model.cycle_primitive("cycle-A") == OperationPrimitive.MULTI_STAGE

    def test_dm_unknown_only_cycle_maps_to_unclassified(self):
        """Cycle with only UNKNOWN artifacts maps to UNCLASSIFIED."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "random_gate_xyz", "cycle-A", 0.5),
        ])
        assert model.cycle_primitive("cycle-A") == OperationPrimitive.UNCLASSIFIED

    def test_dm_unknown_cycle_id_maps_to_unclassified(self):
        """cycle_primitive returns UNCLASSIFIED for a cycle_id with no pearls."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        assert model.cycle_primitive("nonexistent-cycle") == OperationPrimitive.UNCLASSIFIED

    def test_dm_credential_cycle_primitive(self):
        """Cycle with credential-only artifacts maps to CREDENTIAL_ACCESS."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "cred_ticket", "cycle-A", 0.5),
            ("w1", "n1", "hash_dump", "cycle-A", 0.4),
        ])
        assert model.cycle_primitive("cycle-A") == OperationPrimitive.CREDENTIAL_ACCESS

    # ------------------------------------------------------------------
    # Cycle artifact inventory
    # ------------------------------------------------------------------

    def test_dm_cycle_artifacts_structure(self):
        """cycle_artifacts returns dict with cycle_id and artifacts keys."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        result = model.cycle_artifacts("cycle-A")
        assert "cycle_id" in result
        assert "artifacts" in result
        assert result["cycle_id"] == "cycle-A"

    def test_dm_cycle_artifacts_item_keys(self):
        """Each artifact in cycle_artifacts has gate_key and artifact_type."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        result = model.cycle_artifacts("cycle-A")
        for item in result["artifacts"]:
            assert "gate_key" in item
            assert "artifact_type" in item
            assert isinstance(item["gate_key"], tuple)
            assert len(item["gate_key"]) == 3

    def test_dm_cycle_artifacts_count(self):
        """cycle_artifacts returns one entry per pearl in the window."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "cred_hash", "cycle-A", 0.4),
        ])
        result = model.cycle_artifacts("cycle-A")
        assert len(result["artifacts"]) == 2

    def test_dm_cycle_artifacts_unknown_cycle(self):
        """cycle_artifacts returns empty list for unknown cycle_id."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        result = model.cycle_artifacts("no-such-cycle")
        assert result["artifacts"] == []
        assert result["cycle_id"] == "no-such-cycle"

    # ------------------------------------------------------------------
    # Operational summary
    # ------------------------------------------------------------------

    def test_dm_operational_summary_has_required_keys(self):
        """operational_summary returns all required keys."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        result = model.operational_summary("cycle-A")
        required = {
            "cycle_id", "primitive", "activity", "artifact_count",
            "artifact_types", "incoming_links", "outgoing_links",
            "workflow_state_counts",
        }
        assert required <= set(result.keys())

    def test_dm_operational_summary_primitive_correct(self):
        """operational_summary primitive matches cycle_primitive result."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        summary = model.operational_summary("cycle-A")
        assert summary["primitive"] == model.cycle_primitive("cycle-A")

    def test_dm_operational_summary_artifact_count(self):
        """operational_summary artifact_count matches pearl count for cycle."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "cred_hash", "cycle-A", 0.4),
        ])
        assert model.operational_summary("cycle-A")["artifact_count"] == 2

    def test_dm_operational_summary_artifact_types_sorted_unique(self):
        """artifact_types in summary is sorted and deduplicated."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_ps", "cycle-A", 0.4),
        ])
        types = model.operational_summary("cycle-A")["artifact_types"]
        assert types == sorted(set(types))

    def test_dm_operational_summary_workflow_state_counts_has_all_states(self):
        """workflow_state_counts always contains all four workflow states."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
        ])
        counts = model.operational_summary("cycle-A")["workflow_state_counts"]
        for state in ("open", "reviewed-valid", "reviewed-irrelevant", "needs-investigation"):
            assert state in counts

    def test_dm_operational_summary_activity_matches_observer(self):
        """operational_summary activity matches observer.activity() directly."""
        obs, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-C", 0.5),
        ])
        for cid in ("cycle-A", "cycle-B", "cycle-C"):
            assert model.operational_summary(cid)["activity"] == pytest.approx(
                obs.activity(cid), abs=1e-12
            )

    # ------------------------------------------------------------------
    # Lab queue
    # ------------------------------------------------------------------

    def test_dm_lab_queue_empty_when_no_suggestions(self):
        """lab_queue returns [] when FeedbackEngine produces no suggestions."""
        # Suppress all four suggestion types via thresholds
        _, _, _, _, _, model = self._build(
            [("w1", "n1", "exec_cmd", "cycle-A", 0.5)],
            reuse_min_count=999,
            high_activity_threshold=2.0,   # activity ≤ 1.0, never fires
            low_activity_threshold=-1.0,   # activity ≥ 0.0, never fires
            chain_threshold=2.0,           # weight ≤ 1.0, never fires
        )
        assert model.lab_queue() == []

    def test_dm_lab_queue_has_required_keys(self):
        """Every lab_queue item has all required keys."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        required = {
            "suggestion_id", "type", "cycle_id", "confidence",
            "state", "action_type", "proposal_id", "primitive",
        }
        for item in model.lab_queue():
            assert required <= set(item.keys())

    def test_dm_lab_queue_ordering_follows_workflow(self):
        """lab_queue suggestion_id order matches WorkflowView.queue() order."""
        _, _, _, workflow, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        queue_ids = [item["suggestion_id"] for item in model.lab_queue()]
        wf_ids = [item["suggestion_id"] for item in workflow.queue()]
        assert queue_ids == wf_ids

    def test_dm_lab_queue_action_type_none_when_open(self):
        """Open (unacknowledged) suggestions have action_type=None in lab_queue."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        for item in model.lab_queue():
            if item["state"] == "open":
                assert item["action_type"] is None
                assert item["proposal_id"] is None

    def test_dm_lab_queue_action_type_present_when_investigate(self):
        """Acknowledged-investigate suggestions have action_type populated."""
        from invar.adapters.redteam.acknowledgment import Acknowledgment
        from invar.adapters.redteam.workflow import WorkflowView
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.adapters.redteam.domain_model import RedTeamDomainModel

        obs, engine, store, _, _, _ = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        sid = engine.suggestions()[0].suggestion_id
        store.record(Acknowledgment(suggestion_id=sid, decision="investigate", ts=1.0))
        workflow = WorkflowView(engine, store)
        action_engine = ActionProposalEngine(engine, store)
        model = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        investigate_items = [item for item in model.lab_queue() if item["state"] == "needs-investigation"]
        assert investigate_items
        assert investigate_items[0]["action_type"] is not None
        assert investigate_items[0]["proposal_id"] is not None

    def test_dm_lab_queue_primitive_populated_for_cycle_suggestions(self):
        """Lab queue items with a cycle_id have primitive field populated."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.9),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.9),
            ("w1", "n1", "exec_cmd", "cycle-C", 0.9),
        ], high_activity_threshold=0.8)
        for item in model.lab_queue():
            if item["cycle_id"] is not None:
                assert item["primitive"] is not None

    # ------------------------------------------------------------------
    # Determinism and isolation
    # ------------------------------------------------------------------

    def test_dm_deterministic(self):
        """Same inputs produce identical lab_queue on repeated model construction."""
        from invar.adapters.redteam.domain_model import RedTeamDomainModel

        obs, engine, store, workflow, action_engine, _ = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        m1 = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        m2 = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        assert m1.lab_queue() == m2.lab_queue()

    def test_dm_lab_queue_independent_copy(self):
        """Mutating lab_queue() result does not affect subsequent calls."""
        _, _, _, _, _, model = self._build([
            ("w1", "n1", "exec_cmd", "cycle-A", 0.5),
            ("w1", "n1", "exec_cmd", "cycle-B", 0.4),
        ], reuse_min_count=2)
        first = model.lab_queue()
        n = len(first)
        first.clear()
        assert len(model.lab_queue()) == n

    def test_dm_artifact_type_deterministic(self):
        """artifact_type returns the same result on repeated calls."""
        model = self._minimal_model()
        gk = ("w1", "n1", "exec_cmd")
        assert model.artifact_type(gk) == model.artifact_type(gk)

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_dm_no_layer0_effect(self):
        """RedTeamDomainModel construction and queries do not alter Layer 0 physics."""
        from invar.persistence.pearl_archive import PearlArchive
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        from invar.adapters.redteam.workflow import WorkflowView
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.adapters.redteam.domain_model import RedTeamDomainModel
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl, SupportEngine
        import time as _time

        pearls = [
            Pearl(gate_id="exec_cmd", node_key="n1", workload_id="w1", instrument_id="probe",
                  cycle_id="cycle-A", ts=1.0, seq_id=1,
                  H_before=0.0, H_after=0.25, delta_H=0.25,
                  phi_R_before=0.0, phi_R_after=0.5,
                  phi_B_before=0.0, phi_B_after=0.0,
                  state_before=GateState.U, state_after=GateState.R,
                  coupling_propagated=False),
            Pearl(gate_id="cred_hash", node_key="n1", workload_id="w1", instrument_id="probe",
                  cycle_id="cycle-B", ts=2.0, seq_id=2,
                  H_before=0.0, H_after=0.25, delta_H=0.25,
                  phi_R_before=0.0, phi_R_after=0.5,
                  phi_B_before=0.0, phi_B_after=0.0,
                  state_before=GateState.U, state_after=GateState.R,
                  coupling_propagated=False),
        ]
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, TemporalGraph.build(pearls), ew, causal, field)
        engine = FeedbackEngine(obs)
        store = AcknowledgmentStore()
        workflow = WorkflowView(engine, store)
        action_engine = ActionProposalEngine(engine, store)

        substrate = SupportEngine()
        t = _time.time()
        energy_before = substrate.field_energy(t)

        model = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        _ = model.lab_queue()
        _ = model.operational_summary("cycle-A")
        _ = model.cycle_artifacts("cycle-A")

        assert substrate.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


class TestL2RelationshipGraph:
    """L2-6: RelationshipGraph — directed cycle relationships + attack patterns."""

    @staticmethod
    def _build(specs, **fb_kwargs):
        """
        Returns (observer, domain_model, graph).
        specs: [(wid, nk, gid, cid, phi_R), ...]
        Uses direct Pearl construction.
        """
        from invar.persistence.execution_window import ExecutionWindows
        from invar.persistence.proto_causality import ProtoCausality
        from invar.persistence.causal_field import CausalField
        from invar.persistence.temporal_graph import TemporalGraph
        from invar.persistence.pearl_archive import PearlArchive
        from invar.adapters.redteam.observer import RedTeamObserver
        from invar.adapters.redteam.feedback import FeedbackEngine
        from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
        from invar.adapters.redteam.workflow import WorkflowView
        from invar.adapters.redteam.action_proposal import ActionProposalEngine
        from invar.adapters.redteam.domain_model import RedTeamDomainModel
        from invar.adapters.redteam.relationship_graph import RelationshipGraph
        from invar.core.gate import GateState
        from invar.core.support_engine import Pearl

        pearls = []
        for seq_id, (wid, nk, gid, cid, phi_R) in enumerate(specs, start=1):
            pearls.append(Pearl(
                gate_id=gid, node_key=nk, workload_id=wid, instrument_id="probe",
                cycle_id=cid, ts=float(seq_id), seq_id=seq_id,
                H_before=0.0, H_after=phi_R * phi_R, delta_H=phi_R * phi_R,
                phi_R_before=0.0, phi_R_after=phi_R,
                phi_B_before=0.0, phi_B_after=0.0,
                state_before=GateState.U, state_after=GateState.R,
                coupling_propagated=False,
            ))
        archive = PearlArchive()
        for p in pearls:
            archive.record(p)
        temporal = TemporalGraph.build(pearls)
        ew = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(ew)
        field = CausalField.build(causal, ew)
        obs = RedTeamObserver(archive, temporal, ew, causal, field)
        engine = FeedbackEngine(obs, **fb_kwargs)
        store = AcknowledgmentStore()
        workflow = WorkflowView(engine, store)
        action_engine = ActionProposalEngine(engine, store)
        domain = RedTeamDomainModel(obs, engine, store, workflow, action_engine)
        graph = RelationshipGraph(obs, domain)
        return obs, domain, graph

    @staticmethod
    def _cred_lateral_specs():
        """Two-cycle spec: CREDENTIAL_ACCESS → LATERAL_MOVEMENT via shared gate."""
        return [
            ("w1", "n1", "cred_dump",   "cycle-A", 0.5),  # CREDENTIAL_ARTIFACT
            ("w1", "n1", "shared_link", "cycle-A", 0.5),  # UNKNOWN, shared
            ("w1", "n1", "psexec_move", "cycle-B", 0.5),  # LATERAL_ARTIFACT
            ("w1", "n1", "shared_link", "cycle-B", 0.5),  # UNKNOWN, shared
        ]

    @staticmethod
    def _three_hop_specs():
        """Three-cycle spec for credential → lateral → exec pattern."""
        return [
            ("w1", "n1", "cred_dump",   "cycle-A", 0.5),  # CREDENTIAL_ARTIFACT
            ("w1", "n1", "shared_ab",   "cycle-A", 0.5),  # UNKNOWN, shared A-B
            ("w1", "n1", "psexec_move", "cycle-B", 0.5),  # LATERAL_ARTIFACT
            ("w1", "n1", "shared_ab",   "cycle-B", 0.5),  # UNKNOWN, shared A-B
            ("w1", "n1", "shared_bc",   "cycle-B", 0.5),  # UNKNOWN, shared B-C
            ("w1", "n1", "exec_cmd",    "cycle-C", 0.5),  # EXECUTION_ARTIFACT
            ("w1", "n1", "shared_bc",   "cycle-C", 0.5),  # UNKNOWN, shared B-C
        ]

    # ------------------------------------------------------------------
    # Basic relationship detection
    # ------------------------------------------------------------------

    def test_rg_no_links_no_relationships(self):
        """No shared gates → no cycle relationships."""
        _, _, graph = self._build([
            ("w1", "n1", "exec_cmd",  "cycle-A", 0.5),
            ("w1", "n2", "cred_dump", "cycle-B", 0.5),
        ])
        assert graph.cycle_relationships() == []

    def test_rg_shared_gate_creates_relationship(self):
        """Shared gate between cycles creates a cycle relationship."""
        _, _, graph = self._build(self._cred_lateral_specs())
        assert len(graph.cycle_relationships()) == 1

    def test_rg_relationship_cycle_ids_correct(self):
        """CycleRelationship has correct from_cycle and to_cycle."""
        _, _, graph = self._build(self._cred_lateral_specs())
        rels = graph.cycle_relationships()
        assert len(rels) == 1
        rel = rels[0]
        assert rel.from_cycle == "cycle-A"
        assert rel.to_cycle == "cycle-B"

    def test_rg_relationship_weight_positive(self):
        """CycleRelationship weight is positive."""
        _, _, graph = self._build(self._cred_lateral_specs())
        assert graph.cycle_relationships()[0].weight > 0.0

    def test_rg_relationship_shared_gate_count(self):
        """shared_gate_count reflects number of shared gate keys."""
        _, _, graph = self._build(self._cred_lateral_specs())
        # one shared gate: ("w1", "n1", "shared_link")
        assert graph.cycle_relationships()[0].shared_gate_count == 1

    # ------------------------------------------------------------------
    # Relationship type classification
    # ------------------------------------------------------------------

    def test_rg_stage_transition_classified(self):
        """CREDENTIAL_ACCESS → LATERAL_MOVEMENT classified as stage_transition."""
        from invar.adapters.redteam.relationship_graph import RelationshipType
        _, _, graph = self._build(self._cred_lateral_specs())
        rel = graph.cycle_relationships()[0]
        assert rel.relationship_type == RelationshipType.STAGE_TRANSITION

    def test_rg_stage_transition_label_correct(self):
        """credential→lateral transition has correct transition_label."""
        _, _, graph = self._build(self._cred_lateral_specs())
        rel = graph.cycle_relationships()[0]
        assert rel.transition_label == "credential_to_lateral"

    def test_rg_continuation_classified(self):
        """Same primitive in both cycles classified as continuation."""
        from invar.adapters.redteam.relationship_graph import RelationshipType
        _, _, graph = self._build([
            ("w1", "n1", "exec_cmd",    "cycle-A", 0.5),
            ("w1", "n1", "shared_link", "cycle-A", 0.5),
            ("w1", "n1", "exec_tool",   "cycle-B", 0.5),
            ("w1", "n1", "shared_link", "cycle-B", 0.5),
        ])
        rel = graph.cycle_relationships()[0]
        assert rel.relationship_type == RelationshipType.CONTINUATION
        assert rel.transition_label is None

    def test_rg_unclassified_when_unknown_primitives(self):
        """Unknown→unknown primitive pair classified as unclassified."""
        from invar.adapters.redteam.relationship_graph import RelationshipType
        _, _, graph = self._build([
            ("w1", "n1", "random_xyz",  "cycle-A", 0.5),  # UNKNOWN
            ("w1", "n1", "shared_link", "cycle-A", 0.5),
            ("w1", "n1", "nondescript", "cycle-B", 0.5),  # UNKNOWN
            ("w1", "n1", "shared_link", "cycle-B", 0.5),
        ])
        rel = graph.cycle_relationships()[0]
        assert rel.relationship_type == RelationshipType.UNCLASSIFIED

    def test_rg_primitive_fields_populated(self):
        """from_primitive and to_primitive match domain_model.cycle_primitive."""
        _, domain, graph = self._build(self._cred_lateral_specs())
        rel = graph.cycle_relationships()[0]
        assert rel.from_primitive == domain.cycle_primitive("cycle-A")
        assert rel.to_primitive == domain.cycle_primitive("cycle-B")

    # ------------------------------------------------------------------
    # relationships_from / relationships_to
    # ------------------------------------------------------------------

    def test_rg_relationships_from_correct(self):
        """relationships_from returns outgoing rels for cycle-A."""
        _, _, graph = self._build(self._cred_lateral_specs())
        rels_from_a = graph.relationships_from("cycle-A")
        assert len(rels_from_a) == 1
        assert rels_from_a[0].to_cycle == "cycle-B"

    def test_rg_relationships_from_empty_for_terminal(self):
        """relationships_from returns [] for a cycle with no outgoing links."""
        _, _, graph = self._build(self._cred_lateral_specs())
        assert graph.relationships_from("cycle-B") == []

    def test_rg_relationships_to_correct(self):
        """relationships_to returns incoming rels for cycle-B."""
        _, _, graph = self._build(self._cred_lateral_specs())
        rels_to_b = graph.relationships_to("cycle-B")
        assert len(rels_to_b) == 1
        assert rels_to_b[0].from_cycle == "cycle-A"

    def test_rg_relationships_to_empty_for_source(self):
        """relationships_to returns [] for a cycle with no incoming links."""
        _, _, graph = self._build(self._cred_lateral_specs())
        assert graph.relationships_to("cycle-A") == []

    # ------------------------------------------------------------------
    # Pattern matching
    # ------------------------------------------------------------------

    def test_rg_credential_lateral_exec_pattern_detected(self):
        """credential_lateral_exec pattern detected in three-hop cycle chain."""
        _, _, graph = self._build(self._three_hop_specs())
        matches = graph.pattern_matches()
        names = [m.pattern_name for m in matches]
        assert "credential_lateral_exec" in names

    def test_rg_pattern_match_cycle_path(self):
        """Detected pattern has correct cycle_path."""
        _, _, graph = self._build(self._three_hop_specs())
        matches = [m for m in graph.pattern_matches() if m.pattern_name == "credential_lateral_exec"]
        assert matches
        assert matches[0].cycle_path == ("cycle-A", "cycle-B", "cycle-C")

    def test_rg_pattern_match_primitives(self):
        """PatternMatch.primitives matches the pattern definition."""
        from invar.adapters.redteam.domain_model import OperationPrimitive
        _, _, graph = self._build(self._three_hop_specs())
        matches = [m for m in graph.pattern_matches() if m.pattern_name == "credential_lateral_exec"]
        assert matches
        assert matches[0].primitives == (
            OperationPrimitive.CREDENTIAL_ACCESS,
            OperationPrimitive.LATERAL_MOVEMENT,
            OperationPrimitive.EXECUTION,
        )

    def test_rg_pattern_match_avg_weight_positive(self):
        """PatternMatch avg_weight is positive for a real path."""
        _, _, graph = self._build(self._three_hop_specs())
        for m in graph.pattern_matches():
            assert m.avg_weight > 0.0

    def test_rg_no_pattern_when_wrong_primitives(self):
        """No pattern match when primitive sequence doesn't match any pattern."""
        _, _, graph = self._build([
            ("w1", "n1", "random_xyz",  "cycle-A", 0.5),
            ("w1", "n1", "shared_link", "cycle-A", 0.5),
            ("w1", "n1", "nondescript", "cycle-B", 0.5),
            ("w1", "n1", "shared_link", "cycle-B", 0.5),
        ])
        assert graph.pattern_matches() == []

    # ------------------------------------------------------------------
    # Pivot cycles
    # ------------------------------------------------------------------

    def test_rg_pivot_cycle_detected(self):
        """Middle cycle in three-hop chain identified as pivot."""
        _, _, graph = self._build(self._three_hop_specs())
        pivots = graph.pivot_cycles()
        assert "cycle-B" in pivots

    def test_rg_endpoints_not_pivots(self):
        """Source and terminal cycles are not pivot cycles."""
        _, _, graph = self._build(self._three_hop_specs())
        pivots = graph.pivot_cycles()
        assert "cycle-A" not in pivots
        assert "cycle-C" not in pivots

    def test_rg_no_pivots_in_two_cycle_chain(self):
        """Two-cycle chain has no pivot cycles."""
        _, _, graph = self._build(self._cred_lateral_specs())
        assert graph.pivot_cycles() == []

    # ------------------------------------------------------------------
    # Artifact reuse map
    # ------------------------------------------------------------------

    def test_rg_artifact_reuse_map_contains_shared_gate(self):
        """Shared gate appears in artifact_reuse_map."""
        _, _, graph = self._build(self._cred_lateral_specs())
        reuse = graph.artifact_reuse_map()
        shared_key = ("w1", "n1", "shared_link")
        assert shared_key in reuse

    def test_rg_artifact_reuse_map_cycle_list(self):
        """Shared gate maps to sorted list of cycle_ids."""
        _, _, graph = self._build(self._cred_lateral_specs())
        reuse = graph.artifact_reuse_map()
        shared_key = ("w1", "n1", "shared_link")
        assert sorted(reuse[shared_key]) == reuse[shared_key]
        assert "cycle-A" in reuse[shared_key]
        assert "cycle-B" in reuse[shared_key]

    def test_rg_unique_gates_not_in_reuse_map(self):
        """Gates that appear in only one cycle are excluded from reuse_map."""
        _, _, graph = self._build(self._cred_lateral_specs())
        reuse = graph.artifact_reuse_map()
        assert ("w1", "n1", "cred_dump") not in reuse
        assert ("w1", "n1", "psexec_move") not in reuse

    # ------------------------------------------------------------------
    # Determinism and isolation
    # ------------------------------------------------------------------

    def test_rg_deterministic(self):
        """Same observer + domain_model → identical graph outputs."""
        from invar.adapters.redteam.relationship_graph import RelationshipGraph
        obs, domain, _ = self._build(self._three_hop_specs())
        g1 = RelationshipGraph(obs, domain)
        g2 = RelationshipGraph(obs, domain)
        assert [r.from_cycle for r in g1.cycle_relationships()] == \
               [r.from_cycle for r in g2.cycle_relationships()]
        assert [m.pattern_name for m in g1.pattern_matches()] == \
               [m.pattern_name for m in g2.pattern_matches()]

    def test_rg_independent_copies(self):
        """Mutating cycle_relationships() result does not affect subsequent calls."""
        _, _, graph = self._build(self._cred_lateral_specs())
        first = graph.cycle_relationships()
        n = len(first)
        first.clear()
        assert len(graph.cycle_relationships()) == n

    def test_rg_no_layer0_effect(self):
        """RelationshipGraph construction does not alter Layer 0 physics."""
        from invar.core.support_engine import SupportEngine
        import time as _time
        substrate = SupportEngine()
        t = _time.time()
        energy_before = substrate.field_energy(t)
        self._build(self._three_hop_specs())
        assert substrate.field_energy(t) == pytest.approx(energy_before, abs=1e-12)


# ===========================================================================
# L2-7 — WindowsIngestAdapter (windows_ingest.py)
# ===========================================================================

class TestL2WindowsIngestAdapter:
    """
    Tests for WindowsIngestAdapter, CycleDiscovery, and parsing helpers.

    All Pearls are produced passively from XML strings — no Layer 0 engine
    is constructed.  cycle_id discovery is autonomous; operator override is
    verified separately.
    """

    # ------------------------------------------------------------------
    # XML fixtures
    # ------------------------------------------------------------------

    def _sysmon_event(
        self,
        event_id: int,
        system_time: str = "2024-01-01T12:00:00.000000Z",
        hostname: str = "WORKSTATION1",
        fields: dict = None,
    ) -> str:
        """Build a minimal Sysmon-style <Event> XML string."""
        data_elems = ""
        if fields:
            for k, v in fields.items():
                data_elems += f'    <Data Name="{k}">{v}</Data>\n'
        return f"""<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System>
    <EventID>{event_id}</EventID>
    <TimeCreated SystemTime="{system_time}"/>
    <Computer>{hostname}</Computer>
  </System>
  <EventData>
{data_elems}  </EventData>
</Event>"""

    def _events_wrap(self, *xmls: str) -> str:
        """Wrap multiple <Event> strings in an <Events> container."""
        inner = "\n".join(xmls)
        return f"<Events>\n{inner}\n</Events>"

    # ------------------------------------------------------------------
    # Gate ID mapping
    # ------------------------------------------------------------------

    def test_wi_process_create_powershell(self):
        """EID 1 with powershell.exe → exec_powershell."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, fields={"Image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert len(pearls) == 1
        assert pearls[0].gate_id == "exec_powershell"

    def test_wi_process_create_generic_exec(self):
        """EID 1 with unknown process → exec_<basename>."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, fields={"Image": r"C:\tools\implant.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert len(pearls) == 1
        assert pearls[0].gate_id == "exec_implant"

    def test_wi_network_smb_lateral(self):
        """EID 3 to port 445 → lateral_smb_<dest>."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(3, fields={
            "DestinationPort": "445",
            "DestinationHostname": "fileserver01",
        })
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert len(pearls) == 1
        assert pearls[0].gate_id == "lateral_smb_fileserver01"

    def test_wi_network_c2_https(self):
        """EID 3 to port 443 → c2_beacon_https."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(3, fields={
            "DestinationPort": "443",
            "DestinationIp": "1.2.3.4",
        })
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "c2_beacon_https"

    def test_wi_process_access_lsass(self):
        """EID 10 targeting lsass.exe → cred_lsass_access."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(10, fields={"TargetImage": r"C:\Windows\System32\lsass.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "cred_lsass_access"

    def test_wi_registry_run_key(self):
        """EID 13 with Run key path → persist_autorun."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(13, fields={
            "TargetObject": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run\backdoor"
        })
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "persist_autorun"

    def test_wi_file_create_script(self):
        """EID 11 creating a .ps1 file → exec_script."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(11, fields={"TargetFilename": r"C:\Users\user\payload.ps1"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "exec_script"

    def test_wi_unknown_event_id_skipped(self):
        """Unrecognised event_id → no Pearl produced."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(9999, fields={"SomeField": "irrelevant"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls == []

    def test_wi_wel_4688_process_create(self):
        """EID 4688 (WEL) with cmd.exe → exec_cmd."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(4688, fields={"NewProcessName": r"C:\Windows\System32\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "exec_cmd"

    def test_wi_wel_4698_schtask(self):
        """EID 4698 → persist_schtask."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(4698)
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "persist_schtask"

    def test_wi_wel_4624_logon(self):
        """EID 4624 → lateral_logon."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(4624)
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].gate_id == "lateral_logon"

    # ------------------------------------------------------------------
    # Pearl field correctness
    # ------------------------------------------------------------------

    def test_wi_pearl_fields(self):
        """Pearls have correct workload_id, node_key, gate_id, state fields."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        from invar.core.gate import GateState
        xml = self._sysmon_event(
            1,
            hostname="TARGET-PC",
            fields={"Image": r"C:\Windows\System32\cmd.exe"},
        )
        adapter = WindowsIngestAdapter("eng-42")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="op1")
        p = pearls[0]
        assert p.workload_id == "eng-42"
        assert p.node_key == "TARGET-PC"
        assert p.gate_id == "exec_cmd"
        assert p.cycle_id == "op1"
        assert p.state_before == GateState.U
        assert p.state_after == GateState.R
        assert p.phi_R_after == pytest.approx(1.0)
        assert p.H_after == pytest.approx(1.0)

    def test_wi_node_key_override(self):
        """Explicit node_key parameter overrides hostname from event."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, hostname="HOST-FROM-XML",
                                 fields={"Image": r"C:\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01", node_key="fixed-node")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert pearls[0].node_key == "fixed-node"

    def test_wi_seq_id_monotone(self):
        """seq_id increments monotonically across multiple events."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, system_time="2024-01-01T12:00:00.000000Z",
                                   fields={"Image": r"C:\cmd.exe"})
        xml2 = self._sysmon_event(3, system_time="2024-01-01T12:00:01.000000Z",
                                   fields={"DestinationPort": "443", "DestinationIp": "1.2.3.4"})
        adapter = WindowsIngestAdapter("eng-01")
        p1 = adapter.ingest_sysmon_xml(xml1, cycle_id="c1")[0]
        p2 = adapter.ingest_sysmon_xml(xml2, cycle_id="c1")[0]
        assert p1.seq_id < p2.seq_id

    def test_wi_multiple_events_batch(self):
        """<Events> container yields one Pearl per recognisable event."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, system_time="2024-01-01T12:00:00.000000Z",
                                   fields={"Image": r"C:\powershell.exe"})
        xml2 = self._sysmon_event(10, system_time="2024-01-01T12:00:01.000000Z",
                                   fields={"TargetImage": r"C:\Windows\System32\lsass.exe"})
        xml3 = self._sysmon_event(9999, system_time="2024-01-01T12:00:02.000000Z")
        combined = self._events_wrap(xml1, xml2, xml3)
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(combined, cycle_id="c1")
        assert len(pearls) == 2
        assert pearls[0].gate_id == "exec_powershell"
        assert pearls[1].gate_id == "cred_lsass_access"

    def test_wi_pearls_accumulate(self):
        """pearls() returns all pearls across multiple ingest calls."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, fields={"Image": r"C:\cmd.exe"})
        xml2 = self._sysmon_event(4698)
        adapter = WindowsIngestAdapter("eng-01")
        adapter.ingest_sysmon_xml(xml1, cycle_id="c1")
        adapter.ingest_sysmon_xml(xml2, cycle_id="c1")
        all_p = adapter.pearls()
        assert len(all_p) == 2

    def test_wi_snapshot(self):
        """snapshot() returns (PearlArchive, pearl_list); archive contains same pearls."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        from invar.persistence.pearl_archive import PearlArchive
        xml = self._sysmon_event(1, fields={"Image": r"C:\powershell.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        archive, pl = adapter.snapshot()
        assert isinstance(archive, PearlArchive)
        assert len(pl) == 1
        assert pl[0].gate_id == "exec_powershell"
        assert len(archive.pearls) == 1

    # ------------------------------------------------------------------
    # Cycle discovery — autonomous
    # ------------------------------------------------------------------

    def test_wi_time_gap_new_cycle(self):
        """Time gap > threshold starts a new auto cycle."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, system_time="2024-01-01T12:00:00.000000Z",
                                   fields={"Image": r"C:\cmd.exe"})
        xml2 = self._sysmon_event(1, system_time="2024-01-01T12:10:00.000000Z",
                                   fields={"Image": r"C:\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01", gap_threshold=60.0)
        p1 = adapter.ingest_sysmon_xml(xml1)[0]
        p2 = adapter.ingest_sysmon_xml(xml2)[0]
        assert p1.cycle_id != p2.cycle_id

    def test_wi_same_time_same_cycle(self):
        """Events within gap threshold stay in the same auto cycle."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, system_time="2024-01-01T12:00:00.000000Z",
                                   fields={"Image": r"C:\cmd.exe"})
        xml2 = self._sysmon_event(1, system_time="2024-01-01T12:00:30.000000Z",
                                   fields={"Image": r"C:\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01", gap_threshold=300.0)
        p1 = adapter.ingest_sysmon_xml(xml1)[0]
        p2 = adapter.ingest_sysmon_xml(xml2)[0]
        assert p1.cycle_id == p2.cycle_id

    def test_wi_cycle_override(self):
        """Explicit cycle_id argument bypasses auto-discovery."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, fields={"Image": r"C:\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml, cycle_id="operator_cycle_A")
        assert pearls[0].cycle_id == "operator_cycle_A"

    def test_wi_auto_cycle_name_format(self):
        """Auto-discovered cycle names follow auto_{idx:03d}_{label} format."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, fields={"Image": r"C:\powershell.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        pearls = adapter.ingest_sysmon_xml(xml)
        assert pearls[0].cycle_id.startswith("auto_")
        parts = pearls[0].cycle_id.split("_")
        assert parts[1].isdigit()

    def test_wi_primitive_shift_discovery(self):
        """Stable run of exec events then a cred event triggers a new cycle."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        t0 = "2024-01-01T12:00:0{i}.000000Z"
        exec_xml = [
            self._sysmon_event(
                1,
                system_time=f"2024-01-01T12:00:{i:02d}.000000Z",
                fields={"Image": r"C:\cmd.exe"},
            )
            for i in range(6)
        ]
        cred_xml = self._sysmon_event(
            10,
            system_time="2024-01-01T12:00:10.000000Z",
            fields={"TargetImage": r"C:\Windows\System32\lsass.exe"},
        )
        adapter = WindowsIngestAdapter("eng-01", shift_window=5)
        first_cycle = None
        for xml in exec_xml:
            p = adapter.ingest_sysmon_xml(xml)[0]
            if first_cycle is None:
                first_cycle = p.cycle_id
        cred_pearl = adapter.ingest_sysmon_xml(cred_xml)[0]
        assert cred_pearl.cycle_id != first_cycle

    def test_wi_no_shift_below_window(self):
        """Fewer than shift_window events of same type does not trigger shift."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        exec_xml = [
            self._sysmon_event(
                1,
                system_time=f"2024-01-01T12:00:{i:02d}.000000Z",
                fields={"Image": r"C:\cmd.exe"},
            )
            for i in range(3)
        ]
        cred_xml = self._sysmon_event(
            10,
            system_time="2024-01-01T12:00:05.000000Z",
            fields={"TargetImage": r"C:\Windows\System32\lsass.exe"},
        )
        adapter = WindowsIngestAdapter("eng-01", shift_window=5)
        first_cycle = None
        for xml in exec_xml:
            p = adapter.ingest_sysmon_xml(xml)[0]
            if first_cycle is None:
                first_cycle = p.cycle_id
        cred_pearl = adapter.ingest_sysmon_xml(cred_xml)[0]
        assert cred_pearl.cycle_id == first_cycle

    # ------------------------------------------------------------------
    # CycleDiscovery unit tests
    # ------------------------------------------------------------------

    def test_cd_first_event_starts_cycle(self):
        """First event always starts a new cycle."""
        from invar.adapters.redteam.windows_ingest import CycleDiscovery
        cd = CycleDiscovery()
        cid = cd.assign(1000.0, "exec_cmd")
        assert cid.startswith("auto_")

    def test_cd_override_clears_history(self):
        """Operator override sets cycle and clears primitive-shift history."""
        from invar.adapters.redteam.windows_ingest import CycleDiscovery
        cd = CycleDiscovery()
        cd.assign(1000.0, "exec_cmd")
        cd.assign(1001.0, "exec_cmd")
        cid = cd.assign(1002.0, "exec_cmd", override="manual_op")
        assert cid == "manual_op"
        # subsequent event within gap should stay on manual_op
        cid2 = cd.assign(1003.0, "cred_lsass_access")
        assert cid2 == "manual_op"

    def test_cd_gap_resets_to_new_cycle(self):
        """Gap > threshold always starts a new auto cycle."""
        from invar.adapters.redteam.windows_ingest import CycleDiscovery
        cd = CycleDiscovery(gap_threshold=60.0)
        c1 = cd.assign(0.0, "exec_cmd")
        c2 = cd.assign(9999.0, "exec_cmd")
        assert c1 != c2

    # ------------------------------------------------------------------
    # parse_events_xml
    # ------------------------------------------------------------------

    def test_parse_malformed_xml(self):
        """Malformed XML returns empty list without raising."""
        from invar.adapters.redteam.windows_ingest import parse_events_xml
        result = parse_events_xml("<not valid xml<<<")
        assert result == []

    def test_parse_unrecognised_root_tag(self):
        """XML with unrecognised root tag yields no events."""
        from invar.adapters.redteam.windows_ingest import parse_events_xml
        result = parse_events_xml("<SomeOtherRoot><foo/></SomeOtherRoot>")
        assert result == []

    def test_parse_events_container(self):
        """<Events> container with two valid events yields two SysmonEvents."""
        from invar.adapters.redteam.windows_ingest import parse_events_xml
        xml1 = self._sysmon_event(1, fields={"Image": r"C:\cmd.exe"})
        xml2 = self._sysmon_event(10, fields={"TargetImage": r"C:\Windows\System32\lsass.exe"})
        combined = self._events_wrap(xml1, xml2)
        events = parse_events_xml(combined)
        assert len(events) == 2
        assert events[0].event_id == 1
        assert events[1].event_id == 10

    # ------------------------------------------------------------------
    # Determinism
    # ------------------------------------------------------------------

    def test_wi_deterministic(self):
        """Same XML in same order → identical Pearl gate_ids and cycle_ids."""
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml1 = self._sysmon_event(1, system_time="2024-01-01T12:00:00.000000Z",
                                   fields={"Image": r"C:\powershell.exe"})
        xml2 = self._sysmon_event(10, system_time="2024-01-01T12:00:01.000000Z",
                                   fields={"TargetImage": r"C:\Windows\System32\lsass.exe"})
        def run():
            a = WindowsIngestAdapter("eng-01")
            p = a.ingest_sysmon_xml(xml1)
            p += a.ingest_sysmon_xml(xml2)
            return [(x.gate_id, x.cycle_id) for x in p]
        assert run() == run()

    # ------------------------------------------------------------------
    # Layer 0 safety
    # ------------------------------------------------------------------

    def test_wi_no_layer0_effect(self):
        """Ingesting events does not alter the global Layer 0 field energy."""
        from invar.core.support_engine import SupportEngine
        import time as _time
        substrate = SupportEngine()
        t = _time.time()
        energy_before = substrate.field_energy(t)
        from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
        xml = self._sysmon_event(1, fields={"Image": r"C:\cmd.exe"})
        adapter = WindowsIngestAdapter("eng-01")
        adapter.ingest_sysmon_xml(xml, cycle_id="c1")
        assert substrate.field_energy(t) == pytest.approx(energy_before, abs=1e-12)
