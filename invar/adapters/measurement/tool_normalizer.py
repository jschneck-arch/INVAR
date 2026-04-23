"""
invar.adapters.measurement.tool_normalizer
==========================================
Domain-agnostic measurement adapter — tool output normalization layer.

External security tools (nmap, mimikatz, enum4linux, PowerUp, nikto) are
instruments.  Their output is parsed here and normalized into MeasurementEvent
objects, then into Invar Pearls.  Invar never executes any tool; it only reads
what the tool already emitted.

This layer is domain-agnostic: the same normalization pipeline works for any
domain that uses these instruments.  The gate_id naming convention is compatible
with the L2-5 classification rules so Pearls flow straight into the red team
domain model (or any other domain) without modification.

Supported instruments:
    nmap        — XML output (-oX)       → discover_nmap_*
    mimikatz    — text console output    → cred_* / discover_*
    enum4linux  — text output            → discover_smb_*
    PowerUp     — PowerShell text output → persist_*
    nikto       — text/xml output        → discover_nikto_* / discover_web_*

gate_id naming (first-match compatible with _ARTIFACT_RULES in domain_model.py):
    discover_nmap_host        — live host confirmed
    discover_nmap_port_{p}    — open port (p sanitized)
    discover_nmap_smb         — port 445 open
    discover_nmap_http        — port 80/8080 open
    discover_nmap_https       — port 443/8443 open
    discover_nmap_rdp         — port 3389 open
    discover_nmap_winrm       — port 5985/5986 open
    discover_nmap_service_{s} — named service detected
    discover_nmap_os          — OS fingerprint detected
    cred_mimikatz_logonpw     — sekurlsa::logonpasswords output present
    cred_mimikatz_dcsync      — lsadump::dcsync output present
    cred_hash_ntlm            — NTLM hash found
    cred_ticket_kerberos      — Kerberos ticket found
    cred_mimikatz_wdigest     — wdigest plaintext found
    discover_smb_shares       — SMB shares enumerated
    discover_smb_users        — SMB users enumerated
    discover_smb_groups       — SMB groups enumerated
    discover_enum4linux       — generic enum4linux finding
    persist_svc_unquoted      — unquoted service path
    persist_svc_modifiable    — modifiable service binary
    persist_autorun           — autorun/startup abuse
    persist_dll_hijack        — DLL hijack opportunity
    persist_checks            — PowerUp generic check hit
    discover_nikto_vuln       — nikto vulnerability finding
    discover_web_dir          — web directory/file found
    discover_web_server       — server header / version disclosed

Constraints:
    - No tool execution — reads emitted output only
    - No Layer 0 modification
    - Pearls: phi_R=1.0, H=1.0, state_before=U, state_after=R
    - Deterministic: same output string → same Pearls
    - Adapter-local: domain labels never written to core canonical state
    - Discardable: zero side-effects

API:
    adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
    pearls  = adapter.ingest_nmap(xml_str)
    pearls  = adapter.ingest_mimikatz(text, cycle_id="c03")
    pearls  = adapter.ingest_enum4linux(text)
    pearls  = adapter.ingest_powerup(text)
    pearls  = adapter.ingest_nikto(text)
    all_p   = adapter.pearls()
    archive, pl = adapter.snapshot()
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from invar.core.gate import GateState
from invar.core.support_engine import Pearl
from invar.persistence.pearl_archive import PearlArchive
from invar.adapters.redteam.windows_ingest import CycleDiscovery


# ---------------------------------------------------------------------------
# Normalized measurement event
# ---------------------------------------------------------------------------

@dataclass
class MeasurementEvent:
    """
    A single normalized observation from a measurement tool.

    tool    — instrument name ("nmap", "mimikatz", "enum4linux", "powerup", "nikto")
    gate_id — rule-aligned Invar gate identifier
    target  — host/IP/path the observation is about (empty string if not applicable)
    ts      — unix timestamp (time of parse, not tool run — tools rarely embed precise ts)
    raw     — the source line or fragment that produced this event
    """
    tool:    str
    gate_id: str
    target:  str
    ts:      float
    raw:     str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sanitize(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s).strip("_") or "unknown"


# ---------------------------------------------------------------------------
# nmap parser  (XML — nmap -oX)
# ---------------------------------------------------------------------------

_NMAP_PORT_LABELS: Dict[str, str] = {
    "80":   "discover_nmap_http",
    "8080": "discover_nmap_http",
    "443":  "discover_nmap_https",
    "8443": "discover_nmap_https",
    "445":  "discover_nmap_smb",
    "139":  "discover_nmap_smb",
    "3389": "discover_nmap_rdp",
    "5985": "discover_nmap_winrm",
    "5986": "discover_nmap_winrm",
    "22":   "discover_nmap_ssh",
    "21":   "discover_nmap_ftp",
    "25":   "discover_nmap_smtp",
    "53":   "discover_nmap_dns",
}


def parse_nmap(xml_str: str, ts: Optional[float] = None) -> List[MeasurementEvent]:
    """
    Parse nmap XML output (-oX) into MeasurementEvents.

    Emits one event per:
      - live host confirmed (discover_nmap_host)
      - open port (discover_nmap_port_{p} or well-known label)
      - named service (discover_nmap_service_{name})
      - OS match (discover_nmap_os)
    """
    t = ts or time.time()
    events: List[MeasurementEvent] = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return events

    for host in root.findall(".//host"):
        # Host identity
        addr_elem = host.find("address[@addrtype='ipv4']")
        if addr_elem is None:
            addr_elem = host.find("address")
        target = addr_elem.get("addr", "unknown") if addr_elem is not None else "unknown"

        # Host status
        status = host.find("status")
        if status is not None and status.get("state") == "up":
            events.append(MeasurementEvent(
                tool="nmap", gate_id="discover_nmap_host",
                target=target, ts=t, raw=f"host up: {target}",
            ))

        # Ports
        for port in host.findall(".//port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            portid = port.get("portid", "")
            gate_id = _NMAP_PORT_LABELS.get(portid, f"discover_nmap_port_{_sanitize(portid)}")
            events.append(MeasurementEvent(
                tool="nmap", gate_id=gate_id,
                target=target, ts=t, raw=f"open {portid}/tcp on {target}",
            ))
            # Named service
            svc = port.find("service")
            if svc is not None:
                name = svc.get("name", "").strip()
                if name and name not in ("http", "https", "microsoft-ds", "msrdp", "netbios-ssn"):
                    events.append(MeasurementEvent(
                        tool="nmap",
                        gate_id=f"discover_nmap_service_{_sanitize(name)}",
                        target=target, ts=t, raw=f"service {name} on {portid}",
                    ))

        # OS
        for osmatch in host.findall(".//osmatch"):
            name = osmatch.get("name", "")
            if name:
                events.append(MeasurementEvent(
                    tool="nmap", gate_id="discover_nmap_os",
                    target=target, ts=t, raw=f"os: {name}",
                ))
                break  # one OS event per host

    return events


# ---------------------------------------------------------------------------
# mimikatz parser  (console text output)
# ---------------------------------------------------------------------------

# Ordered patterns: more-specific first
_MIMIKATZ_RULES: List[Tuple[str, str]] = [
    (r"(?i)dcsync",                   "cred_mimikatz_dcsync"),
    (r"(?i)sekurlsa::logonpasswords", "cred_mimikatz_logonpw"),
    (r"(?i)wdigest.*password\s*:\s*\S","cred_mimikatz_wdigest"),
    (r"(?i)\bNTLM\b.*:\s*[0-9a-fA-F]{32}", "cred_hash_ntlm"),
    (r"(?i)(Kerberos|kerberos)\s*\*", "cred_ticket_kerberos"),
    (r"(?i)\[kerberos\]",             "cred_ticket_kerberos"),
    (r"(?i)lsass",                    "cred_lsass_access"),
    (r"(?i)sekurlsa::",               "cred_mimikatz_logonpw"),
    (r"(?i)lsadump::",                "cred_mimikatz_dcsync"),
    (r"(?i)mimikatz",                 "cred_mimikatz_logonpw"),
]

_MIMIKATZ_COMPILED = [(re.compile(p), g) for p, g in _MIMIKATZ_RULES]


def parse_mimikatz(text: str, target: str = "", ts: Optional[float] = None) -> List[MeasurementEvent]:
    """
    Parse mimikatz console text output into MeasurementEvents.

    Each matching line → one event.  Duplicate gate_ids per target are
    deduplicated (same tool run rarely needs the same signal twice).
    """
    t = ts or time.time()
    events: List[MeasurementEvent] = []
    seen: set = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for regex, gate_id in _MIMIKATZ_COMPILED:
            if regex.search(line):
                key = (gate_id, target)
                if key not in seen:
                    seen.add(key)
                    events.append(MeasurementEvent(
                        tool="mimikatz", gate_id=gate_id,
                        target=target, ts=t, raw=line[:200],
                    ))
                break
    return events


# ---------------------------------------------------------------------------
# enum4linux parser  (text output)
# ---------------------------------------------------------------------------

_ENUM4LINUX_RULES: List[Tuple[str, str]] = [
    (r"(?i)(share|Disk|IPC\$|ADMIN\$|netlogon|sysvol)", "discover_smb_shares"),
    (r"(?i)(local user|local group|user\s*:|username\s*:|account\s*:)", "discover_smb_users"),
    (r"(?i)(group|member)",                              "discover_smb_groups"),
    (r"(?i)(password\s*policy|lockout)",                 "discover_smb_policy"),
    (r"(?i)(domain\s*name|workgroup)",                   "discover_enum4linux"),
    (r"(?i)(session|established|opened)",                "discover_enum4linux"),
]

_ENUM4LINUX_COMPILED = [(re.compile(p), g) for p, g in _ENUM4LINUX_RULES]


def parse_enum4linux(text: str, target: str = "", ts: Optional[float] = None) -> List[MeasurementEvent]:
    """Parse enum4linux text output into MeasurementEvents."""
    t = ts or time.time()
    events: List[MeasurementEvent] = []
    seen: set = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for regex, gate_id in _ENUM4LINUX_COMPILED:
            if regex.search(line):
                key = (gate_id, target)
                if key not in seen:
                    seen.add(key)
                    events.append(MeasurementEvent(
                        tool="enum4linux", gate_id=gate_id,
                        target=target, ts=t, raw=line[:200],
                    ))
                break
    return events


# ---------------------------------------------------------------------------
# PowerUp parser  (PowerShell text output)
# ---------------------------------------------------------------------------

_POWERUP_RULES: List[Tuple[str, str]] = [
    (r"(?i)unquoted.*service|UnquotedServicePath", "persist_svc_unquoted"),
    (r"(?i)modifiable.*service|ModifiableServiceFile", "persist_svc_modifiable"),
    (r"(?i)modifiable.*binary|ModifiablePath",         "persist_svc_modifiable"),
    (r"(?i)(autorun|startup|CurrentVersion\\Run)",      "persist_autorun"),
    (r"(?i)dll.*hijack|HijackableDLL",                 "persist_dll_hijack"),
    (r"(?i)AlwaysInstallElevated",                     "persist_registry"),
    (r"(?i)modifiable.*schtask|ScheduledTask",         "persist_schtask"),
    (r"(?i)Invoke-AllChecks|\[+\]\s*Checking",        "persist_checks"),
    (r"(?i)AbuseFunction|Abuse\s+Function",            "persist_checks"),
]

_POWERUP_COMPILED = [(re.compile(p), g) for p, g in _POWERUP_RULES]


def parse_powerup(text: str, target: str = "", ts: Optional[float] = None) -> List[MeasurementEvent]:
    """Parse PowerUp PowerShell text output into MeasurementEvents."""
    t = ts or time.time()
    events: List[MeasurementEvent] = []
    seen: set = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for regex, gate_id in _POWERUP_COMPILED:
            if regex.search(line):
                key = (gate_id, target)
                if key not in seen:
                    seen.add(key)
                    events.append(MeasurementEvent(
                        tool="powerup", gate_id=gate_id,
                        target=target, ts=t, raw=line[:200],
                    ))
                break
    return events


# ---------------------------------------------------------------------------
# nikto parser  (text output)
# ---------------------------------------------------------------------------

_NIKTO_RULES: List[Tuple[str, str]] = [
    (r"(?i)(OSVDB|CVE|vulnerability|vuln|XSS|SQL|inject|RFI|LFI|RCE|exec)", "discover_nikto_vuln"),
    (r"(?i)(directory|index of|listing enabled|/backup|/admin)",              "discover_web_dir"),
    (r"(?i)(server:\s*\S|x-powered-by|apache|nginx|iis|tomcat|php)",         "discover_web_server"),
    (r"(?i)(cookie.*httponly|cookie.*secure|missing header)",                 "discover_nikto_vuln"),
    (r"(?i)(allowed methods|OPTIONS|TRACE|PUT|DELETE)",                       "discover_nikto_vuln"),
]

_NIKTO_COMPILED = [(re.compile(p), g) for p, g in _NIKTO_RULES]


def parse_nikto(text: str, target: str = "", ts: Optional[float] = None) -> List[MeasurementEvent]:
    """Parse nikto text output into MeasurementEvents."""
    t = ts or time.time()
    events: List[MeasurementEvent] = []
    seen: set = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        for regex, gate_id in _NIKTO_COMPILED:
            if regex.search(line):
                key = (gate_id, target)
                if key not in seen:
                    seen.add(key)
                    events.append(MeasurementEvent(
                        tool="nikto", gate_id=gate_id,
                        target=target, ts=t, raw=line[:200],
                    ))
                break
    return events


# ---------------------------------------------------------------------------
# Top-level adapter
# ---------------------------------------------------------------------------

class MeasurementAdapter:
    """
    Stateful measurement adapter: normalizes tool output into Invar Pearls.

    Each ingest call parses one tool's output and appends resulting Pearls
    to the internal archive.  Cycle discovery is autonomous (same three-tier
    logic as WindowsIngestAdapter); operator may override per call.

    Nothing is executed.  This is a passive normalization layer only.
    """

    def __init__(
        self,
        workload_id:   str,
        node_key:      Optional[str] = None,
        gap_threshold: float         = 300.0,
        shift_window:  int           = 5,
    ) -> None:
        self._workload_id = workload_id
        self._node_key    = node_key or "unknown_host"
        self._discovery   = CycleDiscovery(gap_threshold, shift_window)
        self._archive     = PearlArchive()
        self._pearls:     List[Pearl] = []
        self._seq         = 0

    # ------------------------------------------------------------------
    # Ingest entry points
    # ------------------------------------------------------------------

    def ingest_nmap(self, xml_str: str, cycle_id: Optional[str] = None, target: Optional[str] = None) -> List[Pearl]:
        """Parse nmap -oX output and ingest. Returns new Pearls."""
        events = parse_nmap(xml_str)
        if target:
            for e in events:
                e.target = e.target or target
        return self._ingest_events(events, cycle_id)

    def ingest_mimikatz(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        """Parse mimikatz console output and ingest. Returns new Pearls."""
        return self._ingest_events(parse_mimikatz(text, target), cycle_id)

    def ingest_enum4linux(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        """Parse enum4linux output and ingest. Returns new Pearls."""
        return self._ingest_events(parse_enum4linux(text, target), cycle_id)

    def ingest_powerup(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        """Parse PowerUp output and ingest. Returns new Pearls."""
        return self._ingest_events(parse_powerup(text, target), cycle_id)

    def ingest_nikto(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        """Parse nikto output and ingest. Returns new Pearls."""
        return self._ingest_events(parse_nikto(text, target), cycle_id)

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def pearls(self) -> List[Pearl]:
        """Return all accumulated Pearls (independent copy)."""
        return list(self._pearls)

    def snapshot(self) -> Tuple[PearlArchive, List[Pearl]]:
        """Return (PearlArchive, pearl_list) for downstream stack construction."""
        return self._archive, list(self._pearls)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ingest_events(
        self,
        events:   List[MeasurementEvent],
        override: Optional[str],
    ) -> List[Pearl]:
        result = []
        for ev in events:
            pearl = self._make_pearl(ev, override)
            result.append(pearl)
        return result

    def _make_pearl(self, ev: MeasurementEvent, override: Optional[str]) -> Pearl:
        node_key = self._node_key if self._node_key != "unknown_host" else (ev.target or "unknown_host")
        cycle_id = self._discovery.assign(ev.ts, ev.gate_id, override)
        self._seq += 1
        pearl = Pearl(
            gate_id=ev.gate_id,
            node_key=node_key,
            workload_id=self._workload_id,
            instrument_id=f"measurement_{ev.tool}",
            cycle_id=cycle_id,
            ts=ev.ts,
            seq_id=self._seq,
            H_before=0.0,
            H_after=1.0,
            delta_H=1.0,
            phi_R_before=0.0,
            phi_R_after=1.0,
            phi_B_before=0.0,
            phi_B_after=0.0,
            state_before=GateState.U,
            state_after=GateState.R,
        )
        self._archive.record(pearl)
        self._pearls.append(pearl)
        return pearl
