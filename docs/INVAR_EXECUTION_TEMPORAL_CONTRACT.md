# INVAR Layer 3 Execution / Temporal Contract

**Version:** 1.9
**Status:** Canonical — defines execution and temporal boundaries above Layer 2 enforcement
**Authority order:** INVAR_STACK_BUILD_ORDER.md > INVAR_CORE_CONTRACT.md > INVAR_STATE_REPRESENTATION_CONTRACT.md > INVAR_CONSTRAINT_ENFORCEMENT_CONTRACT.md > this file

**Changelog:**
- v1.9 (2026-04-17): ET-G6 resolved. Sequencer enforcement boundary added to
  `SupportEngine.ingest()` via `_SEQUENCER_WRITE_TOKEN` capability token.
  `_bypass_count` tracks direct ingest calls (soft enforcement — not a hard raise).
  `IngestSequencer.flush()` is the authorized write path. Ordering Concept section
  added (§4.6). Known issues A–E carried forward. Gap ET-G6B added.
- v1.8 (2026-04-17): ET-G2 resolved. `submit_batch()` added to `IngestSequencer`
  in `invar/core/ingest_sequencer.py`. Deterministic multi-instrument ordering is
  now explicit: envelopes are sorted by `(instrument_id, workload_id, node_key,
  first_gate_id)` before enqueueing. Ordering is wall-clock-free and
  callback-arrival-free. Known issues A–D carried forward explicitly (see §11).
  Gap ET-G2 section updated to Resolved.
- v1.7 (2026-04-17): ET-G1B corrected to PARTIALLY IMPLEMENTED. Base-state model (Option C)
  replaces the snapshot override. `Gate._restore_from_pearl_snapshot()` now establishes a
  decaying base layer (`_base_phi_R`, `_base_phi_B`, `_base_ts`) rather than a frozen
  snapshot. `accumulated(t) = phi_base(t) + Σ contribution_phi(t)`. Single state model —
  no silent ignore of post-restoration contributions. Frozen snapshot semantics removed.
  GR test suite updated. ET-G1B gap section updated to PARTIALLY IMPLEMENTED.
- v1.6 (2026-04-17): ET-G1B incorrectly marked resolved. Snapshot approach implemented but
  contained a dual-state correctness violation (silent ignore of post-restoration ingest).
  Superseded by v1.7 base-state model.
- v1.5 (2026-04-17): ET-G1 split into ET-G1A (RESOLVED) and ET-G1B (OPEN). Pearl archive
  capture is resolved; canonical Pearl-native restoration is not. The synthetic
  `replay_into()` path is demoted: it may be used as an approximate test harness but must
  not be called canonical replay, authoritative restoration, or audit-grade reconstruction.
  Pearl Restoration Invariant added (§5.5). Forbidden pattern table updated. Gap section
  updated to reflect split.
- v1.4 (2026-04-17): ET-G1 (incorrectly marked fully resolved). `PearlArchive` added to
  `invar/persistence/pearl_archive.py`. Append-only record listener with strict `seq_id`
  monotonicity validation. Model A state reconstruction via `replay_into()` bypasses
  `engine.ingest()`. Note: that resolution was premature — synthetic reconstruction is
  not canonical. Superseded by v1.5.
- v1.3 (2026-04-17): ET-G4 resolved. `IngestSequencer` added to
  `invar/core/ingest_sequencer.py`. Canonical ingest ordering is now explicit
  (FIFO queue, monotone `queue_seq` separate from `Pearl.seq_id`, explicit `flush()`).
  ET-G3 float-fingerprint precision caveat documented. Gap ET-G4 section updated
  to "Resolved".
- v1.2 (2026-04-17): ET-G3 resolved. `SupportEngine` now maintains `_admitted` keyed by
  content fingerprint `(instrument_id, workload_id, node_key, sorted_contributions)`.
  Same normalized observation on same engine instance produces canonical effects at most once.
  `cycle_id` and `t0` are excluded from the fingerprint. Gap ET-G3 section updated to "Resolved".
- v1.1 (2026-04-16): ET-G5 resolved. `seq_id` added to `core.Pearl`. Canonical ordering
  invariant ET-1 now has explicit `seq_id` semantics (§4.3). Gap ET-G5 section updated
  to "Resolved". Invariant summary table updated.
- v1.0 (2026-04-16): Initial Layer 3 execution/temporal contract.

---

## 1. Purpose

Layer 0 defines physics. Layer 1 defines representation. Layer 2 defines enforcement.
Layer 3 defines **execution**: how transitions are applied over time, in what order,
with what determinism, and how replay is bounded.

This contract answers:

> How does the system execute transitions over time, in a deterministic order, while
> preserving replay safety and not allowing execution or runtime convenience layers to
> become canonical truth?

This is an **orchestration problem**, not a physics problem. Layer 3 does not extend
or alter the physics of Layers 0–2. It formalizes the temporal envelope in which those
layers operate.

---

## 2. Scope

Layer 3 covers two related concerns that share the same orchestration boundary:

| Concern | Scope |
|---------|-------|
| **Temporal execution** | How observations are sequenced, committed, and replayed |
| **Federation services** | How multiple INVAR cores coordinate without becoming each other's truth (see §12) |

The daemon (`invar/core/daemon.py`), gravity loop, and any future federation harness
all operate at Layer 3. They are orchestration surfaces, not substrate surfaces.

---

## 3. Definitions

### 3.1 Execution Unit

**Definition:** One execution unit is a single completed call to
`core.SupportEngine.ingest(ObsGateEnvelope)` that produces one or more
`core.Pearl` records and notifies registered listeners.

The execution unit is **atomic with respect to canonical state**: either the ingest
completes (Pearls emitted, listeners notified, gate store updated) or it does not.
There is no partial execution unit.

**Pre-conditions for a valid execution unit:**
1. The input is a fully constructed `ObsGateEnvelope` with `instrument_id`,
   `workload_id`, `node_key`, and at least one gate contribution.
