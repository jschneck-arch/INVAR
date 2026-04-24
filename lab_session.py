"""
lab_session.py — Invar lab engagement session
==============================================
Invar drives the engagement.  The operator is a second observer who can
inject additional tool output or redirect at any point.

Quick start — autonomous
-------------------------
    from lab_session import LabSession

    lab = LabSession(workload_id="lab-01", node_key="192.168.1.50")
    lab.engage("192.168.1.50")          # Invar runs nmap → enum4linux → nikto
    lab.status()

Quick start — operator-fed
---------------------------
    lab = LabSession(workload_id="lab-01", node_key="192.168.1.50")

    # Run tools yourself; paste or pipe output in:
    lab.ingest_nmap(open("scan.xml").read())
    lab.ingest_enum4linux(enum_output)
    lab.status()

    # Post-exploitation output (mimikatz, PowerUp) — operator retrieves, Invar structures:
    lab.receive("mimikatz", mimi_output, target="192.168.1.50")
    lab.receive("powerup",  pu_output,   target="192.168.1.50")
    lab.status()

Engagement phases (autonomous)
--------------------------------
    Phase 1 — Port discovery     : nmap -sV -sC -T4 --open
    Phase 2 — SMB enumeration    : enum4linux -a  (if port 445 or 139 open)
    Phase 3 — Web enumeration    : nikto -h       (if port 80/443/8080/8443 open)
    (Post-exploitation phases are operator-driven via receive())

State inspection
-----------------
    lab.status()              print engagement summary to stdout
    lab.pearls()              List[Pearl] — all emitted Pearls
    lab.cycle_ids()           List[str]  — observed cycles in order
    lab.pattern_matches()     detected multi-cycle attack patterns
    lab.driver.run_log()      full audit trail of tool invocations
    lab.driver.available_tools()  which tools are on PATH
"""
from __future__ import annotations

import time
from typing import List, Optional

