# INVAR Layer 2 Constraint Enforcement Contract

**Version:** 1.1
**Status:** Canonical — defines enforcement boundaries above Layer 0 substrate and Layer 1 representation
**Authority order:** INVAR_STACK_BUILD_ORDER.md > INVAR_CORE_CONTRACT.md > INVAR_STATE_REPRESENTATION_CONTRACT.md > this file > INVAR_EXECUTION_TEMPORAL_CONTRACT.md

**Changelog:**
- v1.1 (2026-04-17): ET-G6 enforcement added. §9.5 (sequencer write boundary) added.
  `_SEQUENCER_WRITE_TOKEN` is the authorized write capability. Direct
  `SupportEngine.ingest()` calls without the token are tracked via `_bypass_count`.
  Ordering Concept note added to §3.
- v1.0 (2026-04-16): Initial Layer 2 enforcement contract.

---

## 1. Purpose

Layer 0 defines physics. Layer 1 defines representation. Layer 2 defines enforcement:

- What may write canonical state
- What replay means and where it ends
- What paths must never become canonical writes
- What provenance a canonical write must carry
- What non-authoritative surfaces exist and how they are bounded

These definitions make the representation contract from Layer 1 enforceable at runtime.
Without Layer 2, the representation distinctions are documentation. With Layer 2, they are
executable boundaries.

---

## 2. System Architecture Summary (Enforcement View)

The system currently contains two distinct computation paths. Both are legitimate. They must
not be conflated.

### 2.1 Core Write Path (canonical)

```
ObsGateEnvelope
    → SupportEngine.ingest()         [invar/core/support_engine.py]
    → Gate store update (φ_R, φ_B)
    → Pearl emission                  [invar/core/support_engine.Pearl]
    → Listener notification
```

This is the **only path that produces substrate truth**. It is the canonical write path.
Everything downstream is derived.

### 2.2 Kernel Projection Path (non-canonical)

```
NDJSON event files (observations)
    → load_observations_for_node()   [invar/kernel/adapters.py]
    → kernel.SupportEngine.aggregate()  [invar/kernel/support.py]
    → SupportContribution (realized, blocked, unresolved)
    → kernel.StateEngine.collapse()  [invar/kernel/state.py]
    → TriState per wicket
    → EnergyEngine / GravityScheduler
```

This path **never writes to the core gate store**. It reads from stored observation events,
aggregates them in memory, and produces projection state. It is a **query/projection path**.

The kernel `SupportEngine` in `invar/kernel/support.py` is a **different object** from the
core `SupportEngine` in `invar/core/support_engine.py`. They share a name but have different
interfaces, different semantics, and different authority:

| | Core SupportEngine | Kernel SupportEngine |
|-|-------------------|---------------------|
| Location | `invar/core/support_engine.py` | `invar/kernel/support.py` |
| Input | `ObsGateEnvelope` | `Iterable[Observation]` |
| Output | `List[Pearl]` (canonical) | `SupportContribution` (projection) |
| Writes to substrate | Yes — the only path | No — never |
| Authority | Canonical | None |

**Representation invariant (EE-1):** `SupportContribution` objects from the kernel path are
projections. They must not be passed to `core.SupportEngine.ingest()` as if they were
observations.

---

## 3. Canonical Write Authority

**Only the following may trigger a canonical substrate write:**

1. `invar/core/support_engine.SupportEngine.ingest(ObsGateEnvelope)` — the only authorized
   entry point.
2. The `ObsGateEnvelope` must be constructed from an instrument observation (sensor output,
   adapter translation, or operator-constructed test fixture). It must not be constructed
   by back-computing from projection outputs (`SupportContribution`, `TriState`, `Ψᵢ`, `L`).

**Unauthorized canonical write surfaces (must be blocked):**

| Surface | Reason |
|---------|--------|
| Kernel `SupportContribution` → `ingest()` | Projection back-fed as truth |
| Kernel `TriState` → `ingest()` | Collapsed projection back-fed as truth |
| Graph `WicketPrior` → `ingest()` | Materialized view back-fed as truth |
| `GravityStateDB` row → `ingest()` | Display state back-fed as truth |
| Replay output → `ingest()` (see §4) | Replay-generated truth |
| AI/assistant output → `ingest()` directly | Non-authoritative surface writing truth |

**The `ObsGateEnvelope` interface is the write boundary.** Nothing may cross it except
instrument observations with provenance (instrument_id, timestamp, decay_class).

**Ordering note (ET-G6/ET-G2):**
The sequencer enforces the operational order in which admitted envelopes reach canonical
ingest. This ordering is deterministic and reproducible. It is NOT a causal ordering,
NOT an epistemic priority claim, and NOT a projection of graph truth. Two observations
ordered A before B via `submit_batch()` means only: A is processed first operationally.
It does not mean A happened first in the world. See INVAR_EXECUTION_TEMPORAL_CONTRACT.md §4.6.