2. The envelope is constructed from an instrument observation — not from
   a projection output, cache, or replay-generated object.
3. The `SupportEngine` receiving the call is the single authoritative instance
   for the core being executed.

**Post-conditions of a completed execution unit:**
1. Gate store is updated (`φ_R`, `φ_B` incremented for each contributed gate).
2. At least one `Pearl` is emitted per entropy-changing gate.
3. All registered listeners have been notified synchronously before `ingest()`
   returns.
4. The returned `List[Pearl]` is the complete record of canonical changes
   produced by this execution unit.

### 3.2 Temporal Event

**Definition:** A temporal event is a `core.Pearl` emission — the fact that
`SupportEngine.ingest()` completed for a specific gate and produced a `Pearl`
with a non-zero (or zero) `delta_H`.

The Pearl's `ts` field is the **canonical temporal marker** for that event.

**Temporal event boundary:** The moment `ingest()` returns. Before that moment,
the `ObsGateEnvelope` is in-flight (pending). After that moment, the `Pearl`
records exist as committed canonical facts.

### 3.3 Distinctions: observation / envelope / ingest / event / Pearl

| Stage | Object | State | Authority |
|-------|--------|-------|-----------|
| Raw instrument output | Scan XML, JSON, NDJSON | Pre-canonical | None |
| Translated gate contribution | Gate `(phi_R, phi_B)` inside adapter | Pre-canonical | None |
| Constructed envelope | `ObsGateEnvelope` (not yet ingested) | In-flight | None |
| Completed ingest | `SupportEngine.ingest()` call | Execution unit | Produces canonical truth |
| Canonical temporal event | `core.Pearl` | Committed | Absolute |
| Derived projection | `SupportContribution`, `TriState`, `Ψᵢ` | Ephemeral | None |

**Truth emerges only at the transition from execution unit to Pearl emission.**

---

## 4. Event Ordering

### 4.1 Primary ordering rule

Canonical event order is **Pearl emission order from `SupportEngine.ingest()`
calls as they complete within a single runtime instance**.

- Each `ingest()` call is synchronous and non-concurrent with other `ingest()`
  calls on the same `SupportEngine` instance (Python GIL provides this within
  a single process).
- The order in which `ingest()` calls are dispatched to `SupportEngine` within
  a gravity cycle is the **execution ordering** for that cycle.

### 4.2 seq_id — monotone canonical ordering field

**Definition:** `seq_id` is a non-negative integer assigned to every `core.Pearl`
at emission time by the `SupportEngine` that emitted it.

| Property | Value |
|----------|-------|
| Type | `int` |
| Start | 1 for the first Pearl emitted by a fresh `SupportEngine` |
| Monotonicity | Strictly increasing within one `SupportEngine` instance lifetime |
| Assigned by | `SupportEngine._seq` counter, incremented once per Pearl construction |
| Assigned when | Exactly once, at the moment `Pearl(...)` is constructed inside `ingest()` |
| Depends on | Nothing except the emission count of the engine instance |

**What `seq_id` is:**
- The canonical ordering key for Pearls emitted by one engine instance.
- A deterministic, wall-clock-free ordering basis for replay within one instance.
- The primary sort key for same-`ts` tie-breaking (replaces the lexicographic
  tie-break defined in the v1.0 draft of this section; `seq_id` is unambiguous).

**What `seq_id` is NOT:**
- Not a timestamp.
- Not a truth value.
- Not globally unique across process restarts or engine instances.
- Not a concurrency solution (single-instance monotonicity only).
- Not a distributed ordering guarantee.
- Not a replay input — it is a product of replay, not a source.

**Scope:** `seq_id` is monotone per `SupportEngine` instance lifetime.
Two separate `SupportEngine` instances will produce overlapping `seq_id` spaces.
Cross-instance ordering requires a higher-level sequencer beyond the scope of ET-G4.
`IngestSequencer` (ET-G4) provides single-process FIFO ordering; cross-instance
ordering remains an open gap.

**Implementation:** `SupportEngine.__init__` initializes `self._seq = 0`.
Every Pearl construction inside `ingest()` increments `self._seq` by 1 and
assigns that value to the Pearl's `seq_id` field. There is no global counter,
no threading primitive, and no persistence involved.

### 4.3 Same-timestamp tie-breaking (revised)

When two Pearls carry identical `ts` values, use `seq_id` as the primary
tie-breaker — it is unambiguous within one engine instance.

For cross-instance or cross-restart ordering where `seq_id` spaces overlap,
fall back to lexicographic order on `(workload_id, node_key, gate_id)`.

Two Pearls with identical `ts`, `seq_id`, and `(workload_id, node_key, gate_id)`
cannot exist within one engine instance (seq_id is unique per Pearl).

### 4.4 Determinism rule

**Determinism invariant (ET-1):**
> Given an identical sequence of `ObsGateEnvelope` inputs applied to a
> `SupportEngine` with identical initial state, the resulting Pearl sequence
> and final substrate state are identical.

This holds because:
- Gate physics (`gate_p`, `gate_energy`, `gate_phase`) are pure functions.
- `SupportEngine.ingest()` is deterministic given identical gate store state
  and identical envelope contents.
- No random number generation occurs in the canonical write path.

**Corollary:** Non-determinism in the system comes exclusively from:
1. Ordering differences in envelope delivery from concurrent instruments.
2. Wall-clock timestamps (`ts`) varying between runs.
3. Restart-induced gate store loss (see Gap ET-G1).

None of these corollary sources alter the **physics** of a given execution unit.
They alter **which** execution units occur and **when**.

### 4.5 Commit ordering

Canonical state is committed in **ingest completion order**, not in instrument
dispatch order or wall-clock observation order.

If instrument A completes before instrument B's envelope is delivered:
- A's Pearl is committed first.
- B's envelope, when delivered, operates on the state produced by A's execution.
- This is correct behavior: the system reflects observed evidence in arrival order.

