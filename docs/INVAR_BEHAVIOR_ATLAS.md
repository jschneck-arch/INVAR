# INVAR Behavior Atlas

**Project:** INVAR — Invariant Architecture Runtime  
**Version:** 1.0  
**Source:** Observed from `tests/test_core_stress.py` (41 tests) and `demos/skg_core_demo.py`  
**Purpose:** Map the system's behavioral regimes so that future work can characterize, not guess, what the field is doing.

---

## What This Document Is

INVAR core passes all invariant and stress tests. Passing tests is not the same as understanding behavior. This atlas documents the **observable regimes** — what the system actually does under different initial conditions and observation patterns — so future federation and adapter work can reason about field state without re-running experiments.

Each regime has:
- **Conditions** — what inputs or configurations produce it
- **Observable signature** — what the measurable quantities show
- **Termination** — how it ends (if it does)
- **Invariants still holding** — confirms the regime is legal, not a bug

---

## Regime 1: Convergent Collapse

**The common case.** Strong confirming evidence arrives. Gates collapse. Hebbian coupling loses signal. Field energy decays toward zero.

### Conditions
- φ_R or φ_B ≥ 0.70 (COLLAPSE_THRESHOLD) for most gates
- Confirming evidence only (no contradictions after initial observation)

### Observable Signature
| Quantity | Trajectory |
|----------|-----------|
| `field_energy` | Monotone decreasing → 0 |
| `L_total` | Monotone decreasing (second law) |
| `r(Ψ)` | Increases then drops to 0 (collapsed gates: Ψ=0) |
| `T_eff` | Rises (r→0 → T_eff→T₀) as gates collapse |
| `β₁` | Stays 0 (Hebbian requires Ψ≠0 to build edges) |
| Coupling `A_ij` | Stays near 0.5 (no Hebbian signal) |

### Termination
Absorbing. Once all gates collapse, field_energy=0 and the system is inert. No new information changes this without new evidence injection.

### Invariants Holding
- L ≥ 0 throughout ✓
- |Ψᵢ| ≤ E_self throughout ✓
- C(Ψᵢ) = 0 when E_self = 0 ✓
- Demonstrated: `test_st9_field_energy_near_zero_after_full_collapse`

### Notes
The most common regime in red-team scenarios where evidence is strong and one-directional. **The system has nothing left to say after collapse.** This is correct physics — collapsed gates carry zero entropy.

---

## Regime 2: Sustained Uncertainty (Steady-State)

**The operative regime.** Evidence is mixed or weak. Gates remain in state U. Coupling evolves slowly. The system stays informative.

### Conditions
- φ_R, φ_B < 0.70 for most gates
- Mixed evidence (some R, some B, none dominant)
- Hebbian active but coupling near threshold

### Observable Signature
| Quantity | Trajectory |
|----------|-----------|
| `field_energy` | Stable, non-zero |
| `L_total` | Stable, > 0 |
| `r(Ψ)` | Bounded in (0, 1) |
| `T_eff` | Bounded in (0, T₀) |
| `β₁` | 0 (edges weak, below threshold) |
| Coupling `A_ij` | Slow drift, stays near 0.5 |

### Termination
Persistent until new evidence drives collapse or contradiction. With only Hebbian dynamics and no new evidence, L variance drops to < 1.0 after 500+ steps (convergence test confirmed).

### Invariants Holding
- All invariants hold indefinitely ✓
- Demonstrated: `test_st5_convergence_regime_detection` (variance < 1.0 at 600 steps)

### Notes
This is the **target operating regime** for an active observation cycle. Instruments should be dispatched to resolve high-entropy gates before they drift into regime 1 (convergent collapse) or regime 4 (fold storm).

---

## Regime 3: Phase-Canceling Incoherence

**Contradictory uncertainty.** Multiple gates within a manifestation pull in opposite directions. High field energy, low |Ψ|, high C(Ψ).

### Conditions
- Multiple gates in one manifestation with opposing phases (some strongly R, some strongly B) — all below collapse threshold
- Alternating evidence pattern

### Observable Signature
| Quantity | Value |
|----------|-------|
| `field_energy` | High (gates still in U) |
| `|Ψᵢ|` | Low (R and B phases cancel in vector sum) |
| `C(Ψᵢ)` | High (approaching 1) |
| `E_self` | High (= Σ H(g), all gates uncertain) |
| `T_eff` | Near T₀ (low r → high temperature) |
| `β₁` | 0 (Hebbian produces small signal, coupling weak) |

### Termination
Exits when:
1. New evidence collapses enough gates to reduce E_self (→ Regime 1)
2. Fold event triggers re-ordering (→ Regime 4)
3. Observation functional J targets high-H gates for resolution

### Invariants Holding
- C(Ψᵢ) ∈ [0,1] ✓
- C_contra > C_aligned for sub-threshold gates ✓
- Demonstrated: `test_C3_coherence_increases_with_contradiction`

