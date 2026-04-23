# INVAR Core Contract

**Version:** 2.28
**Status:** Canonical — do not modify without updating the invariant test suite  
**Scope:** `invar/core/` only

**Changelog:**
- v2.28 (2026-04-22): Layer 2 Stage L2-7 — Windows/Sysmon Ingest Adapter.
  New module `invar/adapters/redteam/windows_ingest.py` introduces `SysmonEvent`,
  `CycleDiscovery`, `WindowsIngestAdapter`, and XML parsing helpers.
  Converts Sysmon and Windows Event Log XML into Invar Pearls using rule-aligned
  gate_id naming compatible with L2-5 classification rules.  Supports EID 1, 3, 7,
  8, 10, 11, 12, 13 (Sysmon) and 4688, 4698, 4624 (Security log fallback).
  `CycleDiscovery` performs autonomous three-tier boundary detection: operator override
  takes absolute priority; time-gap > gap_threshold (default 300 s) starts a new cycle;
  conservative primitive-shift (stable run of ≥ shift_window non-UNKNOWN events of one
  type followed by a different type) starts a new cycle.  Cycle naming: auto_{idx:03d}_{label}.
  Pearls constructed directly with phi_R=1.0, H=1.0, state_before=U, state_after=R.
  No Layer 0 modification, no host execution, deterministic, discardable.
  Public API: `classify_gate_id()` (re-exported from domain_model); 31 tests in
  `TestL2WindowsIngestAdapter`.
