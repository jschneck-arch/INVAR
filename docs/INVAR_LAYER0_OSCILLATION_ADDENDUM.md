# INVAR Layer 0 Oscillation Addendum

**Version:** 2.7  
**Status:** Canonical — defines the O-invariant family and staged activation protocol  
**Scope:** `invar/core/gate.py`, `invar/core/functional.py`, `invar/core/topology_trace.py`, `invar/core/topology_candidates.py`, `invar/core/topology_commitments.py`, `invar/core/proto_topology.py`, `invar/core/canonical_boundary.py`

---

## Purpose

Extends Layer 0 so the substrate can support bounded, persistent,
non-equilibrium structure without breaking existing collapse, entropy,
coupling, and topology rules.

**Does NOT:**
- turn Invar into literal quantum simulation
- replace the gate substrate
- move morphology into Layer 0
- make prediction a core function
- introduce narration anywhere below the adapter/domain layer

**Does:**
- add dynamical variables to unresolved structure
- allow persistence without mandatory collapse
- preserve measurement-first and operator-first architecture

---

## 1. Sphere as Boundary Condition (not a runtime object)

```
S := lim_{∇M→0} M
```

The sphere is the maximally symmetric, gradient-free reference condition
of the energy-information manifold. It is **not** represented in Layer 0
runtime state. All runtime states are symmetry-broken deviations from S.

---

## 2. Extended Gate State

Base gate state (unchanged):
```
g := (φ_R, φ_B)
```

Extended dynamical state added by the Oscillation Addendum:
```
g* := (φ_R, φ_B, θ_mem, a, ω, ξ, μ, γ, ρ, ε_p, κ, δ, ζ)
```

| Field | Default | Range | Meaning |
|-------|---------|-------|---------|
| `theta` | `0.0` | `ℝ` | Memory phase offset θᵐᵉᵐ (additive on top of support-derived anchor) |
| `a` | `1.0` | `≥ 0` | Oscillation amplitude (1.0 = no change to existing Ψ) |
| `omega` | `0.0` | `ℝ` | Intrinsic angular frequency |
| `xi` | `0.01` | `≥ 0` | Damping coefficient |
| `mu` | `0.0` | `ℝ` | Contradiction-memory term |
| `gamma` | `0.0` | `≥ 0` | Cross-gate contradiction coupling sensitivity; 0.0 = dormant |
| `rho` | `0.0` | `ℝ` | Resonance coupling coefficient; 0.0 = dormant |
| `epsilon_persist` | `0.0` | `≥ 0` | Persistence reward coefficient; 0.0 = dormant |
| `kappa_emergence` | `0.0` | `≥ 0` | Topology emergence sensitivity; 0.0 = dormant |
| `delta_feedback` | `0.0` | `≥ 0` | Feedback coupling coefficient — emergence → ρ modulation; 0.0 = dormant |
| `zeta_stabilize` | `0.0` | `≥ 0` | Stabilization coefficient — emergence → ω drift reduction; 0.0 = dormant |

**Key invariant:** With all defaults, existing behavior is unchanged.

---

## 3. Phase Law

Support-derived anchor (unchanged, computed from live φ_R/φ_B):
```
θg⁽⁰⁾(t) = (1 - p(g, t)) · π
```

Full dynamic phase (Stage 5 activation):
```
θg(t) = θg⁽⁰⁾(t) + θgᵐᵉᵐ(t)
```

Where `θgᵐᵉᵐ` is the `theta` field, evolved by `step()`:
```
dθgᵐᵉᵐ/dt = ωg + coupling_term + μg + ρg · Rg
```

`ρg · Rg` is the resonance term added in Stage 10 (dormant when `rho=0.0`).
`coupling_term` remains available as an explicit external override (default 0.0).

**Safety property:** With `omega=0, mu=0, rho=0, coupling_term=0`, `step()` is
a no-op and `theta` stays at `0.0` — so `θg(t) = θg⁽⁰⁾(t)` exactly.

---

## 4. Field Tensor with Amplitude (Stage 3) and Dynamic Phase (Stage 5)

Stage 3 introduced amplitude into the field tensor:
```
Ψᵢ(t) = Σ_{g∈Ωᵢ} H(g,t) · ag · e^(iθg⁽⁰⁾(t))
```

Stage 5 activates the memory phase offset:
```
Ψᵢ(t) = Σ_{g∈Ωᵢ} H(g,t) · ag · e^(i(θg⁽⁰⁾(t) + θgᵐᵉᵐ(t)))
```

With `a=1.0` (default) and `theta=0.0` (default): identical to original
`Ψᵢ = Σ H(g)·e^(iθg⁽⁰⁾)`.

---

## 5. Gate Dynamics (staged activation)

### Stage 2 (implemented): Phase memory step
```python
Gate.step(dt, coupling_term=0.0)
    theta += dt * (omega + coupling_term + mu)
```

### Stage 5 (implemented): theta feeds into weighted_phase()
```python
Gate.weighted_phase(t)
    θ_dynamic = phase(t) + theta          # anchor + memory offset
    return H(g) · a · e^(i·θ_dynamic)
```

### Stage 6 (implemented): bounded contradiction-memory evolution
```python
Gate.step(dt, coupling_term=0.0, c_in=0.0)
    # Phase evolution uses current mu (forward Euler)
    theta += dt * (omega + coupling_term + mu)
    # Contradiction-memory evolution: decay + optional explicit input
    mu += dt * (c_in - lambda_mu * mu)
```

**New field:** `lambda_mu` (default `0.1`) — contradiction-memory decay rate.
**New parameter:** `c_in` (default `0.0`) — explicit contradiction input per step.

**Safety properties:**
- With `c_in=0`: mu decays exponentially toward 0 for any initial value
- Steady state under constant input: `mu* = c_in / lambda_mu` (finite and bounded)
- mu never modifies phi_R, phi_B, energy(), p(), or collapse logic
- Default `c_in=0`, `mu=0` → step() is identical to Stage 5 behavior (no change)

**What Stage 6 activates only:**
- Local, deterministic, bounded contradiction-memory evolution
- mu influences phase only through the existing `dθᵐᵉᵐ/dt = ω + coupling_term + μ` path

**What Stage 6 does NOT activate:**
- Amplitude evolution
- Coupling resonance
- Cross-gate contradiction flow
- Persistence reward as runtime driver
- Stochastic behavior of any kind
- Pearl mutation or narration

### Stage 7 (implemented): bounded amplitude evolution
```python
Gate.step(dt, ...)   # only active when alpha != 0.0
    if alpha != 0.0:
        h = self.energy(t)
        a += dt * (alpha * h − xi * a)
        a = max(0.0, a)   # non-negative constraint
```

**New field:** `alpha` (default `0.0`) — amplitude drive coefficient. Dormant when 0.0.
**Steady state:** `a* = alpha · H(g) / xi` (finite for xi > 0; decays to 0 when gate collapses).

**Safety properties:**
- With `alpha=0.0` (default): step() never touches `a` — a=1.0 stays at 1.0 forever
- Setting alpha > 0 activates amplitude dynamics; a converges to `alpha·H/xi`
- a is clamped to ≥ 0 after each step (no negative amplitude)
- amplitude never modifies phi_R, phi_B, energy(), p(), or collapse logic
- H(g) input to amplitude is read-only — gate energy is not changed by step()

**What Stage 7 activates only:**
- Local, deterministic, bounded amplitude dynamics driven by instantaneous gate entropy
- a feeds into weighted_phase() via existing `H(g)·a·e^(iθ)` path (no new coupling)

**What Stage 7 does NOT activate:**
- β·μg coupling to contradiction-memory (deferred to Stage 8)
- Cross-gate amplitude coupling
- Persistence reward as runtime driver

### Stage 8 (implemented): local μ→a coupling
```python
Gate.step(dt, ...)   # amplitude block, only active when alpha != 0.0
    if alpha != 0.0:
        mu_n = mu  # snapshot for forward Euler consistency
        h = self.energy(t)
        a += dt * (alpha * h + beta * mu_n − xi * a)
        a = max(0.0, a)
```

**New field:** `beta` (default `0.0`) — contradiction-memory coupling coefficient. Dormant when 0.0.
**Steady state:** `a* = (alpha·H(g) + beta·μ*) / xi` (finite for xi > 0; fully decoupled when beta=0).

**Forward Euler ordering (all using state at t_n, before any updates):**
1. `theta += dt*(omega + coupling_term + mu_n)` — phase uses pre-update mu
2. `mu += dt*(c_in − lambda_mu·mu_n)` — memory update
3. `a += dt*(alpha·H + beta·mu_n − xi·a)` — amplitude uses same pre-update mu

This ensures causality: no future leakage between coupled fields.

**Safety properties:**
- With `beta=0.0` (default): Stage 7 behavior is unchanged bit-for-bit
- `beta > 0` with positive mu drives amplitude above entropy-only trajectory
- `beta > 0` with mu=0 has no additional effect beyond alpha·H drive
- a is still clamped to ≥ 0 (as in Stage 7)
- Amplitude block requires `alpha != 0.0` to activate — mu alone cannot turn on amplitude dynamics

**What Stage 8 activates only:**
- Local, deterministic, bounded μ→a coupling within the existing amplitude block
- mu influences amplitude via the single additive `beta·mu` term
- Effect is visible in `weighted_phase()` as `H(g)·a·e^(iθ)` magnitude change

**What Stage 8 does NOT activate:**
- Cross-gate contradiction flow
- Cross-gate amplitude coupling
- Feedback from a back into mu or theta
- Coupling resonance (Stage 10)
- Persistence reward as runtime driver (Stage 11)
- Stochastic behavior of any kind
- Pearl mutation or narration

### Stage 9 (implemented): cross-gate contradiction coupling

```python
contradiction_signal(gate, neighbors, t=None) -> float
    # C_i = (1/|N|) · Σ_{j∈N} |sin(θᵢ⁽⁰⁾ − θⱼ⁽⁰⁾)|
    # Range: [0, 1].  Returns 0.0 when neighbors is empty.

Gate.step(dt, coupling_term=0.0, c_in=0.0, c_i=0.0, t=None)
    mu_n = self.mu
    self.theta += dt * (self.omega + coupling_term + mu_n)
    self.mu    += dt * (c_in + self.gamma * c_i - self.lambda_mu * mu_n)
    if self.alpha != 0.0:
        h = self.energy(t)
        self.a += dt * (self.alpha * h + self.beta * mu_n - self.xi * self.a)
        self.a = max(0.0, self.a)
```

**New field:** `gamma` (default `0.0`) — cross-gate contradiction coupling sensitivity. Dormant when 0.0.
**New parameter:** `c_i` (default `0.0`) — pre-computed contradiction signal passed to `step()`.

**C_i definition:** Phase-mismatch signal from neighbors:
```
C_i = (1/|N|) · Σ_{j∈N} |sin(θᵢ⁽⁰⁾ − θⱼ⁽⁰⁾)|
```
- Bounded: C_i ∈ [0, 1] always
- Deterministic: C_i is a pure function of support state at time t
- Symmetric: same formula for all gates; no directed coupling introduced
- C_i = 0 when all neighbors share the same support-derived phase (consensus)
- C_i → 1 when gates are maximally out of phase (maximum contradiction)

