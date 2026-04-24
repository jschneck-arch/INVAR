"""
lab_session.py — Invar lab engagement session
==============================================
Single entry point for a black-box engagement.  Paste raw tool output in;
Invar structures it into Pearls, classifies it, and reports what it observes.

No tools are executed.  Invar is the observer — it receives instrument output
and derives structure from it.

Quick start
-----------
    from lab_session import LabSession

    lab = LabSession(workload_id="lab-01", node_key="192.168.1.50")

    # Paste nmap XML output:
    pearls = lab.ingest_nmap(open("scan.xml").read())
    lab.status()

    # Later — paste enum4linux output:
    lab.ingest_enum4linux(enum_output, cycle_id="cycle-02-enum")
    lab.status()

    # Later — paste mimikatz output:
    lab.ingest_mimikatz(mimi_output)
    lab.status()

Supported instruments
---------------------
    lab.ingest_nmap(xml_str)              # nmap -oX output
    lab.ingest_enum4linux(text)           # enum4linux text output
    lab.ingest_nikto(text)               # nikto text output
    lab.ingest_mimikatz(text)            # mimikatz console output
    lab.ingest_powerup(text)             # PowerUp PowerShell output
    lab.ingest_msf(text)                 # Metasploit console output
    lab.ingest(source, raw)              # generic — any registered normalizer

Optional arguments on every ingest call:
    cycle_id="cycle-02-enum"    # operator override; None → auto-discovered
    target="192.168.1.50"       # override node_key for this call only

State inspection
----------------
    lab.status()                # print engagement summary to stdout
    lab.pearls()                # List[Pearl] — all emitted Pearls
    lab.cycle_ids()             # List[str] — observed cycle IDs in order
    lab.summary(cycle_id)       # dict — observer summary for one cycle
    lab.pattern_matches()       # list of detected attack pattern matches
"""
from __future__ import annotations

import sys
import time
from typing import List, Optional

from invar.adapters.measurement.tool_normalizer import MeasurementAdapter
from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
from invar.adapters.redteam.action_proposal import ActionProposalEngine
from invar.adapters.redteam.domain_model import (
    ArtifactType,
    RedTeamDomainModel,
    classify_gate_id,
)
from invar.adapters.redteam.feedback import FeedbackEngine
from invar.adapters.redteam.observer import RedTeamObserver
from invar.adapters.redteam.relationship_graph import RelationshipGraph
from invar.adapters.redteam.workflow import WorkflowView
from invar.core.support_engine import Pearl
from invar.persistence.causal_field import CausalField
from invar.persistence.execution_window import ExecutionWindows
from invar.persistence.pearl_archive import PearlArchive
from invar.persistence.proto_causality import ProtoCausality
from invar.persistence.temporal_graph import TemporalGraph