- v2.27 (2026-04-22): Layer 2 Stage L2-6 — Red Team Relationship Graph.
  New module `invar/adapters/redteam/relationship_graph.py` introduces `CycleRelationship`,
  `PatternMatch`, `RelationshipType`, and `RelationshipGraph`. Derives directed cycle
  relationships from proto-causal links and domain primitive classifications; detects
  multi-hop attack patterns via DFS with frozenset visited tracking.
  `CycleRelationship` fields: from_cycle, to_cycle, from_primitive, to_primitive,
  relationship_type ("continuation"/"stage_transition"/"unclassified"), transition_label
  (named label string or None), weight (from ProtoCausality), shared_gate_count.
  `PatternMatch` fields: pattern_name, cycle_path (tuple of cycle_ids), primitives (tuple),
  avg_weight. Classification: CONTINUATION when same non-UNCLASSIFIED/non-MULTI_STAGE
  primitive in both cycles; STAGE_TRANSITION for 10 known primitive pairs (credential_to_lateral,
  lateral_to_execution, discovery_to_lateral, discovery_to_execution, execution_to_persistence,
  execution_to_collection, execution_to_c2, collection_to_c2, credential_to_execution,
  persistence_to_c2); UNCLASSIFIED otherwise. Five named attack patterns: credential_lateral_exec,
  discovery_lateral_exec, exec_persist_c2, cred_exec_collect, collect_to_c2. Interface:
  `cycle_relationships()`, `relationships_from(cycle_id)`, `relationships_to(cycle_id)`,
  `pattern_matches()` (sorted by avg_weight desc), `pivot_cycles()` (relay nodes),
  `artifact_reuse_map()` (gate_key → cycle_ids for gates in 2+ cycles). All data precomputed
  at construction. No Layer 0 modification. No mutation. Deterministic and discardable.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.26 (2026-04-22): Layer 2 Stage L2-5 — Red Team Domain Concretization.
  New module `invar/adapters/redteam/domain_model.py` introduces `ArtifactType`,
  `OperationPrimitive`, and `RedTeamDomainModel`. Domain labels are adapter-local
  interpretation only — never written into Pearl or any core Invar truth surface.
  `ArtifactType` constants: UNKNOWN, EXECUTION_ARTIFACT, PERSISTENCE_ARTIFACT,
  CREDENTIAL_ARTIFACT, DISCOVERY_ARTIFACT, LATERAL_ARTIFACT, COLLECTION_ARTIFACT,
  C2_ARTIFACT. `OperationPrimitive` constants: UNCLASSIFIED, EXECUTION, PERSISTENCE,
  CREDENTIAL_ACCESS, DISCOVERY, LATERAL_MOVEMENT, COLLECTION, COMMAND_AND_CONTROL,
  MULTI_STAGE. Classification rules are deterministic, first-match, rule-based:
  `artifact_type(gate_key)` — substring scan of gate_id (case-insensitive, 7 ordered
  rule groups; LATERAL and PERSISTENCE checked before EXECUTION to prevent false-positive
  matches for "psexec"/"autorun" patterns); `cycle_primitive(cycle_id)` — derived from
  distinct non-UNKNOWN artifact type set: 0 types → UNCLASSIFIED, 1 type → matching
  primitive, 2+ types → MULTI_STAGE. Interface: `cycle_artifacts(cycle_id)` → annotated
  gate inventory with gate_key and artifact_type per pearl; `operational_summary(cycle_id)`
  → primitive + activity + artifact_count + sorted unique artifact_types + incoming/outgoing
  link counts + workflow_state_counts (all four states always present); `lab_queue()` →
  WorkflowView-ordered items enriched with action_type, proposal_id, and primitive from
  ActionProposalEngine and domain classification. All outputs derived on demand. No Layer 0
  modification. No mutation of any input layer. Deterministic and discardable.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.25 (2026-04-22): Layer 2 Stage L2-4 — Design-Only Controlled Action Interface.
  New module `invar/adapters/redteam/action_proposal.py` introduces `ProposedAction` (frozen
  dataclass: proposal_id, suggestion_id, action_type, target, parameters, confidence) and
  `ActionProposalEngine`. Eligibility: only suggestions acknowledged as "valid" or "investigate"
  receive a ProposedAction; "open" and "reviewed-irrelevant" suggestions are excluded. Action
  types map directly from Suggestion types: "examine_reuse" (from "reuse"), "examine_high_activity"
  (from "high_activity"), "examine_anomaly" (from "anomaly"), "trace_chain" (from "chain").
  proposal_id is SHA-256 of (suggestion_id + action_type), 16 hex chars; deterministic.
  target is the primary cycle_id or gate-key string from the suggestion. parameters stored as
  sorted tuple of (key, value) string pairs; .params() returns plain dict. confidence inherited
  from source Suggestion. Interface: `proposals()` → sorted by confidence desc; `for_suggestion(sid)`
  → Optional[ProposedAction]; `by_type(action_type)` → filtered list. Operator flow:
  Suggestion → (operator acknowledges) → ProposedAction → operator decides → external system.
  NOTHING is executed, triggered, or automated. No Layer 0 modification. No Suggestion or
  Acknowledgment mutation. Fully derived: same engine + store → same proposals. Discardable.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.24 (2026-04-22): Layer 2 Stage L2-3 — Operator Workflow View (derived queue).
  New module `invar/adapters/redteam/workflow.py` introduces `WorkflowView`. Takes a
  `FeedbackEngine` and an `AcknowledgmentStore` and derives operator workflow state for each
  suggestion on demand — no new canonical state is stored, no mutation occurs, no side-effects.
  Workflow states are derived: "open" (no ack), "reviewed-valid" (decision="valid"),
  "reviewed-irrelevant" (decision="irrelevant"), "needs-investigation" (decision="investigate").
  Interface: `items()` → all suggestions as workflow dicts (suggestion_id, type, cycle_id,
  confidence, state) in suggestion order; `by_state(state)` → filtered dicts for one state,
  returns [] for unrecognised state; `queue()` → all items in priority order
  (needs-investigation → open → reviewed-valid → reviewed-irrelevant, within each tier:
  confidence descending then suggestion_id ascending); `counts()` → {state: int} for all four
  states, always all four keys present (count 0 if empty). Deterministic: same engine + store
  → same outputs. Discardable: zero side-effects on construction or destruction. No Layer 0
  modification. No automation. Human-in-the-loop boundary preserved.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.23 (2026-04-22): Layer 2 Stage L2-2 — Operator Acknowledgment Layer (audit log).
  New module `invar/adapters/redteam/acknowledgment.py` introduces `Acknowledgment` (frozen
  dataclass: suggestion_id, decision, ts) and `AcknowledgmentStore`. Valid decisions:
  "valid" | "irrelevant" | "investigate" — validated at record() time. AcknowledgmentStore is
  append-only: no overwrite (raises ValueError on duplicate suggestion_id), no deletion.
  Interface: `record(ack)` (raises on invalid decision or duplicate), `get(suggestion_id)` →
  Optional[Acknowledgment], `all()` → records in insertion order (independent copy),
  `by_decision(decision)` → filtered list, `len(store)` → count. No explanation field, no
  narrative — decision + suggestion_id + timestamp only. Extended FeedbackEngine with
  `with_ack(store)` → read-only join returning [(Suggestion, Optional[Acknowledgment])] in
  confidence-sorted order; store is never modified by this call. No Layer 0 modification.
  No automation. No feedback loops. Human-in-the-loop boundary preserved: operator records
  decisions, system does nothing automatically as a result.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.22 (2026-04-22): Layer 2 Stage L2-1 — Controlled Feedback Interface (operator suggestions).
  New module `invar/adapters/redteam/feedback.py` introduces `Suggestion` (frozen dataclass)
  and `FeedbackEngine`. Suggestion fields: suggestion_id (SHA-256 of sorted evidence, 16 hex
  chars), type, cycle_id (Optional), supporting_cycles (Tuple[str,...]),
  supporting_artifacts (Tuple[GateKey,...]), confidence (float ∈ [0,1]). No free-text narration
  — evidence fields only. FeedbackEngine derives four suggestion types from RedTeamObserver:
  "reuse" (gate identity in N+ windows, confidence=count/total_windows), "high_activity"
  (activity ≥ threshold, confidence=activity), "anomaly" (activity ≤ threshold,
  confidence=1−activity), "chain" (3+ windows connected by strong causal links,
  confidence=avg_weight). All suggestions generated eagerly at construction; deduplicated by
  suggestion_id. Interface: `suggestions()` → sorted by confidence desc, `by_type(type_str)`,
  `by_cycle(cycle_id)`. Configurable thresholds at construction (defaults: reuse_min_count=2,
  high_activity_threshold=0.7, low_activity_threshold=0.3, chain_threshold=0.5,
  chain_min_length=3). Chain detection uses deterministic DFS over strong-link DAG.
  No Layer 0 modification. No execution. No automation. Operator-in-the-loop boundary preserved.
  Also added `cycle_ids` property to `RedTeamObserver` (L1-7 extension).
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.21 (2026-04-21): Layer 1 Stage L1-7 — Red Team Adapter (observation layer).
  New package `invar/adapters/redteam/` introduces `RedTeamObserver`. A read-only domain
  adapter that maps Invar persistence structures to red team observables without modifying any
  underlying state. Domain mapping (interpretation only): ExecutionWindow → "operation cycle",
  Gate identity → "artifact / signal", CausalField → "activity intensity", ProtoCausality →
  "shared infrastructure usage". Constructor takes five Invar objects (PearlArchive,
  TemporalGraph, ExecutionWindows, ProtoCausality, CausalField) and stores only references —
  derives everything on demand, stores nothing new. Interface: `activity(cycle_id)` → float
  ∈ [0,1] from CausalField; `shared_infra(a, b)` → frozenset of (workload_id, node_key,
  gate_id) gate keys from ProtoCausality; `strong_links(threshold=0.5)` → filtered
  weighted_links where weight ≥ threshold; `summary(cycle_id)` → dict with cycle_id, activity,
  num_artifacts, incoming_links, outgoing_links. All methods return independent copies.
  Unknown cycle_id → zeroed observables. Non-canonical: zero side-effects on construction or
  destruction. Deterministic: same input state → same outputs. Adapter is subordinate to core
  Invar — observation only, no mutation, no control, no feedback into Layer 0.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.20 (2026-04-21): Layer 1 Stage L1-6 — Causal Propagation Field (structural influence).
  New module `invar/persistence/causal_field.py` introduces `CausalField`. Converts proto-
  causal link weights into a per-window normalized influence signal. For each execution window,
  sums the weights of all incoming proto-causal links to produce a raw influence score; raw
  scores are normalized by the maximum raw value across all windows, yielding values ∈ [0,1].
  Windows with no incoming links receive 0.0 (head windows are always 0.0). The window with
  highest accumulated incoming influence receives 1.0. Interface: `build(causal, windows)`
  (classmethod, takes ProtoCausality + ExecutionWindows), `value(cycle_id)` → float ∈ [0,1]
  (0.0 for unknown cycle_id), `all()` → independent copy of {cycle_id → value} for every
  window. Non-canonical: no Pearl, Gate, or Layer 0 state is modified. Deterministic: same
  inputs → same field. This measures accumulated structural influence, not causation.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.19 (2026-04-21): Layer 1 Stage L1-5 — Causal Weighting (bounded link strength).
  Extends ProtoCausality in `invar/persistence/proto_causality.py` with two new methods:
  `weight(a, b)` returns the normalized strength of the proto-causal link between windows
  a and b as `|shared_gates(a,b)| / min(|gates(a)|, |gates(b)|)` ∈ [0.0, 1.0]; returns
  0.0 when no link exists or either cycle_id is unknown; checks both (a,b) and (b,a)
  orderings (symmetric). `weighted_links()` returns all links as ordered
  (earlier_cycle, later_cycle, weight) triples in the same order as links(). All weights are
  pre-computed at construction time — O(1) access per query. Weight = 1.0 when the smaller
  window is entirely contained in the larger; weight approaches 0.0 for minimal overlap relative
  to window size. Deterministic: same input → same weights. Non-canonical: no Pearl, Layer 0,
  or window state is modified. This measures continuity strength, not causation.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.18 (2026-04-21): Layer 1 Stage L1-4 — Proto-Causality (cross-window structural continuity).
  New module `invar/persistence/proto_causality.py` introduces `ProtoCausality`. Detects
  structural continuity between execution windows based on shared gate identity: two windows
  are linked when they share at least one (workload_id, node_key, gate_id) triple. Links are
  ordered pairs (earlier_cycle, later_cycle) by window position in ExecutionWindows ordering.
  Interface: `build(windows)` (classmethod), `links()` → ordered (a,b) pairs, `links_from(cid)`
  → later windows linked from this cycle, `links_to(cid)` → earlier windows linking into this
  cycle, `shared_gates(a, b)` → frozenset of gate keys (checks both orderings), `len(causal)`
  → link count. All methods return independent copies. Non-canonical: discarding the object has
  zero substrate effect. No Pearl fields modified. No Layer 0 physics touched. Deterministic:
  same ExecutionWindows input → identical links. This is structural continuity, not causation.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.17 (2026-04-21): Layer 1 Stage L1-3 — Execution Windows (cycle-based Pearl grouping).
  New module `invar/persistence/execution_window.py` introduces `ExecutionWindows`. Groups
  Pearls from a Pearl sequence by cycle_id into ordered execution windows. Windows are ordered
  by the minimum seq_id of their constituent Pearls. Within each window, Pearls are in seq_id
  order. Interface: `build(pearls)` (classmethod), `get(cycle_id)` → window or [], `of(pearl)`
  → window containing pearl or [], `next_window(cycle_id)` → following window or None,
  `prev_window(cycle_id)` → preceding window or None, `range(start, end)` → inclusive slice of
  windows, `validate()` (raises ValueError on: duplicate seq_ids across windows, non-monotone
  seq_ids within a window), `replay(cycle_id, engine)` (restores gate state from that window
  without ingest(), without _seq advance, without contributions, without firing listeners).
  All navigation methods return independent copies. Non-canonical: discarding the object has
  zero substrate effect. No Pearl fields modified. No Layer 0 physics touched.
  replay() uses Gate._restore_from_pearl_snapshot() — authorized invar/persistence/ scope.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.16 (2026-04-21): Layer 1 Stage L1-2 — Temporal Consistency Graph (Pearl sequencing).
  New module `invar/persistence/temporal_graph.py` introduces `TemporalGraph`. Turns an
  ordered Pearl sequence into a navigable, deterministic temporal structure. Each Pearl is a
  node; adjacent Pearls form a strict linear chain (p[i] → p[i+1]) in seq_id order.
  Interface: `build(pearls)` (class method constructor), `next(pearl)` → next or None,
  `prev(pearl)` → prev or None, `path(start, end)` → inclusive subchain list,
  `head()` / `tail()` → first/last Pearl, `contains(pearl)` → bool, `pearls` (sorted copy),
  `validate()` (raises ValueError on: duplicate seq_ids, non-monotone ordering, seq_id gaps),
  `replay(engine)` (restores gate state without ingest(), without _seq advance, without
  contributions). TemporalGraph sorts its input at construction (normalises any ordering).
  validate() enforces: strictly increasing, gapless (seq[i+1]==seq[i]+1), no duplicates, no
  cycles (monotonicity implies acyclicity). replay() uses Gate._restore_from_pearl_snapshot()
  — authorized invar/persistence/ scope. No Pearl fields modified. No Layer 0 physics touched.
  Non-canonical: discarding the graph has zero substrate effect.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.15 (2026-04-21): Layer 1 Stage L1-1 — Pearl canonical integration (truth without narration).
  New module `invar/persistence/pearl_archive.py` introduces `PearlArchive`. PearlArchive is
  the append-only canonical audit surface for Pearl records emitted by SupportEngine.
  Interface: `record(pearl)` (Pearl listener, enforces monotone seq_id — raises ValueError
  on violation), `pearls` (property returning independent copy in seq_id order),
  `replay_into(engine)` (approximate gate restoration: no ingest(), no listeners, no _seq
  advance, energy equivalent), `restore_into(engine)` (Pearl-native restoration: no
  SupportContributions, no _seq advance, gate accessible via engine.gate()).
  Both restoration paths use Gate._restore_from_pearl_snapshot() — authorized for
  invar/persistence/ scope only. Pearl schema is narration-free: no label, region, cluster,
  meaning, or interpretation fields. Pearl is a frozen dataclass; fields are raw state and
  IDs only. seq_id is strictly monotone per SupportEngine instance. Layer 0 physics
  (phi_R, phi_B, energy(), p(), collapse) are unaffected by archiving. Pearl = truth.
  Pearl is NOT explanation, NOT narration, NOT interpretation.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.14 (2026-04-21): Oscillation Addendum Stage 25 — final saturation control / global safety
  envelope. `effective_weight()` in `invar/core/topology_trace.py` extended with one new
  parameter: `sigma_saturate: float = 0.0`. Saturation formula: for M_raw > 1, compute
  `excess = M_raw − 1` then `M_sat = 1 + excess / (1 + σ·excess)`; for M_raw ≤ 1, pass
  through unchanged. This compresses aggregate reinforcement above unity without affecting
  attenuation. Properties: monotone for all σ ≥ 0 (dM_sat/d(excess) = 1/(1+σ·excess)² > 0);
  bit-identical to Stage 24 when σ=0; M_sat > 1 always for finite σ and M_raw > 1 (topology
  influence not nullified); M_sat → 1 from above as σ → ∞ (bounded). No new state variable,
  memory layer, or graph structure. Signal ordering κ_B << κ_R < κ_K < κ_C < κ_τ preserved;
  saturation compresses aggregate, not ordering. Gate.step() not modified. No canonical graph
  mutation, no support injection, no energy or collapse change, no Pearl creation, no
  narration. Stage 25 introduces global reinforcement safety, not removal of topology influence.
  Domain adapters remain subordinate to core Invar and may not replace Layer 0 truth semantics.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.13 (2026-04-21): Oscillation Addendum Stage 24 — controlled boundary influence.
  `effective_weight()` in `invar/core/topology_trace.py` extended with two new parameters:
  `b_ij: float = 0.0` (same-region boundary flag B_ij ∈ {0.0, 1.0}) and
  `kappa_boundary: float = 0.0` (boundary influence coefficient κ_B). The full weight
  formula is now: `w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock + κ_B·B)`.
  `b_ij` is derived from `float(CanonicalBoundary.same_region(i, j))` — a read-only advisory
  query; the boundary is never mutated by effective_weight(). Safety coefficient ordering:
  κ_B << κ_R < κ_K < κ_C < κ_τ (boundary is the absolute minimum signal, context only).
  With `kappa_boundary=0.0` (default), Stage 23 behavior is preserved bit-for-bit.
  Multiplier clamped ≥ 0 — effective weight always non-negative for non-negative w_ij.
  Gate.step() not modified. No canonical graph mutation, no Pearl creation, no narration.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.12 (2026-04-21): Oscillation Addendum Stage 23 — controlled canonical boundary introduction.
  New module `invar/core/canonical_boundary.py` introduces `CanonicalBoundary` and
  `AdvisorySnapshot`. CanonicalBoundary projects ProtoTopology regions into a deterministic
  advisory surface via `project(proto)`. Region labeling: label(R) = min(R) — lexicographically
  smallest node-id in the region. Interface: project(proto), region_of(node_id) → str|None,
  same_region(i,j) → bool (symmetric), region_sizes() → {label:int}, region_ids() → [str],
  nodes_in_region(node_id) → frozenset|None, contains_node(node_id) → bool, region_count(),
  node_count(), reset(), recompute(proto), snapshot() → AdvisorySnapshot. AdvisorySnapshot is
  a frozen dataclass (node_labels, region_sizes, region_members — all frozensets; to_dicts()).
  Snapshots are immutable and decoupled from the live boundary. project() reads ProtoTopology
  read-only; proto is not mutated. No canonical graph mutation, no support injection, no energy
  or collapse change, no Pearl creation, no narration. Gate.step() not modified. Introduces
  canonical VISIBILITY only, not canonical mutation. Proto-topology remains non-canonical.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.11 (2026-04-21): Oscillation Addendum Stage 22 — controlled proto-topology shaping.
  New module `invar/core/proto_topology.py` introduces `ProtoTopology` — a standalone
  non-canonical regional structure surface. Formation rule: `(i,j) ∈ K ⟹ (i,j) ∈ G_proto`;
  proto-regions are connected components of G_proto with |region| ≥ 2. Algorithm: undirected
  BFS over sorted node keys (deterministic). Interface: evaluate_edges(committed_edges),
  regions(), region_of(node_id), contains_node(node_id), region_count(), node_count(),
  reset(), recompute(edges), snapshot(). Proto-regions are a proposal surface only: no
  canonical graph mutation, no support injection, no energy or collapse change, no Pearl
  creation, no narration. Gate.step() not modified. Deterministic, symmetric (undirected
  adjacency), resettable with zero substrate effect. Canonical graph, Gate state, and
  Pearl remain completely unchanged by all ProtoTopology operations.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.10 (2026-04-21): Oscillation Addendum Stage 21 — controlled stabilization regulation.
  New `regulation_signal(k_ij, tau_hat) -> float` function in `invar/core/topology_trace.py`
  computing R_ij_lock = K_ij · τ̂_ij ∈ [0, 1]. `effective_weight()` extended with two new
  optional parameters: `r_ij_lock` (default 0.0) and `kappa_regulate` (default 0.0 — dormant).
  Full formula: `w_ij_eff = w_ij · max(0, 1 + κ_E·E + κ_τ·τ̂ + κ_C·I + κ_K·K − κ_R·R_lock)`.
  Multiplier clamped to ≥ 0 — effective weight never negative for non-negative w_ij. With
  kappa_regulate=0.0 or r_ij_lock=0.0, result is bit-identical to Stage 20. SAFETY ORDERING:
  κ_R < κ_K < κ_C < κ_τ — regulation is the weakest signal; it tempers over-stabilized structure
  but never dominates. Canonical graph unchanged. Gate.step() not modified. No Pearl created;
  no narration. Commitment, candidate, and trace sets read-only — regulation never mutates them.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.9 (2026-04-21): Oscillation Addendum Stage 20 — controlled commitment influence.
  `effective_weight()` in `invar/core/topology_trace.py` extended with two new optional
  parameters: `k_ij` (binary commitment flag, default 0.0) and `kappa_commitment` (default
  0.0 — dormant). Formula: `w_ij_eff = w_ij*(1 + κ_E*E + κ_τ*τ̂ + κ_C*I + κ_K*K)`.
  With kappa_commitment=0.0 or k_ij=0.0, result is bit-identical to Stage 19. Binary
  flag — not fuzzy. Transient only — never written back. SAFETY CONSTRAINT: κ_K << κ_C <<
  κ_τ must be preserved by callers; commitment reinforces only, never dominates. Canonical
  graph unchanged. Gate.step() not modified. No Pearl created; no narration. Removing
  commitment immediately removes its weight contribution (no hidden persistence).
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.8 (2026-04-21): Oscillation Addendum Stage 19 — controlled topology commitment.
  New module `invar/core/topology_commitments.py` introduces `TopologyCommitments` —
  a standalone non-canonical proto-topological commitment surface. Commitment rule:
  `(i,j) ∈ K ⟺ E_ij ≥ θ_E ∧ τ̂_ij ≥ θ_τ ∧ I_ij = 1` where I_ij is candidate
  membership from TopologyCandidates. Default thresholds theta_e=1.0, theta_tau=1.0
  (dormant). Commitment thresholds are stricter than candidate thresholds by convention.
  Candidate membership is a hard gate — no commitment without candidacy.
  Committed set is a proposal only: no canonical graph mutation, no support injection,
  no energy or collapse change, no Pearl creation, no narration. Gate.step() not
  modified. Symmetric, deterministic, resettable with zero substrate effect.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.7 (2026-04-20): Oscillation Addendum Stage 18 — controlled candidate influence.
  `effective_weight()` in `invar/core/topology_trace.py` extended with two new optional
  parameters: `i_ij` (binary candidate flag, default 0.0) and `kappa_candidate` (default 0.0
  — dormant). Formula: `w_ij_eff = w_ij*(1 + κ_E*E + κ_τ*τ̂ + κ_C*I)`. With
  kappa_candidate=0.0 or i_ij=0.0, result is bit-identical to Stage 17. Binary flag — not
  fuzzy. Transient only — never written back. Canonical graph unchanged. Gate.step() not
  modified. No Pearl created; no narration. κ_C should be weaker than κ_τ by convention.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.6 (2026-04-20): Oscillation Addendum Stage 17 — controlled topology consolidation.
  New module `invar/core/topology_candidates.py` introduces `TopologyCandidates` — a
  standalone non-canonical topology candidate surface. Membership rule:
  `(i,j) ∈ C ⟺ E_ij ≥ θ_E ∧ τ̂_ij ≥ θ_τ` where E_ij is current emergence and τ̂_ij is
  normalized trace history. Default thresholds theta_e=1.0, theta_tau=1.0 (dormant unless
  explicitly set lower). Candidate set is a proposal only — no canonical graph mutation,
  no support injection, no energy modification, no collapse change, no Pearl creation,
  no narration. Gate.step() not modified. Symmetric: (i,j)∈C ⟺ (j,i)∈C. Reversible:
  reset() / recompute() clear proposals without substrate effect. Deterministic.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.5 (2026-04-20): Oscillation Addendum Stage 16 — controlled trace influence.
  New `normalized(id_i, id_j) -> float` method on `TopologyTrace` returning
  `τ̂_ij = τ_ij / τ_max ∈ [0, 1]` (0.0 if eta_tau=0 — dormant). New module-level
  `effective_weight(w_ij, e_ij, tau_hat, kappa_e=0.0, kappa_tau=0.0) -> float` function
  computing `w_ij_eff = w_ij * (1 + κ_E * E_ij + κ_τ * τ̂_ij)` transiently.
  With kappa_e=0.0 and kappa_tau=0.0 (defaults), returns w_ij exactly (bit-identical).
  Canonical graph weights are never modified. Gate.step() is not modified.
  w_ij_eff ≥ 0 for non-negative inputs; bounded above by w_ij*(1+κ_E+κ_τ).
  Zero canonical weight stays zero. No Pearl created; no narration.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.4 (2026-04-20): Oscillation Addendum Stage 15 — controlled topology persistence.
  New module `invar/core/topology_trace.py` introduces `TopologyTrace` class — a standalone
  non-canonical bounded topology trace for gate pairs. Parameters: `eta_tau` (default 0.0 —
  dormant), `lambda_tau` (default 0.1). Trace update: `τ_ij += dt*(η_τ·E_ij − λ_τ·τ_ij)`,
  clamped to τ ≥ 0. Bounded: τ* ≤ η_τ/λ_τ. Symmetric: τ_ij = τ_ji. Decays without input.
  Gate.step() is not modified. Canonical gate state and graph weights are never touched.
  TopologyTrace is entirely separate — discarding it has zero effect on substrate state.
  Does not create Pearls or narration. Permanent graph mutation remains deferred.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.3 (2026-04-19): Oscillation Addendum Stage 14 — controlled stabilization / attractor bias.
  New `zeta_stabilize` field (default 0.0 — dormant). No new step() parameters — reuses `e_bar`
  from Stage 13. Effective natural frequency: `omega_eff = omega / max(1e-9, 1 + zeta_stabilize*e_bar)`.
  Transient only — not stored. With default `zeta_stabilize=0.0` or `e_bar=0.0`, behavior is
  bit-for-bit identical to Stage 13. High-emergence neighborhoods experience reduced intrinsic
  phase drift; coupling, resonance, and contradiction channels are unchanged. Sign of omega_eff
  always matches sign of omega — no polarity reversal. Denominator clamped ≥ 1e-9 for safety.
  Does not modify phi_R, phi_B, energy(), p(), or collapse logic. Does not create hard locking.
  Permanent topology mutation remains deferred. Pearl contains no narration; narration exists
  only at adapter/domain/context layers. Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.2 (2026-04-19): Oscillation Addendum Stage 13 — controlled feedback coupling.
  New `delta_feedback` field (default 0.0 — dormant). New `e_bar` parameter to `step()` (default 0.0).
  New module-level function `local_emergence_summary(gate, neighbors, t)` returns bounded
  neighborhood mean `Ē_i = (1/|N|)·Σ E_ij` ∈ [0,1] of `emergence_weight()` values.
  Phase evolution extended: `rho_eff = rho*(1 + delta_feedback*e_bar)` — transient only,
  not stored. With default `delta_feedback=0.0` or `e_bar=0.0`, behavior is bit-for-bit
  identical to Stage 12. High-emergence neighborhoods slightly strengthen resonance channel.
  Feedback does not modify phi_R, phi_B, energy(), p(), or collapse logic. Permanent topology
  mutation remains deferred. Pearl contains no narration; narration exists only at
  adapter/domain/context layers. Domain adapters remain subordinate to core Invar.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.1 (2026-04-19): Oscillation Addendum Stage 12 — controlled topology emergence.
  New `kappa_emergence` field (default 0.0 — dormant). New module-level function
  `emergence_weight(gate_i, gate_j, t) -> float` returning `E_ij = min(1, ā_ij·max(0, R_ij))`
  where `ā_ij = (aᵢ+aⱼ)/2` and `R_ij = cos(θⱼ⁽⁰⁾−θᵢ⁽⁰⁾)`. E_ij ∈ [0,1]. Symmetric.
  Effective weight computed by callers: `w_ij_eff = w_ij*(1 + κ·E_ij)`. Reversible:
  canonical wᵢⱼ is read-only; effective weight is a transient query, never written back.
  With default `kappa_emergence=0.0`, behavior is bit-for-bit identical to Stage 11.
  emergence_weight() does not modify phi_R, phi_B, theta, mu, a, energy(), p(), or collapse logic.
  No new step() parameters. Topology mutation remains deferred.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v2.0 (2026-04-18): Oscillation Addendum Stage 11 — bounded persistence reward.
  New `epsilon_persist` field (default 0.0 — dormant). No new step() parameters needed.
  Amplitude damping modulated: `ξ_eff = ξ / max(1e-6, 1 + epsilon_persist * P_i)` where
  `P_i = min(1, a * H(g))` is the local persistence score (computed internally in step()).
  P_i ∈ [0,1]; ξ_eff ≤ ξ; ξ_eff always positive. Coherent gates (high a, high H) decay
  more slowly. With default `epsilon_persist=0.0`, behavior is bit-for-bit identical to
  Stage 10. Persistence only active when `alpha != 0.0` (amplitude block live).
  Does not modify phi_R, phi_B, energy(), p(), or collapse logic. Does not inject support,
  create Pearls, or interact with narration or topology.
  Domain adapters remain subordinate to core Invar and may not replace Layer 0 truth semantics.
  Pearl contains no narration; narration exists only at adapter/domain/context layers.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.9 (2026-04-18): Oscillation Addendum Stage 10 — bounded resonance coupling.
  New `rho` field (default 0.0 — dormant). New `r_i` parameter to `step()` (default 0.0).
  Phase evolution extended: `theta += dt*(omega + coupling_term + mu_n + rho*r_i)`.
  New module-level function `resonance_signal(gate, neighbors, t)` computes bounded
  alignment signal `R_i = (1/|N|)·Σcos(θⱼ⁽⁰⁾ − θᵢ⁽⁰⁾)` ∈ [-1,1] using support-anchor
  phases only (not evolved theta — avoids feedback runaway). With default `rho=0.0`,
  behavior is bit-for-bit identical to Stage 9. Contradiction (C_i) and resonance (R_i)
  remain separate, non-interfering signals. O3 (phase continuity) remains Live.
  Phase changes alignment structure, not observed truth. phi_R, phi_B, energy(), p(),
  and collapse logic are never touched by step().
  Domain adapters are subordinate to core Invar — they may not replace Layer 0 truth semantics.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.8 (2026-04-18): Oscillation Addendum Stage 9 — cross-gate contradiction coupling.
  New `gamma` field (default 0.0 — dormant). New `c_i` parameter to `step()` (default 0.0).
  Contradiction-memory evolution extended: `mu += dt*(c_in + gamma*c_i − lambda_mu*mu_n)`.
  New module-level function `contradiction_signal(gate, neighbors, t)` computes bounded
  phase-mismatch signal `C_i = (1/|N|)·Σ|sin(θᵢ⁽⁰⁾ − θⱼ⁽⁰⁾)|` ∈ [0,1].
  With default `gamma=0.0`, behavior is bit-for-bit identical to Stage 8.
  Steady state: `μ* = (c_in + gamma·C_i) / lambda_mu`. O4 remains Live with broader coverage.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.7 (2026-04-19): Oscillation Addendum Stage 8 — local μ→a coupling.
  Amplitude equation extended to `a += dt*(alpha*H + beta*mu_n − xi*a)` where `mu_n` is
  the pre-update contradiction-memory snapshot (forward Euler consistency). New field `beta`
  (default 0.0 — dormant). Amplitude block still gated on `alpha != 0.0`. With default
  beta=0.0, output is bit-for-bit identical to Stage 7. Steady state:
  `a* = (alpha·H + beta·mu*) / xi`. O1 remains Live with stronger coverage.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.6 (2026-04-19): Oscillation Addendum Stage 7 — bounded amplitude evolution.
  `Gate.step()` now evolves `a` via `a += dt*(alpha*H(g) − xi*a)` when `alpha != 0.0`.
  New field `alpha` (default 0.0 — dormant). Steady state `a* = alpha·H(g)/xi`. `a` is
  clamped to ≥ 0. With default `alpha=0.0`, step() never touches `a` — fully backward
  compatible. O1 (bounded amplitude) is now Live.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.5 (2026-04-18): Oscillation Addendum Stage 6 — bounded contradiction-memory evolution.
  `Gate.step()` now evolves `mu` via `mu += dt*(c_in − lambda_mu*mu)` (forward Euler decay).
  New field `lambda_mu` (default 0.1). New `step()` parameter `c_in` (default 0.0).
  With defaults (`mu=0, c_in=0`), output is bit-for-bit identical to Stage 5. O4 (contradiction
  memory bounded) is now Live. Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.4 (2026-04-18): Oscillation Addendum Stages 1–5 applied to `gate.py` and `functional.py`.
  `Gate` extended with `theta` (memory phase offset, default 0.0), `a` (amplitude, default 1.0),
  `omega`, `xi`, `mu`. `Gate.step(dt)` evolves `theta`. `Gate.weighted_phase()` now uses
  `phase(t) + theta` as the dynamic phase — Stage 5 activation. With all defaults, existing
  outputs are bit-for-bit identical. `e_osc`, `p_res`, `local_L_star`, `global_L_star` added
  to `functional.py` (existing `local_L`/`global_L` unchanged). O-invariant family (O1–O6)
  defined; verified by `tests/test_layer0_o_invariants.py`.
  Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.
