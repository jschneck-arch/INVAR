"""
skg.core.observation
====================
The observation functional J_t(Ω) and greedy minimization.

Observation is not arbitrary. It is derived by minimizing an
information-action functional over subsets Ω ⊆ T:

    J_t(Ω) = λU·U_t(Ω) + λC·C_t(Ω) + λO·O_t(Ω) − λN·N_t(Ω)

    Observation rule:  Ω*_t = argmin_{Ω⊆T} J_t(Ω)

Terms:

    U_t(Ω)  = Σ_{g∈T\Ω} H_t(g)            [unresolved uncertainty — what we miss]
    C_t(Ω)  = 1 - |Ψ(Ω)| / (E_self(Ω)+ε)  [slice incoherence — incoherent obs costly]
    O_t(Ω)  = α|Ω| + β·boundary(Ω)         [observation cost — prevents observe-all]
    N_t(Ω)  = Σ_{g∈Ω} W_t(g)·H_t(g)       [narrative utility — future value]

J_t prefers slices that:
    - reduce unresolved uncertainty (minimize U)
    - are internally coherent (minimize C)
    - are not too expensive to maintain (minimize O)
    - are useful for future action (maximize N, i.e. minimize -N)

Connection to gravity:
    The greedy minimization of J_t(Ω) over instrument coverage sets W(I)
    recovers the gravity Φ(I, L, t) = Σ H(g)/c(I) × penalty.
    Gravity is the instrument-constrained gradient descent of J_t.

The argmin over all Ω ⊆ T is NP-hard in general. The greedy_min_J()
function below produces a provably bounded approximation.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .gate import GateState
from .narrative import NarrativeState
from .support_engine import SupportEngine

_EPSILON = 1e-10


@dataclass
class ObservationSlice:
    """A candidate observation slice Ω ⊆ T with its J value."""
    gate_ids: Set[str]
    workload_id: str
    node_key: str
    J: float
    U: float        # unresolved uncertainty term
    C: float        # coherence penalty term
    O: float        # observation cost term
    N: float        # narrative utility term (positive = valuable)


@dataclass
class JWeights:
    """Weights for the observation functional J_t(Ω).

    Required ordering: lambda_U > lambda_C
    Rationale: unresolved uncertainty must dominate coherence penalty,
    otherwise J minimization collapses to coherence-seeking rather than
    uncertainty-reducing. Observation behavior becomes unstable if violated.
    """
    lambda_U: float = 1.0   # unresolved uncertainty — MUST be > lambda_C
    lambda_C: float = 0.5   # coherence penalty
    lambda_O: float = 0.1   # observation cost
    lambda_N: float = 0.8   # narrative utility
    alpha: float = 0.01     # per-gate cost coefficient
    beta: float = 0.1       # boundary complexity cost coefficient

    def __post_init__(self) -> None:
        if self.lambda_U <= self.lambda_C:
            raise ValueError(
                f"JWeights invariant violated: lambda_U ({self.lambda_U}) "
                f"must be > lambda_C ({self.lambda_C}). "
                "Observation becomes coherence-seeking rather than uncertainty-reducing."
            )


# ---------------------------------------------------------------------------
# J_t(Ω) computation
# ---------------------------------------------------------------------------

def U_term(
    Omega: Set[str],
    all_gate_ids: Set[str],
    engine: SupportEngine,
    workload_id: str,
    node_key: str,
    t: float,
) -> float:
    """
    U_t(Ω) = Σ_{g∈T\Ω} H_t(g)

    Unresolved uncertainty: total entropy of gates NOT in the observation slice.
    Minimizing U means observing the highest-entropy gates.
    """
    gates = engine.gates(workload_id, node_key)
    unobserved_ids = all_gate_ids - Omega
    total = 0.0
    for gid in unobserved_ids:
        g = gates.get(gid)
        if g is None:
            total += 1.0   # unobserved gate → H = 1.0 (max entropy)
        elif g.state(t) == GateState.U:
            total += g.energy(t)
    return total


def C_term(
    Omega: Set[str],
    engine: SupportEngine,
    workload_id: str,
    node_key: str,
    t: float,
) -> float:
    """
    C_t(Ω) = 1 - |Ψ(Ω)| / (E_self(Ω) + ε)

    Coherence penalty: if the slice is internally incoherent, it costs more.
    An incoherent slice contains contradictory transitions — observing it
    gives little net information.
    """
    import cmath
    gates = engine.gates(workload_id, node_key)
    psi = complex(0.0)
    e_self = 0.0
    for gid in Omega:
        g = gates.get(gid)
        if g is None:
            # Unobserved gate: H=1, θ=π/2 → contribution = 1.0·i
            psi += complex(0.0, 1.0)
            e_self += 1.0
        else:
            h = g.energy(t)
            psi += g.weighted_phase(t)
            e_self += h
    if e_self < _EPSILON:
        return 0.0
    return 1.0 - abs(psi) / (e_self + _EPSILON)


def O_term(
    Omega: Set[str],
    boundary_cost: float = 0.0,
    alpha: float = 0.01,
    beta: float = 0.1,
) -> float:
    """
    O_t(Ω) = α|Ω| + β·boundary(Ω)

    Observation cost. Prevents "observe everything."
    boundary_cost is the number of inter-slice coupling crossings (caller-supplied).
    """
    return alpha * len(Omega) + beta * boundary_cost


def N_term(
    Omega: Set[str],
    engine: SupportEngine,
    narrative: NarrativeState,
    workload_id: str,
    node_key: str,
    t: float,
) -> float:
    """
    N_t(Ω) = Σ_{g∈Ω} W_t(g) · H_t(g)

    Narrative utility: sum of (narrative weight × gate entropy) for gates
    in the slice. Observing high-W, high-H gates is most valuable.
    """
    gates = engine.gates(workload_id, node_key)
    total = 0.0
    for gid in Omega:
        g = gates.get(gid)
        h = 1.0 if g is None else g.energy(t)
        w = narrative.W(gid)
        total += w * h
    return total


def J(
    Omega: Set[str],
    all_gate_ids: Set[str],
    engine: SupportEngine,
    narrative: NarrativeState,
    workload_id: str,
    node_key: str,
    weights: JWeights = JWeights(),
    t: Optional[float] = None,
    boundary_cost: float = 0.0,
) -> ObservationSlice:
    """
    J_t(Ω) = λU·U_t(Ω) + λC·C_t(Ω) + λO·O_t(Ω) − λN·N_t(Ω)

    Returns an ObservationSlice with J value and all component terms.
    """
    if t is None:
        t = time.time()

    U = U_term(Omega, all_gate_ids, engine, workload_id, node_key, t)
    C = C_term(Omega, engine, workload_id, node_key, t)
    O = O_term(Omega, boundary_cost, weights.alpha, weights.beta)
    N = N_term(Omega, engine, narrative, workload_id, node_key, t)

    J_val = (
        weights.lambda_U * U
        + weights.lambda_C * C
        + weights.lambda_O * O
        - weights.lambda_N * N
    )

    return ObservationSlice(
        gate_ids=set(Omega),
        workload_id=workload_id,
        node_key=node_key,
        J=J_val,
        U=U,
        C=C,
        O=O,
        N=N,
    )


# ---------------------------------------------------------------------------
# Greedy minimization: Ω*_t = argmin_Ω J_t(Ω)
# ---------------------------------------------------------------------------

def greedy_min_J(
    engine: SupportEngine,
    narrative: NarrativeState,
    workload_id: str,
    node_key: str,
    weights: JWeights = JWeights(),
    max_gates: int = 20,
    t: Optional[float] = None,
) -> ObservationSlice:
    """
    Greedy approximation to Ω*_t = argmin_Ω J_t(Ω).

    Algorithm: start with Ω = ∅, greedily add the gate that most reduces J.
    Stop when adding any gate increases J or max_gates is reached.

    This is the greedy submodular approximation. For submodular J (which
    holds when all terms are submodular), this gives a (1-1/e) approximation.

    Connection to gravity: gravity Φ(I,L,t) is the per-instrument version
    of this greedy step — it ranks instruments by their J-reduction per cost.
    """
    if t is None:
        t = time.time()

    gates = engine.gates(workload_id, node_key)
    all_gate_ids = set(gates.keys())

    Omega: Set[str] = set()
    current = J(Omega, all_gate_ids, engine, narrative, workload_id, node_key, weights, t)

    for _ in range(max_gates):
        remaining = all_gate_ids - Omega
        if not remaining:
            break

        best_gain = 0.0
        best_gate = None

        for gid in remaining:
            candidate = Omega | {gid}
            candidate_J = J(
                candidate, all_gate_ids, engine, narrative,
                workload_id, node_key, weights, t
            )
            gain = current.J - candidate_J.J   # positive = improvement
            if gain > best_gain:
                best_gain = gain
                best_gate = gid
                best_slice = candidate_J

        if best_gate is None:
            break   # no improvement possible

        Omega.add(best_gate)
        current = best_slice

    return current
