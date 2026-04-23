"""
invar.core.ingest_sequencer
===========================
Single-threaded ingest sequencer for deterministic canonical write ordering.

Provides an explicit FIFO ordering surface above SupportEngine. Envelopes are
submitted with a monotone queue_seq and flushed to SupportEngine in submission
order. submit() never calls engine.ingest() — processing is always explicit via
flush(). queue_seq is separate from Pearl.seq_id and is not truth-bearing.

submit_batch() accepts a collection of envelopes from potentially different
instruments, sorts them by a deterministic lexicographic key
(instrument_id, workload_id, node_key, first_gate_id), then submits
them in that sorted order. This removes wall-clock and callback-arrival
dependence for multi-instrument ingest cycles. Ordering metadata is
operational only — not canonical, not truth-bearing.

Scope: single-process, single-SupportEngine-instance. Not distributed. Not
persisted. Not a replay engine. Not a scheduler of projections.

ref: docs/INVAR_EXECUTION_TEMPORAL_CONTRACT.md §ET-G4 (Resolved)
ref: docs/INVAR_EXECUTION_TEMPORAL_CONTRACT.md §ET-G2 (Resolved)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Iterable, List, Tuple

from .envelope import ObsGateEnvelope
from .support_engine import Pearl, SupportEngine, _SEQUENCER_WRITE_TOKEN


def _envelope_sort_key(envelope: ObsGateEnvelope) -> Tuple[str, str, str, str]:
    """Deterministic, wall-clock-free sort key for multi-instrument batch ordering.

    Key components (all lexicographic string comparison):
      1. instrument_id   — primary: order by source instrument
      2. workload_id     — secondary: tiebreak within same instrument
      3. node_key        — tertiary: tiebreak within same instrument+workload
      4. first_gate_id   — quaternary: tiebreak within same manifestation
                           ("" if envelope has no contributions)

    This key is operational metadata. It determines queue position only.
    It is not stored, not emitted, and does not affect canonical state.
    """
    first_gate = envelope.contributions[0].gate_id if envelope.contributions else ""
    return (envelope.instrument_id, envelope.workload_id, envelope.node_key, first_gate)


@dataclass
class _QueueItem:
    queue_seq: int            # monotone submission order; NOT Pearl.seq_id
    envelope: ObsGateEnvelope
    coupling_field: Any = None


class IngestSequencer:
    """
    Explicit FIFO ordering surface for canonical ingest.

    submit() enqueues an envelope and returns its queue_seq. It does NOT call
    engine.ingest() — substrate state is unchanged until flush() is called.

    flush() processes all pending envelopes in FIFO (submission) order and
    returns the concatenated Pearl list.

    Usage::

        seq = IngestSequencer(engine)
        seq.submit(env_a)
        seq.submit(env_b)
        pearls = seq.flush()   # env_a processed before env_b

    Or with the convenience method::

        pearls = seq.submit_and_flush(env)

    For multi-instrument batches with deterministic ordering::

        pearls = seq.submit_batch([env_a, env_b, env_c])
    """

    def __init__(self, engine: SupportEngine) -> None:
        self._engine = engine
        self._queue_seq: int = 0
        self._pending: Deque[_QueueItem] = deque()

    def submit(self, envelope: ObsGateEnvelope, coupling_field: Any = None) -> int:
        """Queue one envelope for ingest. Returns its queue_seq (starts at 1).

        Does NOT call engine.ingest(). Substrate state is unchanged.
        queue_seq is monotone per IngestSequencer instance and is separate
        from Pearl.seq_id.
        """
        self._queue_seq += 1
        self._pending.append(_QueueItem(
            queue_seq=self._queue_seq,
            envelope=envelope,
            coupling_field=coupling_field,
        ))
        return self._queue_seq

    def submit_batch(
        self,
        envelopes: Iterable[ObsGateEnvelope],
        coupling_field: Any = None,
    ) -> List[Pearl]:
        """Sort a multi-instrument envelope collection deterministically, then flush.

        Ordering rule:
          Sort by (instrument_id, workload_id, node_key, first_gate_id) —
          all lexicographic string comparison. This ordering is:
          - deterministic: same input set → same output order on every run
          - wall-clock-free: does not use ts, time.time(), or arrival timing
          - callback-free: does not depend on thread/asyncio scheduling
          - non-canonical: the sort key is discarded after ordering

        All envelopes in the batch are submitted (in sorted order) and then
        immediately flushed. Returns the concatenated Pearl list.

        ET-G3 idempotency still applies: duplicate content is deduplicated by
        SupportEngine regardless of whether it arrives via submit() or submit_batch().

        Scope of the guarantee:
          - Applies to the set of envelopes passed in this single call.
          - Does not order across separate submit_batch() calls.
          - Does not provide cross-process or distributed ordering.
          - Direct engine.ingest() calls bypass this guarantee entirely.
        """
        sorted_envs = sorted(envelopes, key=_envelope_sort_key)
        for env in sorted_envs:
            self.submit(env, coupling_field)
        return self.flush()

    def flush(self) -> List[Pearl]:
        """Process all pending envelopes in FIFO (submission) order.

        Returns the concatenated Pearl list from all processed envelopes.
        The queue is empty after this call. Each envelope is passed to
        engine.ingest() in submission order; ET-G3 idempotency applies.
        """
        pearls: List[Pearl] = []
        while self._pending:
            item = self._pending.popleft()
            result = self._engine.ingest(
                item.envelope, item.coupling_field,
                _sequencer_token=_SEQUENCER_WRITE_TOKEN,
            )
            pearls.extend(result)
        return pearls

    def submit_and_flush(
        self, envelope: ObsGateEnvelope, coupling_field: Any = None
    ) -> List[Pearl]:
        """Submit one envelope and immediately flush. Returns its Pearls.

        Semantically equivalent to submit() followed by flush() when no
        other envelopes are pending.
        """
        self.submit(envelope, coupling_field)
        return self.flush()

    @property
    def pending_count(self) -> int:
        """Number of envelopes queued but not yet flushed."""
        return len(self._pending)