---

## 4. Replay Boundary

### 4.1 What replay is

Replay is the process of loading stored observation events and projecting them through the
kernel computation path to produce a query-time state view. It is a **read/projection
operation**, not a substrate reconstruction operation.

The current implementation in `invar/cli/commands/replay.py` does this correctly: it loads
NDJSON events, passes them through `kernel.SupportEngine.aggregate()`, and produces a
`SupportContribution` / `TriState` view. It does not call `core.SupportEngine.ingest()`.

### 4.2 What replay is not

Replay is NOT:
- Substrate reconstruction (the core gate store is not rebuilt from replay)
- Truth generation (replay output is a projection, not canonical state)
- Evidence synthesis (replay may not infer observations not present in the stored events)
- A backdated ingest path (replaying old events does not create new canonical Pearls)

### 4.3 Replay invariant

**Representation invariant (EE-2):** Replay output (kernel `SupportContribution`,
`TriState`, projected `Ψ`) must not be fed back into `core.SupportEngine.ingest()`.
Doing so would create new canonical Pearls from projection outputs — this is
truth generation from projection, which is forbidden.

### 4.4 Canonical substrate reconstruction (not yet implemented)

Canonical substrate reconstruction — rebuilding the core gate store from a canonical Pearl
archive — is distinct from the kernel projection path. It would require:

1. A canonical Pearl archive (append-only log of `invar/core/support_engine.Pearl` records)
2. A replay-from-pearls path that reconstructs `ObsGateEnvelope` instances from Pearl
   records and re-ingests them into a fresh `core.SupportEngine`

This path does not currently exist (see §10, Gap EE-G3). Until it is implemented, "replay"
refers exclusively to the kernel projection path.

---

## 5. Persistence Guarantees

### 5.1 What persistence means in this system

There are two persistence surfaces, with different authority:

| Surface | Location | What it persists | Authority |
|---------|----------|-----------------|-----------|
| Canonical Pearl persistence | Not yet implemented (Gap EE-G3) | `invar/core/support_engine.Pearl` records | Historical canonical archive |
| Kernel bundle persistence | `invar/kernel/pearls.PearlLedger` | `invar/kernel/pearls.Pearl` bundles (cycle snapshots) | Non-canonical; gravity loop history |
| Display/ops persistence | `invar/core/state_db.GravityStateDB` | Credentials, pivot targets, instrument run logs | Non-canonical; operational display |

**None of the currently implemented persistence surfaces is a canonical substrate backup.**
The canonical gate store (`core.SupportEngine` in-memory state) is the only substrate truth,
and it is currently not durably persisted between restarts.

### 5.2 Persistence rules

- **Kernel bundle persistence** (`PearlLedger`) records gravity cycle history. It is not a
  substrate backup. Reloading it does not restore core gate state.
- **Display persistence** (`GravityStateDB`) records operational data (credentials, pivots,
  instrument runs). It is not a substrate backup. Its contents must not be used to construct
  `ObsGateEnvelope` instances that are ingested as truth.
- **Canonical Pearl persistence** (not yet implemented) would persist `core.Pearl` records
  for substrate reconstruction. When implemented, it must guarantee:
  - append-only
  - each record attributable to an instrument observation
  - no synthesized records
  - no projection-back-computed records

### 5.3 Restart behavior (current)

On restart, the core gate store is empty. State is rebuilt by re-running the instrument
discovery + gravity cycle, not by replaying persisted state. This is correct behavior until
canonical Pearl persistence (§5.1, Gap EE-G3) is implemented.

---

## 6. Commit/Validation Sequence

The canonical sequence for a valid observation-to-substrate write is:

```
1. Instrument produces raw output (nmap XML, scan JSON, etc.)
2. Adapter translates to ObsGateEnvelope:
      instrument_id, workload_id, node_key, gate_id, phi_R, phi_B, decay_class
3. SupportEngine.ingest(envelope) called
4. Gate store updated (φ_R, φ_B incremented, GateState evaluated)
5. Pearl emitted for each entropy-changing gate
6. Listeners notified (gravity loop, narrative engine, etc.)
7. Kernel projection path runs (separate, non-writing):
      aggregate() → SupportContribution → StateEngine.collapse() → TriState
8. Display state written to GravityStateDB (non-canonical, display only)
```

**Truth must not flow backward.** Steps 7–8 must not feed back into steps 2–6.

---

## 7. Non-Authoritative Surfaces

The following surfaces exist in the runtime. None may write canonical substrate state:

