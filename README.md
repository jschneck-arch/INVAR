# INVAR — Invariant Architecture Runtime

Domain-agnostic telemetry substrate with information-theoretic physics.

## Structure

```
invar/core/          — Layer 0: gate physics, support engine, gravity, topology
invar/persistence/   — PearlArchive, ProtoCausality, CausalField
invar/adapters/      — Domain adapter layer (read-only over core)
  redteam/           — Red team domain: observer, feedback, workflow, domain model,
                       relationship graph, Windows/Sysmon ingest
docs/                — Canonical contracts and behavior atlas
tests/               — Core invariant tests + L2 adapter tests
```

## Layer rules

- **Layer 0 (`invar/core/`)**: stdlib only, no domain knowledge, no mutable global state.
- **Adapters**: derive and interpret; never write back to core canonical state.
- **Tests**: deterministic, in-memory, no network.

## Running tests

```bash
python3 -m pytest tests/ -q
```

## Docs

- `docs/INVAR_CORE_CONTRACT.md` — canonical physics equations and invariant list
- `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md` — oscillation extension and L2 stage log
- `docs/INVAR_BEHAVIOR_ATLAS.md` — observed behavioral regimes
- `docs/INVAR_REPO_BLUEPRINT.md` — directory structure and layer rules
