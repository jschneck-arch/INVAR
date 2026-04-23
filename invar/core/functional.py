"""
skg.core.functional
===================
The full SKG field functional L(Ψ, A).

Implements all terms from Work 6 Definition 7-8:

    Local:
        L(Ψᵢ, Aᵢ) = E_self(Ωᵢ) + E_couple(Ωᵢ, A) + E_topo(Aᵢ)

        E_self(Ωᵢ)       = Σ_{g∈Ωᵢ} H(g)                    [gate entropy]
        E_couple(Ωᵢ, A)  = Σⱼ |Aᵢⱼ| · H(Aᵢⱼ)                [coupling entropy]
        E_topo(Aᵢ)       = Σ_{c∋i} wc·(1-cos Φ(c))           [curvature cost]

    Global:
        L(Ψ, A) = Σᵢ L(Ψᵢ, Aᵢ)  +  w₁·β₁(A)  +  C(Ψ)

        C(Ψ) = 1 - |ΣᵢΨᵢ| / (Σᵢ|Ψᵢ| + ε)                   [global incoherence]

    Local difference (for Boltzmann factor in evolution equation):
        ΔLᵢⱼ = L(Ψᵢ,Aᵢ) - L(Ψⱼ,Aⱼ)
             = [E_self(i) - E_self(j)]
             + [E_couple(i,A) - E_couple(j,A)]
             + [E_topo(i) - E_topo(j)]

Homogeneity: every term is entropy of something. No mixed units.

For E_couple: coupling entropy H(A_ij) is weighted by |A_ij - 0.5| as a
proxy for intersection mass |Ωᵢ ∩ Ωⱼ|_H. When coupling is fully uncertain
(A=0.5), intersection is unknown. When coupling is resolved (A→0 or →1),
intersection contributes its coupling entropy.
"""
from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

from .field import CouplingField, ManifestationKey
from .gate import binary_entropy
from .gravity import GravityField
from .support_engine import SupportEngine
from .topology import CouplingGraph

_EPSILON = 1e-10


# ---------------------------------------------------------------------------
# Local energy terms
# ---------------------------------------------------------------------------

def e_self(
    workload_id: str,
    node_key: str,
    engine: SupportEngine,
    t: Optional[float] = None,
) -> float:
    """
    E_self(Ωᵢ) = Σ_{g∈Ωᵢ} H(g)

    Total gate entropy in the manifestation. This is the upper bound on |Ψᵢ|.
    """
    return engine.manifestation_energy(workload_id, node_key, t)


def e_couple(
    workload_id: str,
    node_key: str,
    field: CouplingField,
    engine: SupportEngine,
    t: Optional[float] = None,
) -> float:
    """
    E_couple(Ωᵢ, A) = Σⱼ≠ᵢ |Aᵢⱼ| · H(Aᵢⱼ)

    Coupling entropy: the entropic cost of uncertain couplings from i to all j.

    |Aᵢⱼ| here is |Aᵢⱼ - 0.5| * 2 ∈ [0,1] — resolvednesss of coupling.
    When coupling is maximally uncertain (A=0.5), coupling contributes
    full entropy H=1 to the local energy. When resolved (A→0 or →1),
    it contributes H→0.
    """
    mkey_i = (workload_id, node_key)
    total = 0.0
    for edge in field.edges():
        other = None
        if edge.i == mkey_i:
            other = edge.j
        elif edge.j == mkey_i:
            other = edge.i
        if other is None:
            continue
        # Coupling entropy, weighted by resolution (distance from 0.5)
        resolution = abs(edge.value - 0.5) * 2.0   # [0, 1]
        total += resolution * edge.entropy
    return total


def e_topo(
    workload_id: str,
    node_key: str,
    graph: CouplingGraph,
    field: CouplingField,
    theta_fn,
) -> float:
    """
    E_topo(Aᵢ) = Σ_{c∋i} wc·(1-cos Φ(c))

    Local curvature contribution from cycles passing through manifestation i.
    """
    mkey = (workload_id, node_key)
    return graph.local_topo_energy(mkey, field, theta_fn)


