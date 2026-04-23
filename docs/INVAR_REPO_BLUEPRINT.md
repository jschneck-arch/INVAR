# INVAR Repository Blueprint

**Project:** INVAR — Invariant Architecture Runtime  
**Version:** 1.0 (v1 freeze pending federation experiments)

---

## Guiding Principle

The repository is organized by **invariant distance from core**, not by feature or domain. Code that is closer to the core has fewer dependencies and stronger invariant requirements. Code farther from the core has more dependencies and weaker invariant requirements — but can never write back through an unauthorized path.

---

## Canonical Directory Structure

```
/opt/invar/                         ← project root (rename from /opt/skg/)
│
├── AGENTS.md                       ← agent rules (this file's context)
├── README.md                       ← project overview (to be rewritten)
│
├── invar/                          ← INVAR core (rename from skg/)
│   └── core/                       ← THE SUBSTRATE — frozen at v1
│       ├── envelope.py             ← boundary interface
│       ├── gate.py                 ← gate physics
│       ├── support_engine.py       ← write path, Pearl emission
│       ├── gravity.py              ← scheduler, Ψᵢ, T_eff
│       ├── field.py                ← coupling field, Hebbian
│       ├── topology.py             ← β₁, holonomy, cycles
│       ├── functional.py           ← L, ΔL, global_L
│       ├── narrative.py            ← NarrativeState, W_t(g)
│       ├── observation.py          ← J(Ω), greedy_min_J
│       └── coarse_grain.py         ← coarse-graining, federation
│
├── tests/                          ← core invariant tests
│   ├── test_core_physics.py        ← 25 tests (gate, gravity, pearl)
│   ├── test_core_invariants.py     ← 35 tests ([H],[C],[S],[A],[T],[G],[B],[N],[CG])
│   └── test_core_stress.py         ← 41 tests (long runs, fuzz, federation)
│
├── demos/                          ← deterministic demos (regression checks)
│   └── invar_core_demo.py          ← 4-manifestation demo (rename from skg_core_demo.py)
│
├── docs/                           ← frozen documentation
│   ├── INVAR_CORE_CONTRACT.md      ← canonical equations, invariants, scope boundary
│   ├── INVAR_BEHAVIOR_ATLAS.md     ← observed behavioral regimes
│   ├── INVAR_REPO_BLUEPRINT.md     ← this file
│   └── papers/                     ← theoretical foundations (Work 5, Work 6)
│
└── adapters/                       ← domain adapters (NEVER imports from other adapters)
    ├── redteam/                    ← nmap, vuln scanner → ObsGateEnvelope
    │   ├── nmap_adapter.py
    │   ├── nvd_adapter.py
    │   └── tests/
    ├── ai/                         ← LLM output → NarrativeState intent weights
    │   ├── llm_adapter.py
    │   └── tests/
    ├── analysis/                   ← L, r, β₁ → external reporting
    │   ├── metrics_adapter.py
    │   └── tests/
    └── federation/                 ← multi-core coordination (Phase 4)
        ├── harness.py              ← runs N independent cores
        ├── sync.py                 ← shared evidence stream injection
        └── tests/
```

---

## Current State vs Blueprint

| Blueprint Path | Current Path | Status |
|----------------|-------------|--------|
| `invar/core/` | `skg/core/` | Rename pending (code frozen, stable) |
| `AGENTS.md` | `AGENTS.md` | Created |
| `docs/INVAR_CORE_CONTRACT.md` | `docs/SKG_CORE_CONTRACT.md` | Rename pending |
| `docs/INVAR_BEHAVIOR_ATLAS.md` | `docs/INVAR_BEHAVIOR_ATLAS.md` | Created |
| `demos/invar_core_demo.py` | `demos/skg_core_demo.py` | Rename pending |
| `adapters/` | Various `skg-*-toolchain/` dirs | Reorganization pending |
| `adapters/federation/` | — | Not yet built |

The Python package rename (`skg` → `invar`) is a mechanical operation. Do it in one atomic commit with a full test run. Do not do it incrementally.

---

## Layer Rules

### Layer 0: Core (`invar/core/`)

- **No external imports** — stdlib only
- **No domain knowledge** — CVE, AD, nginx, nmap are words that must not appear in core modules
- **No mutable global state** — all state via SupportEngine
- **Invariant test required** — any change must add or update a test in `tests/test_core_*.py`
- **Change requires contract update** — any physics change → update `docs/INVAR_CORE_CONTRACT.md` Section 5