**Callers** compute `C_i = contradiction_signal(gate, neighbors, t)` and pass it
as `c_i` to `step()`. The gate does not pull neighbor state internally.

**Forward Euler ordering (all using state at t_n):**
1. `mu_n = self.mu` — snapshot before any update
2. `theta += dt*(omega + coupling_term + mu_n)` — phase uses pre-update mu
3. `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)` — memory update with cross-gate signal
4. `a += dt*(alpha*H + beta*mu_n − xi*a)` — amplitude uses pre-update mu (if alpha != 0)

**Safety properties:**
- With `gamma=0.0` (default): Stage 8 behavior is unchanged bit-for-bit
- `gamma > 0` with `c_i=0` (no neighbors or consensus): no effect beyond Stage 8
- `c_i` is always pre-computed by caller — gate never reads neighbor state directly
- C_i is bounded [0,1] — mu injection from cross-gate signal is bounded by gamma
- Steady state: μ* = (c_in + gamma·C_i) / lambda_mu  (finite for lambda_mu > 0)
- phi_R, phi_B, energy(), p(), collapse logic never touched by step()

**What Stage 9 activates only:**
- A bounded, deterministic, one-directional signal path: neighbor phases → μᵢ
- Gate becomes contradiction-sensitive to its topological neighborhood
- Effect propagates through existing μ→phase (Stage 6) and μ→amplitude (Stage 8) paths

**What Stage 9 does NOT activate:**
- Symmetric back-reaction: gate does not push into neighbor μ via this mechanism
- Resonance coupling (Stage 10)
- Persistence reward as runtime driver (Stage 11)
- Stochastic behavior of any kind
- Pearl mutation or narration

### Stage 10 (implemented): bounded resonance coupling

```python
resonance_signal(gate, neighbors, t=None) -> float
    # R_i = (1/|N|) · Σ_{j∈N} cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)
    # Range: [-1, 1].  Returns 0.0 when neighbors is empty.
    # Uses support-anchor phase θ⁽⁰⁾ only — not evolved theta.

Gate.step(dt, coupling_term=0.0, c_in=0.0, c_i=0.0, r_i=0.0, t=None)
    mu_n = self.mu
    self.theta += dt * (self.omega + coupling_term + mu_n + self.rho * r_i)
    self.mu    += dt * (c_in + self.gamma * c_i - self.lambda_mu * mu_n)
    if self.alpha != 0.0:
        h = self.energy(t)
        self.a += dt * (self.alpha * h + self.beta * mu_n - self.xi * self.a)
        self.a = max(0.0, self.a)
```

**New field:** `rho` (default `0.0`) — resonance coupling coefficient. Dormant when 0.0.
**New parameter:** `r_i` (default `0.0`) — pre-computed resonance signal passed to `step()`.

**R_i definition:** Cosine phase-alignment signal from neighbors:
```
R_i = (1/|N|) · Σ_{j∈N} cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)
```
- Bounded: R_i ∈ [-1, 1] always
- Deterministic: pure function of support state at time t
- Symmetric: same formula applied to each gate; mutual structure
- R_i = 1.0 when all neighbors share exactly the same support phase (full alignment)
- R_i = 0.0 for orthogonal phases (π/2 apart); R_i = -1.0 for anti-aligned phases (π apart)
- R_i = 0.0 for empty neighborhoods (isolated gate)

**Why support-anchor θ⁽⁰⁾ (not dynamic θ):** Using the support-derived anchor prevents
feedback loops where `rho*R_i` drives `theta`, which would then feed back into `R_i` in the
next step, potentially causing resonance runaway. The anchor is read-only — it reflects observed
truth state without incorporating the memory offset. This is the safe first activation.

**Signal separation:** Resonance (R_i) and contradiction (C_i) are kept as distinct signals:
- `C_i = (1/|N|)·Σ|sin(θᵢ⁽⁰⁾ − θⱼ⁽⁰⁾)|` ∈ [0,1] — disagreement magnitude → μ
- `R_i = (1/|N|)·Σcos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)` ∈ [-1,1] — alignment direction → θ

These are orthogonal in the circular sense: C_i peaks at π/2 mismatch; R_i is zero there.
Combining them into one signal would lose this orthogonality.

**Callers** compute `R_i = resonance_signal(gate, neighbors, t)` and pass it
as `r_i` to `step()`. The gate does not pull neighbor state internally.

**Forward Euler ordering (all using state at t_n):**
1. `mu_n = self.mu` — snapshot before any update
2. `theta += dt*(omega + coupling_term + mu_n + rho*r_i)` — phase with resonance
3. `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)` — memory update
4. `a += dt*(alpha*H + beta*mu_n − xi*a)` — amplitude (if alpha != 0)

**Safety properties:**
- With `rho=0.0` (default): Stage 9 behavior is unchanged bit-for-bit
- `rho > 0` pulls theta toward neighbor phases (alignment coupling)
- `rho < 0` pushes theta away from neighbor phases (anti-alignment)
- R_i is bounded [-1,1] — maximum phase shift per step is `dt * rho`
- phi_R, phi_B, energy(), p(), collapse logic never touched by step()

**What Stage 10 activates only:**
- A bounded, deterministic, symmetric phase-alignment signal path: neighbor support phases → θᵢ
- Phase evolution becomes locally field-sensitive in a symmetric way
- Contradiction and resonance remain distinct, non-interfering paths

**What Stage 10 does NOT activate:**
- Amplitude transfer across gates
- Direct coupling into phi_R, phi_B
- Persistence reward as runtime driver
- Topology mutation
- Pearl-level resonance semantics
- Stochastic behavior of any kind
- Pearl mutation or narration

### Stage 11 (implemented): bounded persistence reward

```python
# Local persistence score (computed internally in step())
p_score = min(1.0, self.a * h)          # P_i ∈ [0, 1]

# Effective damping reduced by persistence reward
xi_denom = max(1e-6, 1.0 + self.epsilon_persist * p_score)
xi_eff = self.xi / xi_denom              # ξ_eff ≤ ξ; always positive

# Amplitude evolution with persistence-modulated damping (only when alpha != 0)
Gate.step(dt, ...)
    if alpha != 0.0:
        h = self.energy(t)
        p_score = min(1.0, self.a * h)
        xi_denom = max(1e-6, 1.0 + self.epsilon_persist * p_score)
        xi_eff = self.xi / xi_denom
        self.a += dt * (self.alpha * h + self.beta * mu_n - xi_eff * self.a)
        self.a = max(0.0, self.a)
```

**New field:** `epsilon_persist` (default `0.0`) — persistence reward coefficient. Dormant when 0.0.

**P_i definition:** Local persistence score, computed from the gate's own current state:
```
P_i = min(1, aᵢ · H(gᵢ))
```
- Bounded: P_i ∈ [0, 1] always (min ensures ceiling; both a ≥ 0 and H ≥ 0 ensure floor)
- Local: depends only on this gate's amplitude and energy — no neighbor reads
- Deterministic: pure function of current state at evaluation time
- Meaningful: high amplitude × high entropy = high structural presence = high retention bias
- A=1.0, H≈1.0 → P_i ≈ 1.0 (maximum persistence); H=0 (collapsed) → P_i = 0 (no persistence)

**ξ_eff formula:**
```
ξ_eff = ξ / (1 + ε_p · P_i)
```
- With ε_p=0.0: ξ_eff = ξ (Stage 10 behavior unchanged)
- With ε_p>0, P_i>0: ξ_eff < ξ (amplitude decays more slowly — persistence retained longer)
- Denominator clamped to ≥ 1e-6: ξ_eff always positive regardless of coefficient value
- Steady state: a* = (α·H + β·μ*) / ξ_eff > (α·H + β·μ*) / ξ (higher than without persistence)

**Why amplitude damping (not memory decay):** Amplitude is the structural persistence carrier
in `weighted_phase()`. Slowing amplitude decay directly prolongs how long coherent gate structure
contributes to the field tensor — the most natural definition of persistence at Layer 0.
Memory decay modulation (Option A) would extend contradiction-memory, with less direct connection
to structural retention.

**Why P_i is computed internally:** Unlike C_i (requires neighbor phases) and R_i (requires
neighbor phases), P_i depends only on this gate's own `a` and `H`. No external reads needed.
The caller does not need to pre-compute or pass P_i.

**Forward Euler ordering (all using state at t_n):**
1. `mu_n = self.mu` — snapshot before any update
2. `theta += dt*(omega + coupling_term + mu_n + rho*r_i)` — phase
3. `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)` — memory
4. If alpha != 0.0:
   - `h = energy(t)` — current gate energy
   - `p_score = min(1, a*h)` — local persistence score
   - `xi_eff = xi / max(1e-6, 1 + epsilon_persist*p_score)` — modulated damping
   - `a += dt*(alpha*h + beta*mu_n − xi_eff*a)` — amplitude with retention bias

**Safety properties:**
- With `epsilon_persist=0.0` (default): Stage 10 behavior unchanged bit-for-bit
- Persistence only activates when `alpha != 0.0` (amplitude block is live)
- ξ_eff ≥ ξ * 1e-6 — never zero, never negative
- P_i ∈ [0,1] — bounded persistence score, never diverges
- phi_R, phi_B, energy(), p(), collapse logic never touched by step()
- Persistence does not inject support, create Pearls, or interact with narration

**What Stage 11 activates only:**
- Local, deterministic, bounded amplitude decay modulation based on gate's own coherent weight
- Coherent (high-amplitude, high-entropy) gates decay more slowly
- Collapsed or quiescent gates (H=0 or a=0) get no persistence benefit

**What Stage 11 does NOT activate:**
- Direct support injection
- Direct entropy modification
- Collapse threshold changes
- Cross-gate persistence coupling
- Topology mutation
- Pearl-level persistence semantics
- Global attractors
- Stochastic behavior of any kind
- Narration

### Stage 12 (implemented): controlled topology emergence

```python
emergence_weight(gate_i, gate_j, t=None) -> float
    # ā_ij   = (aᵢ + aⱼ) / 2
    # R_ij   = cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)
    # E_ij   = min(1, ā_ij · max(0, R_ij))
    # Range: [0, 1].  Symmetric: E_ij = E_ji.
    # Returns 0 when R_ij ≤ 0 (anti-aligned or orthogonal).
    # Returns 0 when ā_ij = 0 (quiescent pair).

# Callers compute effective weight (not written back to canonical state):
w_ij_eff = w_ij * (1 + gate.kappa_emergence * emergence_weight(gate_i, gate_j, t))
```

**New field:** `kappa_emergence` (default `0.0`) — topology emergence sensitivity. Dormant when 0.0.

**E_ij definition:** Amplitude-weighted alignment enhancement factor:
```
E_ij = min(1, ā_ij · max(0, R_ij))
```
- `ā_ij = (aᵢ + aⱼ) / 2` — mean amplitude of the pair (≥ 0)
- `R_ij = cos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)` — pairwise cosine alignment ∈ [-1, 1], using support-anchor phases
- `max(0, R_ij)` — clips anti-alignment to zero (emergence is one-directional: helps aligned pairs)
- `min(1, ...)` — caps at 1 (prevents super-linear enhancement)
- E_ij ∈ [0, 1] — always bounded