`IngestSequencer` (implemented in ET-G4, `invar/core/ingest_sequencer.py`) provides
explicit FIFO ordering of canonical ingest within one process. Envelopes are submitted
to the sequencer, assigned a monotone `queue_seq`, and flushed to `SupportEngine` in
submission order. Processing is always explicit via `flush()` — submission alone does
not trigger ingest.

### 4.6 Ordering Concept

**Ordering in INVAR is strictly operational.** It defines the sequence in which
admitted `ObsGateEnvelope` objects reach canonical ingest — nothing more.

**Operational order** (ET-G4/ET-G2):
- The sequence in which envelopes are submitted to `IngestSequencer` and delivered
  to `SupportEngine.ingest()`.
- Determined by: FIFO submit order for single envelopes; lexicographic sort by
  `(instrument_id, workload_id, node_key, first_gate_id)` for `submit_batch()`.
- Realized as: `queue_seq` (monotone per `IngestSequencer` instance, not canonical).

**Canonical event order** (ET-G5/seq_id):
- The order in which Pearls are emitted by `SupportEngine`, recorded as `Pearl.seq_id`.
- Strictly monotone within one engine instance.
- Determined by operational order in a single process.

**These are related but distinct:**
Operational order determines canonical event order within one process. They are not
the same concept across restarts, across processes, or at the distributed level.

**Ordering is NOT any of the following:**

| What ordering is NOT | Why |
|---------------------|-----|
| Causal truth | If instrument A sorts before instrument B, it means only: A is processed first. It does NOT mean A happened first in the world, or that A's observation is more recent, more accurate, or more causally primary. |
| Epistemic priority | The sort key `(instrument_id, ...)` is a lexicographic tie-break, not a claim about which instrument is more authoritative. |
| Historical certainty | Operational ordering within one process cannot establish cross-process or cross-restart event order. |
| Projection truth | Ordering applies to the write path only. `GravityField.dispatch()` output, kernel projections, and `TriState` values are not ordered by this mechanism and have no causal authority. |
| Graph authority | Pearl.seq_id establishes which Pearl was emitted first within one engine, not which observation is more true in the knowledge graph. |

**Deterministic ≠ Causal:**
The ET-G2 ordering key produces a stable, reproducible operational sequence.
"Stable and reproducible" does not mean "reflecting the true causal order of events
in the world." Two observations arriving in one process during the same cycle are
ordered lexicographically for determinism, not because one caused the other.

**Summary:**

| Concept | Object | Canonical | What it means |
|---------|--------|-----------|---------------|
| Operational order | `queue_seq` (IngestSequencer) | No — metadata | Enqueue position |
| Canonical event order | `Pearl.seq_id` | Yes — ordering key | Emission sequence within one engine |
| Submission sort key | `_envelope_sort_key()` result | No — discarded | Deterministic batch processing order |
| Causal order | (not represented) | N/A | Not a concept in INVAR at this layer |

---

## 5. Deterministic Replay

### 5.1 What replay is

Replay is the process of re-executing an identical sequence of execution units
(ingest calls from reconstructed `ObsGateEnvelope` instances) on a fresh
`SupportEngine` to reproduce prior canonical substrate state.

Replay uses the **canonical Pearl archive** as its source (when it exists).
Each archived Pearl encodes sufficient information to reconstruct the
`ObsGateEnvelope` that produced it (instrument_id, workload_id, node_key,
gate_id, phi_R_after - phi_R_before, phi_B_after - phi_B_before, decay_class).

### 5.2 What replay may reconstruct

Replay may reconstruct:
- Prior admitted canonical substrate transitions (gate store state after
  each archived Pearl sequence).
- Derived/materialized state (kernel projections, graph priors) by running
  the projection path on the reconstructed substrate.
- Non-authoritative execution surfaces (gravity cycle history, dispatch
  selections) from the reconstructed substrate + archived kernel bundles.

### 5.3 What replay must not do

Replay must **not**:
- Infer missing observations not present in the canonical Pearl archive.
- Synthesize projection truth (back-compute `ObsGateEnvelope` values from
  `Ψᵢ`, `L`, or `TriState` outputs and re-ingest them).
- Generate new canonical events during reconstruction (no new Pearls whose
  `instrument_id` is `"replay"` or equivalent synthetic value).
- Duplicate canonical writes — re-ingesting the same Pearl-derived envelope
  twice doubles `φ_R`/`φ_B` and produces false evidence accumulation.
- Use the kernel projection path (aggregate + collapse) as a substitute for
  substrate reconstruction.

**Replay invariant (ET-2):**
> Replay of an archived Pearl sequence through a fresh `SupportEngine`
> produces substrate state equivalent to the original run.
> Replay must not increase the Pearl count in the archive.

### 5.4 Current replay implementation (kernel projection path)

The current `invar/cli/commands/replay.py` is **not** substrate reconstruction.
It runs the kernel projection path over stored NDJSON events — it does not call
`core.SupportEngine.ingest()`. This is a correct and legal query-time projection.

It is explicitly **not** canonical replay as defined in §5.1.

True canonical replay (§5.1) requires a Pearl-native restoration surface, which is
not yet implemented (Gap ET-G1B, blocked on Layer 0 Gate restoration surface).

### 5.5 Pearl Restoration Invariant

**Pearl is memory, not synthetic re-observation.**

Pearl records are the canonical archive of admitted field transformations. They are
the authoritative memory of what actually happened at the substrate boundary. They
are not a replay shim and not a basis for manufacturing new observations.

**Pearl Restoration Invariant:**

> Archived Pearl state may be restored only through direct canonical state
> reconstruction from archived Pearl fields. No restoration path may manufacture
> new observations, synthetic support contributions, or equivalent ingest inputs.

Formally:
- `restore(P)` must not call `ingest(Ô)` for any synthetic envelope `Ô`
- `restore(P)` must not create `SupportContribution` from Pearl fields
- `restore(P)` must not advance `SupportEngine._seq`
- `restore(P)` must not fire Pearl listeners on the restoration target engine