- v1.3 (2026-04-17): §5.9 updated from frozen-snapshot to base-state model (Option C).
  `_restore_from_pearl_snapshot()` now writes `_base_phi_R/_B/_ts`; accumulated(t) returns
  `phi_base(t) + Σ contribution(t)`. Single state model — no silent ignore of post-restoration
  contributions. GR test suite updated (GR2/GR3/GR5 semantics corrected; GR9 added).
- v1.2 (2026-04-17): Gate restoration surface added (§5.9). `Gate._restore_from_pearl_snapshot()`
  is the one authorized non-ingest write path. §4.1 updated to document the restricted restoration
  exception. §7 updated with restoration boundary rule.
- v1.1 (2026-04-16): Corrected coarse-grain Ψ̃_K formula to direct sum (§1.3, §5.5).
  Flagged Pearl coupling_propagated gap (§5.6). Flagged E_couple intersection-mass
  approximation (§5.7). Updated package path from `skg/` to `invar/`.

---

## 1. What the Core Is

The SKG core is a **transition-first field theory** implemented as a set of pure Python modules with no external dependencies beyond the standard library. It provides the mathematical substrate for all higher-level SKG components.

### 1.1 Canonical Objects

| Object | Type | Definition |
|--------|------|-----------|
| Transition `g` | Gate | Atomic unit. Carries `φ_R` (confirming), `φ_B` (blocking) evidence, decay class, timestamp. |
| Manifestation `Ωᵢ` | `(workload_id, node_key)` | Coherent aggregate of gates. Addressed by workload+node pair. |
| Gate probability | `p(g)` | `φ_R/(φ_R+φ_B)` if `φ_R+φ_B > ε`, else `0.5` (zero-observation prior). |
| Gate energy | `H(g)` | `H_binary(p(g))` — binary entropy. H=1 at zero obs, H=0 at collapse. |
| Gate phase | `θ(g)` | `(1 - p(g)) · π`. Range: `[0, π]`. θ=π/2 at p=0.5, θ=0 at p=1 (R), θ=π at p=0 (B). |
| Fiber tensor | `Ψᵢ` | `Σ_{g∈Ωᵢ} H(g)·e^(iθ(g))` — energy-weighted complex state vector. |
| Self-energy | `E_self(Ωᵢ)` | `Σ_{g∈Ωᵢ} H(g)` — total gate entropy. Upper bound on `|Ψᵢ|`. |
| Local incoherence | `C(Ψᵢ)` | `1 - |Ψᵢ|/E_self`. Range: `[0, 1]`. 0=aligned, 1=random phases. |
| Coupling | `Aᵢⱼ` | `∈ [0,1]`. 0.5 = maximum uncertainty, 0/1 = resolved. |
| Coupling energy | `H(Aᵢⱼ)` | `H_binary(Aᵢⱼ)` — entropy of the coupling. |