| Surface | Location | May read substrate | May write substrate |
|---------|-----------|--------------------|---------------------|
| Kernel projection path | `invar/kernel/` | Yes (via GravityField query) | No |
| Replay CLI | `invar/cli/commands/replay.py` | No (reads NDJSON files) | No |
| Graph prior propagation | `invar/graph/` | No (reads from observations) | No |
| Display persistence | `invar/core/state_db.py` | No | No |
| Resonance/LLM pipeline | `invar/resonance/` | Via query API only | No |
| Forge/proposal engine | `invar/forge/` | Via query API only | No |
| Assistant layer | `invar/assistant/` | Via query API only | No |
| MCP server | `invar/mcp/` | Via query API only | No |
| CLI commands | `invar/cli/` | Via query API only | Only if explicitly constructing ObsGateEnvelope |

The CLI "replay" command is non-authoritative despite its name (see §4.1).

---

## 8. Auditability Requirements

Every canonical write (step 3 in §6) must be:

| Requirement | Carried by |
|-------------|-----------|
| Attributable | `instrument_id` on `ObsGateEnvelope` |
| Timestamped | `ts` field on emitted `Pearl` |
| Linked to observation | `cycle_id` on `ObsGateEnvelope` |
| Entropy-change recorded | `H_before`, `H_after`, `delta_H` on `Pearl` |
| State-change recorded | `state_before`, `state_after` on `Pearl` |
| Propagation recorded | `coupling_propagated` on `Pearl` |

The `Pearl` record IS the audit trail for a canonical write. If no Pearl was emitted,
no canonical write occurred (null observations: delta_H = 0 still emit a Pearl, but
with `delta_H = 0`).

**Audit invariant (EE-3):** Every canonical write produces exactly one `Pearl` per
entropy-changing gate. The Pearl is the permanent record. Pearl suppression is forbidden
(INVAR_CORE_CONTRACT.md §4.4).

---

## 9. Enforcement Surfaces

The following are the current enforcement points in the runtime.

### 9.1 Envelope boundary (enforced at Layer 0)

`ObsGateEnvelope` is the only legal input type for `core.SupportEngine.ingest()`. Any
object that is not an `ObsGateEnvelope` will fail the ingest call with a type error
(Python duck typing ensures this at the attribute access level).

**Current status:** Partial. Python duck typing provides implicit enforcement. There is
no explicit `isinstance` check or protocol marker.

### 9.2 Private gate store (enforced at Layer 0)

`SupportEngine._gates` (or equivalent private store) is not accessible via public API.
Domain code that attempts direct gate mutation violates the Layer 0 rules
(INVAR_CORE_CONTRACT.md §4.1) and should fail with an AttributeError on `_`-prefixed
access — though Python does not enforce this by default.

### 9.3 Pearl listener contract (enforced at Layer 0)

`SupportEngine.add_listener()` accepts callables. Listeners may not mutate Pearls
(INVAR_CORE_CONTRACT.md §4.4). This is a doc-level constraint, not enforced by type.

### 9.4 Kernel/core separation (enforced by import structure)

`invar/kernel/support.py` does not import `invar/core/support_engine.py`. The kernel
path cannot accidentally call core ingest because the class is not in scope.
The kernel `SupportEngine.aggregate()` returns `SupportContribution`, not `Pearl`.

**Current status:** Enforced by import isolation. No runtime type guard.

### 9.5 Sequencer write boundary (ET-G6, soft enforcement)

`IngestSequencer` is the designated canonical write surface for admitted observations.
`SupportEngine.ingest()` tracks unauthorized write paths via `_bypass_count`.

**Mechanism:**
- `_SEQUENCER_WRITE_TOKEN` — a module-level private sentinel in `support_engine.py`.
  `IngestSequencer.flush()` imports and passes it when calling `engine.ingest()`.
- `SupportEngine._bypass_count: int` — incremented when `ingest()` is called without
  the token (i.e., when the caller is not `IngestSequencer`).
- Enforcement is **soft**: direct calls still succeed but are observable.

**What "sequencer enforcement" means:**
- Admitted observation writes for canonical ordering should pass through `IngestSequencer`.
- `IngestSequencer.submit()` / `submit_batch()` / `flush()` are the authorized write paths.

**What "sequencer enforcement" does NOT mean:**
- Restoration does not go through `IngestSequencer`. `PearlArchive.restore_into()` writes
  directly to `engine._gates` via `Gate._restore_from_pearl_snapshot()` — this is the
  restoration path, not the observational path.
- Queries do not go through `IngestSequencer`. `GravityField.*()`, `gate()`, `field_energy()`
  are pure reads.
- Projections do not go through `IngestSequencer`. Kernel path is entirely separate.

**Current enforcement status:** Soft. `_bypass_count` is observable but not a hard raise.
Layer 0–2 physics tests legitimately call `engine.ingest()` directly for substrate testing.

---

## 10. Known Enforcement Gaps

### Gap EE-G1: No explicit type guard on `SupportEngine.ingest()` input