**What violates this invariant:**
- Encoding `pearl.phi_R_after` as `SupportContribution.phi_R` and calling
  `gate.add_contribution()` — this manufactures a synthetic observation from
  memory and re-enters the observational currency path.
- Re-ingesting an envelope reconstructed from Pearl fields — even if the result
  is numerically identical, the epistemically correct restoration path must not
  pass through `ingest()`.

**What satisfies this invariant:**
- A dedicated restoration surface on `Gate` that writes `phi_R`/`phi_B`/`state`
  directly from archived Pearl fields without using `SupportContribution`.
- A `PearlArchive.restore_into(engine)` method that uses that surface and nothing
  else. (Not yet implemented — see Gap ET-G1B.)

**Three distinct categories that must remain separate:**

| Category | Definition | Trust |
|----------|-----------|-------|
| Observation | What entered through the real ingest path | Ground truth |
| Pearl archive | What was canonically emitted and preserved from that observation | Canonical memory |
| Restoration | Direct reconstruction from Pearl-native archived state, not through observational currency | Future — requires Gate restoration surface |

**Current status of `PearlArchive.replay_into()`:** This method is an approximate
test harness. It injects synthetic `SupportContribution` values derived from Pearl
fields. It violates the Pearl Restoration Invariant and must not be used as canonical
replay, authoritative restoration, or audit-grade reconstruction. It is retained
only as a temporary approximate tool for test equivalence checks.

---

## 6. Canonical vs Ephemeral Execution State

The following table classifies all execution state kinds:

| State kind | Example | Canonical | May survive restart | May feed ingest |
|------------|---------|-----------|---------------------|-----------------|
| **Committed canonical** | `core.Pearl` records (including `seq_id`, `ts`) | Yes | Only if Pearl archive exists (Gap ET-G1) | No — Pearl is output, not input |
| **Substrate live** | `SupportEngine` gate store | Yes (in-memory) | No (Gap ET-G1) | Via ingest only |
| **In-flight envelope** | `ObsGateEnvelope` constructed but not yet ingested | No | No | Yes — this is the input |
| **Kernel projection** | `SupportContribution`, `TriState`, `Ψᵢ` | No | No | No (EE-1, EE-2) |
| **Scheduler/dispatch** | `GravityField.dispatch()` output, instrument queue | No | No | No |
| **Runtime execution trace** | Gravity cycle logs, daemon stdout | No | No | No |
| **Display persistence** | `GravityStateDB` rows | No | Yes (display only) | No (EE-6) |
| **Kernel bundle** | `invar/kernel/pearls.PearlBundle` (gravity cycle snapshots) | No | Yes (NDJSON) | No |
| **Materialized view / cache** | `WicketPrior`, coarse-grain `Ã_KL` cache | No | No | No |
| **Wall-clock metadata** | `ts` on Pearl, cycle timestamps | No — monotonicity marker only | N/A | No |

**Canonical execution state persists only through the canonical Pearl archive
(when implemented). Everything else is ephemeral.**

---

## 7. Scheduler and Dispatch Boundary

### 7.1 What the scheduler is

The gravity scheduler (`GravityField.dispatch()`, `GravityField.fiber_tensor()`,
the gravity daemon loop) selects which instruments to run against which targets.
It operates by reading current substrate state and producing an ordered list
of dispatch targets.

### 7.2 Scheduler state is operational, not canonical

**Scheduler invariant (ET-3):**
> Scheduler output (dispatch selections, instrument queues, cycle priority lists)
> is operational state. It must not be persisted as canonical state.

Scheduler selections are consequences of substrate state, not causes of it.
Recording which instrument was dispatched does not make the dispatch canonical.

The `GravityStateDB` records instrument run history (non-canonical display
persistence). This is permitted as operational telemetry. It must not be
loaded back into `SupportEngine` as if it were substrate truth.

### 7.3 Scheduling must not create canonical persistence by accident

Forbidden scheduler behaviors:

| Behavior | Reason |
|----------|--------|
| Writing dispatch selections to `SupportEngine` as gate observations | Dispatch is not evidence |
| Persisting scheduler priority queue as a canonical archive | Priority is derived |
| Using `GravityStateDB` to reconstruct `SupportEngine` state on restart | Display ≠ substrate |
| Treating cycle timestamps as ordering guarantees for canonical events | Wall-clock ≠ commit order |

---

## 8. Orchestration Boundary

### 8.1 What orchestration is

Orchestration is the Layer 3 concern of coordinating the execution of multiple
execution units over time — running instruments, delivering envelopes to the
correct `SupportEngine`, sequencing ingest calls, and managing the gravity loop.

### 8.2 Orchestration rules

**Orchestration invariant (ET-4):**
> The orchestration layer (daemon, gravity loop, federation harness) may
> coordinate execution units but must not manufacture canonical state.

Specifically:

| Orchestration action | Permitted |
|---------------------|-----------|
| Calling `SupportEngine.ingest(envelope)` with an envelope from an instrument adapter | Yes |
| Calling `SupportEngine.ingest(envelope)` with an envelope reconstructed from a canonical Pearl archive for replay | Yes |
| Calling `SupportEngine.ingest()` with an envelope back-computed from projection output | **No** |
| Writing directly to `SupportEngine._gates` or equivalent private store | **No** |
| Replaying events to double-count previously admitted evidence | **No** |
| Allowing AI/assistant/LLM output to become an `ObsGateEnvelope` input without explicit operator authorization | **No** |
| Logging execution traces, cycle metrics, dispatch history | Yes (non-canonical) |
| Reading substrate state via `GravityField.*()` query API | Yes |

### 8.3 Execution trace ≠ truth

Execution traces (daemon logs, gravity cycle timing records, instrument run
histories) document **what the orchestrator did**. They are not evidence about
the world. They must not be ingested as observations.

**Execution trace invariant (ET-5):**
> No execution trace or operational log record may be the source of an
> `ObsGateEnvelope` that enters `SupportEngine.ingest()`.

---

