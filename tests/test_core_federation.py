"""
INVAR federation tests — scale invariance validation.

[F1] Invariant preservation at federation level
[F2] No-overlap regime characterization
[F3] Partial-overlap regime characterization
[F4] Strong-overlap regime characterization
[F5] Federation coupling bounded and symmetric
[F6] Scale invariance: same law governs cluster as gate level
[F7] Federation coherence r_coarse ∈ [0, 1]
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from federation.core import (
    FederationCore,
    FederationHarness,
    classify_regime,
    REGIME_ISOLATION,
    REGIME_ALIGNMENT,
    REGIME_STABLE_SPLIT,
    REGIME_DRIFT_BOUNDARY,
    REGIME_UNCERTAIN,
)
from federation.scenarios import (
    scenario_no_overlap,
    scenario_partial_overlap,
    scenario_strong_overlap,
)
from invar.core.envelope import ObsGateEnvelope, DecayClass
from invar.core.support_engine import SupportEngine
from invar.core.gravity import GravityField
from invar.core.field import CouplingField
from invar.core.coarse_grain import CoarseGraining

_N_STEPS = 150   # enough to observe regime without slow tests


def run(harness, n=_N_STEPS):
    """Run harness for n steps, return list of snapshots."""
    snaps = []
    for step in range(1, n + 1):
        harness.step(dt=1.0)
        if step % 50 == 0 or step == n:
            snaps.append(harness.snapshot(step))
    return snaps


# ---------------------------------------------------------------------------
# [F1] Invariant preservation
# ---------------------------------------------------------------------------

class TestFederationInvariants:

    def test_F1_A_KL_bounded_no_overlap(self):
        """[F1] Ã_KL ∈ [0, 1] throughout no-overlap run."""
        harness = scenario_no_overlap()
        snaps = run(harness)
        for s in snaps:
            assert 0.0 <= s.A_KL <= 1.0 + 1e-9, f"Ã_KL={s.A_KL} out of bounds"

    def test_F1_A_KL_bounded_strong_overlap(self):
        """[F1] Ã_KL ∈ [0, 1] throughout strong-overlap run."""
        harness = scenario_strong_overlap()
        snaps = run(harness)
        for s in snaps:
            assert 0.0 <= s.A_KL <= 1.0 + 1e-9

    def test_F1_L_nonneg_all_scenarios(self):
        """[F1] L₁ ≥ 0 and L₂ ≥ 0 throughout all scenarios."""
        for build_fn in [scenario_no_overlap, scenario_partial_overlap, scenario_strong_overlap]:
            harness = build_fn()
            snaps = run(harness)
            for s in snaps:
                assert s.L1 >= 0.0, f"L1 < 0: {s.L1}"
                assert s.L2 >= 0.0, f"L2 < 0: {s.L2}"

    def test_F1_r_bounded_all_scenarios(self):
        """[F1] r₁, r₂ ∈ [0, 1] throughout all scenarios."""
        for build_fn in [scenario_no_overlap, scenario_partial_overlap, scenario_strong_overlap]:
            harness = build_fn()
            snaps = run(harness)
            for s in snaps:
                assert 0.0 <= s.r1 <= 1.0 + 1e-9
                assert 0.0 <= s.r2 <= 1.0 + 1e-9

    def test_F1_r_coarse_bounded(self):
        """[F1] r_coarse ∈ [0, 1] for all scenarios."""
        for build_fn in [scenario_no_overlap, scenario_partial_overlap, scenario_strong_overlap]:
            harness = build_fn()
            snaps = run(harness)
            for s in snaps:
                assert 0.0 <= s.r_coarse <= 1.0 + 1e-9, f"r_coarse={s.r_coarse}"

    def test_F1_delta_L_nonneg(self):
        """[F1] ΔL = |L₁ - L₂| ≥ 0 always."""
        for build_fn in [scenario_no_overlap, scenario_partial_overlap, scenario_strong_overlap]:
            harness = build_fn()
            snaps = run(harness)
            for s in snaps:
                assert s.delta_L >= 0.0

    def test_F1_coherence_bound_at_coarse_level(self):
        """[F1] |Ψ̃_K| and |Ψ̃_L| are finite and non-negative."""
        harness = scenario_strong_overlap()
        run(harness)
        snaps = harness.snapshots()
        for s in snaps:
            assert s.psi_K_amp >= 0.0
            assert s.psi_L_amp >= 0.0


# ---------------------------------------------------------------------------
# [F2] No-overlap regime
# ---------------------------------------------------------------------------

class TestNoOverlapRegime:

    def test_F2_no_overlap_never_aligns(self):
        """[F2] No-overlap cores with opposing evidence → Ã_KL not > 0.6 (no alignment)."""
        harness = scenario_no_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        # Opposing phases → Hebbian < 0 → Ã_KL stays low, never aligns
        assert final.A_KL < 0.6, (
            f"No-overlap scenario unexpectedly aligned: Ã_KL={final.A_KL:.4f}"
        )

    def test_F2_no_overlap_regime_not_alignment(self):
        """[F2] No-overlap with opposing evidence → not classified as alignment."""
        harness = scenario_no_overlap()
        run(harness, n=_N_STEPS)
        regime = harness.final_regime()
        assert regime != REGIME_ALIGNMENT, (
            f"No-overlap regime should not be alignment, got: {regime}"
        )

    def test_F2_no_overlap_stable_state(self):
        """[F2] No-overlap A_KL converges to a stable value (low variance)."""
        harness = scenario_no_overlap()
        snaps = run(harness, n=_N_STEPS)
        # All snapshots should have similar A_KL values (converged)
        A_vals = [s.A_KL for s in snaps]
        if len(A_vals) > 1:
            spread = max(A_vals) - min(A_vals)
            assert spread < 0.05, f"A_KL not stable in no-overlap: spread={spread:.4f}"


# ---------------------------------------------------------------------------
# [F3] Partial-overlap regime
# ---------------------------------------------------------------------------

class TestPartialOverlapRegime:

    def test_F3_partial_overlap_A_KL_drifts(self):
        """[F3] Partial overlap → Ã_KL drifts from 0.5 (shared components align)."""
        harness = scenario_partial_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        # Shared components produce positive Hebbian → A_KL should drift from 0.5
        assert abs(final.A_KL - 0.5) > 0.05, (
            f"Partial overlap: Ã_KL should drift, but Ã_KL={final.A_KL:.4f}"
        )

    def test_F3_partial_overlap_delta_L_nonzero(self):
        """[F3] Partial overlap → ΔL > 0 (cores have different entropy landscapes)."""
        harness = scenario_partial_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        assert final.delta_L > 0.1, (
            f"Expected ΔL > 0 for different cores, got {final.delta_L:.4f}"
        )

    def test_F3_partial_overlap_r_coarse_above_threshold(self):
        """[F3] Partial overlap → r_coarse > 0.3 (some alignment via shared evidence)."""
        harness = scenario_partial_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        assert final.r_coarse > 0.3, (
            f"Partial overlap should produce r_coarse > 0.3, got {final.r_coarse:.4f}"
        )


# ---------------------------------------------------------------------------
# [F4] Strong-overlap regime
# ---------------------------------------------------------------------------

class TestStrongOverlapRegime:

    def test_F4_strong_overlap_alignment(self):
        """[F4] Strong overlap → regime classified as alignment."""
        harness = scenario_strong_overlap()
        run(harness, n=_N_STEPS)
        regime = harness.final_regime()
        assert regime == REGIME_ALIGNMENT, (
            f"Strong overlap expected alignment, got: {regime}"
        )

    def test_F4_strong_overlap_delta_L_zero(self):
        """[F4] Identical evidence → ΔL = 0 (same entropy landscape)."""
        harness = scenario_strong_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        assert final.delta_L < 1e-6, (
            f"Identical cores should have ΔL≈0, got {final.delta_L:.6f}"
        )

    def test_F4_strong_overlap_r_coarse_near_1(self):
        """[F4] Identical evidence → r_coarse near 1 (phases fully aligned)."""
        harness = scenario_strong_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        assert final.r_coarse > 0.9, (
            f"Strong overlap: r_coarse should be near 1, got {final.r_coarse:.4f}"
        )

    def test_F4_strong_overlap_A_KL_above_half(self):
        """[F4] Identical evidence → Ã_KL > 0.5 (Hebbian drives alignment)."""
        harness = scenario_strong_overlap()
        snaps = run(harness, n=_N_STEPS)
        final = snaps[-1]
        assert final.A_KL > 0.5, (
            f"Strong overlap: Ã_KL should be > 0.5, got {final.A_KL:.4f}"
        )


# ---------------------------------------------------------------------------
# [F5] Coupling symmetry
# ---------------------------------------------------------------------------

class TestFederationCouplingSymmetry:

    def test_F5_coupling_symmetric(self):
        """[F5] Ã_KL = Ã_LK (coupling is symmetric)."""
        harness = scenario_partial_overlap()
        run(harness, n=50)
        id1, id2 = list(harness.cores.keys())
        A_12 = harness.A_KL(id1, id2)
        A_21 = harness.A_KL(id2, id1)
        assert abs(A_12 - A_21) < 1e-9, f"Coupling not symmetric: {A_12} vs {A_21}"

    def test_F5_coupling_symmetric_strong(self):
        """[F5] Strong-overlap coupling is also symmetric."""
        harness = scenario_strong_overlap()
        run(harness, n=50)
        id1, id2 = list(harness.cores.keys())
        A_12 = harness.A_KL(id1, id2)
        A_21 = harness.A_KL(id2, id1)
        assert abs(A_12 - A_21) < 1e-9


# ---------------------------------------------------------------------------
# [F6] Scale invariance
# ---------------------------------------------------------------------------

class TestScaleInvariance:

    def test_F6_coarse_psi_satisfies_coherence_bound(self):
        """[F6] |Ψ̃_K| ≤ E_K at cluster level (coherence bound holds at coarse scale)."""
        harness = scenario_partial_overlap()
        run(harness, n=50)

        for core_id, core in harness.cores.items():
            from invar.core.coarse_grain import CoarseGraining
            cg = CoarseGraining(core.engine, core.field, core.gravity)
            cg.define_cluster('K', core.manifestations)
            manifold = cg.manifold('K')
            assert abs(manifold.Psi) <= manifold.E + 1e-9, (
                f"Coherence bound violated at cluster level for {core_id}: "
                f"|Ψ̃|={abs(manifold.Psi):.4f} > E={manifold.E:.4f}"
            )

    def test_F6_same_equation_governs_cluster_as_gate(self):
        """[F6] FederationHarness uses the same CouplingField.step() as intra-core.

        Scale invariance claim: no special federation equation — the same
        Hebbian + decoherence governs Ã_KL as governs Aᵢⱼ.
        """
        harness = scenario_strong_overlap()
        # The federation field is a CouplingField instance
        from invar.core.field import CouplingField
        assert isinstance(harness._fed_field, CouplingField), (
            "Federation coupling must use the same CouplingField as intra-core"
        )

    def test_F6_coarse_manifold_coherence_in_unit_interval(self):
        """[F6] C(Ψ̃_K) ∈ [0, 1] at coarse level."""
        harness = scenario_partial_overlap()
        run(harness, n=50)
        for core_id, core in harness.cores.items():
            cg = CoarseGraining(core.engine, core.field, core.gravity)
            cg.define_cluster('K', core.manifestations)
            manifold = cg.manifold('K')
            assert 0.0 <= manifold.coherence <= 1.0 + 1e-9, (
                f"C(Ψ̃) out of [0,1] for {core_id}: {manifold.coherence}"
            )


# ---------------------------------------------------------------------------
# [F7] Federation coherence
# ---------------------------------------------------------------------------

class TestFederationCoherence:

    def test_F7_r_coarse_equals_1_for_identical_cores(self):
        """[F7] r_coarse = 1 when both cores have identical state."""
        harness = scenario_strong_overlap()
        run(harness, n=_N_STEPS)
        snaps = harness.snapshots()
        # Strong overlap → phases identical → r_coarse near 1
        final = snaps[-1]
        assert final.r_coarse > 0.99, f"Expected r_coarse ≈ 1, got {final.r_coarse}"

    def test_F7_r_coarse_less_than_1_for_partial(self):
        """[F7] r_coarse < 1 when cores have different exclusive components."""
        harness = scenario_partial_overlap()
        run(harness, n=_N_STEPS)
        snaps = harness.snapshots()
        final = snaps[-1]
        # Partial overlap: phases not fully aligned → r_coarse < 1
        assert final.r_coarse < 0.999, (
            f"r_coarse should be < 1 for partial overlap, got {final.r_coarse}"
        )

    def test_F7_r_coarse_ordering(self):
        """[F7] r_coarse(strong) ≥ r_coarse(partial) ≥ r_coarse(no_overlap)."""
        harness_none    = scenario_no_overlap()
        harness_partial = scenario_partial_overlap()
        harness_strong  = scenario_strong_overlap()

        snaps_none    = run(harness_none,    n=_N_STEPS)
        snaps_partial = run(harness_partial, n=_N_STEPS)
        snaps_strong  = run(harness_strong,  n=_N_STEPS)

        r_none    = snaps_none[-1].r_coarse
        r_partial = snaps_partial[-1].r_coarse
        r_strong  = snaps_strong[-1].r_coarse

        assert r_strong >= r_partial - 0.01, (
            f"r_coarse ordering violated: strong={r_strong:.4f} < partial={r_partial:.4f}"
        )
        assert r_partial >= r_none - 0.01, (
            f"r_coarse ordering violated: partial={r_partial:.4f} < none={r_none:.4f}"
        )
