"""
Tests for skg.core physics — gate energy, support engine, gravity field.

These tests verify the mathematical invariants stated in Work 5:
  - H(g) = 1.0 at zero observations (Proposition 1)
  - H(g) = 0 at collapse (Proposition 1)
  - Count formula is zero-observation limit (Proposition 2)
  - Scale invariance: field energy = sum of gate energies
  - Gravity Φ sums H(g) values, not counts
"""
import math
import pytest
from invar.core.envelope import ObsGateEnvelope, DecayClass, coherence
from invar.core.gate import Gate, GateState, gate_p, gate_energy, binary_entropy, COLLAPSE_THRESHOLD
from invar.core.support_engine import SupportEngine
from invar.core.gravity import GravityField, InstrumentProfile


# ---------------------------------------------------------------------------
# gate_p and binary_entropy
# ---------------------------------------------------------------------------

def test_gate_p_zero_observations():
    """Zero-observation prior is 0.5 (maximum superposition)."""
    assert gate_p(0.0, 0.0) == pytest.approx(0.5)


def test_gate_p_r_collapse():
    """p approaches 1 as φ_R dominates."""
    assert gate_p(0.9, 0.0) == pytest.approx(1.0)


def test_gate_p_b_collapse():
    """p approaches 0 as φ_B dominates."""
    assert gate_p(0.0, 0.9) == pytest.approx(0.0)


def test_gate_p_equal_support():
    """Equal support → p = 0.5."""
    assert gate_p(0.5, 0.5) == pytest.approx(0.5)


def test_binary_entropy_max_at_half():
    """H_binary is maximized at 1 bit when p = 0.5."""
    assert binary_entropy(0.5) == pytest.approx(1.0)


def test_binary_entropy_zero_at_extremes():
    """H_binary is 0 at p → 0 and p → 1."""
    assert binary_entropy(1e-10) == pytest.approx(0.0, abs=1e-6)
    assert binary_entropy(1.0 - 1e-10) == pytest.approx(0.0, abs=1e-6)


def test_gate_energy_zero_observations():
    """H(g) = 1 bit at zero observations (Proposition 1)."""
    assert gate_energy(0.0, 0.0, GateState.U) == pytest.approx(1.0)


def test_gate_energy_collapsed_states_are_zero():
    """Collapsed gates carry zero energy regardless of support."""
    assert gate_energy(0.9, 0.0, GateState.R) == 0.0
    assert gate_energy(0.0, 0.9, GateState.B) == 0.0


def test_gate_energy_decreases_with_evidence():
    """Adding directional support reduces entropy (requires mixed support)."""
    # With balanced support (φ_R=φ_B), p=0.5 → H=1.0
    H_balanced = gate_energy(0.5, 0.5, GateState.U)
    # With biased support, p shifts away from 0.5 → H < 1.0
    H_biased = gate_energy(0.8, 0.2, GateState.U)
    # With strongly biased support → H closer to 0
    H_strong = gate_energy(0.9, 0.1, GateState.U)
    assert H_balanced > H_biased > H_strong
    # Confirm: balanced = maximum entropy
    assert H_balanced == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Gate (stateful object)
# ---------------------------------------------------------------------------

def test_gate_starts_in_superposition():
    g = Gate(gate_id="test", workload_id="w1", node_key="n1")
    assert g.state() == GateState.U
    assert g.energy() == pytest.approx(1.0)


def test_gate_collapses_r_above_threshold():
    g = Gate(gate_id="test", workload_id="w1", node_key="n1")
    from invar.core.envelope import SupportContribution
    import time
    # Use 0.8 > threshold=0.7 with structural decay margin over 1 second:
    # 0.8 * exp(-1e-4 * 1) ≈ 0.7999 > 0.7
    c = SupportContribution(
        gate_id="test", phi_R=0.8, phi_B=0.0,
        decay_class=DecayClass.STRUCTURAL, t0=time.time() - 1,
    )
    g.add_contribution(c)
    assert g.state() == GateState.R
    assert g.energy() == 0.0


def test_gate_energy_decreases_after_observation():
    g = Gate(gate_id="test", workload_id="w1", node_key="n1")
    from invar.core.envelope import SupportContribution
    import time
    assert g.energy() == pytest.approx(1.0)
    c = SupportContribution(
        gate_id="test", phi_R=0.3, phi_B=0.0,
        decay_class=DecayClass.OPERATIONAL, t0=time.time(),
    )
    g.add_contribution(c)
    assert g.energy() < 1.0


def test_gate_phase_at_superposition():
    """θ = π/2 at maximum superposition (p=0.5)."""
    g = Gate(gate_id="test", workload_id="w1", node_key="n1")
    assert g.phase() == pytest.approx(math.pi / 2)


# ---------------------------------------------------------------------------
# SupportEngine
# ---------------------------------------------------------------------------

def test_support_engine_emits_pearls():
    engine = SupportEngine()
    env = ObsGateEnvelope(
        instrument_id="probe", workload_id="w1", node_key="n1"
    )
    env.add("gate-a", phi_R=0.5, phi_B=0.0)
    pearls = engine.ingest(env)
    assert len(pearls) == 1
    assert pearls[0].gate_id == "gate-a"


def test_support_engine_H_before_is_one_on_first_observation():
    """First observation: H_before = 1.0 (zero-observation prior)."""
    engine = SupportEngine()
    env = ObsGateEnvelope(instrument_id="p", workload_id="w1", node_key="n1")
    env.add("g1", phi_R=0.5, phi_B=0.0)
    pearls = engine.ingest(env)
    assert pearls[0].H_before == pytest.approx(1.0)


