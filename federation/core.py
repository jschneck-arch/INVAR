"""
federation.core
===============
FederationCore: one independent INVAR instance within a federation.
FederationHarness: orchestrates N cores, evolves federation-level coupling.

The same field equations that govern Ψᵢ within a core also govern Ψ̃_K
between cores. This is the scale-invariance claim — federation is not a
different law, it is the same law one level up.

Architecture:
    Each FederationCore owns:
        - SupportEngine     (gate store, write path)
        - GravityField      (Ψᵢ, T_eff, dispatch)
        - CouplingField     (local Aᵢⱼ, Hebbian within core)

    FederationHarness owns:
        - One FederationCore per core_id
        - One CouplingField for federation-level Ã_KL
        - CoarseGraining per core (computes Ψ̃_K = Σ ωᵢΨᵢ)

    Federation Hebbian (same equation, coarse scale):
        ∂ₜÃ_KL = η_fed · Re[Ψ̃_K* Ψ̃_L] / (|Ψ̃_K||Ψ̃_L| + ε) - λ_fed · Ã_KL

    This is CouplingField.step() with Ψ̃_K as the psi arguments.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from invar.core.envelope import ObsGateEnvelope, DecayClass
from invar.core.support_engine import SupportEngine
from invar.core.gravity import GravityField
from invar.core.field import CouplingField
from invar.core.topology import CouplingGraph
from invar.core.functional import global_L
from invar.core.coarse_grain import CoarseGraining, CoarseManifold

ManifestationKey = Tuple[str, str]
CoreID = str

_EPSILON = 1e-10


# ---------------------------------------------------------------------------
# Regime classification
# ---------------------------------------------------------------------------

REGIME_ISOLATION       = "isolation"
REGIME_ALIGNMENT       = "alignment"
REGIME_STABLE_SPLIT    = "stable_split"
REGIME_DRIFT_BOUNDARY  = "drift_boundary"
REGIME_UNCERTAIN       = "uncertain"


def classify_regime(
    r1: float,
    r2: float,
    r_coarse: float,
    A_KL: float,
    A_KL_history: List[float],
) -> str:
    """
    Classify the federation regime from current measurements.

    Regime definitions:
        isolation       — Ã_KL near 0.5; cores don't influence each other
        alignment       — Ã_KL drifted from 0.5; cores phase-aligned
        stable_split    — Ã_KL < 0.45; cores anti-correlated (persistent opposition)
        drift_boundary  — Ã_KL variance high; neither stable nor converging
        uncertain       — not enough history or signal
    """
    # Isolation: coupling hasn't moved
    if abs(A_KL - 0.5) < 0.02:
        return REGIME_ISOLATION

    # Stable split: coupling driven below 0.5 (anti-alignment)
    if A_KL < 0.45:
        return REGIME_STABLE_SPLIT

    # Alignment: coupling above 0.5 and coarse coherence rising
    if A_KL > 0.55 and r_coarse > 0.1:
        return REGIME_ALIGNMENT

    # Drift boundary: variance in Ã_KL is non-trivial
    if len(A_KL_history) >= 20:
        var = statistics.variance(A_KL_history[-20:])
        if var > 5e-5:
            return REGIME_DRIFT_BOUNDARY

    return REGIME_UNCERTAIN


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

@dataclass
class FederationSnapshot:
    """Measurements at one time step of the federation."""
    step: int
    r1: float
    r2: float
    L1: float
    L2: float
    delta_L: float              # |L1 - L2|
    A_KL: float                 # coarse inter-core coupling
    H_A_KL: float               # H_binary(Ã_KL) — coupling entropy
    r_coarse: float             # |Ψ̃_K + Ψ̃_L| / (|Ψ̃_K| + |Ψ̃_L|)
    psi_K_amp: float            # |Ψ̃_K|
    psi_L_amp: float            # |Ψ̃_L|
    regime: str


# ---------------------------------------------------------------------------
# FederationCore
# ---------------------------------------------------------------------------

class FederationCore:
    """
    One independent INVAR instance in the federation.

    Owns a SupportEngine, GravityField, and CouplingField.
    Steps Hebbian coupling internally. Never communicates with other cores
    except through the FederationHarness coarse-graining.
    """

    def __init__(
        self,
        core_id: CoreID,
        manifestations: List[ManifestationKey],
        eta: float = 0.15,
        lambda_K: float = 5e-4,
    ) -> None:
        self.core_id = core_id
        self.manifestations = list(manifestations)
        self.engine = SupportEngine()
        self.gravity = GravityField(self.engine)
        self.field = CouplingField(eta=eta, lambda_K=lambda_K)

    def inject(
        self,
        workload_id: str,
        node_key: str,
        gate_id: str,
        phi_R: float,
        phi_B: float,
        decay_class: DecayClass = DecayClass.STRUCTURAL,
    ) -> None:
        """Inject evidence into this core's gate store."""
        env = ObsGateEnvelope(
            instrument_id=f'fed_{self.core_id}',
            workload_id=workload_id,
            node_key=node_key,
        )
        env.add(gate_id, phi_R=phi_R, phi_B=phi_B, decay_class=decay_class)
        self.engine.ingest(env)

    def step(self, dt: float = 1.0) -> None:
        """One round of Hebbian coupling within this core."""
        psis = {
            m: self.gravity.fiber_tensor(m[0], m[1])
            for m in self.manifestations
        }
        for i, mi in enumerate(self.manifestations):
            for mj in self.manifestations[i + 1:]:
                self.field.step(mi, mj, psis[mi], psis[mj], dt=dt)
        self.field.decay(dt=dt)

    def psi_coarse(self) -> complex:
        """
        Ψ̃_K = energy-weighted average of all Ψᵢ in this core.
        This is the coarse state fed into the federation Hebbian.
        """
        cg = CoarseGraining(self.engine, self.field, self.gravity)
        cg.define_cluster('K', self.manifestations)
        m = cg.manifold('K')
        return m.Psi

    def measure(self) -> Dict:
        """Return current field measurements."""
        graph = CouplingGraph.build(self.field)
        GL = global_L(self.engine, self.field, graph, self.gravity)
        r = self.gravity.global_coherence()
        E = self.engine.field_energy()
        return {
            'L': GL['total'],
            'r': r,
            'beta_1': graph.beta_1,
            'field_energy': E,
        }


