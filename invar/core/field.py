"""
skg.core.field
==============
CouplingField — the dynamic A matrix between manifestations.

A_ij is the coupling strength between manifestations i and j.
It evolves via Hebbian update (co-realization strengthens coupling)
and decoherence (coupling decays like any gate support):

    ∂ₜA_ij = η · Re[Ψᵢ*Ψⱼ] / (|Ψᵢ||Ψⱼ| + ε)  −  λ_K · A_ij

A_ij ∈ [0, 1] is interpreted as coupling realization probability:
    - A_ij = 0.5: maximum uncertainty (unknown if coupled)
    - A_ij → 1.0: coupled confirmed
    - A_ij → 0.0: decoupled confirmed

H(A_ij) = H_binary(A_ij) is the coupling entropy — same formula as gate entropy.
This is homogeneity: coupling is a gate.

Edge existence: A_ij is "nonzero" when |A_ij - 0.5| > edge_threshold.
Values near 0.5 indicate maximum coupling uncertainty (superposition).
Values near 0 or 1 indicate resolved coupling (coupled or not).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, Iterator, Optional, Tuple

from .gate import binary_entropy, gate_p

ManifestationKey = Tuple[str, str]  # (workload_id, node_key)

_EPSILON = 1e-10
_DEFAULT_INITIAL = 0.5          # start at maximum uncertainty
_EDGE_THRESHOLD = 0.05          # |A - 0.5| > threshold → edge exists
_DEFAULT_ETA = 0.1              # Hebbian learning rate
_DEFAULT_LAMBDA_K = 1e-3        # coupling decoherence rate (operational scale)


@dataclass
class CouplingEdge:
    """One directed coupling A_ij between manifestations i and j."""
    i: ManifestationKey
    j: ManifestationKey
    value: float = _DEFAULT_INITIAL    # A_ij ∈ [0, 1]
    last_update: float = field(default_factory=time.time)

    @property
    def entropy(self) -> float:
        """H(A_ij) = H_binary(A_ij) — coupling uncertainty."""
        return binary_entropy(max(_EPSILON, min(1.0 - _EPSILON, self.value)))

    @property
    def phase(self) -> float:
        """arg(A_ij) ∈ (-π, π] — used for holonomy computation."""
        # Map A_ij from [0,1] to [-π, π]: A=0.5 → 0, A=1 → π, A=0 → -π
        return math.pi * (2.0 * self.value - 1.0)

    @property
    def is_edge(self) -> bool:
        """True if coupling is resolved enough to count as a graph edge."""
        return abs(self.value - 0.5) > _EDGE_THRESHOLD


class CouplingField:
    """
    The full A matrix: all pairwise coupling strengths between manifestations.

    Implements:
        ∂ₜA_ij = η · Re[Ψᵢ*Ψⱼ] / (|Ψᵢ||Ψⱼ| + ε)  −  λ_K · A_ij

    The field is symmetric by default (A_ij = A_ji). Directed coupling
    can be enabled by disabling symmetry enforcement.
    """

    def __init__(
        self,
        eta: float = _DEFAULT_ETA,
        lambda_K: float = _DEFAULT_LAMBDA_K,
        symmetric: bool = True,
    ) -> None:
        self._eta = eta
        self._lambda_K = lambda_K
        self._symmetric = symmetric
        self._edges: Dict[Tuple[ManifestationKey, ManifestationKey], CouplingEdge] = {}

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, i: ManifestationKey, j: ManifestationKey) -> float:
        """A_ij — coupling strength, default 0.5 (maximum uncertainty)."""
        key = self._key(i, j)
        edge = self._edges.get(key)
        return edge.value if edge is not None else _DEFAULT_INITIAL

    def edge(self, i: ManifestationKey, j: ManifestationKey) -> Optional[CouplingEdge]:
        return self._edges.get(self._key(i, j))

    def entropy(self, i: ManifestationKey, j: ManifestationKey) -> float:
        """H(A_ij) = H_binary(A_ij) — coupling entropy."""
        return binary_entropy(max(_EPSILON, min(1.0 - _EPSILON, self.get(i, j))))

    def phase(self, i: ManifestationKey, j: ManifestationKey) -> float:
        """arg(A_ij) — phase of the coupling, for holonomy computation."""
        e = self.edge(i, j)
        return e.phase if e is not None else 0.0

    def edges(self) -> Iterator[CouplingEdge]:
        """All stored edges (including those near 0.5 = uncertain coupling)."""
        yield from self._edges.values()

    def graph_edges(self) -> Iterator[CouplingEdge]:
        """Only edges where coupling is resolved enough to form a graph edge."""
        for e in self._edges.values():
            if e.is_edge:
                yield e

    def manifestations(self) -> set[ManifestationKey]:
        """All manifestations that appear in the coupling field."""
        nodes: set[ManifestationKey] = set()
        for e in self._edges.values():
            nodes.add(e.i)
            nodes.add(e.j)
        return nodes

    # ------------------------------------------------------------------
    # Update: Hebbian step
    # ------------------------------------------------------------------

    def step(
        self,
        i: ManifestationKey,
        j: ManifestationKey,
        psi_i: complex,
        psi_j: complex,
        dt: float = 1.0,
    ) -> float:
        """
        Apply one Hebbian update step:

            ∂ₜA_ij = η · Re[Ψᵢ*Ψⱼ] / (|Ψᵢ||Ψⱼ| + ε)  −  λ_K · A_ij

        Returns the new A_ij value.
        """
        key = self._key(i, j)
        edge = self._edges.get(key)
        a_current = edge.value if edge is not None else _DEFAULT_INITIAL

        amp_i = abs(psi_i)
        amp_j = abs(psi_j)
        denom = amp_i * amp_j + _EPSILON

        # Hebbian term: cos(∠Ψᵢ - ∠Ψⱼ) weighted by amplitudes
        hebbian = (psi_i.conjugate() * psi_j).real / denom

        # Decoherence term
        da = self._eta * hebbian - self._lambda_K * a_current

        a_new = float(max(0.0, min(1.0, a_current + da * dt)))

        self._set(i, j, a_new)
        return a_new

    def decay(self, dt: float = 1.0) -> None:
        """Apply decoherence to all edges (−λ_K·A_ij term, no Hebbian)."""
        for edge in list(self._edges.values()):
            new_val = float(max(0.0, min(1.0, edge.value - self._lambda_K * edge.value * dt)))
            edge.value = new_val
            edge.last_update = time.time()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _key(
        self, i: ManifestationKey, j: ManifestationKey
    ) -> Tuple[ManifestationKey, ManifestationKey]:
        """Canonical key: symmetric field uses lexicographic order."""
        if self._symmetric:
            return (min(i, j), max(i, j))
        return (i, j)

    def _set(self, i: ManifestationKey, j: ManifestationKey, value: float) -> None:
        key = self._key(i, j)
        if key not in self._edges:
            self._edges[key] = CouplingEdge(i=i, j=j, value=value)
        else:
            self._edges[key].value = value
            self._edges[key].last_update = time.time()
