"""
invar.persistence.execution_window
====================================
Cycle-based grouping of Pearls into ordered execution windows.

ExecutionWindows partitions a Pearl sequence by cycle_id.  Each unique
cycle_id becomes one window; windows are ordered by the minimum seq_id of
the Pearls they contain.  Within each window Pearls are in seq_id order.

    window-A  [p0, p1, p2]  → cycle_id="cycle-A"
    window-B  [p3, p4]      → cycle_id="cycle-B"
    window-C  [p5]          → cycle_id="cycle-C"

API:
    windows.of(pearl)                → window (list of Pearls) containing pearl
    windows.get(cycle_id)            → window for that cycle_id
    windows.next_window(cycle_id)    → window after cycle_id in ordering, or None
    windows.prev_window(cycle_id)    → window before cycle_id in ordering, or None
    windows.range(start, end)        → windows from start to end inclusive
    windows.validate()               → raises ValueError on any consistency violation
    windows.replay(cycle_id, engine) → restore gate state from that window

Consistency invariants enforced by validate():
    - Each Pearl appears in exactly one window (keyed by cycle_id)
    - Within each window seq_ids are strictly increasing
    - Windows are internally ordered by seq_id
    - No Pearl is a member of two different windows (guaranteed by cycle_id keying)

Safety:
    - No Pearl fields are modified
    - No Layer 0 physics are touched
    - Non-canonical: discarding this object has zero substrate effect
    - replay() uses Gate._restore_from_pearl_snapshot() (authorized scope)
    - replay() does not call engine.ingest(); engine._seq is not advanced
    - replay() does not create SupportContribution objects

Usage:
    from invar.persistence.pearl_archive import PearlArchive
    from invar.persistence.execution_window import ExecutionWindows

    archive = PearlArchive()
    engine.add_listener(archive.record)
    # ... ingest observations ...

    windows = ExecutionWindows.build(archive.pearls)
    windows.validate()

    w = windows.get("cycle-A")
    nxt = windows.next_window("cycle-A")
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from invar.core.gate import Gate
from invar.core.support_engine import Pearl, SupportEngine


class ExecutionWindows:
    """
    Cycle-based grouping of Pearls into ordered execution windows.

    Each window corresponds to exactly one cycle_id.  Windows are ordered
    by the minimum seq_id of their constituent Pearls.
    """

    def __init__(self, pearls: List[Pearl]) -> None:
        # Group Pearls by cycle_id
        grouped: Dict[str, List[Pearl]] = defaultdict(list)
        for pearl in pearls:
            grouped[pearl.cycle_id].append(pearl)

        # Sort within each window by seq_id
        for cycle_id in grouped:
            grouped[cycle_id].sort(key=lambda p: p.seq_id)

        # Order windows by the min seq_id of their first Pearl
        self._ordered_cycles: List[str] = sorted(
            grouped.keys(),
            key=lambda cid: grouped[cid][0].seq_id,
        )

        self._windows: Dict[str, List[Pearl]] = dict(grouped)

        # O(1) lookup: seq_id → cycle_id
        self._seq_to_cycle: Dict[int, str] = {}
        for cycle_id, window in self._windows.items():
            for p in window:
                self._seq_to_cycle[p.seq_id] = cycle_id

        # O(1) position lookup: cycle_id → index in ordered list
        self._cycle_index: Dict[str, int] = {
            cid: i for i, cid in enumerate(self._ordered_cycles)
        }

    @classmethod
    def build(cls, pearls: List[Pearl]) -> "ExecutionWindows":
        """Construct ExecutionWindows from a Pearl sequence."""
        return cls(pearls)

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Number of distinct execution windows."""
        return len(self._ordered_cycles)

    @property
    def cycle_ids(self) -> List[str]:
        """Ordered list of cycle_ids (by min seq_id)."""
        return list(self._ordered_cycles)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, cycle_id: str) -> List[Pearl]:
        """
        Return the window (list of Pearls) for cycle_id.

        Returns an empty list if cycle_id is not found.
        """
        return list(self._windows.get(cycle_id, []))

    def of(self, pearl: Pearl) -> List[Pearl]:
        """
        Return the window containing pearl.

        Returns an empty list if pearl is not in any window.
        """
        cycle_id = self._seq_to_cycle.get(pearl.seq_id)
        if cycle_id is None:
            return []
        return list(self._windows[cycle_id])

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def next_window(self, cycle_id: str) -> Optional[List[Pearl]]:
        """
        Return the window immediately following cycle_id in ordering.

        Returns None if cycle_id is the last window or not found.
        """
        idx = self._cycle_index.get(cycle_id)
        if idx is None or idx + 1 >= len(self._ordered_cycles):
            return None
        return list(self._windows[self._ordered_cycles[idx + 1]])

    def prev_window(self, cycle_id: str) -> Optional[List[Pearl]]:
        """
        Return the window immediately preceding cycle_id in ordering.

        Returns None if cycle_id is the first window or not found.
        """
        idx = self._cycle_index.get(cycle_id)
        if idx is None or idx == 0:
            return None
        return list(self._windows[self._ordered_cycles[idx - 1]])

    def range(self, start_cycle: str, end_cycle: str) -> List[List[Pearl]]:
        """
        Return all windows from start_cycle to end_cycle inclusive.

        Windows are returned in ordering order.  Returns an empty list if
        either cycle_id is not found or start comes after end.
        """
        i = self._cycle_index.get(start_cycle)
        j = self._cycle_index.get(end_cycle)
        if i is None or j is None or i > j:
            return []
        return [
            list(self._windows[self._ordered_cycles[k]])
            for k in range(i, j + 1)
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """
        Assert consistency of the execution windows.

        Checks (in order):
            1. Each Pearl appears in exactly one window (cycle_id uniqueness)
            2. Within each window, seq_ids are strictly increasing
            3. Windows are ordered by their first seq_id

        Raises
        ------
        ValueError
            On the first consistency violation found.
        """
        seen_seq: set = set()

        for cycle_id in self._ordered_cycles:
            window = self._windows[cycle_id]
            for i, p in enumerate(window):
                if p.seq_id in seen_seq:
                    raise ValueError(
                        f"Pearl seq_id {p.seq_id} appears in multiple windows"
                    )
                seen_seq.add(p.seq_id)
                if i > 0:
                    prev_p = window[i - 1]
                    if p.seq_id <= prev_p.seq_id:
                        raise ValueError(
                            f"Non-monotone seq_id in window '{cycle_id}': "
                            f"{p.seq_id} after {prev_p.seq_id}"
                        )

        # Verify window ordering: first seq_id of each window must be increasing
        first_seqs = [self._windows[cid][0].seq_id for cid in self._ordered_cycles]
        for k in range(1, len(first_seqs)):
            if first_seqs[k] <= first_seqs[k - 1]:
                raise ValueError(
                    f"Window ordering violation: window '{self._ordered_cycles[k]}' "
                    f"starts at seq_id={first_seqs[k]} but previous window "
                    f"'{self._ordered_cycles[k-1]}' starts at {first_seqs[k-1]}"
                )

    # ------------------------------------------------------------------
    # Replay
    # ------------------------------------------------------------------

    def replay(self, cycle_id: str, engine: SupportEngine) -> None:
        """
        Restore gate state from a single execution window into engine.

        For each unique (workload_id, node_key, gate_id) triple in the window,
        takes the most recently seen Pearl and establishes the gate's base
        layer via Gate._restore_from_pearl_snapshot().

        Guarantees:
          - engine.ingest() is never called
          - engine._seq remains unchanged
          - engine listeners are never fired
          - gate._contributions remains empty
          - energy is mathematically equivalent to original

        Authorized to use Gate._restore_from_pearl_snapshot() and to write
        directly to engine._gates (invar/persistence/ scope).
        """
        window = self._windows.get(cycle_id)
        if not window:
            return

        latest: Dict[Tuple[str, str, str], Pearl] = {}
        for pearl in window:
            key = (pearl.workload_id, pearl.node_key, pearl.gate_id)
            latest[key] = pearl

        for (workload_id, node_key, gate_id), pearl in latest.items():
            gate = Gate(
                gate_id=gate_id,
                workload_id=workload_id,
                node_key=node_key,
            )
            gate._restore_from_pearl_snapshot(
                phi_R=pearl.phi_R_after,
                phi_B=pearl.phi_B_after,
                state=pearl.state_after,
                ts=pearl.ts,
            )
            mkey = (workload_id, node_key)
            engine._gates[mkey][gate_id] = gate