## 9. Commit Ordering Semantics

### 9.1 Commit = Pearl emission

A canonical commit occurs at the moment `SupportEngine.ingest()` emits a
`Pearl` for an entropy-changing gate. Commits are:

- **Atomic**: All Pearls for a given envelope are emitted before `ingest()`
  returns.
- **Synchronous**: Listeners are notified before `ingest()` returns.
- **Append-only**: The gate store never un-commits a Pearl by resetting
  `φ_R`/`φ_B` to zero (gate support is monotone — INVAR_CORE_CONTRACT.md §6,
  Layer 0 invariant 2).

### 9.2 Idempotency of commits

A canonical commit is **idempotent within one `SupportEngine` instance lifetime**
(ET-G3 resolved). Re-ingesting the same normalized observation returns the cached
Pearl list without any gate mutation, `seq_id` advancement, or listener notification.

The identity key is a content fingerprint: `(instrument_id, workload_id, node_key,
sorted_contributions)`. `cycle_id` and `t0` are excluded — the same observation
re-delivered with a new `cycle_id` is still the same execution unit. Scope is
per-instance only; idempotency is not persisted across restarts.

### 9.3 Partial execution is not committed state

A constructed-but-not-ingested `ObsGateEnvelope` is in-flight. It has not
produced a Pearl. It is not canonical. If the process terminates between
envelope construction and `ingest()` completion, those observations are lost.

This is correct behavior until durable ingest queuing is implemented.

---

## 10. Forbidden Execution Behaviors

The following behaviors are forbidden at Layer 3 (orchestration and above).
Violations corrupt the canonical record.

| Forbidden behavior | Rule violated |
|--------------------|--------------|
| Back-computing `ObsGateEnvelope` from `Ψᵢ`, `L`, `TriState` and ingesting it | ET-4, EE-2 |
| Re-ingesting a previously ingested envelope (retry duplication) | ET-2, §9.2 |
| Ingesting kernel `SupportContribution` as an envelope | EE-1 |
| Treating `GravityStateDB` rows as substrate backup and restoring from them | EE-4, ET-3 |
| Allowing replay to generate new canonical events (synthesis) | ET-2 |
| Encoding Pearl fields as `SupportContribution` and injecting into a Gate during restoration | ET-2, §5.5 |
| Calling `PearlArchive.replay_into()` as canonical replay, authoritative restoration, or audit-grade reconstruction | §5.5, ET-G1B |
| Treating execution trace timestamps as canonical event ordering | ET-5 |
| AI/LLM/assistant output becoming an `ObsGateEnvelope` without operator authorization | EE-2, ET-4 |
| Marking an in-flight envelope as committed before `ingest()` returns | §3.1 |
| Persisting `GravityField.dispatch()` selections as if they were truth-bearing | ET-3 |
| Running instruments on the basis of scheduler state persisted from a prior run without re-verifying from substrate | ET-3 |

---

## 11. Known Execution Gaps

These gaps are documented here for tracking. Do not fix them unless the fix
is purely documentary. Runtime fixes belong to later Layer 3 implementation work.

### Gap ET-G1A: Pearl archive capture — RESOLVED

**Status:** Resolved (2026-04-17). `PearlArchive` added to
`invar/persistence/pearl_archive.py`.

**What was missing:** No append-only record of emitted Pearls existed. Pearls were
emitted by `SupportEngine` but not durably captured.

**Resolution:** `PearlArchive.record(pearl)` is an append-only Pearl listener that
validates strict `seq_id` monotonicity and can be registered via
`engine.add_listener(archive.record)`. The `.pearls` property returns an ordered copy
of all archived Pearls. This is Pearl-as-memory: the canonical archive of what was
admitted and emitted.

**Enforcement note:** Callers may still invoke `SupportEngine.ingest()` directly
instead of routing through `IngestSequencer`. The sequencer is the recommended
canonical ordering surface, but not yet the globally enforced one. Tightening that
boundary is a later enforcement task and is out of scope for ET-G1A.

**Cross-reference:** Also documented as Gap EE-G3 in Layer 2 contract and
Gap L1-G5 in Layer 1 contract. Those gaps remain open at their respective layers.

### Gap ET-G1B: Pearl-native restoration — PARTIALLY IMPLEMENTED (base-state model)

**Status:** Partially implemented (2026-04-17). Infrastructure is present; full audit
qualification and cross-layer enforcement remain open.

**What is implemented (base-state model, Option C):**

`Gate._restore_from_pearl_snapshot(phi_R, phi_B, state, ts)` in `invar/core/gate.py`
establishes a decaying canonical base layer from archived Pearl fields. The model is:

    phi_total(t) = phi_base(t) + Σ contribution_phi(t)

where `phi_base(t) = phi_after · exp(-λ_STRUCTURAL · (t - ts))`. Pearl is the canonical
BASE STATE, not a final-state override. Future live contributions (via `add_contribution()` /
`ingest()`) accumulate on top and decay according to their own decay class. Both evolve over
time — single state model, no silent ignore, no dual-mode switching.

`PearlArchive.restore_into(engine)` (in `invar/persistence/pearl_archive.py`) iterates the
last Pearl per gate and calls `_restore_from_pearl_snapshot()`. Writes directly to
`engine._gates`. No Pearls emitted, no `_seq` advancement, no listeners fired.

**Pearl sufficiency — CONFIRMED for base-state model:**
Pearl fields `phi_R_after`, `phi_B_after`, `state_after`, `ts` are sufficient to establish
the decaying base layer. Known approximation: decay class is pinned to STRUCTURAL regardless
of original contribution decay class (Pearl does not carry per-contribution decay_class).
This is conservative — STRUCTURAL is the slowest decay. Documented in §5.9 of
INVAR_CORE_CONTRACT.md.

