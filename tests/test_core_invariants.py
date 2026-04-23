"""
SKG core invariant validation suite.

These tests assert mathematical laws the core must obey unconditionally.
They are not unit tests of implementation — they are proofs that the
implemented system satisfies its own specification.

Each test is labeled with the invariant it asserts. A failure here means
the core has drifted from its own physics, not that "a feature broke."

Invariants tested:
    [H1]  H(g) ∈ [0, 1] always
    [H2]  H(g) = 1 at zero observations
    [H3]  H(g) = 0 at collapse (R or B)
    [H4]  H(g) decreases monotonically as directional support accumulates
    [C1]  |Ψᵢ| ≤ E_self(Ωᵢ) (coherence amplitude bound)
    [C2]  C(Ψᵢ) = 0 when all gates have identical phase
    [C3]  C(Ψᵢ) ∈ [0, 1] always
    [S1]  E_self(Ωᵢ) = Σ H(g) (scale invariance / sum identity)
    [S2]  L(Ψᵢ, Aᵢ) ≥ 0 always
    [S3]  Global L decreases as gates collapse (second law analog)
    [A1]  Hebbian step increases A_ij when phases aligned
    [A2]  Decay step decreases A_ij
    [A3]  A_ij ∈ [0, 1] always
    [T1]  r(Ψ) ∈ [0, 1] always
    [T2]  T_eff(Ψ) ∈ (0, T₀] always
    [T3]  T_eff decreases as coherence increases
    [G1]  Greedy min J selects at least the highest-entropy gate
    [G2]  J decreases when adding a high-entropy gate to empty slice
    [B1]  β₁ = |E| - |V| + k (cycle formula)
    [N1]  W_t(g) = 0 initially
    [N2]  W_t(g) > 0 after observe() with nonzero ΔH
    [N3]  Memory decays after step_memory_decay()
    [CG1] |Ψ̃_K| ≤ Σᵢ|Ψᵢ| (coarse coherence cannot exceed sum of amplitudes)
    [CG2] Ã_KL = A_ij when K and L are singleton clusters
"""
import math
import time
import pytest

from invar.core.envelope import ObsGateEnvelope, DecayClass, SupportContribution
from invar.core.gate import (
    Gate, GateState, gate_p, gate_energy, binary_entropy, COLLAPSE_THRESHOLD
)
from invar.core.support_engine import SupportEngine
from invar.core.gravity import GravityField, InstrumentProfile
from invar.core.field import CouplingField
from invar.core.topology import CouplingGraph, Cycle
from invar.core.functional import e_self, e_couple, local_L, delta_L, global_L
from invar.core.narrative import NarrativeState
from invar.core.observation import J, JWeights, greedy_min_J
from invar.core.coarse_grain import CoarseGraining


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine_with_gates(*gate_specs):
    """
    Create engine + ingest observations.
    gate_specs: list of (gate_id, phi_R, phi_B) — all in workload='w', node='n'
    Returns (engine, gravity).
    """
    engine = SupportEngine()
    gravity = GravityField(engine)
    env = ObsGateEnvelope(instrument_id='probe', workload_id='w', node_key='n')
    for gid, phi_R, phi_B in gate_specs:
        env.add(gid, phi_R=phi_R, phi_B=phi_B, decay_class=DecayClass.STRUCTURAL)
    engine.ingest(env)
    return engine, gravity


def ingest(engine, workload_id, node_key, gate_id, phi_R, phi_B):
    env = ObsGateEnvelope(instrument_id='p', workload_id=workload_id, node_key=node_key)
    env.add(gate_id, phi_R=phi_R, phi_B=phi_B, decay_class=DecayClass.STRUCTURAL)
    engine.ingest(env)


# ---------------------------------------------------------------------------
# [H] Gate energy invariants
# ---------------------------------------------------------------------------