**Effective weight formula:**
```
w_ij_eff = w_ij · (1 + κ · E_ij)
```
- With κ=0.0 (default): w_ij_eff = w_ij (canonical weight unchanged)
- With κ>0, aligned persistent pairs: w_ij_eff > w_ij (strengthened)
- With κ>0, anti-aligned or quiescent pairs: w_ij_eff = w_ij (no change)
- w_ij_eff ≤ w_ij · (1 + κ) (bounded above since E_ij ≤ 1)

**Reversibility and non-canonicity:** The effective weight is computed at query time and never
written back to any stored state. Canonical topology (wᵢⱼ) is read-only to this computation.
Changing kappa_emergence immediately changes the effective weight without any state migration.

**Why support-anchor θ⁽⁰⁾:** Consistency with Stage 10 — the anchor is read-only, stable, and
avoids feedback where w_ij_eff would influence theta which would change R_ij in the next step.

**Safety properties:**
- With `kappa_emergence=0.0` (default): Stage 11 behavior unchanged bit-for-bit
- E_ij ∈ [0, 1] — w_ij_eff ≥ w_ij always (for non-negative κ and w_ij)
- emergence_weight() is read-only — phi_R, phi_B, theta, mu, a are never modified
- Canonical weight wᵢⱼ is never modified — changes are transient query-time only
- E_ij = 0 for anti-aligned pairs — no weakening of anti-correlated structure
- Symmetric: E_ij = E_ji (ā and cos are both symmetric in i,j)
- No new step() parameters — topology emergence is read-only, not dynamical

**What Stage 12 activates only:**
- A bounded, deterministic, reversible, read-only effective weight query
- Persistent coherent alignment between gate pairs increases their effective coupling
- Gate pairs with anti-aligned or zero-amplitude dynamics receive no enhancement

**What Stage 12 does NOT activate:**
- Canonical weight mutation
- amplitude or phase modification from this mechanism
- Direct energy injection
- Collapse threshold changes
- Feedback from effective weight into gate dynamics (w_ij_eff does not flow back to step())
- Asymmetric topology (E_ij = E_ji)
- Stochastic behavior of any kind
- Pearl mutation or narration

### Stage 13 (implemented): controlled feedback coupling

```python
local_emergence_summary(gate, neighbors, t=None) -> float
    # Ē_i = (1/|N|) · Σ_{j∈N} emergence_weight(gate, j, t)
    # Range: [0, 1].  Returns 0.0 when neighbors is empty.
    # Deterministic neighborhood mean of pairwise E_ij values.

# Effective resonance coefficient (computed inside step() — not stored):
rho_eff = self.rho * (1.0 + self.delta_feedback * e_bar)

Gate.step(dt, coupling_term=0.0, c_in=0.0, c_i=0.0, r_i=0.0, e_bar=0.0, t=None)
    mu_n = self.mu
    rho_eff = self.rho * (1.0 + self.delta_feedback * e_bar)
    self.theta += dt * (self.omega + coupling_term + mu_n + rho_eff * r_i)
    self.mu    += dt * (c_in + self.gamma * c_i - self.lambda_mu * mu_n)
    if self.alpha != 0.0:
        h = self.energy(t)
        p_score = min(1.0, self.a * h)
        xi_eff = self.xi / max(1e-6, 1.0 + self.epsilon_persist * p_score)
        self.a += dt * (self.alpha * h + self.beta * mu_n - xi_eff * self.a)
        self.a = max(0.0, self.a)
```

**New field:** `delta_feedback` (default `0.0`) — feedback coupling coefficient. Dormant when 0.0.
**New parameter:** `e_bar` (default `0.0`) — pre-computed local emergence summary passed to `step()`.

**Ē_i definition:** Neighborhood mean of pairwise emergence factors:
```
Ē_i = (1/|N(i)|) · Σ_{j∈N(i)} E_ij    where E_ij = emergence_weight(gate_i, gate_j, t)
```
- Bounded: Ē_i ∈ [0, 1] (mean of values each ∈ [0, 1])
- Local: depends only on this gate's neighborhood, not global state
- Deterministic: pure function of support state and amplitudes at time t
- Returns 0.0 for empty neighborhoods (isolated gates)

**Effective resonance modulation:**
```
ρ_eff = ρ · (1 + δ · Ē_i)
```
- With δ=0.0 (default): ρ_eff = ρ (Stage 12 behavior unchanged bit-for-bit)
- With δ>0, Ē_i>0: ρ_eff > ρ (high-emergence neighborhoods strengthen resonance)
- With Ē_i=0 (isolated or quiescent neighborhood): ρ_eff = ρ (no feedback effect)
- ρ_eff ≤ ρ·(1 + δ) since Ē_i ≤ 1 (bounded above)
- If ρ ≥ 0 and δ ≥ 0: ρ_eff ≥ 0 (bounded, non-negative)

**Why resonance channel (not contradiction):** Resonance (ρ·R_i) drives phase alignment directly.
Strengthening the resonance channel for high-emergence neighborhoods creates a self-reinforcing
loop: aligned persistent structures pull their phases further into alignment, increasing future
emergence weight. This is the minimal bounded self-reinforcement step. The contradiction channel
(γ·C_i) is preserved unchanged — only the alignment channel gets the feedback.

**Why Ē_i rather than per-pair E_ij:** A neighborhood mean is strictly more local than a
global signal, bounded in the same range, and averages out per-pair fluctuations. It captures
the structural coherence of the gate's local context without pulling in global topology.

**Feedback is temporary and non-canonical:**
- `rho_eff` is computed inside `step()` — not stored, not returned, not written anywhere
- Changing `delta_feedback` takes effect immediately without state migration
- Canonical `rho` field is read-only from this computation

**Callers** compute `e_bar = local_emergence_summary(gate, neighbors, t)` and pass it as
`e_bar` to `step()`. The gate does not pull neighbor state internally.

**Forward Euler ordering (all using state at t_n):**
1. `mu_n = self.mu` — snapshot before any update
2. `rho_eff = rho * (1 + delta_feedback * e_bar)` — transient effective coefficient
3. `theta += dt*(omega + coupling_term + mu_n + rho_eff*r_i)` — phase with feedback-modulated resonance
4. `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)` — memory update
5. If alpha != 0.0: amplitude block (unchanged from Stage 11)

**Safety properties:**
- With `delta_feedback=0.0` (default): Stage 12 behavior unchanged bit-for-bit
- With `e_bar=0.0` (default): rho_eff = rho → Stage 12 behavior unchanged
- Ē_i ∈ [0,1] — feedback modulation bounded by δ
- rho_eff ≥ 0 for non-negative ρ and δ (natural sign-consistent defaults)
- phi_R, phi_B, energy(), p(), collapse logic never touched by step()
- `rho_eff` is ephemeral — no new canonical field introduced, no state written

**What Stage 13 activates only:**
- Bounded, temporary, deterministic feedback from local emergence → resonance channel strength
- Persistent coherent structures can slightly reinforce their own phase-alignment channel
- Effect visible only when delta_feedback > 0, rho ≠ 0, r_i ≠ 0, and e_bar > 0 simultaneously

**What Stage 13 does NOT activate:**
- Permanent topology mutation (still deferred)
- Feedback into support, energy, p(), or collapse logic
- Contradiction channel modulation (gamma unchanged)
- Feedback into amplitude dynamics (xi, alpha, beta unchanged)
- Pearl-level feedback semantics
- Narration
- Global attractors
- Stochastic behavior of any kind

**Stage 13 activates bounded temporary feedback coupling only. It does not yet activate
permanent graph mutation, morphology, narration, or domain logic.**

### Stage 14 (implemented): controlled stabilization / attractor bias

```python
# Effective natural frequency — reduced by local emergence (computed inside step()):
omega_eff = self.omega / max(1e-9, 1.0 + self.zeta_stabilize * e_bar)

Gate.step(dt, coupling_term=0.0, c_in=0.0, c_i=0.0, r_i=0.0, e_bar=0.0, t=None)
    mu_n = self.mu
    rho_eff   = self.rho * (1.0 + self.delta_feedback * e_bar)    # Stage 13
    omega_eff = self.omega / max(1e-9, 1.0 + self.zeta_stabilize * e_bar)  # Stage 14
    self.theta += dt * (omega_eff + coupling_term + mu_n + rho_eff * r_i)
    self.mu    += dt * (c_in + self.gamma * c_i - self.lambda_mu * mu_n)
    if self.alpha != 0.0:
        h = self.energy(t)
        p_score = min(1.0, self.a * h)
        xi_eff = self.xi / max(1e-6, 1.0 + self.epsilon_persist * p_score)
        self.a += dt * (self.alpha * h + self.beta * mu_n - xi_eff * self.a)
        self.a = max(0.0, self.a)
```

**New field:** `zeta_stabilize` (default `0.0`) — stabilization coefficient. Dormant when 0.0.
**No new parameter:** Stage 14 reuses `e_bar` already introduced in Stage 13.

**ω_eff formula:**
```
ω_eff = ω / (1 + ζ · Ē_i)
```
- With ζ=0.0 (default): ω_eff = ω (Stage 13 behavior unchanged bit-for-bit)
- With ζ>0, Ē_i>0: |ω_eff| < |ω| (intrinsic drift reduced for coherent neighborhoods)
- With Ē_i=0 (isolated or quiescent neighborhood): ω_eff = ω (no stabilization)
- Sign preserved: ω_eff has the same sign as ω always (denominator > 0 for ζ≥0, Ē_i≥0)
- Bounded reduction: ω_eff ≥ ω/(1+ζ) since Ē_i ≤ 1
- Denominator clamped to ≥ 1e-9: ω_eff always finite, same sign as ω

**What is damped vs. what is not:** Only the gate's intrinsic natural frequency ω is reduced.
The coupling term, μ contribution, and resonance term rho_eff·r_i are all unchanged. This means
stabilization slows free drift but does not freeze evolution — gates with non-zero coupling,
mu, or rho can still evolve freely. This prevents hard locking.

**Why ω (not λ_μ):** ω is the free-drift term in phase evolution — the intrinsic tendency for
a gate to drift regardless of neighborhood. Reducing it for coherent neighborhoods creates a
lawful preference for coherence without preventing coupling-driven evolution. λ_μ modulation
(Option B) would affect contradiction-memory decay, which is a separate concern.

**Stabilization is temporary and non-canonical:**
- `omega_eff` is computed inside `step()` — not stored, not returned, not written anywhere
- Canonical `omega` field is read-only from this computation
- Changing `zeta_stabilize` takes effect immediately without state migration

