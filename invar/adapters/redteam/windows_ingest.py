"""
invar.adapters.redteam.windows_ingest
=======================================
Windows 11 / Sysmon ingest adapter for passive red team observation.

Converts Sysmon XML events (and Windows Event Log XML as fallback) into
Invar Pearl objects using rule-aligned gate_id naming compatible with the
L2-5 artifact classification rules in domain_model.py.

The adapter discovers cycle boundaries autonomously from the event stream —
no pre-labeling of operation phases is required.  Operators may supply
explicit cycle_ids to override auto-discovery for any ingestion call.

Cycle boundary discovery (in priority order):
    1. Operator override: explicit cycle_id argument → use verbatim
    2. Time-gap boundary: event gap > gap_threshold seconds (default 300 s)
       → start new cycle
    3. Primitive-shift boundary: when a run of ≥ shift_window consecutive
       non-UNKNOWN events of the same type is followed by a non-UNKNOWN event
       of a different type → start new cycle

gate_id naming (compatible with L2-5 classification rules):
    exec_*          → EXECUTION_ARTIFACT
    exec_script     → EXECUTION_ARTIFACT (script file drops)
    cred_*          → CREDENTIAL_ARTIFACT
    lateral_*       → LATERAL_ARTIFACT   (port-keyed and tool-keyed)
    discover_*      → DISCOVERY_ARTIFACT
    persist_*       → PERSISTENCE_ARTIFACT
    collect_file_*  → COLLECTION_ARTIFACT
    c2_*            → C2_ARTIFACT

Supported Sysmon Event IDs:
    1   ProcessCreate       → exec_* / discover_* / persist_* / lateral_*
    3   NetworkConnect      → lateral_* / c2_*
    7   ImageLoad           → exec_dll_* / cred_dll_load
    8   CreateRemoteThread  → exec_remote_thread / cred_*
    10  ProcessAccess       → cred_lsass_access / cred_*
    11  FileCreate          → persist_autorun / exec_script / collect_file_*
    12  RegistryEvent       → persist_*
    13  RegistryEvent       → persist_*

Windows Event Log fallback:
    4688  ProcessCreate (Security log) — same mapping as Sysmon EID 1
    4698  ScheduledTask created        → persist_schtask
    4624  Logon event                  → lateral_logon

Input formats accepted:
    - Single <Event> element
    - <Events> container wrapping multiple <Event> elements
    - Namespace-qualified or bare tags (both handled)

API:
    adapter = WindowsIngestAdapter(workload_id="engagement-01")
    pearls  = adapter.ingest_sysmon_xml(xml_string)          # Sysmon source
    pearls  = adapter.ingest_event_log_xml(xml_string)       # Security log fallback
    pearls  = adapter.ingest_sysmon_xml(xml, cycle_id="c01") # operator override
    all_p   = adapter.pearls()
    archive, pearl_list = adapter.snapshot()

Constraints:
    - No Layer 0 modification (Pearls are constructed directly, bypassing engine.ingest)
    - No execution, no automation, no side effects on the Windows host
    - Deterministic: same event stream in same order → same Pearls
    - Discovers: cycle boundaries emerge from event data, not pre-assignment
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Dict, List, Optional, Tuple

from invar.core.gate import GateState
from invar.core.support_engine import Pearl
from invar.persistence.pearl_archive import PearlArchive
from invar.adapters.redteam.domain_model import ArtifactType, classify_gate_id

# ---------------------------------------------------------------------------
# XML namespace helpers
# ---------------------------------------------------------------------------

_NS_URI = "http://schemas.microsoft.com/win/2004/08/events/event"
_NS_PFX = f"{{{_NS_URI}}}"


def _find(parent, tag: str):
    result = parent.find(f"{_NS_PFX}{tag}")
    return result if result is not None else parent.find(tag)


def _findall(parent, tag: str) -> list:
    result = parent.findall(f"{_NS_PFX}{tag}")
    return result if result else parent.findall(tag)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _basename(path: str) -> str:
    """Return the final component of a Windows or POSIX path."""
    if not path:
        return ""
    return PurePath(path.replace("\\", "/")).name


def _sanitize(s: str) -> str:
    """Replace non-alphanumeric characters with underscores for gate_id safety."""
    return "".join(c if c.isalnum() else "_" for c in s).strip("_") or "unknown"


def _parse_timestamp(ts: str) -> float:
    """Parse Sysmon/EventLog SystemTime string to Unix float."""
    ts = ts.rstrip("Z").strip()
    if "." in ts:
        base, frac = ts.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        ts = f"{base}.{frac}"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Normalized event
# ---------------------------------------------------------------------------

@dataclass
class SysmonEvent:
    """Normalized Windows telemetry event."""
    event_id:  int
    timestamp: float
    hostname:  str
    fields:    Dict[str, str]

    def f(self, name: str, default: str = "") -> str:
        return self.fields.get(name, default)

    @property
    def image_basename(self) -> str:
        return _basename(self.f("Image") or self.f("NewProcessName") or self.f("NewImage")).lower()

    @property
    def dest_port(self) -> int:
        try:
            return int(self.f("DestinationPort", "0"))
        except ValueError:
            return 0

    @property
    def target_image_basename(self) -> str:
        return _basename(self.f("TargetImage")).lower()

    @property
    def target_object(self) -> str:
        return self.f("TargetObject", "").lower()

    @property
    def target_filename(self) -> str:
        return self.f("TargetFilename", "").lower()

    @property
    def image_loaded_basename(self) -> str:
        return _basename(self.f("ImageLoaded")).lower()


# ---------------------------------------------------------------------------
# gate_id mapping
# ---------------------------------------------------------------------------

# Processes that bypass the generic exec_ fallback with specific labels
_PROCESS_GATE_MAP: Dict[str, str] = {
    # Interpreters / loaders
    "powershell.exe":  "exec_powershell",
    "pwsh.exe":        "exec_powershell",
    "cmd.exe":         "exec_cmd",
    "wscript.exe":     "exec_wscript",
    "cscript.exe":     "exec_wscript",
    "mshta.exe":       "exec_mshta",
    "rundll32.exe":    "exec_rundll32",
    "regsvr32.exe":    "exec_regsvr32",
    "msiexec.exe":     "exec_msiexec",
    "wmic.exe":        "exec_wmi",
    "bitsadmin.exe":   "exec_bits",
    "certutil.exe":    "exec_certutil",
    # Discovery
    "net.exe":         "discover_net_enum",
    "net1.exe":        "discover_net_enum",
    "nltest.exe":      "discover_nltest",
    "whoami.exe":      "discover_whoami",
    "ipconfig.exe":    "discover_enum",
    "systeminfo.exe":  "discover_enum",
    "tasklist.exe":    "discover_enum",
    "arp.exe":         "discover_enum",
    "ping.exe":        "discover_net_enum",
    "nslookup.exe":    "discover_net_enum",
    "nbtstat.exe":     "discover_net_enum",
    "netstat.exe":     "discover_net_enum",
    # Persistence
    "schtasks.exe":    "persist_schtask",
    "reg.exe":         "persist_registry",
    "sc.exe":          "persist_svc",
    "at.exe":          "persist_schtask",
    # Lateral
    "psexec.exe":      "lateral_psexec",
    "psexesvc.exe":    "lateral_psexec",
}

# Credential dumping DLLs (substring match against image_loaded)
_CRED_DLLS = ("wdigest", "kerberos", "msv1_0", "tspkg", "livessp", "samsrv", "ntdsa")


def _map_process_create(ev: SysmonEvent) -> str:
    img = ev.image_basename
    if img in _PROCESS_GATE_MAP:
        return _PROCESS_GATE_MAP[img]
    base = img.rsplit(".", 1)[0] if "." in img else img
    return f"exec_{_sanitize(base)}" if base else "exec_unknown"


def _map_network_connect(ev: SysmonEvent) -> str:
    port = ev.dest_port
    dest = _sanitize(ev.f("DestinationHostname") or ev.f("DestinationIp") or "unknown")
    if port == 445:
        return f"lateral_smb_{dest}"
    if port in (5985, 5986):
        return f"lateral_winrm_{dest}"
    if port == 3389:
        return f"lateral_rdp_{dest}"
    if port == 135:
        return "lateral_rpc_dcom"
    if port in (80, 8080):
        return "c2_beacon_http"
    if port in (443, 8443):
        return "c2_beacon_https"
    if port == 53:
        return "c2_dns_beacon"
    return f"c2_channel_{port}"


def _map_process_access(ev: SysmonEvent) -> str:
    target = ev.target_image_basename
    if "lsass" in target:
        return "cred_lsass_access"
    if "winlogon" in target:
        return "cred_winlogon_access"
    if "sam" in target:
        return "cred_sam_access"
    return "exec_remote_thread"


def _map_registry_event(ev: SysmonEvent) -> str:
    key = ev.target_object
    if any(p in key for p in ("\\run", "\\runonce", "\\startup", "start menu")):
        return "persist_autorun"
    if "services" in key:
        return "persist_svc"
    if "schedule" in key or "tasks" in key or "schtask" in key:
        return "persist_schtask"
    return "persist_registry"


def _map_file_create(ev: SysmonEvent) -> str:
    path = ev.target_filename
    if "startup" in path or "start menu" in path:
        return "persist_autorun"
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    if ext in ("ps1", "bat", "cmd", "vbs", "js", "hta", "wsf"):
        return "exec_script"
    if ext == "dll":
        return "exec_dll"
    name = _sanitize(_basename(ev.f("TargetFilename")))
    return f"collect_file_{name}"


def _map_image_load(ev: SysmonEvent) -> str:
    img = ev.image_loaded_basename
    if any(p in img for p in _CRED_DLLS):
        return "cred_dll_load"
    name = _sanitize(img.rsplit(".", 1)[0] if "." in img else img)
    return f"exec_dll_{name}"


# Map event_id → mapping function
_EID_MAP = {
    1:    _map_process_create,
    3:    _map_network_connect,
    7:    _map_image_load,
    8:    _map_process_access,
    10:   _map_process_access,
    11:   _map_file_create,
    12:   _map_registry_event,
    13:   _map_registry_event,
    4688: _map_process_create,
    4698: lambda _: "persist_schtask",
    4624: lambda _: "lateral_logon",
}


def map_event_to_gate_id(event: SysmonEvent) -> Optional[str]:
    """Return rule-aligned gate_id for a SysmonEvent, or None if unrecognised."""
    fn = _EID_MAP.get(event.event_id)
    return fn(event) if fn is not None else None


# ---------------------------------------------------------------------------
# Cycle auto-discovery
# ---------------------------------------------------------------------------

_TYPE_TO_LABEL: Dict[str, str] = {
    ArtifactType.EXECUTION_ARTIFACT:   "execution",
    ArtifactType.PERSISTENCE_ARTIFACT: "persistence",
    ArtifactType.CREDENTIAL_ARTIFACT:  "cred_access",
    ArtifactType.DISCOVERY_ARTIFACT:   "discovery",
    ArtifactType.LATERAL_ARTIFACT:     "lateral",
    ArtifactType.COLLECTION_ARTIFACT:  "collection",
    ArtifactType.C2_ARTIFACT:          "c2",
    ArtifactType.UNKNOWN:              "unknown",
}


class CycleDiscovery:
    """
    Stateful, autonomous cycle-boundary detector.

    Discovers phase boundaries from the event stream without pre-labeling.
    Operator-supplied override takes absolute priority.

    Boundary triggers (in order):
        1. Operator override — explicit cycle_id argument
        2. Time gap — event timestamp gap > gap_threshold seconds
        3. Primitive shift — stable run of non-UNKNOWN type A followed
           by non-UNKNOWN type B (requires shift_window consecutive events)
    """

    def __init__(
        self,
        gap_threshold: float = 300.0,
        shift_window:  int   = 5,
    ) -> None:
        self._gap       = gap_threshold
        self._win       = shift_window
        self._idx       = 0
        self._cycle:    Optional[str]   = None
        self._last_ts:  Optional[float] = None
        self._history:  List[str]       = []   # recent ArtifactType values

    def assign(
        self,
        ts:       float,
        gate_id:  str,
        override: Optional[str] = None,
    ) -> str:
        """Return the cycle_id for an event at timestamp ts with the given gate_id."""
        if override is not None:
            self._cycle   = override
            self._last_ts = ts
            self._history.clear()
            return override

        new_type = classify_gate_id(gate_id)

        if self._cycle is None:
            return self._start(ts, new_type)
        if self._last_ts is not None and (ts - self._last_ts) > self._gap:
            return self._start(ts, new_type)
        if self._detect_shift(new_type):
            return self._start(ts, new_type)

        self._last_ts = ts
        self._history.append(new_type)
        if len(self._history) > self._win * 2:
            self._history = self._history[-self._win:]
        return self._cycle

    def _start(self, ts: float, artifact_type: str) -> str:
        self._idx   += 1
        label        = _TYPE_TO_LABEL.get(artifact_type, "unknown")
        self._cycle  = f"auto_{self._idx:03d}_{label}"
        self._last_ts = ts
        self._history = [artifact_type]
        return self._cycle

    def _detect_shift(self, new_type: str) -> bool:
        if new_type == ArtifactType.UNKNOWN:
            return False
        non_unk = [t for t in self._history if t != ArtifactType.UNKNOWN]
        if len(non_unk) < self._win:
            return False
        # All recent non-unknown events must be the same type (stable run)
        dominant = non_unk[-1]
        if not all(t == dominant for t in non_unk[-self._win:]):
            return False
        return new_type != dominant


# ---------------------------------------------------------------------------
# XML parser
# ---------------------------------------------------------------------------

def parse_sysmon_event(elem) -> Optional[SysmonEvent]:
    """Parse a single <Event> XML element into a SysmonEvent. Returns None on failure."""
    try:
        system = _find(elem, "System")
        if system is None:
            return None
        eid_e = _find(system, "EventID")
        if eid_e is None or not eid_e.text:
            return None
        event_id = int(eid_e.text.strip())

        tc = _find(system, "TimeCreated")
        ts = _parse_timestamp(tc.get("SystemTime", "")) if tc is not None else 0.0

        comp = _find(system, "Computer")
        hostname = comp.text.strip() if comp is not None and comp.text else "unknown"

        event_data = _find(elem, "EventData")
        fields: Dict[str, str] = {}
        if event_data is not None:
            for data in _findall(event_data, "Data"):
                name = data.get("Name", "")
                if name:
                    fields[name] = (data.text or "").strip()

        return SysmonEvent(
            event_id=event_id,
            timestamp=ts,
            hostname=hostname,
            fields=fields,
        )
    except (ValueError, AttributeError, TypeError):
        return None


def parse_events_xml(xml_str: str) -> List[SysmonEvent]:
    """Parse a Sysmon XML string (single Event or Events container)."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []
    tag = root.tag.replace(f"{_NS_PFX}", "").replace(
        f"{{{_NS_URI}}}", ""
    )
    if tag == "Events":
        elems = list(root)
    elif tag == "Event":
        elems = [root]
    else:
        elems = []
    events = []
    for elem in elems:
        ev = parse_sysmon_event(elem)
        if ev is not None:
            events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Top-level ingest adapter