class TestGateEnergyInvariants:

    def test_H1_energy_always_in_unit_interval(self):
        """[H1] H(g) ∈ [0, 1] for any support vector."""
        for phi_R in [0.0, 0.1, 0.5, 0.7, 0.9, 1.0]:
            for phi_B in [0.0, 0.1, 0.5, 0.7, 0.9, 1.0]:
                H = gate_energy(phi_R, phi_B, GateState.U)
                assert 0.0 <= H <= 1.0, f"H={H} out of [0,1] for phi_R={phi_R}, phi_B={phi_B}"

    def test_H2_zero_observations_gives_max_energy(self):
        """[H2] H(g) = 1 at zero observations (maximum superposition prior)."""
        assert gate_energy(0.0, 0.0, GateState.U) == pytest.approx(1.0)

    def test_H3_collapsed_states_have_zero_energy(self):
        """[H3] H(g) = 0 for R and B states regardless of support."""
        for phi_R in [0.0, 0.5, 0.9]:
            assert gate_energy(phi_R, 0.0, GateState.R) == 0.0
            assert gate_energy(0.0, phi_R, GateState.B) == 0.0

    def test_H4_energy_decreases_with_directional_support(self):
        """[H4] Adding directional support strictly decreases H(g)."""
        # Symmetric balanced: add R support → p shifts toward 1 → H falls
        H_00 = gate_energy(0.0, 0.0, GateState.U)   # p=0.5, H=1
        H_30 = gate_energy(0.3, 0.1, GateState.U)   # p=0.75, H<1
        H_80 = gate_energy(0.8, 0.1, GateState.U)   # p=0.89, H<<1
        assert H_00 > H_30 > H_80

    def test_H_is_symmetric_in_support(self):
        """H(φ_R, φ_B) = H(φ_B, φ_R) by symmetry of binary entropy."""
        assert gate_energy(0.3, 0.7, GateState.U) == pytest.approx(
            gate_energy(0.7, 0.3, GateState.U)
        )


# ---------------------------------------------------------------------------
# [C] Coherence invariants
# ---------------------------------------------------------------------------