from invar.adapters.measurement.instrument_driver import InstrumentDriver
from invar.adapters.measurement.tool_normalizer import MeasurementAdapter
from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
from invar.adapters.redteam.action_proposal import ActionProposalEngine
from invar.adapters.redteam.domain_model import (
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

# Ports whose presence in nmap Pearls triggers follow-on tools
_SMB_PORTS  = {"445", "139"}
_WEB_PORTS  = {"80", "443", "8080", "8443", "8000", "8888"}


class LabSession:
    """
    Black-box engagement session.

    Invar is the primary measurement driver.  The operator is a second observer
    who can supply additional context via receive() or direct ingest_*() calls
    at any point.
    """

    def __init__(
        self,
        workload_id:   str,
        node_key:      str   = "unknown_host",
        gap_threshold: float = 300.0,
        shift_window:  int   = 5,
        timeout:       int   = 300,
        verbose:       bool  = True,
    ) -> None:
        self._workload_id = workload_id
        self._node_key    = node_key
        self._verbose     = verbose

        self._adapter = MeasurementAdapter(
            workload_id=workload_id,
            node_key=node_key,
            gap_threshold=gap_threshold,
            shift_window=shift_window,
        )
        self._archive: PearlArchive = self._adapter._archive
        self.driver = InstrumentDriver(
            adapter=self._adapter,
            timeout=timeout,
            verbose=verbose,
        )

    # ------------------------------------------------------------------
    # Autonomous engagement
    # ------------------------------------------------------------------

    def engage(
        self,
        target:       str,
        ports:        str           = "1-65535",
        cycle_prefix: str           = "cycle",
        nmap_flags:   Optional[str] = None,
    ) -> None:
        """
        Run a full measurement sequence against target.

        Phase 1: nmap port/service/OS discovery
        Phase 2: SMB enumeration (enum4linux) if port 445 or 139 found
        Phase 3: Web enumeration (nikto) for each web port found

        After each phase, calls status() so the operator sees current state.
        Operator may call receive() at any point to inject additional data.
        """
        self._banner(f"ENGAGE — {target}")

        # Phase 1: port discovery
        self._phase("1 — Port discovery (nmap)")
        nmap_pearls = self.driver.run_nmap(
            target, ports=ports, flags=nmap_flags,
            cycle_id=f"{cycle_prefix}-01-recon",
        )
        self.status()

        # Derive open ports from emitted Pearls
        open_ports = _open_ports_from_pearls(nmap_pearls)
        if self._verbose and open_ports:
            print(f"[engage] open ports observed: {sorted(open_ports)}")

        # Phase 2: SMB
        if open_ports & _SMB_PORTS:
            self._phase("2 — SMB enumeration (enum4linux)")
            self.driver.run_enum4linux(
                target,
                cycle_id=f"{cycle_prefix}-02-enum",
            )
            self.status()
        else:
            if self._verbose:
                print("[engage] phase 2 skipped — no SMB ports observed")

        # Phase 3: web
        web = open_ports & _WEB_PORTS
        if web:
            self._phase(f"3 — Web enumeration (nikto) ports={sorted(web)}")
            for port in sorted(web, key=int):
                ssl = port in ("443", "8443")
                self.driver.run_nikto(
                    target, port=int(port), ssl=ssl,
                    cycle_id=f"{cycle_prefix}-03-web",
                )
            self.status()
        else:
            if self._verbose:
                print("[engage] phase 3 skipped — no web ports observed")

        self._banner("ENGAGE COMPLETE")
        self.status()

    # ------------------------------------------------------------------
    # Operator entry points (direct ingest or receive)
    # ------------------------------------------------------------------

    def ingest(
        self,
        source:   str,
        raw:      str,
        cycle_id: Optional[str] = None,
        target:   str           = "",
    ) -> List[Pearl]:
        return self._adapter.ingest(source, raw, cycle_id, target)

    def ingest_nmap(self, xml_str: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_nmap(xml_str, cycle_id, target)

    def ingest_enum4linux(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_enum4linux(text, cycle_id, target)

    def ingest_nikto(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_nikto(text, cycle_id, target)

    def ingest_mimikatz(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_mimikatz(text, cycle_id, target)

    def ingest_powerup(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_powerup(text, cycle_id, target)

    def ingest_msf(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self._adapter.ingest_msf(text, cycle_id, target)

    def receive(
        self,
        source:   str,
        content:  str,
        target:   str           = "",
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """
        Accept operator-retrieved or C2-pulled tool output.

        Use for post-exploitation tools that run on the target:
            lab.receive("mimikatz", mimi_output, target="192.168.1.50")
            lab.receive("powerup",  pu_output,   target="192.168.1.50")
            lab.receive("msf",      msf_output)
        """
        return self.driver.receive(source, content, target=target, cycle_id=cycle_id)

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

    def pattern_matches(self) -> list:
        observer = self._build_observer()
        model    = self._build_domain_model(observer)
        return RelationshipGraph(observer, model).pattern_matches()

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
        model    = self._build_domain_model(observer)
        graph    = RelationshipGraph(observer, model)
        cycles   = self.cycle_ids()

        print()
        print("=" * 64)
        print(f"  INVAR  {self._workload_id}  |  target: {self._node_key}")
        print(f"  Pearls: {len(pearls)}   Cycles: {len(cycles)}")
        print("=" * 64)

        for cid in cycles:
            prim         = model.cycle_primitive(cid)
            cycle_pearls = [p for p in pearls if p.cycle_id == cid]
            gate_ids     = sorted({p.gate_id for p in cycle_pearls})
            art_types    = sorted({classify_gate_id(g) for g in gate_ids})
            nodes        = sorted({p.node_key for p in cycle_pearls})

            print(f"\n  [{cid}]")
            print(f"    Primitive : {prim}")
            print(f"    Nodes     : {nodes}")
            print(f"    Pearls    : {len(cycle_pearls)}   Artifact types: {', '.join(art_types)}")
            for g in gate_ids:
                atype  = classify_gate_id(g)
                gnodes = sorted({p.node_key for p in cycle_pearls if p.gate_id == g})
                print(f"      {g:<42}  [{atype}]  {gnodes}")

        matches = graph.pattern_matches()
        if matches:
            print(f"\n  Attack Patterns detected ({len(matches)}):")
            for m in matches:
                print(f"    {m.pattern_name:<38}  {' → '.join(m.cycle_sequence)}")
        else:
            print("\n  Attack Patterns: none detected yet")

        rels = graph.cycle_relationships()
        if rels:
            print(f"\n  Cycle Relationships ({len(rels)}):")
            for r in rels[:10]:
                print(f"    {r.source_cycle_id} → {r.dest_cycle_id}  [{r.relationship_type}]")

        log = self.driver.run_log()
        if log:
            print(f"\n  Tool Run Log ({len(log)} invocations):")
            for run in log:
                ts_str = time.strftime("%H:%M:%S", time.localtime(run.ts))
                status = "ok" if run.ok else f"exit={run.exit_code}"
                note   = f"  [{run.note}]" if run.note else ""
                print(f"    {ts_str}  {run.source:<12}  {run.target:<20}  {status}  {run.pearls} pearls{note}")

        print()

    # ------------------------------------------------------------------
    # Internal stack construction
    # ------------------------------------------------------------------

    def _build_observer(self) -> RedTeamObserver:
        pearls  = self.pearls()
        temporal = TemporalGraph.build(pearls)
        windows  = ExecutionWindows.build(pearls)
        causal   = ProtoCausality.build(windows)
        field    = CausalField.build(causal, windows)
        return RedTeamObserver(self._archive, temporal, windows, causal, field)

    def _build_domain_model(self, observer: RedTeamObserver) -> RedTeamDomainModel:
        store        = AcknowledgmentStore()
        feedback     = FeedbackEngine(observer)
        workflow     = WorkflowView(feedback, store)
        action_engine = ActionProposalEngine(feedback, store)
        return RedTeamDomainModel(observer, feedback, store, workflow, action_engine)

    def _banner(self, msg: str) -> None:
        if self._verbose:
            print(f"\n{'─' * 64}")
            print(f"  {msg}")
            print(f"{'─' * 64}")

    def _phase(self, msg: str) -> None:
        if self._verbose:
            print(f"\n[engage] Phase {msg}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _open_ports_from_pearls(pearls: List[Pearl]) -> set:
    """
    Derive the set of open port strings from nmap gate_ids in a Pearl list.

    Multiple ports share one gate_id (e.g. 445 and 139 both → discover_nmap_445).
    We build a one-to-many gate→ports map so all ports are represented.
    discover_nmap_port_<N> gate_ids are parsed directly.
    """
    from invar.adapters.measurement.tool_normalizer import _NMAP_PORT_GATE

    # Build gate → {ports} one-to-many map
    gate_to_ports: dict = {}
    for port, gate in _NMAP_PORT_GATE.items():
        gate_to_ports.setdefault(gate, set()).add(port)

    ports: set = set()
    for p in pearls:
        gid = p.gate_id
        if gid in gate_to_ports:
            ports.update(gate_to_ports[gid])
        elif gid.startswith("discover_nmap_port_"):
            port_str = gid[len("discover_nmap_port_"):]
            if port_str.isdigit():
                ports.add(port_str)
    return ports