# ---------------------------------------------------------------------------

class WindowsIngestAdapter:
    """
    Stateful ingest adapter: converts Windows telemetry into Invar Pearls.

    Maintains a PearlArchive and monotone seq_id counter across all calls.
    Cycle boundaries are discovered autonomously; operator may override per call.
    Nothing is executed on the target system; this is a passive parser only.
    """

    def __init__(
        self,
        workload_id:   str,
        node_key:      Optional[str] = None,
        gap_threshold: float         = 300.0,
        shift_window:  int           = 5,
    ) -> None:
        self._workload_id = workload_id
        self._node_key    = node_key
        self._discovery   = CycleDiscovery(gap_threshold, shift_window)
        self._archive     = PearlArchive()
        self._pearls:     List[Pearl] = []
        self._seq         = 0

    def ingest_sysmon_xml(
        self,
        xml_str:  str,
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """Parse Sysmon XML and ingest resulting events. Returns new Pearls."""
        result = []
        for ev in parse_events_xml(xml_str):
            pearl = self._ingest_event(ev, cycle_id)
            if pearl is not None:
                result.append(pearl)
        return result

    def ingest_event_log_xml(
        self,
        xml_str:  str,
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """Parse Windows Event Log XML (Security log fallback). Same path as Sysmon."""
        return self.ingest_sysmon_xml(xml_str, cycle_id)

    def pearls(self) -> List[Pearl]:
        """Return all accumulated Pearls (independent copy)."""
        return list(self._pearls)

    def snapshot(self) -> Tuple[PearlArchive, List[Pearl]]:
        """Return (PearlArchive, pearl_list) for downstream stack construction."""
        return self._archive, list(self._pearls)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ingest_event(
        self,
        event:    SysmonEvent,
        override: Optional[str],
    ) -> Optional[Pearl]:
        gate_id = map_event_to_gate_id(event)
        if gate_id is None:
            return None

        node_key = self._node_key or event.hostname or "unknown_host"
        cycle_id = self._discovery.assign(event.timestamp, gate_id, override)

        self._seq += 1
        pearl = Pearl(
            gate_id=gate_id,
            node_key=node_key,
            workload_id=self._workload_id,
            instrument_id="windows_ingest",
            cycle_id=cycle_id,
            ts=event.timestamp,
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
            coupling_propagated=False,
        )
        self._archive.record(pearl)
        self._pearls.append(pearl)
        return pearl