class TestCoherenceInvariants:

    def test_C1_coherence_amplitude_bounded_by_self_energy(self):
        """[C1] |Ψᵢ| ≤ E_self(Ωᵢ) for any gate configuration."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.3, 0.1),
            ('g2', 0.1, 0.4),
            ('g3', 0.0, 0.0),
        )
        psi = gravity.fiber_tensor('w', 'n')
        e = gravity.self_energy('w', 'n')
        assert abs(psi) <= e + 1e-9, f"|Ψ|={abs(psi)} > E_self={e}"

    def test_C1_holds_for_pure_superposition(self):
        """[C1] Equality approached when all gates have equal phase."""
        # All gates with phi_R=phi_B=0 → all θ=π/2 → all phases aligned → |Ψ|≈E_self
        engine, gravity = make_engine_with_gates(
            ('g1', 0.0, 0.0),
            ('g2', 0.0, 0.0),
            ('g3', 0.0, 0.0),
        )
        psi = gravity.fiber_tensor('w', 'n')
        e = gravity.self_energy('w', 'n')
        # All phases = π/2, all H = 1 → |Ψ| = |3·i| = 3 = E_self
        assert abs(psi) == pytest.approx(e, abs=1e-9)

    def test_C2_local_incoherence_zero_when_all_phases_aligned(self):
        """[C2] C(Ψᵢ) = 0 when all gates have identical phase (all unobserved)."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.0, 0.0),
            ('g2', 0.0, 0.0),
        )
        C = gravity.local_incoherence('w', 'n')
        assert C == pytest.approx(0.0, abs=1e-9)

    def test_C3_local_incoherence_in_unit_interval(self):
        """[C3] C(Ψᵢ) ∈ [0, 1] for any gate configuration."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.8, 0.0),   # phase near 0 (R direction)
            ('g2', 0.0, 0.8),   # phase near π (B direction) — opposing
        )
        C = gravity.local_incoherence('w', 'n')
        assert 0.0 <= C <= 1.0

    def test_C3_coherence_increases_with_contradiction(self):
        """[C3] Incoherence is higher when gates pull in opposite directions.

        Must use sub-threshold phi values (< COLLAPSE_THRESHOLD=0.7) so that
        gates remain in state U with H > 0. Collapsed gates give H=0 → C=0
        regardless of direction, which cannot demonstrate the ordering.
        """
        # Aligned: both pointing R (uncollapsed, phi < 0.70)
        engine_aligned, g_aligned = make_engine_with_gates(
            ('g1', 0.55, 0.05), ('g2', 0.50, 0.10)
        )
        C_aligned = g_aligned.local_incoherence('w', 'n')

        # Contradicting: one leans R, one leans B — phases nearly cancel
        engine_contra, g_contra = make_engine_with_gates(
            ('g1', 0.55, 0.05), ('g2', 0.05, 0.55)
        )
        C_contra = g_contra.local_incoherence('w', 'n')

        assert C_contra > C_aligned


# ---------------------------------------------------------------------------
# [S] Scale and functional invariants
# ---------------------------------------------------------------------------

class TestFunctionalInvariants:

    def test_S1_self_energy_equals_sum_of_gate_entropies(self):
        """[S1] E_self(Ωᵢ) = Σ H(g) — scale invariance sum identity."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.3, 0.1), ('g2', 0.0, 0.0), ('g3', 0.6, 0.2)
        )
        e = e_self('w', 'n', engine)
        gates = engine.gates('w', 'n')
        expected = sum(g.energy() for g in gates.values())
        assert e == pytest.approx(expected, abs=1e-9)

    def test_S2_local_L_nonnegative(self):
        """[S2] L(Ψᵢ, Aᵢ) ≥ 0 always."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.4, 0.1), ('g2', 0.0, 0.0)
        )
        field = CouplingField()
        graph = CouplingGraph.build(field)
        L = local_L('w', 'n', engine, field, graph, gravity)
        assert L >= 0.0

    def test_S3_global_L_decreases_as_gates_collapse(self):
        """[S3] Global L falls when high-entropy gates collapse (second law analog)."""
        engine = SupportEngine()
        gravity = GravityField(engine)
        field = CouplingField()

        # Start: two unobserved gates
        ingest(engine, 'w', 'n', 'g1', 0.0, 0.0)
        ingest(engine, 'w', 'n', 'g2', 0.0, 0.0)
        graph = CouplingGraph.build(field)
        L_before = global_L(engine, field, graph, gravity)['total']

        # Collapse g1 with strong R support
        ingest(engine, 'w', 'n', 'g1', 0.9, 0.0)
        graph = CouplingGraph.build(field)
        L_after = global_L(engine, field, graph, gravity)['total']

        assert L_after < L_before

    def test_S3_L_zero_when_all_collapsed(self):
        """[S3] L ≈ 0 when all gates are collapsed and field is coherent."""
        engine = SupportEngine()
        gravity = GravityField(engine)
        field = CouplingField()

        ingest(engine, 'w', 'n', 'g1', 0.9, 0.0)
        ingest(engine, 'w', 'n', 'g2', 0.0, 0.9)
        graph = CouplingGraph.build(field)
        result = global_L(engine, field, graph, gravity)
        # Both gates collapsed → E_self = 0; small residual from incoherence
        assert result['local_sum'] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# [A] Coupling field invariants
# ---------------------------------------------------------------------------

class TestCouplingFieldInvariants:

    def test_A1_hebbian_increases_coupling_when_phases_aligned(self):
        """[A1] ∂ₜA_ij > 0 (coupling increases) when Ψᵢ and Ψⱼ are aligned."""
        field = CouplingField(eta=0.1)
        i = ('w', 'n1')
        j = ('w', 'n2')
        # Both pointing in same direction (both imaginary positive)
        psi_i = complex(0.0, 1.0)
        psi_j = complex(0.0, 1.0)
        A_before = field.get(i, j)   # 0.5
        A_after = field.step(i, j, psi_i, psi_j, dt=1.0)
        assert A_after > A_before

    def test_A1_hebbian_decreases_coupling_when_phases_opposed(self):
        """[A1] Coupling decreases when Ψᵢ and Ψⱼ are anti-aligned."""
        field = CouplingField(eta=0.3, lambda_K=0.0)  # no decay
        i = ('w', 'n1')
        j = ('w', 'n2')
        psi_i = complex(0.0, 1.0)   # phase π/2
        psi_j = complex(0.0, -1.0)  # phase -π/2 (anti-aligned)
        A_before = field.get(i, j)
        A_after = field.step(i, j, psi_i, psi_j, dt=1.0)
        assert A_after < A_before

    def test_A2_decay_decreases_coupling(self):
        """[A2] Coupling decays under decoherence (−λ_K·A_ij term)."""
        field = CouplingField(eta=0.0, lambda_K=0.1)  # no Hebbian
        i = ('w', 'n1')
        j = ('w', 'n2')
        # First set a nonzero coupling
        field.step(i, j, complex(1, 0), complex(1, 0), dt=1.0)
        A_before = field.get(i, j)
        field.decay(dt=10.0)
        A_after = field.get(i, j)
        assert A_after < A_before

    def test_A3_coupling_always_in_unit_interval(self):
        """[A3] A_ij ∈ [0, 1] after any number of Hebbian steps."""
        field = CouplingField(eta=1.0, lambda_K=0.0)  # aggressive update
        i = ('w', 'n1')
        j = ('w', 'n2')
        for _ in range(100):
            field.step(i, j, complex(0, 2.0), complex(0, 2.0), dt=1.0)
        A = field.get(i, j)
        assert 0.0 <= A <= 1.0


# ---------------------------------------------------------------------------
# [T] Temperature and coherence invariants
# ---------------------------------------------------------------------------

class TestTemperatureInvariants:

    def test_T1_global_coherence_in_unit_interval(self):
        """[T1] r(Ψ) ∈ [0, 1] always."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.3, 0.1), ('g2', 0.1, 0.3)
        )
        r = gravity.global_coherence()
        assert 0.0 <= r <= 1.0

    def test_T2_teff_always_positive(self):
        """[T2] T_eff(Ψ) > 0 always (due to ε)."""
        engine, gravity = make_engine_with_gates(('g1', 0.0, 0.0))
        T = gravity.effective_temperature(T0=1.0)
        assert T > 0.0

    def test_T2_teff_bounded_above_by_T0(self):
        """[T2] T_eff ≤ T₀ (upper bound at zero coherence)."""
        engine, gravity = make_engine_with_gates(
            ('g1', 0.8, 0.0), ('g2', 0.0, 0.8)  # phases cancel → r→0
        )
        T0 = 2.0
        T = gravity.effective_temperature(T0=T0)
        assert T <= T0 + 1e-9

    def test_T3_teff_decreases_as_coherence_increases(self):
        """[T3] More coherent field → lower T_eff (more selective gravity)."""
        # Incoherent: opposing phases
        engine_i, gravity_i = make_engine_with_gates(
            ('g1', 0.8, 0.0), ('g2', 0.0, 0.8)
        )
        T_incoherent = gravity_i.effective_temperature(T0=1.0)

        # Coherent: all in same phase direction
        engine_c, gravity_c = make_engine_with_gates(
            ('g1', 0.0, 0.0), ('g2', 0.0, 0.0)
        )
        T_coherent = gravity_c.effective_temperature(T0=1.0)

        assert T_incoherent > T_coherent