**Forward Euler ordering (all using state at t_n):**
1. `mu_n = self.mu` — snapshot before any update
2. `rho_eff = rho * (1 + delta_feedback * e_bar)` — transient (Stage 13)
3. `omega_eff = omega / max(1e-9, 1 + zeta_stabilize * e_bar)` — transient (Stage 14)
4. `theta += dt*(omega_eff + coupling_term + mu_n + rho_eff*r_i)` — phase with both modulations
5. `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)` — memory (unchanged)
6. If alpha != 0.0: amplitude block (unchanged from Stage 11)

**Safety properties:**
- With `zeta_stabilize=0.0` (default): Stage 13 behavior unchanged bit-for-bit
- With `e_bar=0.0` (default): omega_eff = omega → Stage 13 behavior unchanged
- Denominator ≥ 1e-9: omega_eff always finite; never NaN
- Sign of omega_eff = sign of omega: no polarity reversal
- phi_R, phi_B, energy(), p(), collapse logic never touched by step()
- `omega_eff` is ephemeral — no new canonical field introduced, no state written
- Even at maximum ζ and Ē_i=1: omega_eff = ω/(1+ζ) > 0 for ω > 0 (never zero unless ω=0)
- Gates with omega=0 are unaffected: 0/(1+ζ·Ē_i) = 0 always

**What Stage 14 activates only:**
- Bounded, temporary, deterministic reduction of intrinsic phase drift for high-emergence gates
- Coherent self-reinforcing neighborhoods drift more slowly in their natural frequency channel
- Coupling, resonance, and contradiction channels are completely unchanged

**What Stage 14 does NOT activate:**
- Hard phase locking or irreversible freezing (coupling terms still drive evolution freely)
- Permanent topology mutation (still deferred)
- Modification of support, energy, p(), or collapse logic
- Contradiction or amplitude channel modulation
- Pearl-level stabilization semantics
- Global attractors
- Narration
- Stochastic behavior of any kind

**Stage 14 activates bounded stabilization / attractor bias only. It does not yet activate
permanent graph mutation, morphology, narration, domain logic, or hard locking.**

### Stage 15 (implemented): controlled topology persistence

New module: `invar/core/topology_trace.py` — `TopologyTrace` class.

```python
# Trace update (called once per time step per pair):
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)

# τ_ij evolution (forward Euler):
#   τ_ij += dt * (η_τ · E_ij - λ_τ · τ_ij)
#   τ_ij = max(0.0, τ_ij)   [non-negative clamp]

# Read:
tau = trace.get(gate_i.gate_id, gate_j.gate_id)

# Reset (non-destructive to canonical state):
trace.reset()                          # clear all
trace.reset(gate_i.gate_id, gate_j.gate_id)  # clear one pair
```

**TopologyTrace constructor parameters:**
- `eta_tau` (default `0.0`) — trace accumulation rate. Dormant when 0.0.
- `lambda_tau` (default `0.1`) — trace decay rate. τ decays to 0 without continued E_ij.

**τ_ij update equation:**
```
dτ_ij/dt = η_τ · E_ij - λ_τ · τ_ij
```
- Steady state: τ* = η_τ · E_ij / λ_τ (finite for λ_τ > 0)
- Upper bound: τ* ≤ η_τ / λ_τ (since E_ij ≤ 1)
- Bounded: τ converges to τ* from any initial condition
- Decays to 0 when E_ij = 0 (no continued coherence)
- τ_ij ≥ 0 always (clamped after each step)
- Symmetric: τ_ij = τ_ji (symmetric key scheme — `(i,j)` and `(j,i)` map to same slot)
- Deterministic: pure function of e_ij history and dt

**Non-canonical guarantee:**
- `TopologyTrace` is a standalone object — not embedded in Gate or canonical graph
- Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified
- Canonical graph weights are never read or modified
- Resetting or discarding a `TopologyTrace` object has zero effect on substrate state
- No Pearl is created or modified

**Relationship to emergence_weight():**
- Callers compute `e_ij = emergence_weight(gate_i, gate_j, t)` per pair per step
- This is the same bounded [0,1] signal used in Stages 12/13/14
- Trace accumulates evidence of repeated structural coherence over time

**Callers maintain the trace loop:**
```python
trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)

# Per time step, for each relevant pair:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)

# Read accumulated trace when needed:
tau = trace.get(gate_i.gate_id, gate_j.gate_id)
```

**Gate.step() is NOT modified by Stage 15.** The topology trace is a parallel
structure maintained by callers, not part of gate dynamics.

**Safety properties:**
- With `eta_tau=0.0` (default): trace never accumulates (dormant)
- With `lambda_tau > 0`: trace is stable (bounded ODE with mean-reverting dynamics)
- τ_ij ∈ [0, η_τ/λ_τ]: bounded above by construction
- phi_R, phi_B, energy(), p(), collapse logic never touched
- Canonical graph weights never touched
- No new Gate fields introduced — Stage 14 gate behavior unchanged bit-for-bit

**What Stage 15 activates only:**
- A separate, bounded, reversible, non-canonical topology trace object
- Repeated coherent pair structure accumulates memory over time
- Trace decays without sustained coherence — no irreversible commitment

**What Stage 15 does NOT activate:**
- Canonical graph mutation
- Trace write-back into gate dynamics (tau feeds nothing in this stage)
- Support injection or energy modification
- Pearl creation
- Narration
- Global attractors
- Stochastic behavior of any kind

**Stage 15 activates bounded non-canonical topology trace memory only. It does not yet activate
permanent graph mutation, morphology, narration, or domain logic.**

### Stage 16 (implemented): controlled trace influence

Stage 16 allows the bounded non-canonical topology trace τ_ij to weakly modulate effective
interaction weighting in a reversible, deterministic way.

**Extended effective weight formula:**
```
τ̂_ij = τ_ij / τ_max        where τ_max = η_τ / λ_τ

w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij)
```

**New method on `TopologyTrace`:**
```python
def normalized(self, id_i, id_j) -> float:
    # Returns τ̂_ij = τ_ij / τ_max ∈ [0, 1]
    # Returns 0.0 if eta_tau = 0 (dormant)
```

**New module-level function in `invar/core/topology_trace.py`:**
```python
def effective_weight(w_ij, e_ij, tau_hat, kappa_e=0.0, kappa_tau=0.0) -> float:
    return w_ij * (1.0 + kappa_e * e_ij + kappa_tau * tau_hat)
```

**Caller pattern:**
```python
from invar.core.gate import emergence_weight
from invar.core.topology_trace import TopologyTrace, effective_weight

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)

# Per time step — update trace:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)

# At interaction time — compute effective weight (transient, not stored):
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
w_eff = effective_weight(w_ij, e_ij, tau_hat, kappa_e=0.1, kappa_tau=0.05)
```

**Safety properties:**
- `effective_weight()` is computed transiently — never written back to canonical state
- With `kappa_e=0.0` and `kappa_tau=0.0` (default): returns `w_ij` exactly (bit-identical)
- With `eta_tau=0.0` (dormant Stage 15): `normalized()` returns 0.0 → κ_τ term is inert
- `w_ij_eff ≥ 0` for non-negative inputs — weight polarity preserved
- `w_ij_eff ≤ w_ij · (1 + κ_E + κ_τ)` — bounded above
- Zero canonical weight stays zero regardless of κ values
- Gate.step() is NOT modified; gate state never touched
- No Pearl created; no graph mutation; no narration

**What Stage 16 activates only:**
- Transient effective weight computation incorporating topology trace memory
- `normalized()` method on `TopologyTrace` for τ̂_ij ∈ [0,1]
- `effective_weight()` module-level function as standalone helper

**What Stage 16 does NOT activate:**
- Canonical graph weight mutation
- Gate.step() modification
- Support injection or energy modification
- Pearl creation
- Narration
- Hard locking or irreversible commitment

**Stage 16 activates bounded transient trace influence on effective weights only. It does not
activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 17 (implemented): controlled topology consolidation

New module: `invar/core/topology_candidates.py` — `TopologyCandidates` class.

This is the first explicit structural-consolidation step.  It surfaces pairs whose
current emergence AND accumulated normalized trace simultaneously meet thresholds,
identifying them as candidate structural edges.  The candidate set is a proposal
surface only — entirely non-canonical.

**Membership rule:**
```
(i, j) ∈ C  ⟺  E_ij ≥ θ_E  ∧  τ̂_ij ≥ θ_τ
```
Where:
- `E_ij`  = `emergence_weight(gate_i, gate_j, t)`   ∈ [0, 1]  — current coherence signal
- `τ̂_ij`  = `TopologyTrace.normalized(i, j)`        ∈ [0, 1]  — normalized historical trace
- `θ_E`   = `theta_e`  ∈ [0, 1]                               — emergence threshold
- `θ_τ`   = `theta_tau` ∈ [0, 1]                              — trace threshold

High current emergence alone is insufficient — sustained trace history is required.
High trace alone is insufficient — current coherence is required.
Both conditions must hold simultaneously.

**TopologyCandidates constructor parameters:**
- `theta_e`   (default `1.0`) — emergence threshold. Dormant when 1.0 (only exact-maximum qualifies).
- `theta_tau` (default `1.0`) — trace threshold. Dormant when 1.0.

**Core interface:**
```python
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_trace import TopologyTrace
from invar.core.gate import emergence_weight

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.4, theta_tau=0.4)

# Per time step — update trace:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)

# When evaluating topology — update candidate set:
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)

# Query:
cands.contains(gate_i.gate_id, gate_j.gate_id)  # bool
cands.edges()                                    # sorted list of candidate pairs
cands.count()                                    # number of candidates

# Reset (non-destructive to canonical state):
cands.reset()                                    # clear all
cands.reset(gate_i.gate_id, gate_j.gate_id)      # clear one pair

# Recompute from scratch (deterministic):
cands.recompute([(id_i, id_j, e_ij, tau_hat), ...])
```

**Safety properties:**
- `TopologyCandidates` is standalone — not embedded in Gate, graph, or Pearl
- Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified
- Canonical graph weights are never read or modified
- Gate energy, p(), and collapse logic are unchanged
- Resetting or discarding a `TopologyCandidates` object has zero effect on substrate state
- Candidate membership is deterministic: same signals + thresholds → same result
- Candidate set is symmetric: `(i,j) ∈ C ⟺ (j,i) ∈ C`
- No Pearl is created or modified; no support is injected
- Gate.step() is NOT modified

**What Stage 17 activates only:**
- A standalone, bounded, reversible, non-canonical topology candidate surface
- Pairs with both sustained historical coherence and current emergence are identified
- Candidate set is a proposal only — no write-back to substrate truth

**What Stage 17 does NOT activate:**
- Canonical graph mutation
- Permanent edge creation
- Support injection or energy modification
- Pearl creation
- Narration
- Domain-level interpretation of candidates
- Mandatory use of candidate edges in any downstream system

**Stage 17 activates bounded non-canonical topology candidate consolidation only. It does not
yet activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 18 (implemented): controlled candidate influence

Stage 18 is the first causal use of identified candidate topology.  Non-canonical
candidate membership now weakly modulates effective interaction weighting in a
reversible, deterministic way.

**Extended effective weight formula (Stages 16 + 18):**
```
I_ij ∈ {0, 1}  — candidate membership from TopologyCandidates.contains()

w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij + κ_C · I_ij)
```