def test_support_engine_collapse_pearl():
    """Pearl records collapse event correctly."""
    engine = SupportEngine()
    env = ObsGateEnvelope(instrument_id="p", workload_id="w1", node_key="n1")
    # Use 0.8 > threshold; structural decay is negligible at t=now
    env.add("g1", phi_R=0.8, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
    pearls = engine.ingest(env)
    p = pearls[0]
    assert p.is_collapse_event
    assert p.state_after == GateState.R
    assert p.delta_H == pytest.approx(-1.0)


def test_support_engine_field_energy_is_sum_of_gate_energies():
    """Scale invariance: field energy = Σ H(g). Proposition 2 corollary."""
    engine = SupportEngine()
    env = ObsGateEnvelope(instrument_id="p", workload_id="w1", node_key="n1")
    env.add("g1", phi_R=0.3, phi_B=0.0)
    env.add("g2", phi_R=0.0, phi_B=0.0)  # unobserved (via zero contribution)
    engine.ingest(env)

    gates = engine.gates("w1", "n1")
    expected = sum(g.energy() for g in gates.values())
    assert engine.field_energy() == pytest.approx(expected, abs=1e-9)


def test_support_engine_count_formula_at_zero_observations():
    """Count formula recovery: Σ H(g) = |{U gates}| when all gates unobserved."""
    engine = SupportEngine()
    # Ingest 3 gates with no real directional support
    env = ObsGateEnvelope(instrument_id="p", workload_id="w1", node_key="n1")
    # Inject tiny equal support so they exist in the store without real bias
    env.add("g1", phi_R=0.0, phi_B=0.0)
    env.add("g2", phi_R=0.0, phi_B=0.0)
    env.add("g3", phi_R=0.0, phi_B=0.0)
    engine.ingest(env)

    # All gates in superposition → H=1 each → total = 3.0 = count
    fe = engine.field_energy()
    assert fe == pytest.approx(3.0, abs=1e-6)


# ---------------------------------------------------------------------------
# GravityField
# ---------------------------------------------------------------------------

def test_gravity_phi_for_unobserved_manifestation():
    """Gravity gives max Φ (H=1 per gate) for completely dark manifestation."""
    engine = SupportEngine()
    gravity = GravityField(engine)
    gravity.register_instrument(InstrumentProfile(
        instrument_id="probe",
        gate_coverage={"g1", "g2"},
        cost=1.0,
    ))
    phi = gravity.phi("probe", "w1", "n1")
    # 2 unobserved gates × 1.0 bit each / cost=1
    assert phi == pytest.approx(2.0)


def test_gravity_phi_decreases_after_collapse():
    """Φ decreases after a gate collapses."""
    engine = SupportEngine()
    gravity = GravityField(engine)
    gravity.register_instrument(InstrumentProfile(
        instrument_id="probe",
        gate_coverage={"g1", "g2"},
        cost=1.0,
    ))

    phi_before = gravity.phi("probe", "w1", "n1")  # both dark

    env = ObsGateEnvelope(instrument_id="probe", workload_id="w1", node_key="n1")
    env.add("g1", phi_R=COLLAPSE_THRESHOLD, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
    engine.ingest(env)

    phi_after = gravity.phi("probe", "w1", "n1")  # g1 collapsed
    assert phi_after < phi_before


def test_gravity_ranks_instruments():
    """Rank returns instruments sorted by Φ descending."""
    engine = SupportEngine()
    gravity = GravityField(engine)
    # Two instruments with different coverage
    gravity.register_instrument(InstrumentProfile(
        instrument_id="big_probe", gate_coverage={"g1", "g2", "g3"}, cost=1.0
    ))
    gravity.register_instrument(InstrumentProfile(
        instrument_id="small_probe", gate_coverage={"g1"}, cost=1.0
    ))
    targets = gravity.rank(workload_id="w1", node_key="n1")
    assert len(targets) == 2
    assert targets[0].instrument_id == "big_probe"
    assert targets[0].priority > targets[1].priority


def test_gravity_receptivity_at_superposition():
    """Receptivity = 1.0 when no observations (maximum coupling)."""
    engine = SupportEngine()
    gravity = GravityField(engine)
    r = gravity.receptivity("w1", "n1")
    assert r == pytest.approx(1.0)


def test_gravity_fiber_tensor_zero_at_balanced_field():
    """Z(L) ≈ 0 when one gate is fully R and another fully B."""
    engine = SupportEngine()
    gravity = GravityField(engine)

    env = ObsGateEnvelope(instrument_id="p", workload_id="w1", node_key="n1")
    env.add("g_r", phi_R=0.9, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
    env.add("g_b", phi_R=0.0, phi_B=0.9, decay_class=DecayClass.STRUCTURAL)
    engine.ingest(env)

    Z = gravity.fiber_tensor("w1", "n1")
    # g_r: θ=(1-1)π=0 → e^(i·0)=1
    # g_b: θ=(1-0)π=π → e^(iπ)=-1
    # Z = 1 + (-1) = 0
    assert abs(Z) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Decoherence
# ---------------------------------------------------------------------------

def test_coherence_decays_exponentially():
    """φ(t) = φ₀·exp(-λ(t-t₀)). Structural decay: λ=1e-4."""
    t0 = 0.0
    t = 86400.0  # 1 day later
    phi0 = 1.0
    phi_t = coherence(phi0, DecayClass.STRUCTURAL, t0, t)
    expected = math.exp(-1e-4 * 86400)
    assert phi_t == pytest.approx(expected, rel=1e-6)


def test_ephemeral_decay_faster_than_structural():
    t0 = 0.0
    t = 3600.0  # 1 hour
    phi_s = coherence(1.0, DecayClass.STRUCTURAL, t0, t)
    phi_e = coherence(1.0, DecayClass.EPHEMERAL, t0, t)
    assert phi_e < phi_s
