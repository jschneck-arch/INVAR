"""
invar.adapters.measurement.tool_normalizer
==========================================
Domain-agnostic measurement adapter — M1 tool output normalization layer.

External instruments (nmap, mimikatz, enum4linux, PowerUp, nikto, Metasploit)
produce raw output.  This layer normalizes that output into MeasurementEvent
records, which flow into the Pearl construction pipeline identically to
Sysmon events.  The substrate does not know the difference.

Architecture (Section 3, INVAR Research Paper v2.28):
    ToolNormalizer   — instrument-level parser (one per tool)
    NormalizerRegistry — ordered lookup, first-match dispatch
    MeasurementEvent — canonical normalized event (frozen, schema-stable)
    MeasurementAdapter — orchestrates registry, CycleDiscovery, Pearl emission

MeasurementEvent schema (Section 3.2):
    timestamp   float        — unix time of observation
    source      str          — instrument name: "nmap" | "mimikatz" | ...
    node_key    str          — target host / node identifier
    workload_id str          — engagement workload identifier
    cycle_id    str          — phase cycle (operator override or auto-discovered)
    gate_id     str          — L2-5 compatible gate identifier
    raw_ref     Optional[str] — SHA-256[:16] of the source fragment

gate_id naming — substring-pattern compatible with L2-5 _ARTIFACT_RULES
(first-match, case-insensitive; see Appendix A):
    exec_*          → EXECUTION_ARTIFACT
    cred_*          → CREDENTIAL_ARTIFACT
    lateral_*       → LATERAL_ARTIFACT
    discover_*      → DISCOVERY_ARTIFACT   ← NO "smb" substring in discover_ ids
    persist_*       → PERSISTENCE_ARTIFACT
    collect_*       → COLLECTION_ARTIFACT
    c2_*            → C2_ARTIFACT

Supported instruments:
    nmap        (XML -oX)               → discover_nmap_*
    mimikatz    (console text)          → cred_mimikatz_* / cred_hash_* / cred_ticket_*
    enum4linux  (text)                  → discover_shares / discover_users / discover_groups
    PowerUp     (PowerShell text)       → persist_svc_* / persist_autorun / persist_dll_hijack
    nikto       (text)                  → discover_nikto_vuln / discover_web_*
    msf         (Metasploit console)    → exec_msf_* / cred_msf_* / lateral_msf_*

Constraints:
    - No tool execution — reads emitted output only
    - No Layer 0 modification
    - Pearls: phi_R=1.0, H=1.0, state_before=U, state_after=R
    - Deterministic: same source string + same context → same events
    - Adapter-local: domain labels never written to core canonical state
    - MeasurementEvent is frozen: immutable after construction

API:
    registry = NormalizerRegistry.default()
    context  = {"workload_id": "eng-01", "node_key": "TARGET-HP",
                 "cycle_id": "cycle-02-discovery", "timestamp": time.time()}
    events   = registry.parse("nmap", xml_str, context)

    adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
    pearls  = adapter.ingest("nmap", xml_str)
    pearls  = adapter.ingest("mimikatz", text, cycle_id="cycle-03-cred")
    all_p   = adapter.pearls()
    archive, pl = adapter.snapshot()
"""
from __future__ import annotations

import hashlib
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from invar.core.gate import GateState
from invar.core.support_engine import Pearl
from invar.persistence.pearl_archive import PearlArchive
from invar.adapters.redteam.windows_ingest import CycleDiscovery


# ---------------------------------------------------------------------------
# Canonical normalized event (Section 3.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MeasurementEvent:
    """
    Canonical output of any ToolNormalizer.

    Frozen: immutable after construction.  The gate_id field is the integration
    seam — its value must match the L2-5 substring classification rules so that
    the domain model's artifact_type() and cycle_primitive() functions classify
    the resulting Pearl correctly without modification.
    """
    timestamp:   float
    source:      str            # instrument name: "nmap" | "mimikatz" | ...
    node_key:    str            # target host / node
    workload_id: str
    cycle_id:    str
    gate_id:     str            # L2-5 compatible gate identifier
    raw_ref:     Optional[str]  # SHA-256[:16] of source fragment; None if unavailable