The `effective_weight()` function in `invar/core/topology_trace.py` is extended with two
new optional parameters:
- `i_ij` (default `0.0`) — binary candidate flag; use `float(cands.contains(i, j))`
- `kappa_candidate` (default `0.0` — dormant) — candidate influence coefficient κ_C

**With `kappa_candidate=0.0` (default), behavior is bit-identical to Stage 17.**

**Caller pattern:**
```python
from invar.core.gate import emergence_weight
from invar.core.topology_trace import TopologyTrace, effective_weight
from invar.core.topology_candidates import TopologyCandidates

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.4, theta_tau=0.4)

# Per time step — update trace and candidates:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)

# At interaction time — compute effective weight (transient, not stored):
i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
w_eff = effective_weight(w_ij, e_ij, tau_hat,
                         kappa_e=0.1, kappa_tau=0.05,
                         i_ij=i_ij, kappa_candidate=0.02)
```

**Safety properties:**
- With `kappa_candidate=0.0` (default) OR `i_ij=0.0` (non-candidate): candidate term is exactly zero
- `i_ij` is binary — confirmation bias, not a continuous driver
- `w_ij_eff ≥ 0` for non-negative inputs; bounded above by `w_ij*(1+κ_E+κ_τ+κ_C)`
- Zero canonical weight stays zero regardless of κ_C or membership
- `effective_weight()` is transient — never written back to canonical state
- Gate.step() not modified; phi_R, phi_B, energy(), p(), collapse logic unchanged
- No Pearl created; no graph mutation; no narration
- Candidate set stored separately; reset removes contribution without substrate effect

**Intended usage constraint:** κ_C should be kept weaker than κ_τ to preserve the
intuition that candidate membership is a confirmation signal, not the dominant driver.

**What Stage 18 activates only:**
- Candidate membership flag (binary) as a new optional term in transient effective weight
- `kappa_candidate` coefficient in `effective_weight()` (default 0.0 — dormant)

**What Stage 18 does NOT activate:**
- Canonical graph mutation
- Permanent edge formation
- Support injection or energy modification
- Pearl creation
- Narration
- Domain-level interpretation of candidate influence
- Irreversible topology commitment

**Stage 18 activates bounded non-canonical candidate influence only. It does not yet activate
permanent graph mutation, morphology, narration, or domain logic.**

### Stage 19 (implemented): controlled topology commitment

New module: `invar/core/topology_commitments.py` — `TopologyCommitments` class.

This is the first proto-topological commitment step.  It surfaces pairs that pass
all three conditions simultaneously — stricter thresholds on current emergence and
normalized trace, plus confirmed candidate membership.  The committed set is a
durable (but resettable) proposal surface only — entirely non-canonical.

**Commitment rule (all three conditions required):**
```
(i, j) ∈ K  ⟺  E_ij ≥ θ_E^commit  ∧  τ̂_ij ≥ θ_τ^commit  ∧  I_ij = 1
```
Where:
- `E_ij`   = `emergence_weight(gate_i, gate_j, t)`         ∈ [0, 1]
- `τ̂_ij`   = `TopologyTrace.normalized(i, j)`             ∈ [0, 1]
- `I_ij`   = `float(TopologyCandidates.contains(i, j))`   ∈ {0, 1}
- `θ_E^commit` > `θ_E^candidate` (convention — stricter emergence threshold)
- `θ_τ^commit` > `θ_τ^candidate` (convention — stricter trace threshold)

Candidate membership is a hard gate.  A pair cannot be committed without first
being a candidate.  The commitment layer is a strict refinement of Stage 17.

**TopologyCommitments constructor parameters:**
- `theta_e`   (default `1.0` — dormant)
- `theta_tau` (default `1.0` — dormant)

**Core interface:**
```python
from invar.core.topology_commitments import TopologyCommitments
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_trace import TopologyTrace
from invar.core.gate import emergence_weight

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.35, theta_tau=0.35)  # looser
comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65) # stricter

# Per time step:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)

# When evaluating commitment:
i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
comms.evaluate(gate_i.gate_id, gate_j.gate_id,
               e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)

# Query:
comms.contains(gate_i.gate_id, gate_j.gate_id)  # bool
comms.edges()                                    # sorted list of committed pairs
comms.count()                                    # number of commitments

# Reset:
comms.reset()                                    # clear all
comms.reset(gate_i.gate_id, gate_j.gate_id)      # clear one pair

# Recompute:
comms.recompute([(id_i, id_j, e_ij, tau_hat, i_ij), ...])
```

**Safety properties:**
- `TopologyCommitments` is standalone — not embedded in Gate, graph, or Pearl
- Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified
- Canonical graph weights are never read or modified
- Gate energy, p(), and collapse logic are unchanged
- Resetting or discarding a `TopologyCommitments` object has zero substrate effect
- Commitment is deterministic: same signals + thresholds → same result
- Commitment is symmetric: `(i,j) ∈ K ⟺ (j,i) ∈ K`
- No Pearl is created or modified; no support is injected
- Gate.step() is NOT modified

**Layered structure:**
```
TopologyTrace           — per-pair accumulated coherence memory
    ↓ normalized()
TopologyCandidates      — identified candidate pairs (Stage 17)
    ↓ contains() → i_ij
TopologyCommitments     — committed proto-topological pairs (Stage 19)
```

**What Stage 19 activates only:**
- A standalone, bounded, reversible, non-canonical topology commitment surface
- Pairs satisfying stricter emergence + trace + candidate membership conditions
- Committed set is a proto-topological proposal only — no write-back to substrate

**What Stage 19 does NOT activate:**
- Canonical graph mutation
- Permanent edge creation
- Support injection or energy modification
- Pearl creation
- Narration
- Domain-level interpretation of commitments
- Mandatory use of committed edges in any downstream system

**Stage 19 activates bounded non-canonical topology commitment only. It does not yet activate
permanent graph mutation, morphology, narration, or domain logic.**

### Stage 20 (implemented): controlled commitment influence

Stage 20 is the first causal use of committed topology. Non-canonical commitment membership
now weakly modulates effective interaction weighting in a reversible, deterministic way.

**Extended effective weight formula (Stages 16 + 18 + 20):**
```
K_ij ∈ {0, 1}  — commitment membership from TopologyCommitments.contains()

w_ij_eff = w_ij · (1 + κ_E · E_ij + κ_τ · τ̂_ij + κ_C · I_ij + κ_K · K_ij)
```

The `effective_weight()` function in `invar/core/topology_trace.py` is extended with two
new optional parameters:
- `k_ij` (default `0.0`) — binary commitment flag; use `float(comms.contains(i, j))`
- `kappa_commitment` (default `0.0` — dormant) — commitment influence coefficient κ_K

**With `kappa_commitment=0.0` (default), behavior is bit-identical to Stage 19.**

**CRITICAL SAFETY CONSTRAINT — coefficient ordering:**
```
κ_K << κ_C << κ_τ
```
- `κ_τ` (trace) = memory driver — largest allowed signal
- `κ_C` (candidate) = structural confirmation — moderate signal
- `κ_K` (commitment) = reinforcement only — weakest non-zero signal

Commitment must NEVER dominate weighting. Typical values: κ_τ=0.05, κ_C=0.02, κ_K=0.005.

**Caller pattern:**
```python
from invar.core.gate import emergence_weight
from invar.core.topology_trace import TopologyTrace, effective_weight
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_commitments import TopologyCommitments

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.35, theta_tau=0.35)
comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)

# Per time step — update trace, candidates, and commitments:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)
i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
comms.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)

# At interaction time — compute effective weight (transient, not stored):
k_ij = float(comms.contains(gate_i.gate_id, gate_j.gate_id))
w_eff = effective_weight(w_ij, e_ij, tau_hat,
                         kappa_e=0.1, kappa_tau=0.05,
                         i_ij=i_ij, kappa_candidate=0.02,
                         k_ij=k_ij, kappa_commitment=0.005)
```

**Safety properties:**
- With `kappa_commitment=0.0` (default) OR `k_ij=0.0` (non-committed): commitment term is exactly zero
- `k_ij` is binary — reinforcement signal, not a continuous driver
- `w_ij_eff ≥ 0` for non-negative inputs; bounded above by `w_ij*(1+κ_E+κ_τ+κ_C+κ_K)`
- Zero canonical weight stays zero regardless of κ_K or membership
- `effective_weight()` is transient — never written back to canonical state
- Gate.step() not modified; phi_R, phi_B, energy(), p(), collapse logic unchanged
- No Pearl created; no graph mutation; no narration
- Commitment set stored separately; reset removes contribution without substrate effect
- TopologyCommitments is read-only for weighting — no write-back to candidates, trace, or graph

**What Stage 20 activates only:**
- Commitment membership flag (binary) as a new optional term in transient effective weight
- `kappa_commitment` coefficient in `effective_weight()` (default 0.0 — dormant)
- Committed pairs self-stabilize slightly: structure → commitment → reinforcement → structure

**What Stage 20 does NOT activate:**
- Canonical graph mutation or permanent edge formation
- Support injection or energy modification
- Pearl creation or narration
- Feedback into Gate.step() dynamics (commitment never enters theta, mu, or a)
- Commitment dominance over trace or candidate signals
- Stochastic behavior of any kind

**Stage 20 activates bounded non-canonical commitment influence only. It does not activate
permanent graph mutation, morphology, narration, or domain logic.**

### Stage 21 (implemented): controlled stabilization regulation

Stage 21 introduces the first anti-lock regulation step. When local structure is already
highly stabilized — simultaneously committed and holding high trace memory — the effective
interaction weight is slightly reduced, keeping the field adaptive instead of frozen.

**Regulation signal:**
```
R_ij_lock = K_ij · τ̂_ij   ∈ [0, 1]
```
- Non-zero only when a pair is simultaneously committed (K_ij = 1) and holds high
  normalized trace memory (τ̂_ij near 1)
- Reflects how deeply locked a relationship has become
- Bounded: R_lock ∈ [0, 1] by construction (product of two [0,1] values)
- Deterministic: pure function of current signals
- Symmetric: inherits symmetry from K_ij and τ̂_ij

**Extended effective weight formula (Stages 16 + 18 + 20 + 21):**
```
w_ij_eff = w_ij · max(0, 1 + κ_E·E_ij + κ_τ·τ̂_ij + κ_C·I_ij + κ_K·K_ij − κ_R·R_lock)
```

The multiplier is clamped to ≥ 0, ensuring non-negative effective weight for all
non-negative w_ij regardless of caller-supplied κ_R magnitude.

**New module-level function in `invar/core/topology_trace.py`:**
```python
def regulation_signal(k_ij: float, tau_hat: float) -> float:
    # Returns R_ij_lock = K_ij · τ̂_ij ∈ [0, 1]
    return k_ij * tau_hat
```

**New parameter on `effective_weight()`:**
- `r_ij_lock` (default `0.0`) — pre-computed regulation signal; use `regulation_signal(k_ij, tau_hat)`
- `kappa_regulate` (default `0.0` — dormant) — regulation coefficient κ_R