# ---------------------------------------------------------------------------
# FederationHarness
# ---------------------------------------------------------------------------

class FederationHarness:
    """
    Orchestrates N FederationCore instances and a federation-level CouplingField.

    The federation-level CouplingField evolves Ã_KL using the same Hebbian
    equation as the intra-core field — but with Ψ̃_K as input instead of Ψᵢ.
    This is scale invariance in operation.
    """

    def __init__(
        self,
        cores: Dict[CoreID, FederationCore],
        eta_fed: float = 0.10,
        lambda_fed: float = 1e-3,
    ) -> None:
        self.cores = cores
        self.core_ids = list(cores.keys())
        # Federation-level CouplingField: keys are (core_id, 'fed') pseudo-manifestations
        self._fed_field = CouplingField(eta=eta_fed, lambda_K=lambda_fed)
        self._pseudo_key: Dict[CoreID, ManifestationKey] = {
            cid: (cid, 'fed') for cid in self.core_ids
        }
        self._A_KL_history: List[float] = []
        self._snapshots: List[FederationSnapshot] = []

    def step(self, dt: float = 1.0) -> None:
        """
        One federation step:
        1. Each core runs its internal Hebbian.
        2. Coarse Ψ̃_K computed for each core.
        3. Federation CouplingField updated with coarse Ψ̃_K values.
        """
        # Step each core internally
        for core in self.cores.values():
            core.step(dt=dt)

        # Compute coarse psi for each core
        psi_coarse: Dict[CoreID, complex] = {
            cid: core.psi_coarse()
            for cid, core in self.cores.items()
        }

        # Federation Hebbian over all core pairs
        ids = self.core_ids
        for i, ki in enumerate(ids):
            for kj in ids[i + 1:]:
                pk_i = self._pseudo_key[ki]
                pk_j = self._pseudo_key[kj]
                self._fed_field.step(
                    pk_i, pk_j,
                    psi_coarse[ki], psi_coarse[kj],
                    dt=dt,
                )
        self._fed_field.decay(dt=dt)

    def A_KL(self, K: CoreID, L: CoreID) -> float:
        """Current Ã_KL between two cores."""
        pk_K = self._pseudo_key[K]
        pk_L = self._pseudo_key[L]
        return self._fed_field.get(pk_K, pk_L)

    def r_coarse(self) -> float:
        """r(Ψ̃) = |Σ_K Ψ̃_K| / Σ_K |Ψ̃_K| — federation-level coherence."""
        psis = [core.psi_coarse() for core in self.cores.values()]
        amp_sum = sum(abs(p) for p in psis) + _EPSILON
        return abs(sum(psis)) / amp_sum

    def snapshot(self, step: int) -> FederationSnapshot:
        """Take a full measurement snapshot at the current step."""
        assert len(self.core_ids) == 2, "Snapshot assumes 2-core federation"
        id1, id2 = self.core_ids[0], self.core_ids[1]
        m1 = self.cores[id1].measure()
        m2 = self.cores[id2].measure()
        A = self.A_KL(id1, id2)
        self._A_KL_history.append(A)

        from invar.core.gate import binary_entropy
        H_A = binary_entropy(A)

        psi_K = self.cores[id1].psi_coarse()
        psi_L = self.cores[id2].psi_coarse()

        r_c = self.r_coarse()
        regime = classify_regime(
            m1['r'], m2['r'], r_c, A, self._A_KL_history
        )

        snap = FederationSnapshot(
            step=step,
            r1=m1['r'],
            r2=m2['r'],
            L1=m1['L'],
            L2=m2['L'],
            delta_L=abs(m1['L'] - m2['L']),
            A_KL=A,
            H_A_KL=H_A,
            r_coarse=r_c,
            psi_K_amp=abs(psi_K),
            psi_L_amp=abs(psi_L),
            regime=regime,
        )
        self._snapshots.append(snap)
        return snap

    def snapshots(self) -> List[FederationSnapshot]:
        return list(self._snapshots)

    def final_regime(self) -> str:
        """Regime at the last snapshot."""
        if not self._snapshots:
            return REGIME_UNCERTAIN
        return self._snapshots[-1].regime