def _raw_ref(fragment: str) -> str:
    """Return a 16-char SHA-256 prefix of a raw output fragment."""
    return hashlib.sha256(fragment.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# ToolNormalizer protocol (Section 3.3)
# ---------------------------------------------------------------------------

class ToolNormalizer:
    """
    Base class for all instrument normalizers.

    Subclasses implement supports() and parse().  Normalizers do not score,
    rank, or interpret findings — they detect patterns and map to gate_ids.
    """

    def supports(self, source: str) -> bool:
        raise NotImplementedError

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        """
        Parse raw tool output into MeasurementEvents.

        context keys (all required):
            workload_id  str
            node_key     str
            cycle_id     str
            timestamp    float

        Returns an empty list for empty or unrecognised input.
        Never raises.
        """
        raise NotImplementedError

    # Shared helpers for subclasses
    def _event(
        self,
        gate_id:   str,
        context:   dict,
        fragment:  str = "",
        node_key:  Optional[str] = None,
    ) -> MeasurementEvent:
        return MeasurementEvent(
            timestamp=context["timestamp"],
            source=self.source_name(),
            node_key=node_key or context["node_key"],
            workload_id=context["workload_id"],
            cycle_id=context["cycle_id"],
            gate_id=gate_id,
            raw_ref=_raw_ref(fragment) if fragment else None,
        )

    def source_name(self) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _sanitize(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s).strip("_") or "unknown"


# ---------------------------------------------------------------------------
# NmapNormalizer
# ---------------------------------------------------------------------------

_NMAP_PORT_GATE: Dict[str, str] = {
    "80":   "discover_nmap_http",
    "8080": "discover_nmap_http",
    "443":  "discover_nmap_https",
    "8443": "discover_nmap_https",
    "445":  "discover_nmap_445",       # NOT discover_smb_* — avoids lateral collision
    "139":  "discover_nmap_445",
    "3389": "discover_nmap_rdp",
    "5985": "discover_nmap_winrm",
    "5986": "discover_nmap_winrm",
    "22":   "discover_nmap_ssh",
    "21":   "discover_nmap_ftp",
    "25":   "discover_nmap_smtp",
    "53":   "discover_nmap_dns",
}


class NmapNormalizer(ToolNormalizer):
    """Parses nmap XML output (-oX)."""

    def source_name(self) -> str:
        return "nmap"

    def supports(self, source: str) -> bool:
        return source == "nmap"

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        try:
            root = ET.fromstring(raw_input)
        except ET.ParseError:
            return events

        for host in root.findall(".//host"):
            addr_elem = host.find("address[@addrtype='ipv4']")
            if addr_elem is None:
                addr_elem = host.find("address")
            target = addr_elem.get("addr", context["node_key"]) if addr_elem is not None else context["node_key"]

            status = host.find("status")
            if status is None or status.get("state") != "up":
                continue

            frag = f"host up: {target}"
            events.append(self._event("discover_nmap_host", context, frag, node_key=target))

            for port in host.findall(".//port"):
                state = port.find("state")
                if state is None or state.get("state") != "open":
                    continue
                portid = port.get("portid", "")
                gate_id = _NMAP_PORT_GATE.get(portid, f"discover_nmap_port_{_sanitize(portid)}")
                frag = f"open {portid}/tcp on {target}"
                events.append(self._event(gate_id, context, frag, node_key=target))

                svc = port.find("service")
                if svc is not None:
                    name = svc.get("name", "").strip()
                    known = {"http", "https", "microsoft-ds", "msrdp", "netbios-ssn", "ms-wbt-server"}
                    if name and name not in known:
                        svc_frag = f"service {name} on {portid}"
                        events.append(self._event(
                            f"discover_nmap_service_{_sanitize(name)}",
                            context, svc_frag, node_key=target,
                        ))

            for osmatch in host.findall(".//osmatch"):
                name = osmatch.get("name", "")
                if name:
                    events.append(self._event("discover_nmap_os", context, f"os: {name}", node_key=target))
                    break

        return events


# ---------------------------------------------------------------------------
# MimikatzNormalizer
# ---------------------------------------------------------------------------

_MIMIKATZ_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)dcsync"),                          "cred_mimikatz_dcsync"),
    (re.compile(r"(?i)sekurlsa::logonpasswords"),        "cred_mimikatz_logonpw"),
    (re.compile(r"(?i)wdigest.*password\s*:\s*\S"),      "cred_mimikatz_wdigest"),
    (re.compile(r"(?i)\bNTLM\b.*:\s*[0-9a-fA-F]{32}"),  "cred_hash_ntlm"),
    (re.compile(r"(?i)(Kerberos|kerberos)\s*\*"),        "cred_ticket_kerberos"),
    (re.compile(r"(?i)\[kerberos\]"),                    "cred_ticket_kerberos"),
    (re.compile(r"(?i)lsass"),                           "cred_lsass_access"),
    (re.compile(r"(?i)sekurlsa::"),                      "cred_mimikatz_logonpw"),
    (re.compile(r"(?i)lsadump::"),                       "cred_mimikatz_dcsync"),
    (re.compile(r"(?i)mimikatz"),                        "cred_mimikatz_logonpw"),
]