### Layer 1: Tests (`tests/`)

- **Tests core only** — no adapter logic in core tests
- **No network, no filesystem** — core tests are pure in-memory
- **Deterministic seeds** — random tests use fixed seeds, parametrized over small seed sets
- **101 tests total must pass** at all times

### Layer 2: Adapters (`adapters/*/`)

- **One direction only** — adapters write `ObsGateEnvelope` and read `DispatchEnvelope`; they never modify gate state
- **No cross-adapter imports** — `adapters/redteam/` never imports from `adapters/ai/`
- **Own test suite** — each adapter has its own `tests/` directory
- **May have external dependencies** — nmap, requests, ollama, etc. are fine here
- **May have domain language** — CVE, vulnerability, lateral movement are adapter-layer words

### Layer 3: Federation (`adapters/federation/`)

- **Multi-core orchestration only** — creates N independent `SupportEngine` + `GravityField` instances
- **Coarse-graining via core** — uses `CoarseGraining` from `invar/core/coarse_grain.py`
- **Controlled overlap** — experiments use explicit shared evidence injection, not implicit state sharing
- **Tests must cover the 3 federation conditions** from the behavior atlas: synchronization, isolation, partial alignment

---

## Adapter Contract

Every adapter must implement this interface (informal protocol):

```python
class InvarAdapter:
    """
    Minimal contract for an INVAR adapter.
    
    Adapters translate between domain events and INVAR core primitives.
    They never touch core internals.
    """
    
    def observe(self, domain_event) -> List[ObsGateEnvelope]:
        """
        Translate a domain event into one or more ObsGateEnvelope objects.
        The adapter decides workload_id, node_key, gate_id, and phi values.
        The core decides what to do with them.
        """
        ...
    
    def dispatch(self, envelope: DispatchEnvelope) -> None:
        """
        Receive instrument targets from core gravity dispatch.
        Adapter decides how to act (schedule scan, query LLM, etc.).
        Core decides which targets to prioritize.
        """
        ...
```

The adapter is responsible for everything outside the envelope. The core is responsible for everything inside.

---

## What Does NOT Belong in the Repo

| Category | Where it belongs | Not in the repo because |
|----------|-----------------|------------------------|
| Trained models / weights | External storage | Core has no training loop |
| Database schemas | External service | Core has no storage layer |
| Network topology maps | Domain data, not code | Core is topology-agnostic |
| CVE databases | NVD adapter, not core | Domain knowledge is adapter-layer |
| LLM prompts | AI adapter | Reasoning is not core physics |
| Dashboard config | Analysis adapter | Display is not core physics |
| Scan results | Evidence store, not repo | Raw data ≠ code |

---

## v1 Freeze Checklist

Before tagging `invar-v1.0`:

- [ ] All 101 core tests pass
- [ ] Demo runs without errors
- [ ] `docs/INVAR_CORE_CONTRACT.md` version bumped to 1.0
- [ ] `docs/INVAR_BEHAVIOR_ATLAS.md` documents all 8 regimes
- [ ] `AGENTS.md` reflects current naming and scope
- [ ] Federation harness: 2+ cores, 3 overlap conditions tested
- [ ] Package rename `skg/` → `invar/` complete with full test run
- [ ] `git tag invar-v1.0` on main branch

After the tag:
- Core changes require a new tag
- Any invariant change requires updating `docs/INVAR_CORE_CONTRACT.md`
- Adapters can release independently without touching the tag

---

## Anti-Patterns to Prevent

These patterns have historically caused scope contamination in complex systems. INVAR is specifically designed to resist them, but only if the blueprint is enforced.

**1. Protocol stack creep** — adding layers between core and adapters "for convenience." Every intermediate layer is a future scope breach.

**2. Shared state through side channels** — adapters communicating by writing to a shared database instead of through the core. Bypasses all invariant guarantees.

**3. Domain logic migration** — moving domain knowledge into core "because it's used everywhere." The correct answer is a shared adapter utility, not core pollution.

**4. Naming erosion** — gradually reverting to "node," "edge," "graph," "SKG" in internal discussions. Naming drift precedes design drift.

**5. Invariant exemptions** — "this one case doesn't need the invariant." There are no exemptions. If the invariant is wrong, update it and all tests explicitly.
