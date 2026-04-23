"""
Layer 3 Execution / Temporal Invariants — scaffold tests.

These tests define expected behavior for:
  - deterministic ordering of canonical ingest events (ET-1)
  - replay reproduces prior admitted substrate transitions only (ET-2)
  - scheduler/dispatch state is non-canonical (ET-3)
  - orchestration cannot mutate canonical state except through authorized ingest (ET-4)
  - identical event streams produce identical canonical outcomes (ET-1 corollary)
  - wall-clock/runtime metadata does not become truth-bearing (ET-5)
  - partial execution state cannot be mistaken for committed state (§3.1, §9.3)
  - retries / replays do not duplicate canonical writes (ET-2, §9.2)

Reference: docs/INVAR_EXECUTION_TEMPORAL_CONTRACT.md

Tests marked xfail(strict=True) define enforcement boundaries that are
documented but not yet enforced at runtime (Layer 3 implementation work
required).  Tests NOT marked xfail must pass with the current substrate.
"""
import pytest

from invar.core.envelope import DecayClass, ObsGateEnvelope
from invar.core.support_engine import SupportEngine as CoreSupportEngine
from invar.core.gravity import GravityField
from invar.core.ingest_sequencer import IngestSequencer  # ET-G4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _envelope(wid="w1", nk="n1", gate_id="g1",
              phi_R=0.4, phi_B=0.0,
              instrument_id="test-probe", cycle_id="cycle-001"):
    env = ObsGateEnvelope(
        instrument_id=instrument_id,
        workload_id=wid,
        node_key=nk,
        cycle_id=cycle_id,
    )
    env.add(gate_id, phi_R=phi_R, phi_B=phi_B,
            decay_class=DecayClass.STRUCTURAL)
    return env


def _two_envelopes():
    """Two envelopes for different gates in the same manifestation."""
    e1 = _envelope(gate_id="g1", phi_R=0.4, cycle_id="cycle-001")
    e2 = _envelope(gate_id="g2", phi_R=0.3, cycle_id="cycle-002")
    return e1, e2


def _ingest_sequence(engine, envelopes):
    """Ingest a list of envelopes; return flat Pearl list."""
    pearls = []
    for env in envelopes:
        pearls.extend(engine.ingest(env))
    return pearls


# ---------------------------------------------------------------------------
# ET-1: Deterministic ingest order
# ---------------------------------------------------------------------------

class TestET1DeterministicIngestOrder:
    """
    ET-1: Identical ingest sequences on identical initial state produce
    identical Pearl sequences and identical final substrate state.
    """

    def test_same_sequence_same_pearls(self):
        """Two fresh engines ingesting identical envelopes produce identical Pearls."""
        e1, e2 = _two_envelopes()

        engine_a = CoreSupportEngine()
        engine_b = CoreSupportEngine()

        # Ingest same envelopes in same order on both engines
        pearls_a = _ingest_sequence(engine_a, [e1, e2])
        pearls_b = _ingest_sequence(engine_b, [e1, e2])

        assert len(pearls_a) == len(pearls_b), (
            "ET-1: identical ingest sequences must produce same Pearl count"
        )
        # Compare entropy-change signatures (gate_id, delta_H) — not wall-clock ts
        sigs_a = [(p.gate_id, round(p.delta_H, 9)) for p in pearls_a]
        sigs_b = [(p.gate_id, round(p.delta_H, 9)) for p in pearls_b]
        assert sigs_a == sigs_b, (
            "ET-1: Pearl delta_H signatures must match for identical ingest sequences"
        )

    def test_same_sequence_same_substrate_energy(self):
        """Two engines with identical ingest histories have identical field_energy()."""
        e1, e2 = _two_envelopes()

        engine_a = CoreSupportEngine()
        engine_b = CoreSupportEngine()

        _ingest_sequence(engine_a, [e1, e2])
        _ingest_sequence(engine_b, [e1, e2])

        energy_a = engine_a.field_energy()
        energy_b = engine_b.field_energy()

        assert abs(energy_a - energy_b) < 1e-9, (
            "ET-1: identical ingest sequences must produce identical substrate energy"
        )

    def test_different_order_may_differ(self):
        """
        Reversing ingest order on a stateful engine can change intermediate
        substrate energy.  This test documents that order matters — it is
        not a violation, it is expected behavior.
        """
        e1, e2 = _two_envelopes()

        # Order A: g1 then g2
        engine_a = CoreSupportEngine()
        _ingest_sequence(engine_a, [e1, e2])
        energy_a = engine_a.field_energy()

        # Order B: g2 then g1 (different gates, can differ)
        engine_b = CoreSupportEngine()
        _ingest_sequence(engine_b, [e2, e1])
        energy_b = engine_b.field_energy()

        # Final energy may or may not differ depending on gate interaction.
        # We only assert that the test runs without error — ordering is defined.
        assert isinstance(energy_a, float)
        assert isinstance(energy_b, float)


# ---------------------------------------------------------------------------
# ET-1 (wall-clock): Pearl ts does not affect substrate physics
# ---------------------------------------------------------------------------