class MimikatzNormalizer(ToolNormalizer):
    """Parses mimikatz console text output."""

    def source_name(self) -> str:
        return "mimikatz"

    def supports(self, source: str) -> bool:
        return source == "mimikatz"

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        seen: set = set()
        for line in raw_input.splitlines():
            line = line.strip()
            if not line:
                continue
            for regex, gate_id in _MIMIKATZ_RULES:
                if regex.search(line):
                    key = (gate_id, context["node_key"])
                    if key not in seen:
                        seen.add(key)
                        events.append(self._event(gate_id, context, line[:200]))
                    break
        return events


# ---------------------------------------------------------------------------
# Enum4linuxNormalizer
# ---------------------------------------------------------------------------

_ENUM4LINUX_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)(share|Disk|IPC\$|ADMIN\$|netlogon|sysvol)"), "discover_shares"),
    (re.compile(r"(?i)(local user|user\s*:|username\s*:|account\s*:)"), "discover_users"),
    (re.compile(r"(?i)(local group|group|member)"),                 "discover_groups"),
    (re.compile(r"(?i)(password\s*policy|lockout)"),               "discover_domain_policy"),
    (re.compile(r"(?i)(domain\s*name|workgroup)"),                 "discover_enum"),
    (re.compile(r"(?i)(session|established|opened)"),              "discover_enum"),
]


class Enum4linuxNormalizer(ToolNormalizer):
    """Parses enum4linux text output."""

    def source_name(self) -> str:
        return "enum4linux"

    def supports(self, source: str) -> bool:
        return source == "enum4linux"

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        seen: set = set()
        for line in raw_input.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for regex, gate_id in _ENUM4LINUX_RULES:
                if regex.search(line):
                    key = (gate_id, context["node_key"])
                    if key not in seen:
                        seen.add(key)
                        events.append(self._event(gate_id, context, line[:200]))
                    break
        return events


# ---------------------------------------------------------------------------
# PowerUpNormalizer
# ---------------------------------------------------------------------------

_POWERUP_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)unquoted.*service|UnquotedServicePath"),     "persist_svc_unquoted"),
    (re.compile(r"(?i)modifiable.*service|ModifiableServiceFile"), "persist_svc_modifiable"),
    (re.compile(r"(?i)modifiable.*binary|ModifiablePath"),         "persist_svc_modifiable"),
    (re.compile(r"(?i)(autorun|startup|CurrentVersion\\Run)"),     "persist_autorun"),
    (re.compile(r"(?i)dll.*hijack|HijackableDLL"),                 "persist_dll_hijack"),
    (re.compile(r"(?i)AlwaysInstallElevated"),                     "persist_registry"),
    (re.compile(r"(?i)modifiable.*schtask|ScheduledTask"),         "persist_schtask"),
    (re.compile(r"(?i)Invoke-AllChecks|\[+\]\s*Checking"),        "persist_checks"),
    (re.compile(r"(?i)AbuseFunction|Abuse\s+Function"),           "persist_checks"),
]


class PowerUpNormalizer(ToolNormalizer):
    """Parses PowerUp PowerShell text output."""

    def source_name(self) -> str:
        return "powerup"

    def supports(self, source: str) -> bool:
        return source in ("powerup", "powershell")

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        seen: set = set()
        for line in raw_input.splitlines():
            line = line.strip()
            if not line:
                continue
            for regex, gate_id in _POWERUP_RULES:
                if regex.search(line):
                    key = (gate_id, context["node_key"])
                    if key not in seen:
                        seen.add(key)
                        events.append(self._event(gate_id, context, line[:200]))
                    break
        return events


# ---------------------------------------------------------------------------
# NiktoNormalizer
# ---------------------------------------------------------------------------