**With `kappa_regulate=0.0` (default), behavior is bit-identical to Stage 20.**

**CRITICAL SAFETY CONSTRAINT — full coefficient ordering:**
```
κ_R < κ_K < κ_C < κ_τ
```
- `κ_τ` (trace) = memory driver — largest allowed signal
- `κ_C` (candidate) = structural confirmation — moderate
- `κ_K` (commitment) = reinforcement — smaller
- `κ_R` (regulation) = counter-pressure only — weakest of all

Typical values: κ_τ=0.05, κ_C=0.02, κ_K=0.005, κ_R=0.001.

Regulation moderates only — it never overwhelms the positive structure terms.

**Caller pattern:**
```python
from invar.core.topology_trace import TopologyTrace, effective_weight, regulation_signal
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_commitments import TopologyCommitments
from invar.core.gate import emergence_weight

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.35, theta_tau=0.35)
comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)

# Per time step — update trace, candidates, and commitments:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)
i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
comms.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)

# At interaction time — compute effective weight with regulation (transient, not stored):
k_ij = float(comms.contains(gate_i.gate_id, gate_j.gate_id))
r_lock = regulation_signal(k_ij, tau_hat)
w_eff = effective_weight(w_ij, e_ij, tau_hat,
                         kappa_e=0.1, kappa_tau=0.05,
                         i_ij=i_ij, kappa_candidate=0.02,
                         k_ij=k_ij, kappa_commitment=0.005,
                         r_ij_lock=r_lock, kappa_regulate=0.001)
```

**Safety properties:**
- With `kappa_regulate=0.0` (default) OR `r_ij_lock=0.0`: regulation term is exactly zero
- `r_ij_lock` is bounded [0, 1] — regulation contribution is bounded by κ_R
- `max(0, ...)` clamp ensures w_ij_eff ≥ 0 for non-negative w_ij always
- Zero canonical weight stays zero regardless of κ_R or R_lock
- `effective_weight()` and `regulation_signal()` are both transient — never written back
- Gate.step() not modified; phi_R, phi_B, energy(), p(), collapse logic unchanged
- No Pearl created; no graph mutation; no narration
- Commitment, candidate, and trace sets are read-only — regulation never mutates them

**What Stage 21 activates only:**
- `regulation_signal()` — a pure, bounded, deterministic helper computing K_ij · τ̂_ij
- `r_ij_lock` and `kappa_regulate` as new optional parameters in `effective_weight()`
- Highly committed, high-trace pairs experience slight bounded counter-pressure on effective weight
- Field remains adaptive: structure can self-stabilize (Stage 20) but not freeze (Stage 21)

**What Stage 21 does NOT activate:**
- Canonical graph mutation or permanent edge modification
- Support injection or energy modification
- Pearl creation or narration
- Feedback into Gate.step() dynamics
- Regulation dominance over commitment, candidate, or trace signals
- Irreversible topology decay or forced decoupling
- Stochastic behavior of any kind

**Stage 21 activates bounded non-canonical stabilization regulation only. It does not yet
activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 22 (implemented): controlled proto-topology shaping

New module: `invar/core/proto_topology.py` — `ProtoTopology` class.

Stage 22 is the first step where structure appears as regional / multi-node form rather
than only pairwise edges.  Connected components of the committed-pair graph are surfaced
as bounded, reversible, non-canonical proto-regions.

**Formation rule:**
```
(i, j) ∈ K  ⟹  (i, j) ∈ G_proto
proto-regions = connected components of G_proto with |region| ≥ 2
```
Where K is the committed pair set from `TopologyCommitments`.

**Core interface:**
```python
from invar.core.proto_topology import ProtoTopology
from invar.core.topology_commitments import TopologyCommitments

comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)
# ... (evaluate commitments per time step) ...

proto = ProtoTopology()
proto.evaluate_edges(comms.edges())  # committed pairs → connected components

# Query regional structure:
proto.regions()                      # list of frozensets of node ids (|region| ≥ 2)
proto.region_of("gate_id")           # frozenset or None
proto.contains_node("gate_id")       # bool
proto.region_count()                 # int
proto.node_count()                   # int
proto.snapshot()                     # frozenset[frozenset[str]] — immutable

# Reset / rebuild (non-destructive to canonical state):
proto.reset()
proto.recompute(comms.edges())
```

**Algorithm:**
1. Build an undirected adjacency graph from the committed edges
2. BFS connected-component traversal over sorted node keys (deterministic)
3. Retain only components with |component| ≥ 2 as proto-regions

**Layered structure now complete through Stage 22:**
```
TopologyTrace           — per-pair accumulated coherence memory (Stage 15)
    ↓ normalized()
TopologyCandidates      — identified candidate pairs (Stage 17)
    ↓ contains() → i_ij
TopologyCommitments     — committed proto-topological pairs (Stage 19)
    ↓ edges()
ProtoTopology           — connected regional structure (Stage 22)
```

**Safety properties:**
- `ProtoTopology` is standalone — not embedded in Gate, graph, or Pearl
- Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified
- Canonical graph weights and topology are never read or modified
- Gate energy, p(), and collapse logic are unchanged
- Resetting or discarding a `ProtoTopology` object has zero substrate effect
- Proto-regions are deterministic: same edges → same components → same regions
- Proto-regions are symmetric: region membership is order-independent (undirected graph)
- No Pearl is created or modified; no support is injected
- Gate.step() is NOT modified

**What Stage 22 activates only:**
- A standalone, bounded, reversible, non-canonical regional structure surface
- Committed pairs define an undirected adjacency; connected components of size ≥ 2 are
  surfaced as proto-regions
- Proto-regions are a proposal surface only — no write-back to any substrate truth

**What Stage 22 does NOT activate:**
- Canonical graph mutation or permanent edge/region creation
- Support injection or energy modification
- Pearl creation or narration
- Feedback into Gate.step() dynamics
- Weighted clustering, fuzzy community detection, or probabilistic grouping
- Domain-level interpretation of proto-regions
- Irreversible region formation

**Stage 22 activates bounded non-canonical proto-topology shaping only. It does not yet
activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 23 (implemented): controlled canonical boundary introduction

New module: `invar/core/canonical_boundary.py` — `CanonicalBoundary` class and
`AdvisorySnapshot` dataclass.

Stage 23 introduces **canonical visibility** of proto-topology without canonical mutation.
Non-canonical proto-regions are projected into a deterministic advisory surface that
canonical-layer consumers may query.  The canonical boundary is a view, not a mutation.
Proto-topology remains non-canonical throughout.

**Key principle:**
```
Stage 23 introduces canonical visibility, not canonical mutation.
```

**Region labeling scheme:**
```
label(R) = min(R)    where R is a frozenset of str node-ids
```
The label is the lexicographically smallest node-id in each region.  This is deterministic
and stable as long as the minimum member of a region is unchanged.

**Core interface:**
```python
from invar.core.proto_topology import ProtoTopology
from invar.core.canonical_boundary import CanonicalBoundary, AdvisorySnapshot

proto = ProtoTopology()
proto.evaluate_edges(comms.edges())

boundary = CanonicalBoundary()
boundary.project(proto)           # read-only projection — proto is not modified

# Advisory queries (read-only; no canonical mutation):
boundary.region_of("gate_id")         # str label or None
boundary.same_region("g1", "g2")      # bool — symmetric
boundary.region_sizes()               # {label: int}
boundary.region_ids()                 # sorted list of labels
boundary.nodes_in_region("gate_id")   # frozenset or None
boundary.contains_node("gate_id")     # bool
boundary.region_count()               # int
boundary.node_count()                 # int
boundary.snapshot()                   # AdvisorySnapshot — immutable, decoupled

# Reset / rebuild (non-destructive to canonical state):
boundary.reset()
boundary.recompute(proto)
```

**`AdvisorySnapshot` (frozen dataclass):**
```python
@dataclass(frozen=True)
class AdvisorySnapshot:
    node_labels: frozenset       # frozenset of (node_id, label) pairs
    region_sizes: frozenset      # frozenset of (label, size) pairs
    region_members: frozenset    # frozenset of (label, frozenset) pairs

    def to_dicts(self) -> tuple  # unpack into three plain dicts for inspection
```
Snapshots are immutable and decoupled — subsequent boundary mutations do not affect them.

**Layered structure now complete through Stage 23:**
```
TopologyTrace           — per-pair accumulated coherence memory (Stage 15)
    ↓ normalized()
TopologyCandidates      — identified candidate pairs (Stage 17)
    ↓ contains() → i_ij
TopologyCommitments     — committed proto-topological pairs (Stage 19)
    ↓ edges()
ProtoTopology           — connected regional structure (Stage 22)
    ↓ regions()
CanonicalBoundary       — advisory canonical-facing projection (Stage 23)
```

**Safety properties:**
- `CanonicalBoundary` is standalone — not embedded in Gate, graph, or Pearl
- Canonical gate state (phi_R, phi_B, theta, a, mu, ...) is never read or modified
- Canonical graph weights and topology are never read or modified
- `project()` reads ProtoTopology read-only — proto-regions are not mutated
- Gate energy, p(), and collapse logic are unchanged
- Resetting or discarding a `CanonicalBoundary` object has zero substrate effect
- Projection is deterministic: same proto-topology → same advisory labels
- No Pearl is created or modified; no support is injected
- Gate.step() is NOT modified

**What Stage 23 activates only:**
- A standalone, bounded, reversible, advisory boundary surface
- Proto-regions are projected into deterministic region labels and pairwise queries
- The boundary is a query surface only — no write-back to any substrate truth

**What Stage 23 does NOT activate:**
- Canonical graph mutation or permanent edge formation
- Support injection or energy modification
- Pearl creation or narration
- Feedback into Gate.step() dynamics
- Region ids treated as authoritative topology
- Domain-level interpretation of regional structure
- Irreversible canonicalization

**Stage 23 activates bounded canonical-facing advisory projection only. It does not yet
activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 24 (implemented): controlled boundary influence

**Formula:**
```
B_ij ∈ {0, 1}  — same-region flag: float(boundary.same_region(i, j))
w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B)
```

Stage 24 extends `effective_weight()` with a canonical boundary influence term.  When a
gate pair `(i, j)` is projected into the same advisory proto-region by `CanonicalBoundary`,
the flag `B_ij = 1.0` weakly amplifies their effective interaction weight.  Pairs in
different regions or not projected receive `B_ij = 0.0` — no boundary effect.

The boundary signal is the **weakest** of all influence terms, strictly subordinate to
all others:

```
κ_B << κ_R < κ_K < κ_C < κ_τ
boundary < regulation < commitment < candidate < trace
```