### Notes
**The observation functional J is most valuable in this regime.** High C(Ω) raises J(Ω), making incoherent slices expensive to observe. The greedy minimizer will prefer resolving the contradicting gates.

---

## Regime 4: Fold Storm

**Persistent contradiction.** Evidence repeatedly contradicts the gate's prior direction. H increases on each injection. The system is actively oscillating.

### Conditions
- Gate leans toward one pole (H near 0, φ < COLLAPSE_THRESHOLD)
- New evidence pushes toward opposite pole, raising H
- Crucially: neither pole's φ exceeds collapse threshold

### Observable Signature
| Quantity | Behavior |
|----------|---------|
| `delta_H` | Positive (fold pearls) on each new injection |
| `field_energy` | Oscillates — rises on contradiction, falls on confirmation |
| `L_total` | Non-monotone (L can temporarily rise during fold) |
| `C(Ψᵢ)` | Elevated |

### Critical Mechanics
A fold requires:
1. Gate leans strongly toward one pole (p near 0 or 1, H near 0)
2. Gate is still in state U (φ < 0.70 — NOT collapsed)
3. New evidence pushes p back toward 0.5, raising H → ΔH > 0

**A collapsed gate (φ ≥ 0.70) absorbs contradicting evidence differently:** the new φ may re-open the gate toward U (decoherence), but ΔH starts from 0 (collapsed), so subsequent behavior depends on whether the combined φ pushes p back toward 0.5 or exceeds the opposite threshold.

### Termination
- Fold storm ends when one direction accumulates enough φ to collapse
- Or when observer intentionally stops injecting contradicting evidence

### Invariants Holding
- L ≥ 0 throughout (even during fold) ✓
- field_energy ≥ 0 through 50 rapid contradictions ✓
- Demonstrated: `test_st8_*`

### Notes
Fold storms are signals, not failures. A gate in persistent fold indicates a contested condition — the environment is genuinely ambiguous about this transition. **Narrative should increase W(g) on fold gates** to prioritize their resolution.

---

## Regime 5: Topology Emergence

**Coupling resolves into a graph.** When manifestations remain uncertain and coupling evolves, Hebbian dynamics can push A_ij across the edge threshold. β₁ becomes positive.

### Conditions
- Multiple manifestations simultaneously in state U (H > 0)
- Sustained Hebbian coupling (steps 4–8 in demo scenario)
- At least 3 coupled manifestations forming a potential cycle

### Observable Signature
| Quantity | Behavior |
|----------|---------|
| `β₁` | Transitions from 0 to ≥ 1 |
| `A_ij` | Crosses ±0.05 from 0.5 (edge threshold) |
| `E_topo` | Non-zero (holonomy cost appears) |
| `L_total` | L_topo term begins contributing |

### Current Limitation (v1)
The edge threshold |A-0.5| > 0.05 is discrete. In the 4-manifestation demo, collapsed hosts produce Ψ=0, so Hebbian = Re[Ψᵢ*Ψⱼ]/(|Ψᵢ||Ψⱼ|+ε) ≈ 0. Coupling never crosses threshold. **β₁ > 0 requires concurrent uncertainty in linked manifestations.**

### Producing This Regime
```python
# Correct: both manifestations uncertain, weak partial evidence
ingest(engine, 'w', 'node-0', 'g0', 0.35, 0.20)
ingest(engine, 'w', 'node-1', 'g0', 0.30, 0.25)
# Both stay in U → Hebbian is non-zero → coupling evolves
for _ in range(200):
    hebbian_step(field, gravity, manifestations)
# Now check β₁
```

### Invariants Holding
- β₁ = |E| - |V| + k ✓
- β₁ ≥ 0 always ✓
- Demonstrated: `test_st5_beta1_non_negative`, `test_st4_*`

---

## Regime 6: Collapse Cascade

**Sequential total collapse.** All gates across all manifestations collapse in rapid succession. Field energy drops to zero. The system goes dark.

### Conditions
- Strong confirming evidence (φ ≥ 0.70) applied to all gates
- No contradicting evidence

### Observable Signature
| Quantity | Value after cascade |
|----------|-------------------|
| `field_energy` | ≈ 0 |
| `|Ψᵢ|` | ≈ 0 for all i |
| `C(Ψᵢ)` | 0 (no energy) |
| `T_eff` | T₀ (r=0, high temperature, paradoxically) |
| `β₁` | 0 |
| `L_total` | ≈ 0 |

### Termination
Absorbing. Requires new evidence injection to re-activate.

### Invariants Holding
- field_energy < 0.1 after cascade ✓
- C = 0 when E_self = 0 ✓
- Demonstrated: `test_st9_*`

### Notes
Cascade is not pathological — it means the system successfully resolved all uncertainty. But it means **instruments have nothing left to observe**. A well-functioning INVAR system should have a mix of collapsed (known) and uncertain (active) gates at all times during an engagement.

---

## Regime 7: Stable Multi-Cluster (Federation)

**Independent cores remain independent.** Two INVAR instances with non-overlapping evidence streams maintain distinct Ψ̃ and A values after coarse-graining.