**What `_restore_from_pearl_snapshot()` does:**
- Sets `_base_phi_R`, `_base_phi_B`, `_base_ts` — base layer fields only
- Does NOT create `SupportContribution`
- Does NOT call `add_contribution()`
- Does NOT call `ingest()`
- Does NOT emit Pearl
- Does NOT advance `_seq`
- Does NOT fire listeners
- Raises if target gate already has contributions (precondition: fresh gate only)

**What remains open (not yet resolved):**
- Cross-layer enforcement: no guarantee that `_restore_from_pearl_snapshot()` is called
  only from `invar/persistence/`. Requires linter or import guard (EE-G3 scope).
- Audit qualification: `restore_into()` is not yet classified as audit-trusted. Requires
  formal audit trail entry and review.
- Distributed/multi-process scope: not yet defined. This is single-process only.

**Current safe status of `replay_into()`:** Remains demoted. It may be used as an
approximate test harness. It must not be called canonical replay, authoritative
restoration, or audit-grade reconstruction. See §5.5.

**Cross-reference:** Gap EE-G3 in Layer 2 contract. Gap L1-G5 in Layer 1 contract.
Those gaps remain open at their respective layers.

### Gap ET-G2: Deterministic multi-instrument ordering — RESOLVED

**Status:** Resolved (2026-04-17). `submit_batch()` added to
`invar/core/ingest_sequencer.py`.

**What was missing:** When envelopes from multiple instruments arrived at
`SupportEngine.ingest()`, their ordering depended on wall-clock timing,
thread scheduling, or asyncio callback interleaving — not on a deterministic
policy. Two otherwise-identical runs could produce different Pearl orders.

**Resolution:** `IngestSequencer.submit_batch(envelopes)` accepts a
collection of `ObsGateEnvelope` objects from any number of instruments,
sorts them by a deterministic lexicographic key, and enqueues them in that
order before flushing.

**Ordering rule (ET-G2):**

The ordering key is a 4-tuple of strings, compared lexicographically:

    (instrument_id, workload_id, node_key, first_gate_id)

where `first_gate_id` is `envelope.contributions[0].gate_id` if the envelope
has contributions, otherwise `""`.

**What this guarantee covers:**
- All envelopes passed in a single `submit_batch()` call are sorted before
  enqueueing. Same input set → same enqueue order on every run.
- Ordering is determined by the sort key alone. Wall-clock timestamps (`ts`),
  arrival timing, callback order, and thread scheduling have no effect.
- Ordering metadata (the sort key) is computed and discarded. It is not
  stored, not emitted on Pearls, and does not affect substrate energy or
  canonical state.
- ET-G3 idempotency (content fingerprint dedup) still fires through the
  batch path.
- Single-envelope `submit()` is unaffected — pure FIFO as before.

**What this guarantee explicitly does NOT cover:**
- Ordering across separate `submit_batch()` calls (sequential calls are FIFO
  in queue order — the sort applies only within one batch).
- Cross-process or distributed ordering.
- Callers that invoke `engine.ingest()` directly instead of routing through
  `IngestSequencer`. Direct ingest bypasses the ET-G2 guarantee (see Known
  Issue B below).
- Archive replay ordering across process restarts (Gap ET-G1B remains open).

**Implementation reference:** `invar/core/ingest_sequencer.py`,
function `_envelope_sort_key()`, method `IngestSequencer.submit_batch()`.

**Tests:** `tests/test_layer3_execution_temporal.py::TestETG2MultiInstrumentOrdering`

### Known Issues / Known Later Concerns

These issues are documented here explicitly and must not be silently fixed
in tasks that do not have them as a stated objective.

**Issue A — ET-G3 float precision caveat:**
The content fingerprint in `SupportEngine._admitted` uses raw `float` values
for `phi_R` and `phi_B`. Two semantically equivalent observations with tiny
floating-point drift (e.g., from serialization round-trip or numerical jitter)
will produce different fingerprints and will not be deduplicated. This is a
known future canonicalization concern. Fixing it (e.g., rounding to a fixed
precision before fingerprinting) is explicitly out of scope for ET-G2 and all
tasks until a canonicalization pass is scheduled.

**Issue B — Sequencer enforcement gap:**
Callers may still invoke `SupportEngine.ingest()` directly instead of routing
through `IngestSequencer`. Sequencer use is recommended, not yet globally
enforced. The ET-G2 ordering guarantee applies only to the `submit_batch()`
path. Tightening this boundary is a later enforcement task (see Gap EE-G3 in
Layer 2 contract).

**Issue C — ET-G1B partial implementation status:**
Pearl-native restoration exists (base-state model, `PearlArchive.restore_into()`,
`Gate._restore_from_pearl_snapshot()`), but the following remain open:
- Cross-layer enforcement: no guarantee that `_restore_from_pearl_snapshot()`
  is called only from `invar/persistence/`.
- Audit qualification: `restore_into()` is not yet classified as audit-trusted.
- Distributed/multi-process scope: not yet defined. Single-process only.

**Issue D — ET-G1B decay approximation:**
Base restoration currently pins restored base decay to `STRUCTURAL` because
`Pearl` does not carry a per-contribution `decay_class`. This is a conservative
approximation (STRUCTURAL is the slowest decay). It is documented and accepted.
Solving it requires adding `decay_class` to the `Pearl` dataclass — out of scope
for ET-G2.

**Issue E — Ordering is deterministic operational order, not causal truth:**
The ET-G2 ordering key `(instrument_id, workload_id, node_key, first_gate_id)` produces
a stable, reproducible operational sequence for canonical ingest within one process.
This ordering does NOT imply:
- Causal priority between observations
- Epistemic authority of one instrument over another
- Historical order of events in the world
- Graph truth relative to other observations
See §4.6 (Ordering Concept) for the full definition.

### Gap ET-G3: Idempotency guard on `SupportEngine.ingest()` — RESOLVED

**Status:** Resolved (2026-04-17). `SupportEngine._admitted` added to
`invar/core/support_engine.py`.

**What idempotency means here:**
Re-ingesting the same admitted execution unit into the same `SupportEngine` instance
produces canonical effects (Pearl emission, substrate mutation, `seq_id` advancement)
at most once.