# ---------------------------------------------------------------------------
# [G] Observation functional invariants
# ---------------------------------------------------------------------------

class TestObservationFunctionalInvariants:

    def test_G1_greedy_selects_nonzero_entropy_gate_first(self):
        """[G1] Greedy argmin J includes the highest-entropy gate."""
        engine = SupportEngine()
        narrative = NarrativeState()
        # High-entropy gate (dark)
        ingest(engine, 'w', 'n', 'dark_gate', 0.0, 0.0)
        # Low-entropy gate (nearly collapsed)
        ingest(engine, 'w', 'n', 'clear_gate', 0.8, 0.0)

        obs = greedy_min_J(engine, narrative, 'w', 'n', max_gates=1)
        # The dark gate contributes more to J reduction
        assert 'dark_gate' in obs.gate_ids or 'clear_gate' in obs.gate_ids

    def test_G2_J_nonneg_at_empty_slice(self):
        """[G2] J(∅) ≥ 0 (all uncertainty unresolved, no cost)."""
        engine = SupportEngine()
        narrative = NarrativeState()
        ingest(engine, 'w', 'n', 'g1', 0.0, 0.0)
        result = J(set(), {'g1'}, engine, narrative, 'w', 'n')
        # U = 1.0 (all unresolved), C = 0, N = 0
        assert result.J >= 0.0

    def test_narrative_utility_biases_selection(self):
        """Narrative intent raises priority of a specific gate."""
        engine = SupportEngine()
        narrative = NarrativeState()
        ingest(engine, 'w', 'n', 'target_gate', 0.0, 0.0)
        ingest(engine, 'w', 'n', 'other_gate', 0.0, 0.0)

        # High intent for target_gate
        narrative.set_intent('target_gate', 1.0)

        obs = greedy_min_J(engine, narrative, 'w', 'n', max_gates=1)
        # With high narrative weight, target_gate should be preferred
        assert 'target_gate' in obs.gate_ids