def local_L(
    workload_id: str,
    node_key: str,
    engine: SupportEngine,
    field: CouplingField,
    graph: CouplingGraph,
    gravity: GravityField,
    t: Optional[float] = None,
) -> float:
    """
    L(Ψᵢ, Aᵢ) = E_self(Ωᵢ) + E_couple(Ωᵢ, A) + E_topo(Aᵢ)

    Full local functional. Each term is entropy of something (homogeneous).
    """
    if t is None:
        t = time.time()

    # theta_fn: mean phase of manifestation (for holonomy)
    def theta_fn(mkey):
        gates = engine.gates(mkey[0], mkey[1])
        if not gates:
            return math.pi / 2   # default: maximum superposition phase
        phases = [g.phase(t) for g in gates.values()]
        return sum(phases) / len(phases)

    es = e_self(workload_id, node_key, engine, t)
    ec = e_couple(workload_id, node_key, field, engine, t)
    et = e_topo(workload_id, node_key, graph, field, theta_fn)
    return es + ec + et


def delta_L(
    i: Tuple[str, str],
    j: Tuple[str, str],
    engine: SupportEngine,
    field: CouplingField,
    graph: CouplingGraph,
    gravity: GravityField,
    t: Optional[float] = None,
) -> float:
    """
    ΔLᵢⱼ = L(Ψᵢ, Aᵢ) - L(Ψⱼ, Aⱼ)

    Local functional difference — used in the Boltzmann factor of evolution:
        e^(-ΔLᵢⱼ / T_eff)

    Decomposed as:
        ΔL = [E_self(i)-E_self(j)] + [E_couple(i)-E_couple(j)] + [E_topo(i)-E_topo(j)]
    """
    if t is None:
        t = time.time()
    Li = local_L(i[0], i[1], engine, field, graph, gravity, t)
    Lj = local_L(j[0], j[1], engine, field, graph, gravity, t)
    return Li - Lj


# ---------------------------------------------------------------------------
# Global functional
# ---------------------------------------------------------------------------

def global_incoherence(gravity: GravityField, t: Optional[float] = None) -> float:
    """
    C(Ψ) = 1 - |ΣᵢΨᵢ| / (Σᵢ|Ψᵢ| + ε)

    Global field incoherence. 0 = coherent. 1 = incoherent.
    Same as 1 - r(Ψ) where r is the Kuramoto order parameter.
    """
    r = gravity.global_coherence(t)
    return 1.0 - r


def global_L(
    engine: SupportEngine,
    field: CouplingField,
    graph: CouplingGraph,
    gravity: GravityField,
    w1: float = 1.0,
    t: Optional[float] = None,
) -> Dict[str, float]:
    """
    L(Ψ, A) = Σᵢ L(Ψᵢ, Aᵢ)  +  w₁·β₁(A)  +  C(Ψ)

    Returns a breakdown dict with all components.
    """
    if t is None:
        t = time.time()

    local_sum = 0.0
    local_terms: Dict[Tuple[str, str], float] = {}

    for wid, nk in engine.manifestations():
        L_i = local_L(wid, nk, engine, field, graph, gravity, t)
        local_sum += L_i
        local_terms[(wid, nk)] = L_i

    topo = w1 * graph.beta_1
    incoherence = global_incoherence(gravity, t)
    total = local_sum + topo + incoherence

    return {
        "total": total,
        "local_sum": local_sum,
        "topo": topo,
        "beta_1": graph.beta_1,
        "incoherence": incoherence,
        "local_terms": local_terms,
    }


# ---------------------------------------------------------------------------
# Layer 0 Oscillation Addendum — Stage 4: E_osc, P_res, L*, global_L*
#
# Invariant: L* ≥ 0 always (P_res ≤ Σ|Ψᵢ| ≤ E_self_total ≤ L).
# Existing local_L / global_L are NOT modified. L* is an extension.
# Default parameters (a=1, ω=0, μ=0) leave L untouched since L* is
# a separate function — existing call-sites still invoke local_L/global_L.
# ---------------------------------------------------------------------------