**Canonical identity key:** A content fingerprint derived from normalized envelope fields:
`(instrument_id, workload_id, node_key, sorted_contributions)` where each contribution
entry is `(gate_id, phi_R, phi_B, decay_class.value)`.

Fields **excluded** from the fingerprint:
- `cycle_id` — transport/delivery identifier; the same observation may be resent with a
  new `cycle_id` on retry without changing what was observed.
- `t0` — wall-clock timestamp on each contribution; excluded because the same observation
  at a different wall-clock time is still the same observation.
- `raw_evidence` — non-canonical passthrough; does not affect gate semantics.

**Guard location:** `SupportEngine.ingest()`. `SupportEngine._admitted: Dict[_IngestKey,
Tuple[Pearl, ...]]` stores the Pearl tuple from the first admission. On a duplicate
fingerprint, `ingest()` returns `list(cached)` and skips all gate updates, `seq_id`
increments, and listener notifications.

**Return on duplicate:** A fresh mutable list copied from the immutable cached tuple.
No side effects. Same Pearl count and `delta_H` values as original admission.

**Scope and limitations (explicit):**
- Idempotency is **per-SupportEngine-instance** and **not persisted** across restarts.
- This is **not** cross-process deduplication.
- This is **not** distributed idempotency.
- This is **not** archive-level replay idempotency (Gap ET-G1 remains open).
- This is **not** concurrency-safe (`SupportEngine` is single-threaded by contract).
- A new `SupportEngine` instance starts with an empty `_admitted` dict.

**What this guarantees:**
- Same normalized observation content on the same engine instance → canonical effects at most once.
- `seq_id` does not advance on duplicate ingest.
- `field_energy()` does not change on duplicate ingest.
- Pearl listeners are not re-fired on duplicate ingest.
- Dedup fires even when the adapter assigns a new `cycle_id` to equivalent content.

**What this does NOT guarantee:**
- Cross-restart deduplication.
- Cross-instance deduplication.
- Replay archive safety (Gap ET-G1 remains open).
- Ordering guarantees across processes.

**Known precision caveat (ET-G3):**
The content fingerprint uses raw `float` values for `phi_R` and `phi_B`. Two
semantically equivalent observations with tiny floating-point drift (e.g., due to
serialization round-trip or numerical jitter) will produce different fingerprints
and will not be deduplicated. This is a known future canonicalization issue.
Fixing it (e.g., rounding to a fixed precision before fingerprinting) is explicitly
out of scope for ET-G4 and all subsequent tasks until a canonicalization pass is
scheduled.

### Gap ET-G4: Explicit ingest sequencer — RESOLVED

**Status:** Resolved (2026-04-17). `IngestSequencer` implemented in
`invar/core/ingest_sequencer.py`.

**What the sequencer is:**
`IngestSequencer` is a single-threaded FIFO ordering surface that wraps
`SupportEngine`. It makes canonical ingest ordering an explicit, testable
system property rather than an accident of call order.

**What enters the queue:**
Raw `ObsGateEnvelope` objects, exactly as submitted by the caller. The
sequencer does not inspect or transform envelope content.

**Ordering rule:**
FIFO (first-submitted, first-processed). Submission position determines
processing order. No wall-clock tie-breaking. `submit()` never calls
`engine.ingest()` — processing is always explicit via `flush()`.

**Queue authority:**
`IngestSequencer` assigns `queue_seq` (a monotone int starting at 1 per
instance). `queue_seq` is separate from `Pearl.seq_id` and is not
truth-bearing: it does not affect substrate energy, gate state, or Pearl
content. Submitting to the queue does not change substrate state.

**What this guarantees:**
- Envelopes are processed in FIFO (submit) order.
- Identical submit sequences produce identical Pearl sequences and
  `seq_id` patterns.
- `queue_seq` is monotone and does not affect canonical state.
- ET-G3 idempotency (content fingerprint dedup) still fires through the
  sequencer.
- No implicit processing: ordering is explicit and testable.

**What this does NOT guarantee:**
- Cross-process ordering.
- Distributed sequencing.
- Archive replay ordering (Gap ET-G1 remains open).
- Enforced use: callers can still call `engine.ingest()` directly. The
  sequencer is the recommended path but is not the only path at this layer.

**Scope:**
Single-process, single-`SupportEngine`-instance. Not persisted. Not
distributed. Not a replay engine.

### Gap ET-G5: Wall-clock timestamp (`ts`) on Pearl is not a monotone counter — RESOLVED

**Status:** Resolved (2026-04-16). `seq_id: int` added to `invar/core/support_engine.Pearl`.

**Location:** `invar/core/support_engine.py`

**Resolution:** `SupportEngine` now maintains a `_seq: int` counter initialized to `0` at
construction. Each Pearl construction inside `ingest()` increments `_seq` by 1 and assigns
that value to `Pearl.seq_id`. The first Pearl emitted by a fresh engine has `seq_id = 1`.

`seq_id` is:
- Strictly monotone within one `SupportEngine` instance lifetime.
- Deterministic: two engines with identical ingest histories produce the same `seq_id`
  values.
- Wall-clock independent: does not depend on `time.time()` or any clock source.
- Not globally unique: separate engine instances overlap in `seq_id` space.

`ts` remains on Pearl as a human-readable audit timestamp. For canonical ordering within
one instance, use `seq_id`. For same-ts tie-breaking, `seq_id` is now unambiguous (§4.3).

**Tests:** `test_ET1_pearl_has_monotone_seq_id` — now passes (was xfail).

### Gap ET-G6: Execution trace / runtime logs not explicitly separated from audit trail

**Location:** `invar/core/daemon.py`, `invar/core/state_db.py`

**Issue:** The daemon writes operational data (instrument run timestamps, target
lists, credential records) to `GravityStateDB` alongside display state. There is
no explicit marker distinguishing "operational execution trace" from "canonical
audit trail." A developer could mistake `GravityStateDB` run records for a
canonical audit source.

