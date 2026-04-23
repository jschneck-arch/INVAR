"""
federation.scenarios
====================
Three canonical federation scenarios: no overlap, partial overlap, strong overlap.

Each scenario returns a fully configured FederationHarness ready to run.

Scenario definitions:
    NO_OVERLAP    — Core1 and Core2 observe completely different manifestations.
                    No shared evidence. A_KL should stay near 0.5 (isolation).

    PARTIAL_OVERLAP — Core1 and Core2 share 2 manifestations with identical evidence,
                      plus exclusive manifestations with different evidence.
                      A_KL may drift as shared Ψ̃ components partially align.

    STRONG_OVERLAP  — Core1 and Core2 observe identical manifestations with
                      identical evidence. Ψ̃_K ≈ Ψ̃_L → Hebbian > 0 → alignment.
"""
from __future__ import annotations

from .core import FederationCore, FederationHarness
from invar.core.envelope import DecayClass

SEED_NO_OVERLAP      = 1001
SEED_PARTIAL_OVERLAP = 1002
SEED_STRONG_OVERLAP  = 1003


def _mk(workload: str, host: str) -> tuple:
    return (workload, host)


# ---------------------------------------------------------------------------
# Scenario: NO_OVERLAP
# ---------------------------------------------------------------------------

def scenario_no_overlap() -> FederationHarness:
    """
    Core 1: exclusively observes 4 hosts with R-leaning evidence.
    Core 2: exclusively observes 4 different hosts with B-leaning evidence.

    No shared manifestations. Ψ̃_K and Ψ̃_L have different phases.
    Re[Ψ̃_K* Ψ̃_L] averages near 0 → decay dominates → Ã_KL ≈ 0.5.
    Expected regime: ISOLATION.
    """
    c1_mflds = [_mk('c1', f'host-{i}') for i in range(4)]
    c2_mflds = [_mk('c2', f'host-{i}') for i in range(4)]

    core1 = FederationCore('core1', c1_mflds)
    core2 = FederationCore('core2', c2_mflds)

    # Core 1: R-leaning evidence (phase near 0)
    for wid, nk in c1_mflds:
        core1.inject(wid, nk, 'g_reach', phi_R=0.45, phi_B=0.10)
        core1.inject(wid, nk, 'g_patch', phi_R=0.40, phi_B=0.05)

    # Core 2: B-leaning evidence (phase near π)
    for wid, nk in c2_mflds:
        core2.inject(wid, nk, 'g_reach', phi_R=0.05, phi_B=0.45)
        core2.inject(wid, nk, 'g_patch', phi_R=0.10, phi_B=0.40)

    return FederationHarness({'core1': core1, 'core2': core2})


# ---------------------------------------------------------------------------
# Scenario: PARTIAL_OVERLAP
# ---------------------------------------------------------------------------

def scenario_partial_overlap() -> FederationHarness:
    """
    Core 1 and Core 2 share 2 manifestations with identical evidence,
    plus 3 exclusive manifestations each with distinct evidence patterns.

    Shared Ψ̃ components have the same phase → Re[...] > 0 for that portion.
    Exclusive components are misaligned → partial cancellation.
    Expected regime: DRIFT_BOUNDARY or partial ALIGNMENT.
    """
    shared_mflds = [_mk('shared', f'host-{i}') for i in range(2)]
    c1_exclusive = [_mk('c1', f'host-{i}') for i in range(3)]
    c2_exclusive = [_mk('c2', f'host-{i}') for i in range(3)]

    c1_mflds = shared_mflds + c1_exclusive
    c2_mflds = shared_mflds + c2_exclusive

    core1 = FederationCore('core1', c1_mflds)
    core2 = FederationCore('core2', c2_mflds)

    # Shared manifestations: same evidence injected into both cores
    for wid, nk in shared_mflds:
        core1.inject(wid, nk, 'g_reach', phi_R=0.40, phi_B=0.15)
        core1.inject(wid, nk, 'g_patch', phi_R=0.35, phi_B=0.10)
        core2.inject(wid, nk, 'g_reach', phi_R=0.40, phi_B=0.15)
        core2.inject(wid, nk, 'g_patch', phi_R=0.35, phi_B=0.10)

    # Core 1 exclusive: R-leaning
    for wid, nk in c1_exclusive:
        core1.inject(wid, nk, 'g_reach', phi_R=0.45, phi_B=0.10)
        core1.inject(wid, nk, 'g_patch', phi_R=0.38, phi_B=0.08)

    # Core 2 exclusive: B-leaning (opposing)
    for wid, nk in c2_exclusive:
        core2.inject(wid, nk, 'g_reach', phi_R=0.08, phi_B=0.45)
        core2.inject(wid, nk, 'g_patch', phi_R=0.05, phi_B=0.38)

    return FederationHarness({'core1': core1, 'core2': core2})


# ---------------------------------------------------------------------------
# Scenario: STRONG_OVERLAP
# ---------------------------------------------------------------------------

def scenario_strong_overlap() -> FederationHarness:
    """
    Core 1 and Core 2 observe identical manifestations with identical evidence.

    Ψ̃_K ≈ Ψ̃_L (same phases, same energies).
    Re[Ψ̃_K* Ψ̃_L] = |Ψ̃|² > 0 → federation Hebbian pushes Ã_KL above 0.5.
    Expected regime: ALIGNMENT.
    """
    mflds = [_mk('shared', f'host-{i}') for i in range(4)]

    core1 = FederationCore('core1', mflds)
    core2 = FederationCore('core2', mflds)

    # Identical evidence in both cores
    evidence = [
        ('g_reach', 0.42, 0.12),
        ('g_patch', 0.38, 0.08),
    ]
    for wid, nk in mflds:
        for gate_id, phi_R, phi_B in evidence:
            core1.inject(wid, nk, gate_id, phi_R=phi_R, phi_B=phi_B)
            core2.inject(wid, nk, gate_id, phi_R=phi_R, phi_B=phi_B)

    return FederationHarness({'core1': core1, 'core2': core2})


# ---------------------------------------------------------------------------
# All scenarios
# ---------------------------------------------------------------------------

ALL_SCENARIOS = [
    ("NO_OVERLAP",      scenario_no_overlap),
    ("PARTIAL_OVERLAP", scenario_partial_overlap),
    ("STRONG_OVERLAP",  scenario_strong_overlap),
]
