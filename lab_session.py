"""
lab_session.py — Invar lab engagement session
==============================================
Invar drives the engagement.  The operator is a second observer who can
inject additional tool output, redirect phases, or feed post-exploitation
results at any point.

Both network tool output (nmap, nikto, enum4linux) and Windows host telemetry
(Sysmon XML, Windows Event Log XML) flow into the same unified Pearl stream
and are classified together.

Quick start — autonomous
-------------------------
    from lab_session import LabSession

    lab = LabSession(workload_id="lab-01", node_key="192.168.1.50")
    lab.engage("192.168.1.50")          # nmap → enum4linux → nikto
    lab.next_actions()                  # Invar tells you what comes next
    lab.status()

Quick start — operator-fed
---------------------------
    lab = LabSession(workload_id="lab-01", node_key="192.168.1.50")
    lab.ingest_nmap(xml_str)
    lab.ingest_sysmon(sysmon_xml)       # Sysmon events from the host
    lab.next_actions()
    lab.status()

    # Post-exploitation output (mimikatz, PowerUp, msf):
    lab.receive("mimikatz", mimi_output, target="192.168.1.50")
    lab.next_actions()

Engagement phases (autonomous)
--------------------------------
    Phase 1 — Port discovery     : nmap -sV -sC -T4 --open
    Phase 2 — SMB enumeration    : enum4linux -a  (if port 445/139 observed)
    Phase 3 — Web enumeration    : nikto -h       (if port 80/443/8080/8443 observed)
    Post-exploitation            : operator-driven via receive()

State inspection
-----------------
    lab.status()                print full engagement summary
    lab.next_actions()          print prioritized recommendations
    lab.pearls()                List[Pearl] — all Pearls (tools + Sysmon unified)
    lab.cycle_ids()             List[str]  — observed cycles in order
    lab.pattern_matches()       detected multi-cycle attack patterns
    lab.driver.run_log()        audit trail of tool invocations
    lab.driver.available_tools()  which recon tools are on PATH
"""
from __future__ import annotations

import time
from typing import List, Optional

from invar.adapters.measurement.instrument_driver import InstrumentDriver
from invar.adapters.measurement.next_action import NextAction, NextActionEngine
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
from invar.adapters.redteam.windows_ingest import WindowsIngestAdapter
from invar.adapters.redteam.workflow import WorkflowView
from invar.core.support_engine import Pearl
from invar.persistence.causal_field import CausalField
from invar.persistence.execution_window import ExecutionWindows
from invar.persistence.pearl_archive import PearlArchive
from invar.persistence.proto_causality import ProtoCausality
from invar.persistence.temporal_graph import TemporalGraph

_SMB_PORTS = {"445", "139"}
_WEB_PORTS = {"80", "443", "8080", "8443", "8000", "8888"}

_PRIORITY_LABEL = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW"}