### 1.2 The Local Functional

```
L(Ψᵢ, Aᵢ) = E_self(Ωᵢ) + E_couple(Ωᵢ) + E_topo(Ωᵢ)
```

Every term is entropy of something:
- `E_self` = gate entropy (what we don't know about transitions in Ωᵢ)
- `E_couple` = coupling entropy (what we don't know about Ωᵢ's relationships)
- `E_topo` = curvature cost from cycle holonomy (structural uncertainty)

**Invariant:** L ≥ 0 always. L = 0 iff all gates collapsed and all couplings resolved.

### 1.3 The Canonical Equations

**State evolution (covariant):**
```
∇ₜΨᵢ = Σⱼ [ Aᵢⱼ · sin(π(1-p̄ᵢⱼ)) · e^(-ΔLᵢⱼ/T_eff) · e^(i(θⱼ-θᵢ)) ] Ψⱼ
```

**Coupling evolution (Hebbian + decoherence):**
```
∂ₜAᵢⱼ = η · Re[Ψᵢ*Ψⱼ] / (|Ψᵢ||Ψⱼ| + ε) - λ_K · Aᵢⱼ
```

**Temperature (coherence-modulated):**
```
T_eff(Ψ) = T₀ · (1 - r + ε)
r = |ΣᵢΨᵢ| / (Σᵢ|Ψᵢ| + ε)
```

**Observation functional:**
```
J_t(Ω) = λU·U_t(Ω) + λC·C_t(Ω) + λO·O_t(Ω) - λN·N_t(Ω)
Ω*_t = argmin_{Ω⊆T} J_t(Ω)
```

**Narrative update:**
```
W_{t+1}(g) = γM·M_t(g) + γI·I_t(g) + γR·R_t(g)
```

**Coarse-graining (scale invariance):**
```
Ψ̃_K = Σ_{i∈K} Ψᵢ                                          [direct sum — see §5.5]
ωᵢ  = E_self(Ωᵢ) / (Σⱼ E_self(Ωⱼ) + ε)                   [energy weights — used for Ã only]
Ã_KL = Σ_{i∈K,j∈L} ωᵢωⱼ·Aᵢⱼ / (Σ ωᵢωⱼ + ε)
```

The coarse-grained system satisfies the same equations. This is scale invariance.

**Note:** Earlier drafts of this document stated `Ψ̃_K = Σ ωᵢ·Ψᵢ` (normalized weighted average). That
formula cannot satisfy the closure property `C̃_K = 0` for a fully coherent multi-member cluster,
because a normalized weighted average of unit-amplitude vectors cannot equal the summed self-energy
E_K when n > 1. The correct formula is the direct sum, parallel to the gate-level definition
`Ψᵢ = Σ H(g)·e^(iθ(g))`. The ω weights are retained for the coupling computation Ã_KL only.
Invariant test `test_CG4_coherent_cluster_has_zero_coherence_cost` in `tests/test_layer0_invariants.py`
proves the direct sum is correct and the weighted average is not.

---

## 2. Module Boundary

### 2.1 What Is In Scope (`invar/core/`)

| Module | Role | Exports |
|--------|------|---------|
| `envelope.py` | Boundary interface — domain-agnostic ingestion | `ObsGateEnvelope`, `DispatchEnvelope`, `DecayClass` |
| `gate.py` | Gate physics — p, H, θ, state, collapse | `Gate`, `GateState`, `gate_p`, `gate_energy`, `gate_phase` |
| `support_engine.py` | Gate store — write path, Pearl emission | `SupportEngine`, `Pearl` — see §5.6 for gap vs Work 5 Addendum §7 |
| `gravity.py` | Scheduler — Ψᵢ, T_eff, dispatch | `GravityField`, `InstrumentProfile` |
| `field.py` | Coupling field — Aᵢⱼ, Hebbian, decay | `CouplingField`, `CouplingEdge` |
| `topology.py` | Graph structure — cycles, holonomy, β₁ | `CouplingGraph`, `Cycle` |
| `functional.py` | L computation — all energy terms | `local_L`, `global_L`, `delta_L` |
| `narrative.py` | Narrative state — W_t(g), M/I/R | `NarrativeState`, `NarrativeWeights` |
| `observation.py` | Observation selection — J(Ω), greedy_min_J | `J`, `greedy_min_J`, `JWeights` |
| `coarse_grain.py` | Coarse-graining — clusters, Ψ̃_K, Ã_KL | `CoarseGraining`, `CoarseField`, `CoarseManifold` |

### 2.2 What Is Out of Scope

The following are explicitly **not** part of the core:

- **Resonance/LLM pipeline** (`invar/resonance/`) — no imports from core to resonance
- **Forge/proposal generation** (`invar/forge/`) — forge consumes core outputs, never modifies core state
- **Domain toolchains** (`skg-*-toolchain/`) — use the envelope API only, never touch gates directly
- **Sensor/probe layer** (`invar/sensors/`) — sensors emit `ObsGateEnvelope` only
- **Discovery/scanning** (`skg-discovery/`) — discovery produces targets, not gate state
- **Gravity dispatch** (`skg-gravity/`) — consumes `DispatchEnvelope` from core, does not write back
- **UI/API layer** (`ui/`) — read-only consumers of core state
- **NVD/feed ingestors** (`feeds/`) — translate domain events to envelopes

**Rule:** Any code outside `invar/core/` communicates with the core exclusively through:
1. `ObsGateEnvelope` (write path — observations in)
2. `DispatchEnvelope` (read path — instrument targets out)
3. `SupportEngine.field_energy()`, `GravityField.*()` (query path — state queries out)

---

## 3. Invariants the Core Must Maintain

These are verified by `tests/test_core_invariants.py`. All 35 must pass before any core change is merged.

### H-Invariants (Gate Energy)

| ID | Invariant |
|----|-----------|
| H1 | `H(g) ∈ [0, 1]` always |
| H2 | `H(g) = 1` at zero observations (`φ_R = φ_B = 0`) |
| H3 | `H(g) → 0` as `|p - 0.5| → 0.5` (collapse limit) |
| H4 | `H(g) = 0` when gate state ≠ U (collapsed gate contributes zero field energy) |
| H5 | `H` is symmetric: `H(p) = H(1-p)` |

### C-Invariants (Coherence)

| ID | Invariant |
|----|-----------|
| C1 | `|Ψᵢ| ≤ E_self(Ωᵢ)` always (coherence bound) |
| C2 | `C(Ψᵢ) ∈ [0, 1]` always |
| C3 | `C(Ψᵢ) = 0` when all gates collapsed (zero energy → zero incoherence) |

### S-Invariants (Functional / Scale)

| ID | Invariant |
|----|-----------|
| S1 | `L ≥ 0` always |
| S2 | Adding a confirmed gate does not increase L (second law: L is non-increasing under confirming evidence) |
| S3 | `global_L ≥ 0` and contains `local_sum`, `topo`, `incoherence` terms |

### A-Invariants (Coupling Field)

| ID | Invariant |
|----|-----------|
| A1 | `Aᵢⱼ ∈ [0, 1]` always (clamped by field.step) |
| A2 | `A` initialized at 0.5 (maximum uncertainty) |
| A3 | Hebbian update on coherent manifestations moves A away from 0.5 |

### T-Invariants (Temperature / Coherence)

| ID | Invariant |
|----|-----------|
| T1 | `T_eff ∈ (0, T₀]` always |
| T2 | `T_eff = T₀` when `r = 0` (maximum disorder) |
| T3 | `T_eff → ε·T₀` when `r → 1` (full coherence, near-zero temperature) |

### G-Invariants (Observation Functional)

| ID | Invariant |
|----|-----------|
| G1 | `J` returns finite value for any valid Ω |
| G2 | `greedy_min_J` returns a slice with J ≤ J(∅) (greedy doesn't make things worse) |

### B-Invariants (Topology)

| ID | Invariant |
|----|-----------|
| B1 | `β₁ = |E| - |V| + k` (first Betti number formula) |
| B2 | Single edge: `β₁ = 0` |
| B3 | Triangle: `β₁ = 1` |
| B4 | Disconnected components: k increments correctly |

### N-Invariants (Narrative)

| ID | Invariant |
|----|-----------|
| N1 | `W(g) ∈ [0, 1]` always |
| N2 | `observe(g, ΔH)` increases M monotonically |
| N3 | `step_memory_decay()` decreases all M values |

### CG-Invariants (Coarse-Graining)

| ID | Invariant |
|----|-----------|
| CG1 | `|Ψ̃_K| ≤ E_K` (coherence bound holds at coarse level) |
| CG2 | `Ã_KL = Ã_LK` (symmetry) |
| CG3 | `Ã_KL ∈ [0, 1]` always |

### O-Invariants (Oscillation Addendum — Stages 1–5)

Verified by `tests/test_layer0_o_invariants.py`.
Reference: `docs/INVAR_LAYER0_OSCILLATION_ADDENDUM.md`.

| ID | Invariant | Status |
|----|-----------|--------|
| O1 | `a` stays bounded; `step()` never increases `a` (amplitude evolution deferred) | Active |
| O2 | `E_osc ≥ 0`; `L* = L + E_osc − P_res ≥ 0` always (`P_res ≤ E_self ≤ L`) | Active |
| O3 | `theta` (memory offset) evolves continuously via `step(dt)`; feeds into `weighted_phase()` live. With `omega=0, mu=0, coupling=0`: zero change to `theta`, hence zero change to output | **Live (Stage 5)** |
| O4 | `mu` is bounded; no hidden contradiction reservoir. Auto-evolution deferred | Partial |
| O5 | `step()` never modifies `phi_R`, `phi_B`, `_state`, or triggers collapse | Active |
| O6 | Coherence bound `|Ψᵢ| ≤ E_self(Ωᵢ)` holds for amplitude-scaled tensor | Active |

**Stage 5 activates dynamic phase only.** Amplitude evolution, contradiction-memory
evolution, resonance coupling, morphology, and narration remain deferred.

**Pearl contains no narration.** Narration lives at the adapter/domain/context layer only.

---

## 4. Domain Code Rules

Code outside `invar/core/` must obey these rules:

### 4.1 The Envelope Rule
**Domain code may not directly modify gate state.** All observations enter via `ObsGateEnvelope.add()` and `SupportEngine.ingest()`. The ingest path is the **only legal write path for domain and kernel code**.

```python
# CORRECT
env = ObsGateEnvelope(instrument_id='nmap', workload_id='cve', node_key='host-1')
env.add('g_reach', phi_R=0.85, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
pearls = engine.ingest(env)

# FORBIDDEN — never do this
engine._gates[('cve','host-1')]['g_reach']._phi_R = 0.85  # direct state mutation
```

**Restricted exception — Gate restoration surface:**

There is exactly **one** authorized non-ingest write path: `Gate._restore_from_pearl_snapshot()`.

This method is part of the Layer 0 Gate restoration surface (§5.9) and exists exclusively
for the persistence restoration boundary (`invar/persistence/`). It is not a domain API.
It may not be called from domain code, kernel code, sensor code, or any code outside
`invar/persistence/`. Calling it from any other module violates this contract.

Properties that must hold (enforced by the method itself):
- Target gate must have no existing contributions (fresh gate only)
- No `SupportContribution` is created
- No `ingest()` is called  
- No Pearl is emitted
- No listener is notified
- `SupportEngine._seq` is not advanced

The two authorized write paths are:

| Write path | Caller | Creates contribution | Emits Pearl |
|-----------|--------|---------------------|-------------|
| `SupportEngine.ingest(ObsGateEnvelope)` | Domain, sensor, adapter code | Yes | Yes |
| `Gate._restore_from_pearl_snapshot(...)` | `invar/persistence/` only | **No** | **No** |

### 4.2 The Query Rule
**Domain code reads state only through public API.** Private attributes (prefixed `_`) are internal to the core.

```python
# CORRECT
psi = gravity.fiber_tensor('cve', 'host-1')
energy = engine.field_energy()
targets = gravity.dispatch('cve', 'host-1', top_k=5)

# FORBIDDEN
engine._manifestations  # private store
gravity._field._A       # internal matrix
```

### 4.3 The No-Import Rule
**`invar/core/` modules must not import from outside `invar/core/`.** The core has no knowledge of resonance, forge, sensors, or any domain toolchain.

```python
# FORBIDDEN inside invar/core/
from skg.resonance import drafter       # resonance depends on core, not vice versa
from skg_gravity import exploit_dispatch  # domain toolchain, not core
import ollama                           # external service, not core physics
```

### 4.4 The Pearl Contract
**Pearls are read-only notifications.** Domain code may subscribe to pearls via `engine.add_listener()` but may not replay, suppress, or modify them.

```python
# CORRECT
def on_pearl(pearl):
    if pearl.is_fold:
        narrative.observe(pearl.gate_id, pearl.delta_H)

engine.add_listener(on_pearl)

# FORBIDDEN
pearl.delta_H = 0.0      # mutation
pearls.pop()             # suppression
```

---

## 5. Known Limitations (v1)

### 5.1 Thresholded Topology
The current `CouplingGraph.build()` uses a hard threshold: a coupling `Aᵢⱼ` becomes a graph edge only when `|Aᵢⱼ - 0.5| > 0.05`. This is a discrete approximation.

**Consequence:** β₁ cannot grow continuously. Coupling must cross the threshold before topology changes. The holonomy and curvature cost computations are exact once the edge exists, but the emergence of edges is threshold-gated.

**Known artifact:** Hebbian coupling on collapsed manifestations (Ψ=0) produces zero Hebbian signal. Collapsed hosts cannot bootstrap edges. β₁ > 0 requires concurrent uncertainty in linked manifestations.

**Planned fix (v2):** Replace binary edge detection with continuous topology using persistent homology or weighted Betti numbers. The `CouplingGraph` interface will remain stable.

### 5.2 Greedy J-Minimization
`greedy_min_J()` is a `(1-1/e)` approximation. It does not find the global optimum of `J(Ω)`. For workloads with high gate counts and strong correlations, the greedy solution may miss optimal observation slices.

**Planned fix (v2):** Simulated annealing or branch-and-bound for small gate sets; beam search for large ones.

### 5.3 No Temporal Decay in Coupling Field
The coupling field `Aᵢⱼ` decays uniformly (`decay()` applies global λ_K). There is no per-edge decay or age-weighted forgetting.

**Planned fix:** Per-edge decay class mirroring gate `DecayClass`.

### 5.4 Real-Valued Coupling
Current `Aᵢⱼ ∈ ℝ ∩ [0,1]`. The canonical formulation allows complex `Aᵢⱼ` to carry phase (U(1) gauge). Phase tracking is implemented in `CouplingEdge.phase` but the evolution equation uses only real Hebbian update.

**Planned fix (v3):** Full complex coupling with gauge-covariant Hebbian update.

### 5.5 Coarse-Grain Formula Correction (v1 → current)
**Conflict resolved.** Earlier contract drafts specified `Ψ̃_K = Σᵢ ωᵢ·Ψᵢ` (normalized weighted
average, weights summing to 1). Work 5 Addendum closure requirement and invariant test
`test_CG4_coherent_cluster_has_zero_coherence_cost` prove this is wrong: the closure property
`C̃_K = 1 - |Ψ̃_K|/E_K → 0` for a fully coherent cluster requires `|Ψ̃_K| → E_K`, which a
normalized weighted average cannot achieve for n > 1 members.

**Current runtime:** `Ψ̃_K = Σᵢ Ψᵢ` (direct sum). The ω weights are retained for `Ã_KL` only.

**Authority:** Work 5 Addendum §4 (scale invariance — same formula at every level). The direct sum
is the correct discretization of `Ψ(Ω) = ∫_Ω e^(iθ) dμ` over a cluster's union of manifestations.

**Compatibility note:** Any Layer 3+ code that called `CoarseManifold.Psi` and expected a
magnitude bounded by `max(|Ψᵢ|)` instead of `E_K` must be updated. The bound is now `|Ψ̃_K| ≤ E_K`.

### 5.6 Pearl `coupling_propagated` Field — RESOLVED

Work 5 Addendum §7, Definition 5 specifies Pearl as:

    P = (gate_id, node_key, workload_id,
         H_before, H_after,
         φ_R_before, φ_R_after,
         φ_B_before, φ_B_after,
         ts, instrument, cycle_id,
         coupling_propagated: [(node_key_B, gate_id, ΔP_B)])

**Status:** Implemented (2026-04-16). `Pearl.coupling_propagated` is populated when
`coupling_field` is passed to `SupportEngine.ingest()`.

**Propagation law:**

    ΔP_j = A_ij × Δφ

where Δφ is the dominant support change (R or B direction, whichever larger) at the
observed gate. A_ij is the current coupling strength from the caller-supplied field.

**Design:** `SupportEngine` accepts `coupling_field` via duck typing at call time. It does
not import `CouplingField` — preserving the GS3 invariant (write path has no knowledge of
read path types). `coupling_propagated` is empty when `coupling_field=None` (default).

**Invariant tests:** `TestCouplingPropagationInvariant::test_coupling_propagation_is_recorded_in_pearl`
and `test_coupling_propagation_empty_without_field` — both pass (92 total, 0 xfailed).

### 5.7 E_couple Uses Proxy for H-Weighted Intersection Mass
**Flagged mismatch — known approximation.**

Work 6 §4, Definition 7 specifies coupling energy as:

    E_couple(Ωᵢ, A) = Σⱼ≠ᵢ |Ωᵢ ∩ Ωⱼ|_H · H(Aᵢⱼ)
    |Ωᵢ ∩ Ωⱼ|_H = Σ_{g ∈ Ωᵢ ∩ Ωⱼ} H(g)   [H-weighted intersection mass]

The current `e_couple()` in `functional.py` uses:

    E_couple ≈ Σⱼ |Aᵢⱼ - 0.5| × 2 × H(Aᵢⱼ)

This substitutes `2|Aᵢⱼ - 0.5|` (coupling resolution) for `|Ωᵢ ∩ Ωⱼ|_H` (actual shared gate
entropy). The proxy is dimensionally compatible and has the correct extremes (0 at A=0.5, positive
when coupling is resolved), but it does not compute the intersection mass of shared gates between
two manifestations — which requires knowing which gate_ids are in both gate stores.

**Current runtime:** proxy formula. This is documented as a **bootstrap approximation**.
**Canonical path:** compute `|Ωᵢ ∩ Ωⱼ|_H` by intersecting the gate sets of Ωᵢ and Ωⱼ.
This requires `SupportEngine` to expose gate-set intersection, which it currently does not.

**Consequence:** `E_couple` may be systematically lower than canonical when coupling is high but
shared gate sets are small, or higher when coupling is low but gate sets overlap. This affects
`local_L` and `global_L` magnitudes but not their monotone behavior under confirming evidence.

**Authority:** Work 6 §4. This is a runtime approximation gap, not a physics error.
**Planned fix:** add `SupportEngine.shared_gates(wid_i, nk_i, wid_j, nk_j)` and use it in `e_couple`.

### 5.9 Gate Restoration Surface (updated 2026-04-17 — base-state model)

**Purpose:** Enable Pearl-native restoration (ET-G1B) without manufacturing synthetic observations.

**What restoration is:**
Direct canonical base-state reconstruction from archived Pearl fields. A restored Gate
establishes Pearl as its decaying base layer — not a frozen snapshot override. The base
decays from `Pearl.ts` using STRUCTURAL decay. Future live contributions accumulate on top.

**What restoration is not:**
- Not an observation (no `ObsGateEnvelope`, no instrument, no sensor)
- Not ingest (no `SupportContribution`, no `ingest()`, no Pearl emission)
- Not a synthetic observation manufactured from memory
- Not a frozen override that silently ignores subsequent contributions

**The state model (Option C / base-state model):**

    phi_total(t) = phi_base(t) + Σ contribution_phi(t)

where `phi_base(t) = phi_after · exp(-λ_STRUCTURAL · (t - ts))`. Pearl is the canonical
BASE STATE, not a final-state override. This is a single state model — no dual modes,
no silent ignore. Adding contributions after restoration always has an additive effect.

**Pearl sufficiency for base-state restoration:**

Pearl provides: `phi_R_after`, `phi_B_after`, `state_after`, `ts`.

These fields are **sufficient** for base-state restoration. Known approximation: the base
decays at STRUCTURAL rate regardless of the original contribution decay class (Pearl does
not carry per-contribution decay_class). This is conservative — STRUCTURAL is the slowest
decay class. All decay classes eventually decohere; STRUCTURAL approximation is safe.

**The Gate restoration method:**

```python
Gate._restore_from_pearl_snapshot(
    phi_R:  float,      # pearl.phi_R_after — sets _base_phi_R
    phi_B:  float,      # pearl.phi_B_after — sets _base_phi_B
    state:  GateState,  # pearl.state_after — initializes _state for decoherence detection
    ts:     float,      # pearl.ts          — sets _base_ts (decay origin)
) -> None
```

**Invariants it maintains:**

| Invariant | Status |
|-----------|--------|
| H1: `H(g) ∈ [0,1]` | Preserved — phi values from Pearl are valid |
| H4: `H=0` for collapsed | Preserved — state_after R/B → energy 0 at ts |
| No domain direct mutation | Preserved — method is infrastructure-only |
| `_contributions == []` | Preserved — precondition enforced by assertion |
| Single state model | Preserved — no dual-mode switching, no silent ignore |

**Behavior of restored gate:**

- `accumulated(t)` = `phi_base(t) + Σ contribution_phi(t)` — decays, evolves, additive
- `state(t)` computed from `accumulated(t)` via threshold — decoherence possible at far future
- `energy(t)` = `H_binary(p)` if U, else 0 — same computation as live gates
- Adding new contributions after restoration: always additive (single state model)

**Boundary rule:**

This method is prefixed `_restore_` to signal it is infrastructure-internal. It is called only
by `invar/persistence/PearlArchive.restore_into()`. No other code may call it. This rule is
documented here and in §7 below.

### 5.8 Alignment Corrections Applied (2026-04-16)

The following alignment pass was performed against the authority order in the task prompt.
No invariants were broken. All three required test suites pass (90 + 1 xfailed).

**TASK 1 — U normalization (documentation only):**
- Core layer (`invar/core/`) is already correct. U is NOT stored as a physics channel.
  `GateState.U` is the default absence-of-collapse state. `gate_p()` uses the zero-observation
  prior (p=0.5) when φ_R = φ_B = 0. No explicit phi_U in gate physics.
- `state_db.py` stores `phi_u` as a legacy mirror column for the gravity loop display.
  This is NOT a physics driver. Comment added to schema.
- `invar/kernel/adapters.py` emits `"U"` key in support_mapping — legacy kernel pattern.
  Comment added documenting the canonical path (emit only R/B; unknown → φ_R=φ_B=0).
  Runtime not changed to avoid breaking kernel tests outside the required suites.

**TASK 2 — Projection purity:**
- `invar/kernel/projections.py::ProjectionEngine.evaluate()` is a pure function.
  No state mutation, no side effects, no caching. Invariant holds.

**TASK 3 — Pearl semantics:**
- `invar/kernel/pearls.py::Pearl` docstring updated to align with Work 5 Definition 5.
  Pearl is explicitly NOT a generic log, database object, or full state snapshot.
  The canonical Pearl definition lives in `invar/core/support_engine.py`.

**TASK 4 — Energy usage audit (count-based special case):**
- All physics energy terms (E_self, E_couple, E_topo) confirmed entropy-based.
- `O_t(Ω) = α|Ω|` in `observation.py::O_term` uses a gate count. This is an intentional
  special case: observation cost must scale with cardinality, not information content.
  Comment added marking this as the count-based special case per §1.2 rule.

**TASK 5 — Failing invariant test:**
- `tests/test_core_invariants.py::TestCouplingPropagationInvariant::test_coupling_propagation_is_recorded_in_pearl`
  added as `@pytest.mark.xfail(strict=True)`. Defines expected Pearl shape from Work 5 §coupling_propagated.
  This test will fail until `Pearl.coupling_propagated` is implemented. Do not suppress it.

**TASK 6 — Inference audit:**
- Core layer: no inference leakage found. U_term uses H=1.0 for unobserved gates (correct
  zero-observation prior, not inference). C_term uses max-entropy defaults (correct physics).
- Kernel boundary: `invar/kernel/adapters.py` defaults confidence to 0.8 when not provided.
  This is a boundary heuristic at the adapter layer, not core inference.
  Comment added flagging this for future provenance surfacing.
- No probabilistic collapse, no LLM-generated truth, no heuristic state completion found.

---

## 6. Build Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 — Substrate | `gate.py`, `support_engine.py`, `envelope.py` | Complete |
| 2 — Field | `gravity.py`, `field.py`, `functional.py`, `topology.py` | Complete |
| 3 — Observer | `narrative.py`, `observation.py`, `coarse_grain.py` | Complete |
| 4 — Federation | Multi-node `CoarseGraining` over SKG deployments | Available (API ready) |

Phase 4 does not require new core code. It uses `CoarseGraining` with manifestation keys that are themselves SKG deployment addresses. The same equations govern federation-level dynamics.

---

## 7. Invariant Enforcement Contract

This section defines what operators and implementations working on this codebase must not do.

**Do not:**
- Add domain-specific logic to `invar/core/`. Core is domain-agnostic. CVE, AD, nginx are toolchain concerns.
- Import resonance, forge, or LLM backends into core modules.
- Add new gate state values. The three states (U, R, B) are canonical and complete.
- Replace `ObsGateEnvelope` with direct calls. The envelope is the contract surface.
- Modify the collapse threshold without updating all tests that depend on it.
- Introduce new energy terms to L without proving they are entropy of something.
- Add heuristics or ML-trained weights to the observation functional J. All weights in `JWeights` are operator-configurable, not learned.
- Expand coarse-graining to support non-energy-weighted schemes without updating the scale-invariance invariant tests.
- Add external API calls, filesystem access, or subprocess calls to any `invar/core/` module.
- Call `Gate._restore_from_pearl_snapshot()` from any module outside `invar/persistence/`. This method is not a general backdoor — it is the one authorized restoration surface and its caller is restricted to the persistence layer.
- Use `Gate._restore_from_pearl_snapshot()` on a gate that already has contributions. The restoration precondition (empty contributions) is enforced by assertion and must be respected.

**Do:**
- Add tests to `tests/test_core_invariants.py` when fixing any physics bug.
- Document deviations from the canonical equations in this file (Section 5).
- Bump the version in this file when any invariant or canonical equation changes.
- Use the demo (`demos/skg_core_demo.py`) as a regression check after core changes.

---

## 8. Test Checklist

Before merging any change to `invar/core/`:

```bash
# All must pass
python -m pytest tests/test_core_physics.py -v         # physics primitives
python -m pytest tests/test_core_invariants.py -v      # mathematical invariants
python -m pytest tests/test_layer0_invariants.py -v    # six Layer 0 structural invariants

# Demo must run without assertion errors
python demos/skg_core_demo.py
```

If a test fails because the physics changed intentionally, update the test and document the change in Section 5 of this file.

---

## 9. Glossary

| Term | Meaning |
|------|---------|
| Gate `g` | Atomic transition. Binary question with evidence accumulation. |
| Manifestation `Ωᵢ` | Coherent aggregate of gates, addressed by `(workload_id, node_key)`. |
| Fiber tensor `Ψᵢ` | Energy-weighted complex state of a manifestation. |
| Pearl | Notification emitted when a gate state changes. |
| Fold event | Pearl with ΔH > 0: new evidence contradicts prior direction. |
| Collapse | Gate transitions from U to R or B. Energy drops to zero. |
| Hebbian | Coupling update rule: `Aᵢⱼ` grows when Ψᵢ and Ψⱼ align. |
| β₁ | First Betti number: number of independent coupling cycles. |
| Holonomy | Phase accumulated around a coupling cycle. |
| Coarse-graining | Aggregating manifestations into clusters. Same equations at higher scale. |
| Narrative | Operator-supplied attention bias on the observation functional. |
| T_eff | Effective temperature: decreases as global coherence increases. |