_LAMBDA_A  = 0.01   # amplitude cost coefficient
_LAMBDA_W  = 0.01   # frequency cost coefficient
_LAMBDA_MU = 0.01   # contradiction-memory cost coefficient


def e_osc(gates) -> float:
    """
    E_osc = Σg (λ_a·ag² + λ_ω·ωg² + λ_μ·μg²)

    Penalizes unbounded or excessive oscillatory activity.
    Non-negative by construction (squares of real values).

    gates: iterable of Gate objects.
    """
    total = 0.0
    for g in gates:
        total += (_LAMBDA_A * g.a ** 2
                  + _LAMBDA_W * g.omega ** 2
                  + _LAMBDA_MU * g.mu ** 2)
    return total


def p_res(
    manifestations: List[Tuple[str, str]],
    gravity,
    t: Optional[float] = None,
) -> float:
    """
    P_res = Σᵢ |Ψᵢ| · Πᵢ

    Resonant persistence reward. Bounded coherent oscillation is a
    lawful low-energy regime — this is the anti-static correction.

    Πᵢ stub = 1.0 (to be replaced with a real phase-lock score when
    oscillatory regimes are fully activated).

    Bounded: P_res ≤ Σ|Ψᵢ| ≤ Σ E_self(Ωᵢ).
    """
    if t is None:
        t = time.time()
    total = 0.0
    for wid, nk in manifestations:
        psi = gravity.fiber_tensor(wid, nk, t)
        abs_psi = abs(psi)
        if abs_psi < 1e-12:
            continue
        pi_i = 1.0   # stub: will become phase-lock score
        total += abs_psi * pi_i
    return total


def local_L_star(
    workload_id: str,
    node_key: str,
    engine: "SupportEngine",
    field: "CouplingField",
    graph: "CouplingGraph",
    gravity: "GravityField",
    t: Optional[float] = None,
) -> float:
    """
    L*(Ψᵢ, Aᵢ) = L(Ψᵢ, Aᵢ) + E_osc(Ωᵢ) − P_res({i})

    Extended local functional. Bounded below by 0:
      L* ≥ L + 0 − E_self ≥ E_couple + E_topo ≥ 0.
    """
    if t is None:
        t = time.time()
    l_base = local_L(workload_id, node_key, engine, field, graph, gravity, t)
    gates = list(engine.gates(workload_id, node_key).values())
    osc_cost = e_osc(gates)
    persistence = p_res([(workload_id, node_key)], gravity, t)
    return l_base + osc_cost - persistence


def global_L_star(
    engine: "SupportEngine",
    field: "CouplingField",
    graph: "CouplingGraph",
    gravity: "GravityField",
    w1: float = 1.0,
    t: Optional[float] = None,
) -> Dict[str, float]:
    """
    L*(Ψ, A) = L(Ψ, A) + E_osc − P_res

    Extended global functional. Returns a breakdown dict that includes
    all keys from global_L plus 'e_osc', 'p_res', and 'total_star'.

    Bounded below: L*_total ≥ Σ E_couple + Σ E_topo + w1·β₁ + C(Ψ) ≥ 0.
    """
    if t is None:
        t = time.time()

    base = global_L(engine, field, graph, gravity, w1, t)

    all_gates: list = []
    all_manifestations: List[Tuple[str, str]] = []
    for wid, nk in engine.manifestations():
        all_manifestations.append((wid, nk))
        all_gates.extend(engine.gates(wid, nk).values())

    osc_cost = e_osc(all_gates)
    persistence = p_res(all_manifestations, gravity, t)
    total_star = base["total"] + osc_cost - persistence

    return {
        **base,
        "e_osc": osc_cost,
        "p_res": persistence,
        "total_star": total_star,
    }