**Consequence:** Risk of using execution trace records to reconstruct envelopes
and re-ingest them — violating ET-5.

**Required fix:** Add explicit `canonical=False` flag or module-level docstring
to all `GravityStateDB` tables. Rename instrument run history tables to make
their non-canonical status unmistakable.

### Gap ET-G6B: Sequencer enforcement — RESOLVED (soft enforcement)

**Status:** Resolved (2026-04-17). `_SEQUENCER_WRITE_TOKEN` and `_bypass_count` added
to `invar/core/support_engine.py`. `IngestSequencer.flush()` passes the token.

**What was missing:** Direct external calls to `SupportEngine.ingest()` bypassed
the ordering surface entirely with no observable enforcement boundary.

**Resolution (soft enforcement):**
- `_SEQUENCER_WRITE_TOKEN = object()` defined in `support_engine.py` as a private sentinel.
- `SupportEngine.ingest()` accepts `_sequencer_token` (keyword-only, private).
- When called without the token, `_bypass_count` is incremented.
- `IngestSequencer.flush()` passes the token — it is the authorized write path.
- Direct calls still succeed but are tracked.

**Why soft (not hard) enforcement:**
Hard enforcement (raise on direct call) would require rewriting 50+ existing layer 0–2
physics tests that legitimately test the substrate directly. That constitutes a global
framework rewrite, which is forbidden by the ET-G6 task spec. Soft enforcement makes
the boundary observable and test-detectable without a rewrite.

**Scope:**
Single-process, single-engine. Not distributed. Not audit-certified.

**Tests:** `tests/test_layer3_execution_temporal.py::TestETG6SequencerEnforcement`

**Known limitation:** Callers who import `_SEQUENCER_WRITE_TOKEN` directly from
`support_engine` can bypass the enforcement boundary. The `_` prefix signals
"internal use only" per Python convention. This is not enforced at runtime.

### Gap ET-G7: No boundary between dispatch/runtime state and canonical state in daemon startup

**Location:** `invar/core/daemon.py` startup sequence

**Issue:** On daemon startup, the current code may read from `GravityStateDB`
to determine which targets to scan. If the startup logic constructs envelopes
from persisted display state and ingests them before fresh instrument runs
complete, it creates canonical state from non-canonical sources.

**Status:** Not confirmed — requires runtime audit of daemon startup path.

**Required fix:** Audit daemon startup. If any startup path constructs
`ObsGateEnvelope` from `GravityStateDB` rows, it must be removed. Startup
should begin with an empty gate store and let the gravity loop populate it
from live instruments.

---

## 12. Federation Execution Boundary

Layer 3 also governs multi-core federation. The temporal execution rules
apply at the federation level as they do at the single-core level.

**Federation invariant (ET-6):**
> A remote INVAR core is an instrument, not a substrate authority.
> Evidence from a remote core enters this core only through an
> `ObsGateEnvelope` produced by a federation adapter.
> The remote core's `core.Pearl` records are not directly replayed into
> this core's `SupportEngine`.

Implications:
- Cross-core coarse-graining (`Ã_KL` computation) is a Layer 0 physics
  operation (read-only query on each core's substrate).
- Cross-core evidence sharing requires a federation adapter that translates
  remote substrate projections into `ObsGateEnvelope` observations.
- A federation adapter that back-computes `φ_R`/`φ_B` from a remote core's
  `Ψᵢ` and injects them as observations is forbidden — that is projection
  back-fed as truth.

---

## 13. Layer 3 Object Classification

Layer 3 introduces no new canonical objects. It defines these execution-level
operational concepts:

| Concept | Realized by | Layer | Canonical |
|---------|-------------|-------|-----------|
| Execution unit | A completed `SupportEngine.ingest()` call | L0 physics + L3 delivery | Produces canonical Pearls |
| Temporal event | `core.Pearl` with `ts` | L0 | Yes |
| Ingest queue | `IngestSequencer._pending` (ET-G4 resolved) | L3 | No — operational metadata |
| Sequencer | `IngestSequencer` in `invar/core/ingest_sequencer.py` (ET-G4 resolved) | L3 | No — operational metadata |
| Canonical Pearl archive | Not yet implemented (Gap ET-G1) | L3 | Yes — append-only |
| Gravity loop / daemon | `invar/core/daemon.py` (misplaced — should move to L3 module) | L3 | No — orchestration |
| Federation harness | `adapters/federation/` (planned) | L3 | No — operational |
| Execution trace | Daemon logs, `GravityStateDB` run records | L3 | No — telemetry |

---

## 14. Invariant Summary

| ID | Invariant | Test |
|----|-----------|------|
| ET-1 | Identical ingest sequence on identical initial state produces identical Pearl sequence and identical `seq_id` ordering pattern | `test_ET1_deterministic_ingest_order`, `test_ET1_pearl_has_monotone_seq_id` |
| ET-2 | Canonical replay reproduces prior substrate state; replay does not increase Pearl count | `test_ET2_replay_does_not_create_new_pearls` |
| ET-3 | Scheduler dispatch output does not alter substrate state | `test_ET3_dispatch_does_not_write_substrate` |
| ET-4 | Orchestration may not construct ObsGateEnvelope from projection output and ingest it | `test_ET4_orchestration_cannot_backfeed_projection` |
| ET-5 | Execution trace records are not ingested as observations | `test_ET5_execution_trace_not_ingested` |
| ET-6 | Federation produces envelopes from remote projections; does not replay remote Pearls directly | (scaffold — not yet testable) |

---

## 15. What This Contract Must Not Do

This contract must not:
- Alter Layer 0 physics (gate, field, functional, topology, coarse-grain).
- Alter Layer 1 representation boundaries.
- Alter Layer 2 write authority.
- Let scheduler/dispatch become truth-bearing.
- Let replay infer or invent state.
- Let retries duplicate canonical writes.
- Let execution traces/logs become canonical truth.
- Let AI/assistant/orchestrators acquire canonical write authority.