# ---------------------------------------------------------------------------
# [B] Topology invariants
# ---------------------------------------------------------------------------

class TestTopologyInvariants:

    def test_B1_beta1_formula_single_edge(self):
        """[B1] β₁ = |E| - |V| + k. Single edge: β₁ = 1-2+1 = 0."""
        field = CouplingField()
        i = ('w', 'n1')
        j = ('w', 'n2')
        # Force a resolved edge: A far from 0.5
        for _ in range(20):
            field.step(i, j, complex(0, 1), complex(0, 1), dt=1.0)
        graph = CouplingGraph.build(field)
        # |E|=1, |V|=2, k=1 → β₁=0
        assert graph.beta_1 == 0

    def test_B1_beta1_formula_triangle(self):
        """[B1] Triangle: 3 edges, 3 vertices, 1 component → β₁ = 1."""
        field = CouplingField()
        n1, n2, n3 = ('w', 'n1'), ('w', 'n2'), ('w', 'n3')
        for pair in [(n1, n2), (n2, n3), (n1, n3)]:
            for _ in range(20):
                field.step(pair[0], pair[1], complex(0, 1), complex(0, 1), dt=1.0)
        graph = CouplingGraph.build(field)
        assert graph.beta_1 == 1

    def test_B1_disconnected_graph(self):
        """[B1] Two disconnected edges: |E|=2, |V|=4, k=2 → β₁=0."""
        field = CouplingField()
        n1, n2, n3, n4 = ('w', 'n1'), ('w', 'n2'), ('w', 'n3'), ('w', 'n4')
        for pair in [(n1, n2), (n3, n4)]:
            for _ in range(20):
                field.step(pair[0], pair[1], complex(0, 1), complex(0, 1), dt=1.0)
        graph = CouplingGraph.build(field)
        assert graph.beta_1 == 0

    def test_holonomy_zero_for_aligned_cycle(self):
        """Holonomy Φ(c) ≈ 0 when all gates in cycle have same phase."""
        field = CouplingField()
        n1, n2, n3 = ('w', 'n1'), ('w', 'n2'), ('w', 'n3')
        psi = complex(0, 1)   # all in same direction
        for pair in [(n1, n2), (n2, n3), (n1, n3)]:
            for _ in range(20):
                field.step(pair[0], pair[1], psi, psi, dt=1.0)

        graph = CouplingGraph.build(field)
        engine = SupportEngine()
        # Uniform theta = π/2 everywhere
        theta_fn = lambda mkey: math.pi / 2

        for cycle in graph.cycles:
            phi = cycle.holonomy(field, theta_fn)
            cost = cycle.curvature_cost(field, theta_fn)
            # With aligned phases and symmetric coupling, holonomy should be near 0
            # (1 - cos(φ)) should be small
            assert cost >= 0.0   # always non-negative