class LabSession:
    """
    Black-box engagement session.

    A single PearlArchive is shared across MeasurementAdapter (tool output)
    and WindowsIngestAdapter (Sysmon/WEL telemetry) so that all signals are
    classified and pattern-matched together.
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

        # Each adapter owns its archive; LabSession merges by timestamp for observation
        self._adapter = MeasurementAdapter(
            workload_id=workload_id,
            node_key=node_key,
            gap_threshold=gap_threshold,
            shift_window=shift_window,
        )
        self._sysmon = WindowsIngestAdapter(
            workload_id=workload_id,
            node_key=node_key,
            gap_threshold=gap_threshold,
            shift_window=shift_window,
        )
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
        Autonomous engagement loop.

        INVAR runs every instrument it can reach from its network position
        without stopping or asking.  Phases execute immediately in sequence;
        each phase's Pearl output drives the next decision.

        The loop stops exactly once — at the end — to surface:
          - What was observed (status)
          - What entropy remains that requires operator action or a foothold
            INVAR cannot reach (next_actions / decision surface)

        The operator's terminal shows INVAR working, not waiting.
        The only inputs the operator should ever supply:
          - Post-exploitation output from tools running on the target
            (mimikatz, PowerUp, msf sessions) that require a foothold
          - Authorization for exploitation actions
          - Redirection when the field isn't pointing where they need it
        """
        self._banner(f"ENGAGE {target}")

        # Port discovery — always first
        nmap_pearls = self.driver.run_nmap(
            target, ports=ports, flags=nmap_flags,
            cycle_id=f"{cycle_prefix}-01-recon",
        )
        open_ports = _open_ports_from_pearls(nmap_pearls)

        # SMB enumeration — immediate if 445 or 139 observed, no pause
        if open_ports & _SMB_PORTS:
            self.driver.run_enum4linux(target, cycle_id=f"{cycle_prefix}-02-enum")

        # Web enumeration — immediate for every web port observed, no pause
        for port in sorted(open_ports & _WEB_PORTS, key=int):
            self.driver.run_nikto(
                target, port=int(port), ssl=(port in ("443", "8443")),
                cycle_id=f"{cycle_prefix}-03-web",
            )

        # All instruments reachable from this position are exhausted.
        # Show what was observed, then surface what entropy remains.
        self.status()
        self._surface_decision(target)

    # ------------------------------------------------------------------
    # Tool output — operator or driver
    # ------------------------------------------------------------------

    def ingest(self, source: str, raw: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
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

    # ------------------------------------------------------------------
    # Sysmon / Windows Event Log — host telemetry
    # ------------------------------------------------------------------

    def ingest_sysmon(self, xml_str: str, cycle_id: Optional[str] = None) -> List[Pearl]:
        """
        Ingest Sysmon XML from the target host.

        Accepts a single <Event> element, an <Events> container, or a raw
        Sysmon XML string as produced by Get-WinEvent | ConvertTo-Xml.
        Pearls flow into the same archive as tool output.
        """
        return self._sysmon.ingest_sysmon_xml(xml_str, cycle_id)

    def ingest_event_log(self, xml_str: str, cycle_id: Optional[str] = None) -> List[Pearl]:
        """Ingest Windows Security Event Log XML (4688, 4624, 4698 fallback)."""
        return self._sysmon.ingest_event_log_xml(xml_str, cycle_id)

    def receive(self, source: str, content: str, target: str = "", cycle_id: Optional[str] = None) -> List[Pearl]:
        """
        Accept operator-retrieved or C2-pulled tool output.

            lab.receive("mimikatz", mimi_output, target="192.168.1.50")
            lab.receive("powerup",  pu_output,   target="192.168.1.50")
            lab.receive("msf",      msf_output)
        """
        return self.driver.receive(source, content, target=target, cycle_id=cycle_id)

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def pearls(self) -> List[Pearl]:
        """All Pearls — tool output and Sysmon telemetry unified, sorted by timestamp."""
        return PearlArchive.merge(
            self._adapter._archive, self._sysmon._archive
        ).pearls

    def cycle_ids(self) -> List[str]:
        seen: list = []
        for p in self.pearls():
            if p.cycle_id not in seen:
                seen.append(p.cycle_id)
        return seen

    def pattern_matches(self) -> list:
        observer = self._build_observer()
        model    = self._build_domain_model(observer)
        return RelationshipGraph(observer, model).pattern_matches()

    # ------------------------------------------------------------------
    # Intelligence
    # ------------------------------------------------------------------

    def next_actions(self) -> List[NextAction]:
        """
        Print and return prioritized next-action recommendations.

        Invar derives recommendations from the current Pearl set — what has
        been observed, what gaps remain, what attack patterns are emerging.
        """
        actions = NextActionEngine(self.pearls()).recommendations()

        print()
        print("─" * 64)
        print("  INVAR NEXT ACTIONS")
        print("─" * 64)
        if not actions:
            print("  No further actions recommended — engagement complete or insufficient data.")
        for a in actions:
            label = _PRIORITY_LABEL.get(a.priority, str(a.priority))
            print(f"\n  [{label}] {a.phase.upper()}: {a.action}")
            print(f"    tool   : {a.tool}")
            print(f"    cmd    : {a.command}")
            print(f"    why    : {a.reason}")
            if a.targets:
                print(f"    targets: {a.targets}")
        print()

        return actions

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def status(self) -> None:
        """Print full engagement state to stdout."""
        pearls = self.pearls()
        if not pearls:
            print("[lab] No data ingested yet.")
            return

        observer = self._build_observer()
        model    = self._build_domain_model(observer)
        graph    = RelationshipGraph(observer, model)
        cycles   = self.cycle_ids()

        # Count Sysmon vs tool Pearls
        sysmon_p = [p for p in pearls if p.instrument_id.startswith(("sysmon_", "wel_"))]
        tool_p   = [p for p in pearls if not p.instrument_id.startswith(("sysmon_", "wel_"))]

        print()
        print("=" * 64)
        print(f"  INVAR  {self._workload_id}  |  target: {self._node_key}")
        print(f"  Pearls: {len(pearls)}  "
              f"(tools: {len(tool_p)}  sysmon/WEL: {len(sysmon_p)})  "
              f"Cycles: {len(cycles)}")
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
            print(f"    Pearls    : {len(cycle_pearls)}   "
                  f"Artifact types: {', '.join(art_types)}")
            for g in gate_ids:
                atype  = classify_gate_id(g)
                gnodes = sorted({p.node_key for p in cycle_pearls if p.gate_id == g})
                print(f"      {g:<44}  [{atype}]  {gnodes}")

        matches = graph.pattern_matches()
        if matches:
            print(f"\n  Attack Patterns detected ({len(matches)}):")
            for m in matches:
                print(f"    {m.pattern_name:<40}  {' → '.join(m.cycle_sequence)}")
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
                st     = "ok" if run.ok else f"exit={run.exit_code}"
                note   = f"  [{run.note}]" if run.note else ""
                print(f"    {ts_str}  {run.source:<12}  {run.target:<22}  "
                      f"{st}  {run.pearls} pearls{note}")
        print()

    # ------------------------------------------------------------------
    # Internal stack construction
    # ------------------------------------------------------------------

    def _build_observer(self) -> RedTeamObserver:
        merged   = PearlArchive.merge(self._adapter._archive, self._sysmon._archive)
        pearls   = merged.pearls
        temporal = TemporalGraph.build(pearls)
        windows  = ExecutionWindows.build(pearls)
        causal   = ProtoCausality.build(windows)
        field    = CausalField.build(causal, windows)
        return RedTeamObserver(merged, temporal, windows, causal, field)

    def _build_domain_model(self, observer: RedTeamObserver) -> RedTeamDomainModel:
        store         = AcknowledgmentStore()
        feedback      = FeedbackEngine(observer)
        workflow      = WorkflowView(feedback, store)
        action_engine = ActionProposalEngine(feedback, store)
        return RedTeamDomainModel(observer, feedback, store, workflow, action_engine)

    def _surface_decision(self, target: str = "") -> None:
        """
        The single point where INVAR stops and surfaces to the operator.

        Called when all instruments reachable from INVAR's network position
        are exhausted.  Separates what INVAR observed from what requires
        the operator: foothold access, post-exploitation tools, or
        explicit authorization to cross from observation into exploitation.
        """
        actions = NextActionEngine(self.pearls()).recommendations()
        if not actions:
            self._banner("ENGAGEMENT COMPLETE — no further entropy detected")
            return

        # Actions INVAR can drive autonomously (additional recon/enum tools)
        # vs. actions that require operator input or foothold
        _INVAR_PHASES    = {"recon", "enum"}
        _OPERATOR_PHASES = {"cred", "lateral", "privesc", "persist", "collect"}

        invar_actions    = [a for a in actions if a.phase in _INVAR_PHASES]
        operator_actions = [a for a in actions if a.phase in _OPERATOR_PHASES]

        self._banner("INVAR DECISION SURFACE")

        if invar_actions:
            print("  Additional instruments available from this position:")
            for a in invar_actions:
                print(f"    [{a.tool}]  {a.action}")
                print(f"             {a.command}")
            print()

        if operator_actions:
            print("  Entropy remains — requires operator action or foothold:")
            print()
            for a in operator_actions:
                label = _PRIORITY_LABEL.get(a.priority, str(a.priority))
                print(f"  [{label}] {a.phase.upper()}: {a.action}")
                print(f"    tool : {a.tool}")
                print(f"    cmd  : {a.command}")
                print(f"    why  : {a.reason}")
                print()
            print("  When you have output:")
            print(f"    lab.receive('mimikatz', text, target='{target or self._node_key}')")
            print(f"    lab.receive('powerup',  text, target='{target or self._node_key}')")
            print(f"    lab.receive('msf',      text)")
            print(f"    lab.next_actions()  # recomputes from new state")
        print()

    def _banner(self, msg: str) -> None:
        if self._verbose:
            print(f"\n{'─' * 64}\n  {msg}\n{'─' * 64}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _open_ports_from_pearls(pearls: List[Pearl]) -> set:
    from invar.adapters.measurement.tool_normalizer import _NMAP_PORT_GATE
    gate_to_ports: dict = {}
    for port, gate in _NMAP_PORT_GATE.items():
        gate_to_ports.setdefault(gate, set()).add(port)
    ports: set = set()
    for p in pearls:
        gid = p.gate_id
        if gid in gate_to_ports:
            ports.update(gate_to_ports[gid])
        elif gid.startswith("discover_nmap_port_"):
            s = gid[len("discover_nmap_port_"):]
            if s.isdigit():
                ports.add(s)
    return ports