**Caller pattern (Stage 24):**
```python
from invar.core.topology_trace import TopologyTrace, effective_weight, regulation_signal
from invar.core.topology_candidates import TopologyCandidates
from invar.core.topology_commitments import TopologyCommitments
from invar.core.proto_topology import ProtoTopology
from invar.core.canonical_boundary import CanonicalBoundary

trace = TopologyTrace(eta_tau=0.05, lambda_tau=0.1)
cands = TopologyCandidates(theta_e=0.4, theta_tau=0.4)
comms = TopologyCommitments(theta_e=0.65, theta_tau=0.65)
proto = ProtoTopology()
boundary = CanonicalBoundary()

# Per time step:
e_ij = emergence_weight(gate_i, gate_j, t)
trace.step(gate_i.gate_id, gate_j.gate_id, e_ij, dt)
tau_hat = trace.normalized(gate_i.gate_id, gate_j.gate_id)
cands.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat)
i_ij = float(cands.contains(gate_i.gate_id, gate_j.gate_id))
comms.evaluate(gate_i.gate_id, gate_j.gate_id, e_ij=e_ij, tau_hat=tau_hat, i_ij=i_ij)
k_ij = float(comms.contains(gate_i.gate_id, gate_j.gate_id))
proto.evaluate_edges(comms.edges())
boundary.project(proto)
b_ij = float(boundary.same_region(gate_i.gate_id, gate_j.gate_id))
r_lock = regulation_signal(k_ij, tau_hat)
w_eff = effective_weight(
    w_ij, e_ij, tau_hat,
    kappa_e=0.1, kappa_tau=0.05,
    i_ij=i_ij, kappa_candidate=0.02,
    k_ij=k_ij, kappa_commitment=0.005,
    r_ij_lock=r_lock, kappa_regulate=0.001,
    b_ij=b_ij, kappa_boundary=0.0005,
)
```

**Safety properties:**
- `kappa_boundary=0.0` (default) → Stage 23 behavior preserved bit-for-bit
- `b_ij ∈ {0.0, 1.0}` — binary, derived from advisory-only `same_region()` query
- `CanonicalBoundary` is not mutated by calling `effective_weight()`
- Multiplier remains clamped ≥ 0 — effective weight always non-negative for non-negative `w_ij`
- Gate.step() not modified; φ_R, φ_B, energy(), p() not touched
- No canonical graph mutation, no Pearl creation, no narration

**Layered structure now complete through Stage 24:**
```
TopologyTrace           — bounded historical coherence memory (Stage 15)
TopologyCandidates      — candidate pair surface (Stage 17)
TopologyCommitments     — committed pair surface (Stage 19)
ProtoTopology           — connected regional structure (Stage 22)
CanonicalBoundary       — advisory canonical-facing projection (Stage 23)
effective_weight()      — transient weight modifier (all stages; boundary term Stage 24)
```

**What Stage 24 activates only:**
- `b_ij` boundary flag from `CanonicalBoundary.same_region()` as a weak additive term in `effective_weight()`
- `kappa_boundary` coefficient controlling boundary influence strength

**What Stage 24 does NOT activate:**
- Canonical graph mutation of any kind
- Gate.step() changes
- Morphology, narration, or domain logic

**Stage 24 activates bounded canonical boundary influence on transient interaction weights only.
It does not activate permanent graph mutation, morphology, narration, or domain logic.**

### Stage 25 (implemented): final saturation control / global safety envelope

**Formula:**
```
excess_ij = max(0, M_raw − 1)   where:
  M_raw = 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B

M_sat = M_raw                                     if excess_ij = 0  (M_raw ≤ 1)
M_sat = 1 + excess_ij / (1 + σ · excess_ij)      if excess_ij > 0  (M_raw > 1)

w_ij_eff = w_ij · max(0, M_sat)
```

Stage 25 is the final Layer 0 control pass. It does not introduce new structure. It adds a
bounded algebraic compression of the aggregate reinforcement above unity, preventing the field
from drifting toward over-stiffness as multiple individually-safe signals accumulate over long
runs.

When M_raw ≤ 1 (net attenuation or no reinforcement), the saturation path is skipped entirely
— M_sat = M_raw passes through unchanged. Saturation only compresses the excess reinforcement
above unity.

**Why this formula:**
```
excess → excess / (1 + σ·excess)
```
This is a saturating response function. Its key properties:
- Monotone for all σ ≥ 0: dM_sat/d(excess) = 1/(1+σ·excess)² > 0 always
- Identity at σ=0: M_sat = 1 + excess = M_raw → Stage 24 preserved bit-for-bit
- Always above unity for M_raw > 1 and finite σ → topology influence never nullified
- Asymptote: M_sat → 1 from above as σ → ∞ → bounded from below at identity multiplier
- Smooth: continuous and differentiable at all M_raw

**Caller pattern (Stage 25):**
```python
w_eff = effective_weight(
    w_ij, e_ij, tau_hat,
    kappa_e=0.1, kappa_tau=0.05,
    i_ij=i_ij, kappa_candidate=0.02,
    k_ij=k_ij, kappa_commitment=0.005,
    r_ij_lock=r_lock, kappa_regulate=0.001,
    b_ij=b_ij, kappa_boundary=0.0005,
    sigma_saturate=0.5,   # NEW Stage 25; 0.0 → Stage 24 exactly
)
```

**Safety properties:**
- `sigma_saturate=0.0` (default) → Stage 24 behavior preserved bit-for-bit
- No new state variable, memory layer, or graph structure introduced
- No write-back to Gate state, canonical graph, or any topology structure
- Multiplier remains clamped ≥ 0 — effective weight always non-negative for non-negative `w_ij`
- Gate.step() not modified; φ_R, φ_B, energy(), p() not touched
- No canonical graph mutation, no Pearl creation, no narration
- Signal ordering κ_B << κ_R < κ_K < κ_C < κ_τ is preserved — saturation compresses the aggregate, not the ordering

**What Stage 25 is:**
Bounded long-run reinforcement safety. The field can remain adaptive indefinitely without
letting accumulated structure harden into rigidity.

**What Stage 25 is NOT:**
Removal of topology influence. Pairs with stronger combined reinforcement remain relatively
stronger after saturation (monotonicity guaranteed). Saturation compresses reinforcement; it
does not remove the meaning of topology.

**Layered structure now complete through Stage 25:**
```
TopologyTrace           — bounded historical coherence memory (Stage 15)
TopologyCandidates      — candidate pair surface (Stage 17)
TopologyCommitments     — committed pair surface (Stage 19)
ProtoTopology           — connected regional structure (Stage 22)
CanonicalBoundary       — advisory canonical-facing projection (Stage 23)
effective_weight()      — transient weight modifier with global safety envelope (Stages 16–25)
```

**What Stage 25 activates only:**
- `sigma_saturate` coefficient controlling saturation compression of aggregate reinforcement above unity
- Algebraic bounded compression path in `effective_weight()` — no new objects or memory

**What Stage 25 does NOT activate:**
- New state variable, new graph structure, new memory layer
- Canonical graph mutation of any kind
- Gate.step() changes
- Morphology, narration, or domain logic
- Irreversible weakening of topology influence

**Stage 25 activates bounded global saturation control only. It does not yet activate
permanent graph mutation, morphology, narration, or domain logic.**

Stage 25 introduces global reinforcement safety, not removal of topology influence.

---

## 6. Oscillatory Functional (Stage 4)

### Oscillation cost (implemented)
```
E_osc = Σg (λ_a·ag² + λ_ω·ωg² + λ_μ·μg²)
```

### Resonant persistence reward (implemented, Π_i stub = 1.0)
```
P_res = Σᵢ |Ψᵢ| · Πᵢ
```

### Extended functional (implemented as new functions, not replacing L)
```
L* = L + E_osc − P_res
```

`local_L` and `global_L` are unchanged. `local_L_star` / `global_L_star`
are new functions available alongside them.

---

## 7. O-Invariant Family

| ID | Name | Status | Statement |
|----|------|--------|-----------|
| O1 | Bounded amplitude | **Live (Stage 7)** | ag converges to α·H/ξ; bounded for xi > 0 |
| O2 | No energy creation | Active | L* ≥ 0; energy accounted for |
| O3 | Phase continuity | **Live (Stage 5)** | `theta` evolves continuously via `step()` and feeds into `weighted_phase()` |
| O4 | Contradiction memory bounded | **Live (Stage 6)** | μg decays to 0 without input; bounded under constant drive |
| O5 | Persistence allowed | Active | step() never triggers collapse |
| O6 | Coarse-grain stability | Active | coherence bound holds at cluster level |

Verified by `tests/test_layer0_o_invariants.py`.

---

## 8. Staged Activation Status