**Location:** `invar/core/support_engine.py::SupportEngine.ingest()`

**Issue:** `ingest()` accepts any object with the right attribute structure due to Python
duck typing. A `SupportContribution`, `WicketPrior`, or other non-`ObsGateEnvelope`
object with `.contributions` and `.workload_id` attributes could be accidentally
accepted.

**Risk level:** Medium. Currently the kernel and core paths are isolated and no caller
does this. Risk increases as more adapters are added.

**Required fix (Layer 2):** Add `isinstance(envelope, ObsGateEnvelope)` guard to
`SupportEngine.ingest()`. This is a one-line check that enforces the write boundary
without changing physics.

**Test:** `test_EE1_ingest_rejects_non_envelope` (xfail until guard added)

### Gap EE-G2: Kernel `SupportEngine` and core `SupportEngine` share a name

**Location:** `invar/core/support_engine.py::SupportEngine` vs
`invar/kernel/support.py::SupportEngine`

**Issue:** Both classes are named `SupportEngine`. A developer importing from the wrong
module would get a different class — one that aggregates observations, not one that
manages gates. This is a naming collision that creates confusion about authority.

**Risk level:** High for new contributors. Low for the current runtime (imports are
explicit). The replay CLI already demonstrates the confusion: it imports from
`invar.kernel.support` but could easily be mistakenly changed to `invar.core.support_engine`.

**Required fix (Layer 2):** Rename `invar/kernel/support.py::SupportEngine` to
`ObservationAggregator` or `KernelAggregator`. Update all kernel and replay callers.

**Test:** `test_EE2_kernel_engine_name_is_distinct` (xfail until rename done)

### Gap EE-G3: No canonical Pearl archive or substrate replay path

**Location:** `invar/core/`, `invar/kernel/pearls.py`

**Issue:** The canonical `core.Pearl` records are emitted at ingest time but are not
durably persisted. The `PearlLedger` in `invar/kernel/pearls.py` persists kernel bundle
objects (gravity cycle data), not canonical Pearls. On restart, the core gate store is
empty.

**Consequence:** There is no audit trail that can prove what canonical writes occurred
across restarts. Substrate reconstruction requires re-running instruments from scratch.

**Risk level:** Medium for operational use; high for auditability.

**Required fix (Layer 2):** Implement a canonical Pearl archive:
1. A file/db writer that appends `core.Pearl` records on emission (hook into
   `SupportEngine.add_listener()`)
2. A verified replay path that reconstructs `ObsGateEnvelope` from archived Pearls
   and re-ingests them into a fresh `core.SupportEngine`
3. A test that proves replay produces equivalent substrate state

### Gap EE-G4: `GravityStateDB` in `invar/core/` violates layer placement

**Location:** `invar/core/state_db.py`

**Issue:** `GravityStateDB` stores operational display data (credentials, pivot targets,
instrument run logs). This is Layer 2 persistence infrastructure, not Layer 0 substrate
physics. Its presence in `invar/core/` implies Layer 0 authority it does not have.

**Risk level:** Low for physics (it does not affect gate computation). High for
contributor confusion about what `invar/core/` means.

**Required fix (Layer 2):** Move `invar/core/state_db.py` to `invar/persistence/` or
`invar/runtime/`. Update imports in the gravity daemon and CLI.

### Gap EE-G5: Replay CLI naming implies substrate reconstruction

**Location:** `invar/cli/commands/replay.py`

**Issue:** The `skg replay` command is named "replay" and its docstring says "the
substrate is event-sourced." This implies canonical substrate reconstruction. But the
implementation uses the kernel projection path — it does NOT call `core.SupportEngine.ingest()`.
This is a naming/documentation mismatch that could cause a future developer to "fix"
the replay to call core ingest, accidentally creating truth from projection.

**Risk level:** Medium. The naming creates an incorrect mental model.

**Required fix (Layer 2/4):** Either:
1. Rename to `skg project` or `skg view-events` to make clear it is a projection; OR
2. Implement true canonical replay (Gap EE-G3) and make the current behavior a
   separate `skg project-events` command

Until this is resolved, the docstring must be updated to state explicitly:
"This command runs a kernel projection over stored events. It does not reconstruct
canonical substrate state."

### Gap EE-G6: No Pearl listener audit log in production runtime

**Location:** `invar/core/support_engine.py`, `invar/core/daemon.py`

**Issue:** `SupportEngine.add_listener()` allows Pearl notification, but the production
daemon does not currently add a listener that writes canonical Pearls to a durable log.
The audit trail for canonical writes is therefore in-memory only.

**Risk level:** High for compliance; low for immediate physics correctness.

**Required fix (Layer 2):** Wire a canonical Pearl archive listener into the daemon
startup (see also Gap EE-G3).