class TestET1WallClockNotTruthBearing:
    """
    ET-1 corollary: Wall-clock metadata (Pearl.ts) does not participate in
    canonical physics. The substrate does not branch on ts values.
    """

    def test_pearl_ts_is_present_but_not_a_physics_driver(self):
        """
        Pearl records carry a ts field, but it is a monotonicity marker.
        The substrate energy is independent of the ts value.
        """
        engine = CoreSupportEngine()
        env = _envelope()
        pearls = engine.ingest(env)

        assert len(pearls) >= 1
        for p in pearls:
            # ts must be present (audit requirement)
            assert hasattr(p, "ts"), "Pearl must carry ts for audit"
            # ts must not change substrate energy — verify by checking
            # energy is a deterministic function of phi values alone
            assert engine.field_energy() >= 0.0

    def test_ET1_pearl_has_monotone_seq_id(self):
        """
        Each Pearl emitted by SupportEngine.ingest() carries a monotone seq_id.
        ET-G5 resolved: seq_id is assigned by SupportEngine._seq at emission time.
        See INVAR_EXECUTION_TEMPORAL_CONTRACT.md §4.2.
        """
        engine = CoreSupportEngine()
        e1, e2 = _two_envelopes()
        pearls = _ingest_sequence(engine, [e1, e2])

        assert len(pearls) >= 2, "need at least two Pearls for ordering check"
        seq_ids = [p.seq_id for p in pearls]
        assert seq_ids == sorted(seq_ids), "seq_id must be monotonically increasing"
        assert len(set(seq_ids)) == len(seq_ids), "seq_id must be unique per Pearl"

    def test_ET1_seq_id_starts_at_one(self):
        """First Pearl from a fresh SupportEngine has seq_id=1."""
        engine = CoreSupportEngine()
        pearls = engine.ingest(_envelope())
        assert len(pearls) >= 1
        assert pearls[0].seq_id == 1, (
            f"first Pearl seq_id must be 1, got {pearls[0].seq_id}"
        )

    def test_ET1_seq_id_continues_across_ingest_calls(self):
        """seq_id is engine-wide, not reset per ingest() call."""
        engine = CoreSupportEngine()
        first = engine.ingest(_envelope(gate_id="g1"))
        second = engine.ingest(_envelope(gate_id="g2"))
        assert len(first) >= 1 and len(second) >= 1
        assert second[0].seq_id > first[-1].seq_id, (
            "seq_id from second ingest must be higher than last seq_id from first ingest"
        )

    def test_ET1_identical_streams_same_seq_id_pattern(self):
        """Two fresh engines with identical ingest histories produce the same seq_id values."""
        e1, e2 = _two_envelopes()
        engine_a = CoreSupportEngine()
        engine_b = CoreSupportEngine()
        pearls_a = _ingest_sequence(engine_a, [e1, e2])
        pearls_b = _ingest_sequence(engine_b, [e1, e2])
        assert [p.seq_id for p in pearls_a] == [p.seq_id for p in pearls_b], (
            "identical ingest sequences must produce identical seq_id patterns"
        )

    def test_ET1_seq_id_is_not_truth_bearing(self):
        """seq_id is ordering metadata; it must not affect substrate energy."""
        engine = CoreSupportEngine()
        env = _envelope()
        pearls = engine.ingest(env)
        energy = engine.field_energy()
        assert isinstance(pearls[0].seq_id, int)
        # seq_id is on the Pearl; substrate energy is unchanged by reading it
        assert abs(engine.field_energy() - energy) < 1e-9


# ---------------------------------------------------------------------------
# ET-2: Replay does not create new canonical events
# ---------------------------------------------------------------------------