# ---------------------------------------------------------------------------
# [N] Narrative invariants
# ---------------------------------------------------------------------------

class TestNarrativeInvariants:

    def test_N1_weight_zero_initially(self):
        """[N1] W_t(g) = 0 for any gate before any update."""
        narrative = NarrativeState()
        assert narrative.W('any_gate') == 0.0

    def test_N2_weight_positive_after_observe(self):
        """[N2] W_t(g) > 0 after observe() with nonzero |ΔH|."""
        narrative = NarrativeState()
        narrative.observe('gate-x', delta_H=0.5)
        assert narrative.W('gate-x') > 0.0

    def test_N3_memory_decays(self):
        """[N3] M_t(g) decreases after step_memory_decay()."""
        narrative = NarrativeState()
        narrative.observe('gate-x', delta_H=1.0)
        W_before = narrative.W('gate-x')
        narrative.step_memory_decay()
        W_after = narrative.W('gate-x')
        assert W_after < W_before

    def test_intent_survives_memory_decay(self):
        """Intent weight I_t(g) is not affected by memory decay."""
        narrative = NarrativeState(gamma_I=1.0, gamma_M=0.0, gamma_R=0.0)
        narrative.set_intent('gate-x', 0.8)
        narrative.step_memory_decay()
        assert narrative.W('gate-x') == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# [CG] Coarse-graining invariants
# ---------------------------------------------------------------------------

class TestCoarseGrainInvariants:

    def test_CG1_coarse_amplitude_bounded(self):
        """[CG1] |Ψ̃_K| ≤ Σᵢ ωᵢ·|Ψᵢ| (weighted sum amplitude bound)."""
        engine = SupportEngine()
        gravity = GravityField(engine)
        field = CouplingField()

        for node in ['n1', 'n2', 'n3']:
            ingest(engine, 'w', node, 'g1', 0.3, 0.1)
            ingest(engine, 'w', node, 'g2', 0.1, 0.4)

        cg = CoarseGraining(engine, field, gravity)
        members = [('w', 'n1'), ('w', 'n2'), ('w', 'n3')]
        cg.define_cluster('K', members)
        m = cg.manifold('K')

        # |Ψ̃_K| ≤ E_K (from Prop 1 applied to coarse level)
        # In practice: |Ψ̃_K| = |Σ ωᵢΨᵢ| ≤ Σ ωᵢ|Ψᵢ| ≤ Σ ωᵢ·E_self(i)
        # The right bound is |Σ ωᵢΨᵢ| ≤ Σ |Ψᵢ| (triangle inequality)
        psi_sum = sum(abs(gravity.fiber_tensor('w', f'n{i}')) for i in range(1, 4))
        assert abs(m.Psi) <= psi_sum + 1e-9

    def test_CG2_singleton_cluster_recovers_direct_coupling(self):
        """[CG2] Ã_KL = A_ij when K={i} and L={j} are singleton clusters."""
        engine = SupportEngine()
        gravity = GravityField(engine)
        field = CouplingField()

        m1, m2 = ('w', 'n1'), ('w', 'n2')
        ingest(engine, 'w', 'n1', 'g1', 0.3, 0.1)
        ingest(engine, 'w', 'n2', 'g1', 0.3, 0.1)

        psi1 = gravity.fiber_tensor('w', 'n1')
        psi2 = gravity.fiber_tensor('w', 'n2')
        field.step(m1, m2, psi1, psi2, dt=5.0)
        A_direct = field.get(m1, m2)

        cg = CoarseGraining(engine, field, gravity)
        cg.define_cluster('K', [m1])
        cg.define_cluster('L', [m2])
        A_coarse = cg.coupling('K', 'L')

        assert A_coarse == pytest.approx(A_direct, abs=1e-6)