class LabSession:
    """
    Black-box engagement session.

    Wraps a MeasurementAdapter and rebuilds the full observer + domain stack
    after each ingest so that status() always reflects current state.
    """

    def __init__(
        self,
        workload_id: str,
        node_key: str = "unknown_host",
        gap_threshold: float = 300.0,
        shift_window: int = 5,
    ) -> None:
        self._workload_id = workload_id
        self._node_key = node_key
        self._adapter = MeasurementAdapter(
            workload_id=workload_id,
            node_key=node_key,
            gap_threshold=gap_threshold,
            shift_window=shift_window,
        )
        self._archive: PearlArchive = self._adapter._archive

    # ------------------------------------------------------------------
    # Ingest — instrument entry points
    # ------------------------------------------------------------------

    def ingest(
        self,
        source: str,
        raw: str,
        cycle_id: Optional[str] = None,
        target: str = "",
    ) -> List[Pearl]:
        return self._adapter.ingest(source, raw, cycle_id, target)

    def ingest_nmap(
        self, xml_str: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_nmap(xml_str, cycle_id, target)

    def ingest_enum4linux(
        self, text: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_enum4linux(text, cycle_id, target)

    def ingest_nikto(
        self, text: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_nikto(text, cycle_id, target)

    def ingest_mimikatz(
        self, text: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_mimikatz(text, cycle_id, target)

    def ingest_powerup(
        self, text: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_powerup(text, cycle_id, target)

    def ingest_msf(
        self, text: str, cycle_id: Optional[str] = None, target: str = ""
    ) -> List[Pearl]:
        return self._adapter.ingest_msf(text, cycle_id, target)

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def pearls(self) -> List[Pearl]:
        return self._adapter.pearls()

    def cycle_ids(self) -> List[str]:
        seen: list = []
        for p in self._adapter.pearls():
            if p.cycle_id not in seen:
                seen.append(p.cycle_id)
        return seen

    def summary(self, cycle_id: str) -> dict:
        observer = self._build_observer()
        return observer.summary(cycle_id)

    def pattern_matches(self) -> list:
        observer = self._build_observer()
        model = self._build_domain_model(observer)
        graph = RelationshipGraph(observer, model)
        return graph.pattern_matches()

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status(self) -> None:
        """Print engagement state to stdout."""
        pearls = self.pearls()
        if not pearls:
            print("[lab] No data ingested yet.")
            return

        observer = self._build_observer()
        model = self._build_domain_model(observer)
        graph = RelationshipGraph(observer, model)

        cycle_ids = self.cycle_ids()

        print()
        print("=" * 60)
        print(f"  INVAR LAB SESSION — {self._workload_id}")
        print(f"  Target: {self._node_key}")
        print(f"  Pearls: {len(pearls)}   Cycles: {len(cycle_ids)}")
        print("=" * 60)

        for cid in cycle_ids:
            prim = model.cycle_primitive(cid)
            cycle_pearls = [p for p in pearls if p.cycle_id == cid]
            gate_ids = sorted({p.gate_id for p in cycle_pearls})
            artifact_types = sorted({classify_gate_id(g) for g in gate_ids})

            print(f"\n  Cycle: {cid}")
            print(f"    Primitive : {prim}")
            print(f"    Pearls    : {len(cycle_pearls)}")
            print(f"    Artifacts : {', '.join(artifact_types)}")
            print(f"    Gates     :")
            for g in gate_ids:
                atype = classify_gate_id(g)
                nodes = sorted({p.node_key for p in cycle_pearls if p.gate_id == g})
                print(f"      {g:<40}  [{atype}]  {nodes}")

        matches = graph.pattern_matches()
        if matches:
            print(f"\n  Attack Patterns ({len(matches)} detected):")
            for m in matches:
                print(f"    {m.pattern_name:<35}  {' → '.join(m.cycle_sequence)}")
        else:
            print("\n  Attack Patterns: none detected yet")

        rels = graph.cycle_relationships()
        if len(rels) > 0:
            print(f"\n  Cycle Relationships ({len(rels)}):")
            for r in rels[:10]:
                print(f"    {r.source_cycle_id} → {r.dest_cycle_id}  [{r.relationship_type}]")

        print()

    # ------------------------------------------------------------------
    # Internal stack construction
    # ------------------------------------------------------------------

    def _build_observer(self) -> RedTeamObserver:
        pearls = self.pearls()
        temporal = TemporalGraph.build(pearls)
        windows = ExecutionWindows.build(pearls)
        causal = ProtoCausality.build(windows)
        field = CausalField.build(causal, windows)
        return RedTeamObserver(self._archive, temporal, windows, causal, field)

    def _build_domain_model(self, observer: RedTeamObserver) -> RedTeamDomainModel:
        store = AcknowledgmentStore()
        feedback = FeedbackEngine(observer)
        workflow = WorkflowView(feedback, store)
        action_engine = ActionProposalEngine(feedback, store)
        return RedTeamDomainModel(observer, feedback, store, workflow, action_engine)