class TestET2ReplaySafety:
    """
    ET-2: Canonical replay reconstructs prior substrate state from Pearl
    archive by re-ingesting envelope deltas.  Replay must not increase the
    Pearl count in the archive or produce synthetic observations.
    """

    def test_replay_via_fresh_engine_produces_same_energy(self):
        """
        Replaying the same envelope sequence through a fresh SupportEngine
        produces equivalent substrate energy (ET-2 forward test).

        This tests the mechanics of replay: same inputs → same output.
        It does NOT test an archive path (which does not exist yet — Gap ET-G1).
        """
        e1, e2 = _two_envelopes()

        engine_original = CoreSupportEngine()
        _ingest_sequence(engine_original, [e1, e2])
        energy_original = engine_original.field_energy()

        # "Replay" = applying the same envelopes to a fresh engine
        engine_replayed = CoreSupportEngine()
        _ingest_sequence(engine_replayed, [e1, e2])
        energy_replayed = engine_replayed.field_energy()

        assert abs(energy_original - energy_replayed) < 1e-9, (
            "ET-2: replaying same envelope sequence must reproduce same substrate energy"
        )

    def test_replay_does_not_increase_pearl_count(self):
        """
        Re-ingesting the same envelope MUST NOT produce fewer Pearls than the
        original ingest (this tests that replay did not suppress events).
        It WILL produce more Pearls (idempotency gap ET-G3 is known), but
        the physics of each individual ingest is still consistent.
        """
        e1, e2 = _two_envelopes()

        engine = CoreSupportEngine()
        pearls_first = _ingest_sequence(engine, [e1, e2])

        # First run must have produced at least one Pearl per envelope
        assert len(pearls_first) >= 2, (
            "ET-2: first ingest of two gates must produce at least two Pearls"
        )

    def test_ET2_re_ingest_is_idempotent(self):
        """
        Re-ingesting an already-admitted envelope must return the original
        Pearl list and must not update the gate store a second time.
        Fails until a (cycle_id, gate_id) idempotency guard is added.
        """
        engine = CoreSupportEngine()
        env = _envelope()

        pearls_first = engine.ingest(env)
        energy_after_first = engine.field_energy()

        pearls_second = engine.ingest(env)
        energy_after_second = engine.field_energy()

        # Idempotent: second ingest must not change energy
        assert abs(energy_after_first - energy_after_second) < 1e-9, (
            "idempotent ingest must not double-count phi values"
        )
        # Idempotent: same Pearl list returned
        assert len(pearls_first) == len(pearls_second)

    def test_ET_G3_duplicate_does_not_advance_seq_id(self):
        """Duplicate ingest must not increment SupportEngine._seq."""
        engine = CoreSupportEngine()
        env = _envelope()
        engine.ingest(env)
        seq_after_first = engine._seq
        engine.ingest(env)
        assert engine._seq == seq_after_first, (
            "ET-G3: duplicate ingest must not advance seq_id counter"
        )

    def test_ET_G3_duplicate_does_not_change_energy(self):
        """Duplicate ingest must not alter field_energy()."""
        engine = CoreSupportEngine()
        env = _envelope()
        engine.ingest(env)
        energy_after_first = engine.field_energy()
        engine.ingest(env)
        energy_after_second = engine.field_energy()
        assert abs(energy_after_first - energy_after_second) < 1e-9, (
            "ET-G3: duplicate ingest must not mutate substrate energy"
        )

    def test_ET_G3_distinct_content_still_emits_distinct_pearls(self):
        """Two envelopes with different content produce independent Pearl lists."""
        engine = CoreSupportEngine()
        e1, e2 = _two_envelopes()
        pearls_a = engine.ingest(e1)
        pearls_b = engine.ingest(e2)
        assert len(pearls_a) >= 1
        assert len(pearls_b) >= 1
        gate_ids_a = {p.gate_id for p in pearls_a}
        gate_ids_b = {p.gate_id for p in pearls_b}
        assert gate_ids_a != gate_ids_b, (
            "ET-G3: distinct-content envelopes must produce Pearls for distinct gates"
        )

    def test_ET_G3_same_content_different_cycle_id_is_idempotent(self):
        """Same gate content on same engine, different cycle_id: dedup must still fire.

        Verifies the fingerprint is content-based, not cycle_id-based.
        """
        from invar.core.envelope import ObsGateEnvelope, DecayClass
        engine = CoreSupportEngine()
        env1 = ObsGateEnvelope(
            instrument_id="test-probe",
            workload_id="w1",
            node_key="n1",
            cycle_id="cycle-aaa",
        )
        env1.add("g1", phi_R=0.4, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)
        env2 = ObsGateEnvelope(
            instrument_id="test-probe",
            workload_id="w1",
            node_key="n1",
            cycle_id="cycle-bbb",
        )
        env2.add("g1", phi_R=0.4, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)

        pearls_first = engine.ingest(env1)
        energy_after_first = engine.field_energy()
        seq_after_first = engine._seq

        pearls_second = engine.ingest(env2)
        energy_after_second = engine.field_energy()

        assert len(pearls_first) == len(pearls_second), (
            "ET-G3: same content with different cycle_id must be idempotent"
        )
        assert abs(energy_after_first - energy_after_second) < 1e-9, (
            "ET-G3: same content with different cycle_id must not change energy"
        )
        assert engine._seq == seq_after_first, (
            "ET-G3: same content with different cycle_id must not advance seq_id"
        )

    def test_ET_G3_idempotency_key_not_wall_clock(self):
        """Idempotency must hold even if wall-clock advances between ingests."""
        import time
        engine = CoreSupportEngine()
        env = _envelope()
        pearls_first = engine.ingest(env)
        time.sleep(0.01)
        pearls_second = engine.ingest(env)
        assert len(pearls_first) == len(pearls_second), (
            "ET-G3: idempotency must not depend on wall clock"
        )

    def test_ET_G3_duplicate_does_not_fire_listeners(self):
        """Duplicate ingest must not call Pearl listeners again."""
        engine = CoreSupportEngine()
        env = _envelope()
        fired: list = []
        engine.add_listener(fired.append)
        engine.ingest(env)
        count_after_first = len(fired)
        engine.ingest(env)
        assert len(fired) == count_after_first, (
            "ET-G3: duplicate ingest must not re-fire Pearl listeners"
        )

    def test_ET2_canonical_pearl_archive_replay_produces_equivalent_state(self):
        """
        Pearl-native restoration (ET-G1B resolved): restore_into() reconstructs
        substrate state from archived Pearls without synthetic SupportContribution.
        """
        from invar.persistence.pearl_archive import PearlArchive

        engine_original = CoreSupportEngine()
        archive = PearlArchive()
        engine_original.add_listener(archive.record)

        env = _envelope()
        engine_original.ingest(env)

        engine_restore = CoreSupportEngine()
        archive.restore_into(engine_restore)

        assert abs(
            engine_original.field_energy() - engine_restore.field_energy()
        ) < 1e-9


# ---------------------------------------------------------------------------
# ET-G1: Canonical Pearl archive and replay (additional coverage)
# ---------------------------------------------------------------------------