_NIKTO_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)(OSVDB|CVE|vulnerability|vuln|XSS|SQL|inject|RFI|LFI|RCE|exec)"),
     "discover_nikto_vuln"),
    (re.compile(r"(?i)(directory|index of|listing enabled|/backup|/admin)"),
     "discover_web_dir"),
    (re.compile(r"(?i)(server:\s*\S|x-powered-by|apache|nginx|iis|tomcat|php)"),
     "discover_web_server"),
    (re.compile(r"(?i)(cookie.*httponly|cookie.*secure|missing header)"),
     "discover_nikto_vuln"),
    (re.compile(r"(?i)(allowed methods|OPTIONS|TRACE|PUT|DELETE)"),
     "discover_nikto_vuln"),
]


class NiktoNormalizer(ToolNormalizer):
    """Parses nikto text output."""

    def source_name(self) -> str:
        return "nikto"

    def supports(self, source: str) -> bool:
        return source == "nikto"

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        seen: set = set()
        for line in raw_input.splitlines():
            line = line.strip()
            if not line or line.startswith("-"):
                continue
            for regex, gate_id in _NIKTO_RULES:
                if regex.search(line):
                    key = (gate_id, context["node_key"])
                    if key not in seen:
                        seen.add(key)
                        events.append(self._event(gate_id, context, line[:200]))
                    break
        return events


# ---------------------------------------------------------------------------
# MetasploitNormalizer
# ---------------------------------------------------------------------------

_MSF_RULES: List[Tuple[re.Pattern, str]] = [
    # Specific rules first; meterpreter prompt catch-all last
    (re.compile(r"(?i)psexec|psexesvc"),                                     "lateral_msf_psexec"),
    # hashdump output line: username:rid:lmhash:nthash::: format
    (re.compile(r"[A-Za-z0-9_$]+:\d+:[0-9a-fA-F]{32}:[0-9a-fA-F]{32}:::"), "cred_msf_capture"),
    (re.compile(r"(?i)(\bhashdump\b|credential\s*:|ntlm\s*:|password\s*:)"), "cred_msf_capture"),
    (re.compile(r"(?i)(auxiliary|exploit)\s*/\w"),                           "exec_msf_module"),
    (re.compile(r"(?i)post/\w"),                                             "exec_msf_module"),
    (re.compile(r"(?i)(loot|collect|download)"),                             "collect_msf_loot"),
    (re.compile(r"(?i)shell\s+command"),                                     "exec_msf_session"),
    # catch-all: any line referencing a session open or meterpreter prompt
    (re.compile(r"(?i)(session\s+\d+\s+opened|meterpreter)"),                "exec_msf_session"),
]


class MetasploitNormalizer(ToolNormalizer):
    """Parses Metasploit Framework console text output."""

    def source_name(self) -> str:
        return "msf"

    def supports(self, source: str) -> bool:
        return source in ("msf", "metasploit")

    def parse(self, raw_input: str, context: dict) -> List[MeasurementEvent]:
        events: List[MeasurementEvent] = []
        seen: set = set()
        for line in raw_input.splitlines():
            line = line.strip()
            if not line:
                continue
            for regex, gate_id in _MSF_RULES:
                if regex.search(line):
                    key = (gate_id, context["node_key"])
                    if key not in seen:
                        seen.add(key)
                        events.append(self._event(gate_id, context, line[:200]))
                    break
        return events


# ---------------------------------------------------------------------------
# NormalizerRegistry (Section 3.5)
# ---------------------------------------------------------------------------

class NormalizerRegistry:
    """
    Ordered lookup of ToolNormalizer instances.

    Iterates registered normalizers in order; calls parse() on the first
    where supports() returns True.  Unrecognized source values produce an
    empty list — not an error — so unknown tool output cannot crash the pipeline.
    """

    def __init__(self) -> None:
        self._normalizers: List[ToolNormalizer] = []

    def register(self, normalizer: ToolNormalizer) -> None:
        """Append a normalizer to the end of the lookup list."""
        self._normalizers.append(normalizer)

    def parse(self, source: str, raw: str, context: dict) -> List[MeasurementEvent]:
        """
        Dispatch raw output to the first normalizer that supports the source.

        Returns an empty list if no normalizer claims the source or if the
        normalizer produces no events.  Never raises.
        """
        for n in self._normalizers:
            if n.supports(source):
                try:
                    return n.parse(raw, context)
                except Exception:
                    return []
        return []

    @classmethod
    def default(cls) -> "NormalizerRegistry":
        """Return a registry pre-loaded with all built-in normalizers."""
        reg = cls()
        reg.register(NmapNormalizer())
        reg.register(MimikatzNormalizer())
        reg.register(Enum4linuxNormalizer())
        reg.register(PowerUpNormalizer())
        reg.register(NiktoNormalizer())
        reg.register(MetasploitNormalizer())
        return reg