### Conditions
- Two cores with different evidence patterns
- No shared observation events
- Independent narrative weights

### Observable Signature
| Quantity | Behavior |
|----------|---------|
| `Ã_KL` | Near 0.5 (maximum uncertainty between clusters) |
| `Ψ̃_K` vs `Ψ̃_L` | Different amplitudes and phases |
| `r_coarse` | Depends on whether cores happen to align |
| Narrative | W(g) in core 1 ≠ W(g) in core 2 |

### Alignment Conditions
Cores will align when:
- They observe the same transitions
- External synchronization via shared evidence stream
- Coarse-grained coupling A_KL evolves via Hebbian at the federation layer

Cores will decouple when:
- Evidence streams diverge
- Narrative weights set conflicting intent
- Topology barriers (β₁ = 0 between clusters)

### Invariants Holding
- |Ψ̃_K| ≤ E_K at coarse level ✓
- Ã_KL = Ã_LK (symmetry) ✓
- Ã_KL ∈ [0,1] ✓
- Demonstrated: `test_st6_two_cores_coarse_grained`, `test_st6_independent_narratives_dont_cross`

---

## Regime 8: Narrative-Biased Exploration

**The observer shapes the field.** High narrative weights W(g) bias the greedy J minimization toward specific gates. The observation slice Ω* differs from the entropy-optimal slice.

### Conditions
- Non-zero intent I(g) or outcome weights R(g)
- λN > 0 in JWeights (default: 0.8)
- λU > λC (required invariant: default 1.0 > 0.5)

### Observable Signature
- Greedy J selects gates with high W(g)·H(g) even if not globally highest H
- J(Ω*) < J(∅) always (greedy doesn't make things worse)
- Gate selection changes under different narrative state, same evidence

### Stability
The weight ordering λU > λC is enforced structurally (`JWeights.__post_init__` raises `ValueError` if violated). This ensures:
- Unresolved uncertainty always dominates coherence penalty
- J minimization cannot become a pure coherence-seeking behavior
- Observation behavior remains stable across sessions

### Invariants Holding
- J(greedy) ≤ J(∅) ✓
- λU > λC enforced at construction ✓
- Demonstrated: `test_st7_J_weight_ordering_enforced`, `test_st7_greedy_J_not_worse_than_empty`

---

## Regime Transition Map

```
                        ┌─────────────────────────────────────────┐
                        │         New Evidence Injection           │
                        └─────────────────────────────────────────┘
                                            │
                        ┌───────────────────┴──────────────────────┐
                        │                                          │
                        ▼                                          ▼
              Strong confirming                          Mixed / contradictory
              (φ ≥ 0.70)                                 (φ < 0.70, balanced)
                        │                                          │
                        ▼                                          ▼
           [R1] Convergent Collapse                   [R2] Sustained Uncertainty
              L → 0, gates dark                         L stable, H active
                        │                                          │
                        │                          ┌───────────────┴──────────┐
                        │                          │                          │
                        │                          ▼                          ▼
                        │            Opposing phases in         Same phase direction
                        │            same manifestation         across manifestation
                        │                          │                          │
                        │                          ▼                          ▼
                        │              [R3] Phase-Canceling         Hebbian builds
                        │                 Incoherence              over many steps
                        │                 C(Ψ) high                          │
                        │                          │                          ▼
                        │                          │             [R5] Topology Emergence
                        │                   new contra-           β₁ > 0 when
                        │                   diction arrives       all mflds uncertain
                        │                          │
                        │                          ▼
                        │              [R4] Fold Storm
                        │              ΔH > 0 pearls
                        │              H oscillates
                        │                          │
                        │              accumulates  │
                        │              enough φ     │
                        └──────────────────────────►
                                                    │
                                                    ▼
                                         [R6] Collapse Cascade
                                         System goes dark

Federation (multiple cores):
    Each core independently in any regime above
    Coarse-graining produces [R7] Stable Multi-Cluster
    when cores have different evidence streams

Observation biased by narrative → [R8] Narrative-Biased Exploration
    (orthogonal to all regimes — modifies which gates get observed)
```

---

## Measurement Protocol

To characterize which regime a live system is in, measure in this order:

1. **`field_energy`** — If < 0.01: likely R1 or R6 (collapsed/dark)
2. **`r(Ψ)`** — If < 0.1 and field_energy > 0: likely R3 (incoherent)
3. **fold rate** (pearls with ΔH > 0 / total pearls) — If > 0.2: R4 (fold storm)
4. **`β₁`** — If > 0: R5 (topology active)
5. **coupling variance** — If A_ij spread > 0.1: topology evolving
6. **L variance over last 100 steps** — If < 1.0: converged (stable R2 or absorbed R1)

---

## What This Atlas Is Not

- Not a simulation. All observations are from actual test runs.
- Not exhaustive. Real deployments will have regime mixtures.
- Not static. The atlas should be updated as new behaviors are characterized.

When a new test reveals an unexpected behavior, add it here before explaining it away.
