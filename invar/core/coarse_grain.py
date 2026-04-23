"""
skg.core.coarse_grain
=====================
Coarse-graining operator: aggregates manifestations into higher-scale units.

Given a cluster C_K = {Ωᵢ}_{i∈I_K}, the coarse-grained state is:

    Ψ̃_K = Σ_{i∈I_K} ωᵢ · Ψᵢ

    ωᵢ = E_self(Ωᵢ) / (Σⱼ E_self(Ωⱼ) + ε)     [self-energy weighted]

The coarse-grained coupling between two clusters K and L:

    Ã_KL = Σ_{i∈I_K, j∈I_L} ωᵢωⱼ · A_ij  /  (Σ_{i,j} ωᵢωⱼ + ε)

The coarse-grained functional uses the same form:

    L̃(Ψ̃_K, Ã_K) = E_self(Ψ̃_K) + E_couple(Ψ̃_K, Ã) + E_topo(Ã_K)

This is scale invariance: the same law applies after coarse-graining.
The coarse-grained system IS an SKG system at a higher scale.

Use case (Phase 4 — federation):
    Each SKG deployment is a manifestation at the federation level.
    The same equations govern federation-level dynamics.
    SKG cores cluster into meta-SKG with Ψ̃_K and Ã_KL.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .field import CouplingField, ManifestationKey
from .gravity import GravityField
from .support_engine import SupportEngine

_EPSILON = 1e-10

ClusterKey = str   # opaque cluster label


@dataclass
class CoarseManifold:
    """
    The coarse-grained state of a cluster K.

    Ψ̃_K:   complex state (weighted sum of member Ψᵢ)
    E_K:    self-energy = Σ E_self(Ωᵢ) (total gate entropy in cluster)
    ω:      weight vector {mkey → ωᵢ}
    members: list of manifestation keys in this cluster
    """
    key: ClusterKey
    Psi: complex
    E: float           # self-energy
    omega: Dict[ManifestationKey, float]
    members: List[ManifestationKey]

    @property
    def coherence(self) -> float:
        """C(Ψ̃_K) = 1 - |Ψ̃_K| / E_K"""
        if self.E < _EPSILON:
            return 0.0
        return 1.0 - abs(self.Psi) / self.E

    @property
    def phase(self) -> float:
        """Mean phase of the coarse-grained state."""
        if abs(self.Psi) < _EPSILON:
            return math.pi / 2
        return math.atan2(self.Psi.imag, self.Psi.real)


class CoarseGraining:
    """
    Coarse-graining operator for clusters of manifestations.

    Usage:
        cg = CoarseGraining(engine, field, gravity)
        cg.define_cluster("cluster-A", [("cve-1", "host-1"), ("cve-1", "host-2")])
        manifold = cg.manifold("cluster-A")
        A_KL = cg.coupling("cluster-A", "cluster-B")
        Psi_K = manifold.Psi
    """

    def __init__(
        self,
        engine: SupportEngine,
        field: CouplingField,
        gravity: GravityField,
    ) -> None:
        self._engine = engine
        self._field = field
        self._gravity = gravity
        self._clusters: Dict[ClusterKey, List[ManifestationKey]] = {}

    def define_cluster(
        self,
        key: ClusterKey,
        members: List[ManifestationKey],
    ) -> None:
        """Register a cluster of manifestations as a coarse-grained unit."""
        self._clusters[key] = list(members)

    def manifold(
        self, key: ClusterKey, t: Optional[float] = None
    ) -> CoarseManifold:
        """
        Compute Ψ̃_K = Σᵢ ωᵢ · Ψᵢ for cluster K.

        ωᵢ = E_self(Ωᵢ) / Σⱼ E_self(Ωⱼ)    [energy-weighted average]
        """
        members = self._clusters.get(key, [])
        if not members:
            return CoarseManifold(
                key=key, Psi=complex(0.0), E=0.0,
                omega={}, members=[],
            )

        # Compute self-energies and weights
        energies = {
            m: self._engine.manifestation_energy(m[0], m[1], t)
            for m in members
        }
        E_total = sum(energies.values())
        denom = E_total + _EPSILON

        omega = {m: e / denom for m, e in energies.items()}

        # Coarse-grained state: Ψ̃_K = Σ ωᵢ · Ψᵢ
        Psi = complex(0.0)
        for m, w in omega.items():
            psi_i = self._gravity.fiber_tensor(m[0], m[1], t)
            Psi += w * psi_i

        return CoarseManifold(
            key=key,
            Psi=Psi,
            E=E_total,
            omega=omega,
            members=list(members),
        )

    def coupling(
        self,
        K: ClusterKey,
        L: ClusterKey,
        t: Optional[float] = None,
    ) -> float:
        """
        Ã_KL = Σ_{i∈K, j∈L} ωᵢωⱼ · A_ij  /  (Σ ωᵢωⱼ + ε)

        Energy-weighted average coupling between clusters K and L.
        """
        manifold_K = self.manifold(K, t)
        manifold_L = self.manifold(L, t)

        members_K = manifold_K.members
        members_L = manifold_L.members

        if not members_K or not members_L:
            return 0.5   # maximum uncertainty (no information)

        numerator = 0.0
        denominator = 0.0

        for i in members_K:
            wi = manifold_K.omega.get(i, 0.0)
            for j in members_L:
                wj = manifold_L.omega.get(j, 0.0)
                A_ij = self._field.get(i, j)
                weight = wi * wj
                numerator += weight * A_ij
                denominator += weight

        if denominator < _EPSILON:
            return 0.5
        return numerator / (denominator + _EPSILON)

    def coarse_field(self, t: Optional[float] = None) -> "CoarseField":
        """
        Build the full coarse-grained state for all registered clusters.
        Returns a CoarseField containing all manifolds and inter-cluster couplings.
        """
        manifolds = {k: self.manifold(k, t) for k in self._clusters}
        keys = list(self._clusters.keys())
        couplings: Dict[Tuple[ClusterKey, ClusterKey], float] = {}
        for i, K in enumerate(keys):
            for L in keys[i+1:]:
                A_KL = self.coupling(K, L, t)
                couplings[(K, L)] = A_KL
                couplings[(L, K)] = A_KL   # symmetric

        return CoarseField(manifolds=manifolds, couplings=couplings)


@dataclass
class CoarseField:
    """The complete coarse-grained field state: all manifolds + all couplings."""
    manifolds: Dict[ClusterKey, CoarseManifold]
    couplings: Dict[Tuple[ClusterKey, ClusterKey], float]

    def global_coherence(self) -> float:
        """r(Ψ̃) = |Σ_K Ψ̃_K| / Σ_K|Ψ̃_K|"""
        psi_sum = complex(0.0)
        amp_sum = 0.0
        for m in self.manifolds.values():
            psi_sum += m.Psi
            amp_sum += abs(m.Psi)
        if amp_sum < _EPSILON:
            return 0.0
        return abs(psi_sum) / amp_sum

    def global_L(self) -> float:
        """
        L̃(Ψ̃, Ã) approximation at the coarse level.
        = Σ_K E_K·C_K  +  coupling terms  (simplified, no topology)
        """
        incoherence_sum = sum(m.E * m.coherence for m in self.manifolds.values())
        coupling_entropy_sum = sum(
            abs(A - 0.5) * (-A * math.log2(max(A, _EPSILON)) - (1-A) * math.log2(max(1-A, _EPSILON)))
            for A in self.couplings.values()
            if A > _EPSILON and A < 1.0 - _EPSILON
        )
        return incoherence_sum + coupling_entropy_sum