# ---------------------------------------------------------------------------
# Source → representative gate_id for CycleDiscovery
# ---------------------------------------------------------------------------

_SOURCE_GATE: Dict[str, str] = {
    "nmap":        "discover_nmap_host",
    "enum4linux":  "discover_enum",
    "nikto":       "discover_nikto_vuln",
    "mimikatz":    "cred_mimikatz_logonpw",
    "powerup":     "persist_checks",
    "powershell":  "persist_checks",
    "msf":         "exec_msf_session",
    "metasploit":  "exec_msf_session",
}


# ---------------------------------------------------------------------------
# MeasurementAdapter (Section 3.6 + Section 4.6)
# ---------------------------------------------------------------------------

class MeasurementAdapter:
    """
    Stateful adapter: normalizes tool output into Invar Pearls via registry.

    Uses NormalizerRegistry.default() by default; accepts a custom registry
    for testing or extension.  Cycle discovery is per ingest() call: the
    source's representative gate_id drives CycleDiscovery's primitive-shift
    logic, keeping phase boundaries consistent with Sysmon ingest.

    Convenience methods (ingest_nmap, ingest_mimikatz, ...) delegate to
    ingest() with the appropriate source string.
    """

    def __init__(
        self,
        workload_id:   str,
        node_key:      str              = "unknown_host",
        gap_threshold: float            = 300.0,
        shift_window:  int              = 5,
        registry:      Optional[NormalizerRegistry] = None,
    ) -> None:
        self._workload_id = workload_id
        self._node_key    = node_key
        self._discovery   = CycleDiscovery(gap_threshold, shift_window)
        self._archive     = PearlArchive()
        self._pearls:     List[Pearl] = []
        self._seq         = 0
        self._registry    = registry or NormalizerRegistry.default()

    # ------------------------------------------------------------------
    # Primary ingest entry point
    # ------------------------------------------------------------------

    def ingest(
        self,
        source:   str,
        raw:      str,
        cycle_id: Optional[str] = None,
        target:   str           = "",
    ) -> List[Pearl]:
        """
        Normalize raw tool output and emit Pearls.

        source   — instrument name ("nmap", "mimikatz", "enum4linux", ...)
        raw      — raw tool output string
        cycle_id — operator cycle override; None → auto-discover
        target   — node_key override for this call; falls back to adapter node_key
        """
        ts = time.time()
        node = target or self._node_key
        rep_gate = _SOURCE_GATE.get(source, f"discover_{_sanitize(source)}")
        assigned_cycle = self._discovery.assign(ts, rep_gate, cycle_id)
        context = {
            "workload_id": self._workload_id,
            "node_key":    node,
            "cycle_id":    assigned_cycle,
            "timestamp":   ts,
        }
        events = self._registry.parse(source, raw, context)
        return [self._make_pearl(ev) for ev in events]

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def ingest_nmap(self, xml_str: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("nmap", xml_str, cycle_id, target)

    def ingest_mimikatz(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("mimikatz", text, cycle_id, target)

    def ingest_enum4linux(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("enum4linux", text, cycle_id, target)

    def ingest_powerup(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("powerup", text, cycle_id, target)

    def ingest_nikto(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("nikto", text, cycle_id, target)

    def ingest_msf(self, text: str, cycle_id: Optional[str] = None, target: str = "") -> List[Pearl]:
        return self.ingest("msf", text, cycle_id, target)

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def pearls(self) -> List[Pearl]:
        return list(self._pearls)

    def snapshot(self) -> Tuple[PearlArchive, List[Pearl]]:
        return self._archive, list(self._pearls)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_pearl(self, ev: MeasurementEvent) -> Pearl:
        self._seq += 1
        pearl = Pearl(
            gate_id=ev.gate_id,
            node_key=ev.node_key,
            workload_id=ev.workload_id,
            instrument_id=f"measurement_{ev.source}",
            cycle_id=ev.cycle_id,
            ts=ev.timestamp,
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