| Stage | Content | Status |
|-------|---------|--------|
| Stage 1 | Dormant fields added to Gate | ✅ Complete |
| Stage 2 | `step()` evolves theta | ✅ Complete |
| Stage 3 | `weighted_phase()` uses amplitude `a` | ✅ Complete |
| Stage 4 | `e_osc`, `p_res`, `local_L_star`, `global_L_star` | ✅ Complete |
| Stage 5 | Dynamic theta feeds into `weighted_phase()` live path | ✅ Complete |
| Stage 6 | Bounded μ evolution: `mu += dt*(c_in − λ_μ·mu)` | ✅ Complete |
| Stage 7 | Bounded amplitude evolution: `a += dt*(α·H − ξ·a)` when alpha > 0 | ✅ Complete |
| Stage 8 | Local μ→a coupling: `a += dt*(α·H + β·μ − ξ·a)` when alpha > 0 | ✅ Complete |
| Stage 9 | Cross-gate contradiction coupling: `mu += dt*(c_in + γ·C_i − λ_μ·mu)`; `contradiction_signal()` | ✅ Complete |
| Stage 10 | Bounded resonance coupling: `theta += dt*(…+ρ·R_i)`; `resonance_signal()` using anchor θ⁽⁰⁾ | ✅ Complete |
| Stage 11 | Bounded persistence reward: `ξ_eff = ξ/(1+ε_p·P_i)` when alpha > 0; P_i = min(1,a·H) | ✅ Complete |
| Stage 12 | Controlled topology emergence: `w_ij_eff = w_ij(1+κ·E_ij)`; `emergence_weight()` read-only | ✅ Complete |
| Stage 13 | Controlled feedback coupling: `ρ_eff = ρ(1+δ·Ē_i)`; `local_emergence_summary()` | ✅ Complete |
| Stage 14 | Controlled stabilization: `ω_eff = ω/(1+ζ·Ē_i)`; reuses `e_bar`; `zeta_stabilize` field | ✅ Complete |
| Stage 15 | Controlled topology persistence: `TopologyTrace` class; `τ_ij` non-canonical decay-bounded trace | ✅ Complete |
| Stage 16 | Controlled trace influence: `w_ij_eff = w_ij(1+κ_E·E_ij+κ_τ·τ̂_ij)`; `normalized()` + `effective_weight()` | ✅ Complete |
| Stage 17 | Controlled topology consolidation: `TopologyCandidates`; `(i,j)∈C ⟺ E≥θ_E ∧ τ̂≥θ_τ`; non-canonical candidate surface | ✅ Complete |
| Stage 18 | Controlled candidate influence: `w_ij_eff = w_ij(1+κ_E·E+κ_τ·τ̂+κ_C·I)`; binary `i_ij` flag + `kappa_candidate` in `effective_weight()` | ✅ Complete |
| Stage 19 | Controlled topology commitment: `TopologyCommitments`; `(i,j)∈K ⟺ E≥θ_E ∧ τ̂≥θ_τ ∧ I=1`; stricter thresholds; non-canonical proto-topology | ✅ Complete |
| Stage 20 | Controlled commitment influence: `w_ij_eff = w_ij(1+κ_E·E+κ_τ·τ̂+κ_C·I+κ_K·K)`; binary `k_ij` flag + `kappa_commitment` in `effective_weight()`; κ_K << κ_C << κ_τ | ✅ Complete |
| Stage 21 | Controlled stabilization regulation: `R_lock = K_ij·τ̂_ij`; `w_ij_eff = w_ij·max(0,1+…−κ_R·R_lock)`; `regulation_signal()` helper; κ_R < κ_K; multiplier clamped ≥ 0 | ✅ Complete |
| Stage 22 | Controlled proto-topology shaping: `ProtoTopology` class; committed edges → BFS connected components → proto-regions (|region|≥2); non-canonical, reversible, deterministic | ✅ Complete |
| Stage 23 | Controlled canonical boundary introduction: `CanonicalBoundary` + `AdvisorySnapshot`; proto-regions → advisory labels (label=min(R)); `region_of()`, `same_region()`, `region_sizes()`, immutable snapshot; visibility only, no mutation | ✅ Complete |
| Stage 24 | Controlled boundary influence: `B_ij = float(boundary.same_region(i,j))`; `w_ij_eff = w_ij·max(0,1+…+κ_B·B)`; `b_ij` + `kappa_boundary` in `effective_weight()`; κ_B << κ_R; weakest signal, context only | ✅ Complete |
| Stage 25 | Final saturation control: `excess=max(0,M_raw−1)`; `M_sat=1+excess/(1+σ·excess)` for excess>0; `sigma_saturate` in `effective_weight()`; monotone, bounded, dormant at σ=0; global reinforcement safety, not topology removal | ✅ Complete |
| L1-1 | Pearl canonical integration: `PearlArchive`; append-only, monotone seq_id enforcement; `replay_into()` / `restore_into()` via `Gate._restore_from_pearl_snapshot()`; no narration, no topology; `invar/persistence/pearl_archive.py` | ✅ Complete |
| L1-2 | Temporal consistency graph: `TemporalGraph`; sorted linear chain of Pearls; `next()`/`prev()`/`path()`/`validate()`/`replay()`; no-gap/no-cycle/no-duplicate invariants; non-canonical read-only overlay; `invar/persistence/temporal_graph.py` | ✅ Complete |
| L1-3 | Execution windows: `ExecutionWindows`; cycle_id-based Pearl grouping; window ordering by min seq_id; `of()`/`get()`/`next_window()`/`prev_window()`/`range()`/`validate()`/`replay()`; non-canonical, reversible, zero substrate effect; `invar/persistence/execution_window.py` | ✅ Complete |
| L1-4 | Proto-causality: `ProtoCausality`; cross-window structural continuity via shared gate identity triples; `links()`/`links_from()`/`links_to()`/`shared_gates()`; ordered (earlier,later) pairs; non-canonical, deterministic, no Layer 0 effect; `invar/persistence/proto_causality.py` | ✅ Complete |
| L1-5 | Causal weighting: `weight(a,b)=|shared|/min(|A|,|B|)` ∈ [0,1]; `weighted_links()` → (a,b,weight) triples; symmetric weight, ordered links; extends `ProtoCausality`; deterministic, bounded, non-canonical; continuity strength, not causation | ✅ Complete |
| L1-6 | Causal propagation field: `CausalField`; `raw(W)=Σweight(A→W)`, normalized to [0,1] by max raw; `value(cycle_id)` → normalized influence; `all()` → full map; head windows always 0.0; non-canonical, deterministic, zero substrate effect; `invar/persistence/causal_field.py` | ✅ Complete |
| L1-7 | Red team adapter: `RedTeamObserver`; read-only mapping Invar → operation observables; `activity()`, `shared_infra()`, `strong_links(threshold)`, `summary()`, `cycle_ids`; derives all outputs from five Invar objects; stores nothing new; deterministic, non-canonical, zero mutation; `invar/adapters/redteam/observer.py` | ✅ Complete |
| L2-1 | Controlled feedback interface: `Suggestion` frozen dataclass (id, type, cycle_id, supporting_cycles, supporting_artifacts, confidence); `FeedbackEngine` derives "reuse" / "high_activity" / "anomaly" / "chain" suggestions from `RedTeamObserver` signals; evidence-only, no narration, no execution; deterministic IDs (SHA-256 of sorted evidence); `suggestions()` / `by_type()` / `by_cycle()` / `with_ack()`; sorted by confidence desc; `invar/adapters/redteam/feedback.py` | ✅ Complete |
| L2-2 | Operator acknowledgment layer: `Acknowledgment` frozen dataclass (suggestion_id, decision, ts); `AcknowledgmentStore` append-only audit log; decisions: "valid"/"irrelevant"/"investigate"; `record()` / `get()` / `all()` / `by_decision()`; no overwrite, no deletion, no narration; `FeedbackEngine.with_ack(store)` read-only join; zero Layer 0 effect; `invar/adapters/redteam/acknowledgment.py` | ✅ Complete |
| L2-3 | Operator workflow view: `WorkflowView(engine, store)` derives workflow states on demand from `FeedbackEngine` + `AcknowledgmentStore`; states: "open" / "reviewed-valid" / "reviewed-irrelevant" / "needs-investigation"; `items()` → all as workflow dicts; `by_state(state)` → filtered; `queue()` → priority order (needs-investigation → open → reviewed-valid → reviewed-irrelevant, then confidence desc, then suggestion_id); `counts()` → {state: count} all four states always present; no new canonical state, no mutation, no side-effects; deterministic and discardable; `invar/adapters/redteam/workflow.py` | ✅ Complete |
| L2-4 | Design-only controlled action interface: `ProposedAction` frozen dataclass (proposal_id, suggestion_id, action_type, target, parameters, confidence); `ActionProposalEngine(engine, store)` derives proposals only for suggestions acknowledged as "valid" or "investigate"; action types: "examine_reuse" / "examine_high_activity" / "examine_anomaly" / "trace_chain"; `proposals()` / `for_suggestion(sid)` / `by_type(atype)`; deterministic proposal_id (SHA-256 of suggestion_id + action_type); confidence inherited; no execution, no triggering, no automation; operator decides and acts externally; `invar/adapters/redteam/action_proposal.py` | ✅ Complete |
| L2-5 | Red team domain concretization: `ArtifactType` and `OperationPrimitive` adapter-local constants (never written to Pearl); `RedTeamDomainModel(observer, engine, store, workflow, action_engine)`; `artifact_type(gate_key)` → first-match substring classification of gate_id (case-insensitive, 7 types + UNKNOWN); `cycle_primitive(cycle_id)` → derived from distinct non-UNKNOWN artifact types (UNCLASSIFIED / single-type primitive / MULTI_STAGE); `cycle_artifacts(cycle_id)` → annotated gate inventory; `operational_summary(cycle_id)` → primitive + activity + artifact_count + artifact_types + link counts + workflow_state_counts; `lab_queue()` → workflow-ordered items enriched with action_type, proposal_id, primitive; domain labels are adapter-local only; no Layer 0 effect; no mutation; deterministic; `invar/adapters/redteam/domain_model.py` | ✅ Complete |
| L2-6 | Red team relationship graph: `CycleRelationship` frozen dataclass (from/to cycle, from/to primitive, relationship_type, transition_label, weight, shared_gate_count); `PatternMatch` frozen dataclass (pattern_name, cycle_path, primitives, avg_weight); `RelationshipGraph(observer, domain_model)`; relationship types: "continuation" / "stage_transition" / "unclassified"; 10 labeled stage transitions (credential_to_lateral, lateral_to_execution, etc.); 5 named attack patterns (credential_lateral_exec, discovery_lateral_exec, exec_persist_c2, cred_exec_collect, collect_to_c2); `cycle_relationships()` / `relationships_from()` / `relationships_to()` / `pattern_matches()` / `pivot_cycles()` / `artifact_reuse_map()`; DFS pattern matching with frozenset visited tracking; all adapter-local, no Layer 0 effect, deterministic; `invar/adapters/redteam/relationship_graph.py` | ✅ Complete |
| L2-7 | Windows/Sysmon ingest adapter: `SysmonEvent` dataclass with property accessors (image_basename, dest_port, target_image_basename, target_object, target_filename, image_loaded_basename); namespace-aware XML helpers (_find/_findall); `parse_sysmon_event(elem)` / `parse_events_xml(xml_str)` handle both single `<Event>` and `<Events>` containers, bare and namespace-qualified tags; `map_event_to_gate_id(event)` dispatches by event_id (EID 1/4688→process, 3→network, 7→image load, 8/10→process access, 11→file, 12/13→registry, 4698→persist_schtask, 4624→lateral_logon); rule-aligned gate_id naming compatible with L2-5 classification (exec_*, cred_*, lateral_*, discover_*, persist_*, collect_*, c2_*); `CycleDiscovery(gap_threshold=300.0, shift_window=5)` autonomous three-tier boundary detection: operator override > time-gap > conservative primitive-shift (requires stable run of ≥shift_window non-UNKNOWN events); cycle names: `auto_{idx:03d}_{label}`; `WindowsIngestAdapter(workload_id, node_key, gap_threshold, shift_window)` with `ingest_sysmon_xml()` / `ingest_event_log_xml()` / `pearls()` / `snapshot()`; Pearls constructed directly (phi_R=1.0, H=1.0, state U→R), bypassing SupportEngine.ingest(); discovers not is told; no Layer 0 effect, no host execution, deterministic; `invar/adapters/redteam/windows_ingest.py` | ✅ Complete |

---

## 9. What Is Explicitly Deferred

- Matrix-valued Unknown
- Complex-valued coupling
- Morphology as Layer 0 primitive
- Dynamic-theta-based resonance (feedback loop prevention — anchor used instead)
- Cross-gate persistence coupling (persistence is local-only; no neighbor reads)
- Topology mutation
- Morphology as Layer 0 primitive
- Narration of any kind

**Pearl contains no narration.** Narration exists only at the adapter/domain layer.

---

## 10. Domain Adapter Architecture Note

Domain adapters may build domain-specific interpretation and control layers above Invar,
but may **not** replace or fork Layer 0 truth semantics.

A domain adapter is subordinate to core Invar, not a peer substrate. It should preserve:

- observation discipline (truth enters only via support accumulation)
- constraint-first flow (unknowns before resolution)
- explicit unknowns (no hidden state)
- no narration in canonical state (Pearl is narration-free)
- bounded interpretation surfaces

Breakage at the domain layer must not propagate into Layer 0 physics. The substrate is the
single canonical truth engine; adapters interpret and extend it, not replace it.

---

## 10. Pearl Boundary

Pearl stores **no narration**. Narration is generated only at the adapter/domain layer,
and may be further shaped by context.

The pipeline remains:
```
Layer 0 substrate
→ Pearl structural artifact
→ adapter/domain/context
→ narration
→ operator
```