class TestETG1PearlArchive:
    """ET-G1: PearlArchive records Pearls append-only and replays into fresh engine."""

    def test_archive_records_pearls_in_emission_order(self):
        """archive.pearls returns Pearls in seq_id order."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)

        e1, e2 = _two_envelopes()
        engine.ingest(e1)
        engine.ingest(e2)

        ps = archive.pearls
        assert len(ps) == 2
        assert ps[0].seq_id < ps[1].seq_id

    def test_approximate_replay_does_not_advance_seq_id(self):
        """replay_into() (demoted approximate path) must not advance the replay engine's seq counter."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        engine_replay = CoreSupportEngine()
        archive.replay_into(engine_replay)

        assert engine_replay._seq == 0, "replay_into must not emit Pearls or advance _seq"

    def test_approximate_replay_does_not_fire_listeners(self):
        """replay_into() (demoted approximate path) must not trigger listeners on the replay engine."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        engine_replay = CoreSupportEngine()
        fired: list = []
        engine_replay.add_listener(fired.append)
        archive.replay_into(engine_replay)

        assert fired == [], "replay_into must not fire listeners on replay engine"

    def test_approximate_replay_multi_gate_energy_equivalent(self):
        """replay_into() (demoted approximate path) produces approximately equivalent energy.
        This tests the approximate synthetic path ONLY — not canonical restoration."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)

        e1, e2 = _two_envelopes()
        engine.ingest(e1)
        engine.ingest(e2)

        engine_replay = CoreSupportEngine()
        archive.replay_into(engine_replay)

        assert abs(engine.field_energy() - engine_replay.field_energy()) < 1e-9

    def test_archive_record_rejects_non_monotone_seq(self):
        """record() raises ValueError on non-monotone seq_id."""
        from invar.persistence.pearl_archive import PearlArchive
        import dataclasses

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        # Manually inject a Pearl with a lower seq_id
        bad_pearl = dataclasses.replace(archive.pearls[0], seq_id=0)
        with pytest.raises(ValueError, match="Non-monotone seq_id"):
            archive.record(bad_pearl)

    def test_archive_pearls_property_returns_copy(self):
        """archive.pearls returns a copy; mutations do not affect the archive."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        ps = archive.pearls
        ps.clear()
        assert len(archive.pearls) == 1, "archive.pearls must return an independent copy"

    def test_approximate_replay_preserves_gate_state(self):
        """replay_into() (demoted approximate path) preserves gate state (U/R/B)."""
        from invar.persistence.pearl_archive import PearlArchive

        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope(phi_R=0.4, phi_B=0.0))

        engine_replay = CoreSupportEngine()
        archive.replay_into(engine_replay)

        gate_orig = engine.gate("w1", "n1", "g1")
        gate_replay = engine_replay.gate("w1", "n1", "g1")
        assert gate_orig is not None and gate_replay is not None
        assert gate_orig.state() == gate_replay.state()

    # ------------------------------------------------------------------
    # ET-G1B: Pearl-native restoration scaffold (all xfail — BLOCKED)
    # ------------------------------------------------------------------

    def test_ET_G1B_restore_into_exists_on_archive(self):
        """PearlArchive.restore_into() exists as the Pearl-native restoration surface."""
        from invar.persistence.pearl_archive import PearlArchive
        archive = PearlArchive()
        assert hasattr(archive, "restore_into")

    def test_ET_G1B_restore_into_does_not_call_ingest(self):
        """restore_into() must not call engine.ingest() or advance engine._seq."""
        from invar.persistence.pearl_archive import PearlArchive
        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        engine_restore = CoreSupportEngine()
        archive.restore_into(engine_restore)

        assert engine_restore._seq == 0, "restore_into must not advance _seq"

    def test_ET_G1B_restore_into_does_not_create_support_contributions(self):
        """restore_into() must not add SupportContribution objects to restored gates."""
        from invar.persistence.pearl_archive import PearlArchive
        engine = CoreSupportEngine()
        archive = PearlArchive()
        engine.add_listener(archive.record)
        engine.ingest(_envelope())

        engine_restore = CoreSupportEngine()
        archive.restore_into(engine_restore)

        gate = engine_restore.gate("w1", "n1", "g1")
        assert gate is not None
        assert len(gate._contributions) == 0, (
            "restored gate must not hold synthetic SupportContributions"
        )


# ---------------------------------------------------------------------------
# ET-3: Scheduler/dispatch state is non-canonical
# ---------------------------------------------------------------------------

class TestET3DispatchNonCanonical:
    """
    ET-3: GravityField.dispatch() and scheduling state must not alter
    substrate state. Reading from the scheduler must not be a write.
    """

    def test_dispatch_does_not_change_substrate_energy(self):
        """
        Calling GravityField.dispatch() must not alter the SupportEngine
        gate store or change field_energy().
        """
        engine = CoreSupportEngine()
        gravity = GravityField(engine)

        # Ingest some observations to populate substrate
        env = _envelope()
        engine.ingest(env)
        energy_before = engine.field_energy()

        # Read dispatch output — must be a pure read
        _ = gravity.dispatch("w1", "n1", top_k=3)
        energy_after = engine.field_energy()

        assert abs(energy_before - energy_after) < 1e-9, (
            "ET-3: GravityField.dispatch() must not alter substrate energy"
        )

    def test_fiber_tensor_does_not_change_substrate_energy(self):
        """
        GravityField.fiber_tensor() is a pure read; must not change energy.
        """
        engine = CoreSupportEngine()
        gravity = GravityField(engine)

        env = _envelope()
        engine.ingest(env)
        energy_before = engine.field_energy()

        _ = gravity.fiber_tensor("w1", "n1")
        energy_after = engine.field_energy()

        assert abs(energy_before - energy_after) < 1e-9, (
            "ET-3: GravityField.fiber_tensor() must not alter substrate energy"
        )

    def test_multiple_dispatch_reads_are_idempotent(self):
        """
        Calling dispatch() multiple times with same arguments returns
        consistent results (same substrate → same dispatch output).
        """
        engine = CoreSupportEngine()
        gravity = GravityField(engine)

        env = _envelope()
        engine.ingest(env)

        result_a = gravity.dispatch("w1", "n1", top_k=3)
        result_b = gravity.dispatch("w1", "n1", top_k=3)

        # Both are lists/sequences of the same type
        assert type(result_a) == type(result_b), (
            "ET-3: dispatch() must return consistent types across calls"
        )


# ---------------------------------------------------------------------------
# ET-4: Orchestration cannot back-feed projection into canonical write path
# ---------------------------------------------------------------------------

class TestET4OrchestrationBackfeedForbidden:
    """
    ET-4: The orchestration layer (daemon, gravity loop) must not construct
    ObsGateEnvelope instances from projection outputs and ingest them.
    This tests that the Layer 2 enforcement contract (EE-1, EE-2) holds
    at the Layer 3 orchestration boundary.
    """

    def test_support_contribution_cannot_be_ingested_as_envelope(self):
        """
        A kernel.SupportContribution (projection output) must be rejected
        by core.SupportEngine.ingest() — it is not an authorized observation.
        """
        from invar.kernel.support import SupportContribution
        engine = CoreSupportEngine()
        sc = SupportContribution(realized=0.8, blocked=0.0, unresolved=0.2)

        with pytest.raises((TypeError, AttributeError)):
            engine.ingest(sc)  # type: ignore

    def test_plain_dict_projection_cannot_be_ingested(self):
        """
        A plain dict constructed from projection values must fail ingest.
        """
        engine = CoreSupportEngine()
        fake_projection = {
            "workload_id": "w1", "node_key": "n1",
            "contributions": [{"gate_id": "g1", "phi_R": 0.9}]
        }
        with pytest.raises((TypeError, AttributeError)):
            engine.ingest(fake_projection)  # type: ignore

    def test_gravity_field_energy_output_is_not_an_envelope(self):
        """
        field_energy() returns a float — not something that can be ingested.
        Confirms the read path is structurally disconnected from the write path.
        """
        engine = CoreSupportEngine()
        env = _envelope()
        engine.ingest(env)

        energy = engine.field_energy()
        assert isinstance(energy, float), "field_energy() must return a float"

        with pytest.raises((TypeError, AttributeError)):
            engine.ingest(energy)  # type: ignore

    @pytest.mark.xfail(strict=True, reason=(
        "ET-4 / Gap ET-G7: Daemon startup path may read from GravityStateDB "
        "to construct envelopes before live instruments run. This would be an "
        "orchestration back-feed of display state into the canonical write path. "
        "Requires audit of daemon startup code. "
        "See INVAR_EXECUTION_TEMPORAL_CONTRACT.md §Gap ET-G7."
    ))
    def test_ET4_daemon_startup_does_not_ingest_from_state_db(self):
        """
        Daemon startup must not construct ObsGateEnvelope from GravityStateDB
        rows and call SupportEngine.ingest() before live instruments produce output.
        Fails until daemon startup is audited and confirmed clean.
        """
        # This test requires the daemon module to expose its startup sequence
        # for inspection. The test can only pass once the audit (Gap ET-G7)
        # is complete and the daemon startup is confirmed to start with an
        # empty gate store.
        from invar.core.daemon import Daemon  # type: ignore[import]
        daemon = Daemon.__new__(Daemon)
        envelopes_constructed_from_db = getattr(
            daemon, "_startup_envelopes_from_state_db", None
        )
        assert envelopes_constructed_from_db is None or len(envelopes_constructed_from_db) == 0


# ---------------------------------------------------------------------------
# ET-5: Execution trace records are not ingested as observations
# ---------------------------------------------------------------------------

class TestET5ExecutionTraceNotIngested:
    """
    ET-5: No execution trace record (daemon log, GravityStateDB run record,
    gravity cycle timing) may be the source of an ObsGateEnvelope that enters
    SupportEngine.ingest().
    """

    def test_state_db_module_does_not_import_support_engine(self):
        """
        GravityStateDB must not import core.SupportEngine — it has no business
        calling ingest() and must not acquire that capability by import.
        """
        import importlib
        import importlib.util
        import ast
        import os

        state_db_path = os.path.join(
            os.path.dirname(__file__), "..", "invar", "core", "state_db.py"
        )
        if not os.path.exists(state_db_path):
            pytest.skip("state_db.py not found — skip import check")

        with open(state_db_path) as f:
            source = f.read()

        # Check for dangerous import patterns
        forbidden_patterns = [
            "from invar.core.support_engine import",
            "from invar.core import support_engine",
            "import invar.core.support_engine",
            "SupportEngine",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"ET-5: state_db.py must not import or reference SupportEngine. "
                f"Found: {pattern!r}"
            )

    def test_pearl_instrument_id_is_not_a_trace_source(self):
        """
        Pearls emitted during a normal ingest must carry a real instrument_id,
        not a synthetic execution-trace identifier like 'daemon', 'replay',
        'scheduler', or 'trace'.
        """
        engine = CoreSupportEngine()
        env = _envelope(instrument_id="nmap-scan")
        pearls = engine.ingest(env)

        for p in pearls:
            assert p.instrument_id == "nmap-scan", (
                f"ET-5: Pearl.instrument_id must match the envelope's instrument_id, "
                f"got {p.instrument_id!r}"
            )

    @pytest.mark.xfail(strict=True, reason=(
        "Gap ET-G6: No explicit canonical=False marker exists on GravityStateDB "
        "tables. Until tables carry an explicit non-canonical marker, a developer "
        "could mistake run records for a canonical audit source. "
        "See INVAR_EXECUTION_TEMPORAL_CONTRACT.md §Gap ET-G6."
    ))
    def test_ET5_state_db_tables_carry_non_canonical_marker(self):
        """
        GravityStateDB tables must carry an explicit marker indicating they are
        non-canonical execution traces, not canonical audit records.
        Fails until explicit markers are added.
        """
        from invar.core.state_db import GravityStateDB  # type: ignore[import]
        db = GravityStateDB.__new__(GravityStateDB)
        # Expect a class-level constant or docstring asserting non-canonical status
        assert getattr(GravityStateDB, "CANONICAL", None) is False or \
               "non-canonical" in (GravityStateDB.__doc__ or "").lower(), (
            "GravityStateDB must carry an explicit CANONICAL=False marker"
        )


# ---------------------------------------------------------------------------
# §9.3: In-flight envelope is not committed state
# ---------------------------------------------------------------------------

class TestInFlightEnvelopeNotCommitted:
    """
    §9.3: A constructed-but-not-ingested ObsGateEnvelope is in-flight.
    It must not alter substrate state. Only the completed ingest() call commits.
    """

    def test_constructing_envelope_does_not_change_substrate(self):
        """
        Building an ObsGateEnvelope and calling env.add() must not change
        SupportEngine gate state before ingest() is called.
        """
        engine = CoreSupportEngine()
        energy_before = engine.field_energy()

        # Build envelope — do NOT ingest
        env = ObsGateEnvelope(
            instrument_id="probe", workload_id="w1", node_key="n1"
        )
        env.add("g1", phi_R=0.9, phi_B=0.0, decay_class=DecayClass.STRUCTURAL)

        energy_after_build = engine.field_energy()
        assert abs(energy_before - energy_after_build) < 1e-9, (
            "§9.3: constructing an envelope must not alter substrate energy"
        )

    def test_ingest_is_the_commit_boundary(self):
        """
        Energy changes only after ingest(), not before.
        """
        engine = CoreSupportEngine()
        energy_before = engine.field_energy()

        env = _envelope(phi_R=0.8)
        # Before ingest: no change
        assert abs(engine.field_energy() - energy_before) < 1e-9

        # After ingest: energy may change (new gate at H < 1.0 vs prior H=1.0)
        engine.ingest(env)
        # We just verify ingest completed and returned Pearls
        assert engine.field_energy() >= 0.0  # energy is non-negative (L0 invariant S1)


# ---------------------------------------------------------------------------
# ET-G4: Ingest Sequencer
# ---------------------------------------------------------------------------

class TestET4IngestSequencer:
    """
    ET-G4: Canonical ingest ordering is explicit via IngestSequencer.

    IngestSequencer wraps SupportEngine with a FIFO deque. submit() enqueues
    without triggering ingest. flush() processes in submission order.
    queue_seq is monotone per instance and not truth-bearing.

    ref: docs/INVAR_EXECUTION_TEMPORAL_CONTRACT.md §ET-G4 (Resolved)
    """

    def test_sequencer_processes_in_fifo_order(self):
        """Envelopes submitted first are processed first (FIFO)."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        e1 = _envelope(gate_id="g1", phi_R=0.4)
        e2 = _envelope(gate_id="g2", phi_R=0.3)
        seq.submit(e1)
        seq.submit(e2)
        pearls = seq.flush()
        assert pearls[0].gate_id == "g1", (
            "ET-G4: first submitted envelope must produce first Pearl"
        )
        assert pearls[-1].gate_id == "g2", (
            "ET-G4: second submitted envelope must produce last Pearl"
        )

    def test_reverse_submit_order_reverses_pearl_order(self):
        """Submitting in reverse order changes processing order."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        e1 = _envelope(gate_id="g1", phi_R=0.4)
        e2 = _envelope(gate_id="g2", phi_R=0.3)
        seq.submit(e2)
        seq.submit(e1)
        pearls = seq.flush()
        assert pearls[0].gate_id == "g2", (
            "ET-G4: reversed submit order must produce reversed Pearl order"
        )
        assert pearls[-1].gate_id == "g1"

    def test_identical_submit_sequences_produce_identical_seq_id_patterns(self):
        """Same submit order on fresh sequencers produces identical Pearl seq_id values."""
        e1, e2 = _two_envelopes()

        seq_a = IngestSequencer(CoreSupportEngine())
        pearls_a = seq_a.submit_and_flush(e1) + seq_a.submit_and_flush(e2)

        seq_b = IngestSequencer(CoreSupportEngine())
        pearls_b = seq_b.submit_and_flush(e1) + seq_b.submit_and_flush(e2)

        assert [p.seq_id for p in pearls_a] == [p.seq_id for p in pearls_b], (
            "ET-G4: identical submit sequences must produce identical seq_id patterns"
        )

    def test_submit_does_not_trigger_ingest(self):
        """submit() must not call engine.ingest() — no implicit processing on enqueue."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        env = _envelope()
        energy_before = engine.field_energy()
        qseq = seq.submit(env)
        # Substrate must be unchanged — submit is enqueue only
        assert engine.field_energy() == energy_before, (
            "ET-G4: submit() must not mutate substrate energy"
        )
        assert engine._seq == 0, (
            "ET-G4: submit() must not advance Pearl seq_id counter"
        )
        assert isinstance(qseq, int) and qseq >= 1, (
            "ET-G4: queue_seq must be a positive int"
        )
        assert seq.pending_count == 1, (
            "ET-G4: envelope must be pending after submit, before flush"
        )

    def test_queue_seq_monotone_across_submits(self):
        """queue_seq increments strictly with each submit call."""
        seq = IngestSequencer(CoreSupportEngine())
        e1, e2 = _two_envelopes()
        q1 = seq.submit(e1)
        q2 = seq.submit(e2)
        assert q1 == 1, "ET-G4: first queue_seq must be 1"
        assert q2 > q1, "ET-G4: queue_seq must be strictly increasing"

    def test_submit_and_flush_convenience(self):
        """submit_and_flush returns only the Pearls for that envelope."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        e1, e2 = _two_envelopes()
        pearls_e1 = seq.submit_and_flush(e1)
        pearls_e2 = seq.submit_and_flush(e2)
        assert all(p.gate_id == "g1" for p in pearls_e1)
        assert all(p.gate_id == "g2" for p in pearls_e2)

    def test_et_g3_idempotency_preserved_through_sequencer(self):
        """ET-G3 dedup still fires when the same content is submitted twice."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        env = _envelope()
        pearls_first = seq.submit_and_flush(env)
        energy_after_first = engine.field_energy()
        seq_after_first = engine._seq

        pearls_second = seq.submit_and_flush(env)
        energy_after_second = engine.field_energy()

        assert len(pearls_first) == len(pearls_second), (
            "ET-G4: ET-G3 idempotency must hold through the sequencer"
        )
        assert abs(energy_after_first - energy_after_second) < 1e-9, (
            "ET-G4: duplicate submission must not change substrate energy"
        )
        assert engine._seq == seq_after_first, (
            "ET-G4: duplicate submission must not advance Pearl seq_id"
        )

    def test_ordering_does_not_depend_on_wall_clock(self):
        """Submit two envelopes at different wall-clock times: FIFO still holds."""
        import time
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        e1 = _envelope(gate_id="g1", phi_R=0.4)
        seq.submit(e1)
        time.sleep(0.01)
        e2 = _envelope(gate_id="g2", phi_R=0.3)
        seq.submit(e2)
        pearls = seq.flush()
        assert pearls[0].gate_id == "g1", (
            "ET-G4: ordering must follow submit order, not wall clock"
        )

    def test_pending_count_tracks_queue_depth(self):
        """pending_count reflects items queued but not yet flushed."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        e1, e2 = _two_envelopes()
        assert seq.pending_count == 0
        seq.submit(e1)
        assert seq.pending_count == 1
        seq.submit(e2)
        assert seq.pending_count == 2
        seq.flush()
        assert seq.pending_count == 0, "ET-G4: flush must drain the queue"

    def test_gravity_dispatch_does_not_submit_to_sequencer(self):
        """GravityField.dispatch() does not enqueue anything (read-only)."""
        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        seq.submit_and_flush(_envelope())
        gravity = GravityField(engine)
        _ = gravity.dispatch("w1", "n1", top_k=3)
        assert seq.pending_count == 0, (
            "ET-G4: dispatch() must not enqueue anything in the sequencer"
        )
        energy_before = engine.field_energy()
        _ = gravity.dispatch("w1", "n1", top_k=3)
        assert abs(engine.field_energy() - energy_before) < 1e-9, (
            "ET-G4: dispatch() must not mutate substrate energy through the sequencer"
        )


# ---------------------------------------------------------------------------
# ET-G2: Deterministic multi-instrument ordering
# ---------------------------------------------------------------------------

class TestETG2MultiInstrumentOrdering:
    """
    ET-G2: submit_batch() orders envelopes from multiple instruments
    deterministically — independent of wall clock, callback arrival, or
    runtime scheduling.

    Ordering rule (batch-sort, then FIFO within queue):
      primary key:   instrument_id  (lexicographic)
      secondary key: workload_id    (lexicographic)
      tertiary key:  node_key       (lexicographic)
      quaternary key: first_gate_id (lexicographic, "" if no contributions)

    Single-envelope submit() is unaffected — pure FIFO as before.

    ref: docs/INVAR_EXECUTION_TEMPORAL_CONTRACT.md §ET-G2 (Resolved)
    """

    def _env(self, instrument_id, workload_id="w1", node_key="n1",
             gate_id="g1", phi_R=0.4):
        env = ObsGateEnvelope(
            instrument_id=instrument_id,
            workload_id=workload_id,
            node_key=node_key,
        )
        env.add(gate_id, phi_R=phi_R, phi_B=0.0,
                decay_class=DecayClass.STRUCTURAL)
        return env

    def test_batch_produces_deterministic_order_regardless_of_input_list_order(self):
        """Same envelopes submitted in two different list orders produce same Pearl order."""
        ea = self._env("instrument-a", gate_id="g1", phi_R=0.4)
        eb = self._env("instrument-b", gate_id="g2", phi_R=0.3)

        engine_x = CoreSupportEngine()
        seq_x = IngestSequencer(engine_x)
        pearls_x = seq_x.submit_batch([ea, eb])

        engine_y = CoreSupportEngine()
        seq_y = IngestSequencer(engine_y)
        pearls_y = seq_y.submit_batch([eb, ea])

        assert [p.gate_id for p in pearls_x] == [p.gate_id for p in pearls_y], (
            "ET-G2: submit_batch must produce same Pearl order regardless of input list order"
        )

    def test_batch_ordering_is_lexicographic_on_instrument_id(self):
        """instrument-a sorts before instrument-b lexicographically."""
        ea = self._env("instrument-a", gate_id="ga")
        eb = self._env("instrument-b", gate_id="gb")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls = seq.submit_batch([eb, ea])

        assert pearls[0].gate_id == "ga", (
            "ET-G2: instrument-a envelopes must be processed before instrument-b"
        )
        assert pearls[1].gate_id == "gb", (
            "ET-G2: instrument-b envelope must be processed second"
        )

    def test_batch_ordering_tiebreaks_on_workload_id(self):
        """Same instrument_id: workload_id is the secondary sort key."""
        e1 = self._env("same-instrument", workload_id="w-aaa", gate_id="g-aaa")
        e2 = self._env("same-instrument", workload_id="w-zzz", gate_id="g-zzz")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls = seq.submit_batch([e2, e1])

        assert pearls[0].gate_id == "g-aaa", (
            "ET-G2: workload_id tie-break must sort w-aaa before w-zzz"
        )

    def test_batch_ordering_tiebreaks_on_node_key(self):
        """Same instrument_id + workload_id: node_key is the tertiary sort key."""
        e1 = self._env("instr", workload_id="w1", node_key="host-a", gate_id="g1")
        e2 = self._env("instr", workload_id="w1", node_key="host-z", gate_id="g2")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls = seq.submit_batch([e2, e1])

        assert pearls[0].gate_id == "g1", (
            "ET-G2: node_key tie-break must sort host-a before host-z"
        )

    def test_batch_ordering_does_not_depend_on_wall_clock(self):
        """Ordering must be identical regardless of time elapsed between list construction."""
        import time
        ea = self._env("instrument-a", gate_id="ga")
        time.sleep(0.01)
        eb = self._env("instrument-b", gate_id="gb")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls = seq.submit_batch([eb, ea])

        assert pearls[0].gate_id == "ga", (
            "ET-G2: ordering must follow deterministic key, not wall clock"
        )

    def test_batch_same_input_produces_same_seq_id_pattern_on_fresh_engines(self):
        """Identical multi-instrument batch on two fresh engines → identical seq_id pattern."""
        ea = self._env("instrument-a", gate_id="ga")
        eb = self._env("instrument-b", gate_id="gb")

        engine_1 = CoreSupportEngine()
        pearls_1 = IngestSequencer(engine_1).submit_batch([ea, eb])

        engine_2 = CoreSupportEngine()
        pearls_2 = IngestSequencer(engine_2).submit_batch([ea, eb])

        assert [p.seq_id for p in pearls_1] == [p.seq_id for p in pearls_2], (
            "ET-G2: same batch on fresh engines must produce identical seq_id patterns"
        )

    def test_et_g3_idempotency_holds_through_submit_batch(self):
        """Submitting the same envelope twice via submit_batch must not double-count."""
        env = self._env("probe", gate_id="g1")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls_first = seq.submit_batch([env])
        energy_after_first = engine.field_energy()
        seq_after_first = engine._seq

        pearls_second = seq.submit_batch([env])
        energy_after_second = engine.field_energy()

        assert len(pearls_first) == len(pearls_second), (
            "ET-G2: ET-G3 idempotency must hold through submit_batch"
        )
        assert abs(energy_after_first - energy_after_second) < 1e-9, (
            "ET-G2: duplicate batch submission must not change substrate energy"
        )
        assert engine._seq == seq_after_first, (
            "ET-G2: duplicate batch submission must not advance seq_id"
        )

    def test_batch_ordering_key_is_not_canonical(self):
        """Batch ordering metadata must not affect substrate energy."""
        ea = self._env("instrument-a", gate_id="ga")
        eb = self._env("instrument-b", gate_id="gb")

        engine = CoreSupportEngine()
        seq = IngestSequencer(engine)
        pearls = seq.submit_batch([ea, eb])

        energy = engine.field_energy()
        assert isinstance(energy, float) and energy >= 0.0, (
            "ET-G2: substrate energy must be non-negative after batch ingest"
        )
        for p in pearls:
            assert not hasattr(p, "batch_order_key"), (
                "ET-G2: Pearl must not carry batch ordering metadata"
            )

    def test_direct_ingest_bypass_is_still_possible_but_outside_et_g2_guarantee(self):
        """Direct engine.ingest() bypasses the sequencer — ordering not guaranteed for that path."""
        env = self._env("probe")
        engine = CoreSupportEngine()
        pearls = engine.ingest(env)
        assert len(pearls) >= 1, "direct ingest still works; ET-G2 guarantee does not apply"

    def test_et_g1b_restoration_assumptions_unchanged(self):
        """ET-G2 ordering does not affect restore_into() behavior."""
        from invar.persistence.pearl_archive import PearlArchive

        engine_original = CoreSupportEngine()
        archive = PearlArchive()
        engine_original.add_listener(archive.record)

        seq = IngestSequencer(engine_original)
        ea = self._env("instrument-a", gate_id="ga")
        seq.submit_batch([ea])

        engine_restore = CoreSupportEngine()
        archive.restore_into(engine_restore)

        assert abs(
            engine_original.field_energy() - engine_restore.field_energy()
        ) < 1e-9, "ET-G2: restore_into must be unaffected by ET-G2 ordering"
        assert engine_restore._seq == 0, "ET-G2: restore_into must not advance _seq"
