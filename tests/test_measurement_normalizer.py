"""
Tests for M1 — Tool Output Normalization Layer
invar/adapters/measurement/tool_normalizer.py

Each test class covers one instrument parser plus the MeasurementAdapter
integration.  No tools are executed; all inputs are synthetic output strings.
"""
from __future__ import annotations
import time
import pytest

from invar.adapters.measurement.tool_normalizer import (
    MeasurementAdapter,
    MeasurementEvent,
    parse_nmap,
    parse_mimikatz,
    parse_enum4linux,
    parse_powerup,
    parse_nikto,
)
from invar.core.gate import GateState
from invar.persistence.pearl_archive import PearlArchive


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
	Sharename       Type      Comment
	---------       ----      -------
	ADMIN$          Disk      Remote Admin
	C$              Disk      Default share
	IPC$            IPC       Remote IPC
	Users           Disk

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


# ===========================================================================
# nmap parser
# ===========================================================================

class TestNmapParser:

    def test_nmap_host_up(self):
        events = parse_nmap(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_host" in gate_ids

    def test_nmap_smb_port(self):
        events = parse_nmap(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_smb" in gate_ids

    def test_nmap_http_port(self):
        events = parse_nmap(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_http" in gate_ids

    def test_nmap_ssh_port(self):
        events = parse_nmap(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_ssh" in gate_ids

    def test_nmap_os(self):
        events = parse_nmap(NMAP_XML_BASIC)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_os" in gate_ids

    def test_nmap_target_from_xml(self):
        events = parse_nmap(NMAP_XML_BASIC)
        for e in events:
            assert e.target == "192.168.1.50"

    def test_nmap_closed_host_no_events(self):
        events = parse_nmap(NMAP_XML_CLOSED)
        assert events == []

    def test_nmap_multi_host(self):
        events = parse_nmap(NMAP_XML_MULTI_HOST)
        targets = {e.target for e in events}
        assert "10.0.0.1" in targets
        assert "10.0.0.2" in targets

    def test_nmap_rdp(self):
        events = parse_nmap(NMAP_XML_MULTI_HOST)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_rdp" in gate_ids

    def test_nmap_https(self):
        events = parse_nmap(NMAP_XML_MULTI_HOST)
        gate_ids = [e.gate_id for e in events]
        assert "discover_nmap_https" in gate_ids

    def test_nmap_malformed_xml(self):
        events = parse_nmap("<not valid<<<")
        assert events == []

    def test_nmap_tool_label(self):
        events = parse_nmap(NMAP_XML_BASIC)
        for e in events:
            assert e.tool == "nmap"

    def test_nmap_deterministic(self):
        t = 1_000_000.0
        assert parse_nmap(NMAP_XML_BASIC, ts=t) == parse_nmap(NMAP_XML_BASIC, ts=t)


# ===========================================================================
# mimikatz parser
# ===========================================================================

class TestMimikatzParser:

    def test_mimi_logonpw(self):
        events = parse_mimikatz(MIMIKATZ_SEKURLSA, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "cred_mimikatz_logonpw" in gate_ids

    def test_mimi_ntlm_hash(self):
        events = parse_mimikatz(MIMIKATZ_SEKURLSA, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "cred_hash_ntlm" in gate_ids

    def test_mimi_dcsync(self):
        events = parse_mimikatz(MIMIKATZ_DCSYNC, target="DC01")
        gate_ids = [e.gate_id for e in events]
        assert "cred_mimikatz_dcsync" in gate_ids

    def test_mimi_dcsync_ntlm(self):
        events = parse_mimikatz(MIMIKATZ_DCSYNC, target="DC01")
        gate_ids = [e.gate_id for e in events]
        assert "cred_hash_ntlm" in gate_ids

    def test_mimi_deduplication(self):
        """Same gate_id for same target appears only once."""
        doubled = MIMIKATZ_DCSYNC + "\n" + MIMIKATZ_DCSYNC
        events = parse_mimikatz(doubled, target="DC01")
        gate_ids = [e.gate_id for e in events]
        assert gate_ids.count("cred_mimikatz_dcsync") == 1

    def test_mimi_target_preserved(self):
        events = parse_mimikatz(MIMIKATZ_SEKURLSA, target="WORKSTATION1")
        for e in events:
            assert e.target == "WORKSTATION1"

    def test_mimi_empty_text(self):
        events = parse_mimikatz("", target="host")
        assert events == []

    def test_mimi_tool_label(self):
        events = parse_mimikatz(MIMIKATZ_SEKURLSA)
        for e in events:
            assert e.tool == "mimikatz"

    def test_mimi_deterministic(self):
        t = 1_000_000.0
        assert parse_mimikatz(MIMIKATZ_SEKURLSA, ts=t) == parse_mimikatz(MIMIKATZ_SEKURLSA, ts=t)


# ===========================================================================
# enum4linux parser
# ===========================================================================

class TestEnum4linuxParser:

    def test_e4l_shares(self):
        events = parse_enum4linux(ENUM4LINUX_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_smb_shares" in gate_ids

    def test_e4l_users(self):
        events = parse_enum4linux(ENUM4LINUX_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_smb_users" in gate_ids

    def test_e4l_groups(self):
        events = parse_enum4linux(ENUM4LINUX_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_smb_groups" in gate_ids

    def test_e4l_deduplication(self):
        events = parse_enum4linux(ENUM4LINUX_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert gate_ids.count("discover_smb_shares") == 1

    def test_e4l_tool_label(self):
        events = parse_enum4linux(ENUM4LINUX_OUTPUT)
        for e in events:
            assert e.tool == "enum4linux"

    def test_e4l_empty_text(self):
        events = parse_enum4linux("")
        assert events == []

    def test_e4l_deterministic(self):
        t = 1_000_000.0
        assert (
            parse_enum4linux(ENUM4LINUX_OUTPUT, ts=t)
            == parse_enum4linux(ENUM4LINUX_OUTPUT, ts=t)
        )


# ===========================================================================
# PowerUp parser
# ===========================================================================

class TestPowerUpParser:

    def test_pu_unquoted(self):
        events = parse_powerup(POWERUP_OUTPUT, target="WORKSTATION1")
        gate_ids = [e.gate_id for e in events]
        assert "persist_svc_unquoted" in gate_ids

    def test_pu_modifiable(self):
        events = parse_powerup(POWERUP_OUTPUT, target="WORKSTATION1")
        gate_ids = [e.gate_id for e in events]
        assert "persist_svc_modifiable" in gate_ids

    def test_pu_autorun(self):
        events = parse_powerup(POWERUP_OUTPUT, target="WORKSTATION1")
        gate_ids = [e.gate_id for e in events]
        assert "persist_autorun" in gate_ids

    def test_pu_dll_hijack(self):
        events = parse_powerup(POWERUP_OUTPUT, target="WORKSTATION1")
        gate_ids = [e.gate_id for e in events]
        assert "persist_dll_hijack" in gate_ids

    def test_pu_checks(self):
        events = parse_powerup(POWERUP_OUTPUT, target="WORKSTATION1")
        gate_ids = [e.gate_id for e in events]
        assert "persist_checks" in gate_ids

    def test_pu_deduplication(self):
        doubled = POWERUP_OUTPUT + "\n" + POWERUP_OUTPUT
        events = parse_powerup(doubled, target="host")
        gate_ids = [e.gate_id for e in events]
        assert gate_ids.count("persist_svc_unquoted") == 1

    def test_pu_tool_label(self):
        events = parse_powerup(POWERUP_OUTPUT)
        for e in events:
            assert e.tool == "powerup"

    def test_pu_empty_text(self):
        events = parse_powerup("")
        assert events == []

    def test_pu_deterministic(self):
        t = 1_000_000.0
        assert parse_powerup(POWERUP_OUTPUT, ts=t) == parse_powerup(POWERUP_OUTPUT, ts=t)


# ===========================================================================
# nikto parser
# ===========================================================================

class TestNiktoParser:

    def test_nikto_vuln(self):
        events = parse_nikto(NIKTO_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_nikto_vuln" in gate_ids

    def test_nikto_server(self):
        events = parse_nikto(NIKTO_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_web_server" in gate_ids

    def test_nikto_web_dir(self):
        events = parse_nikto(NIKTO_OUTPUT, target="192.168.1.50")
        gate_ids = [e.gate_id for e in events]
        assert "discover_web_dir" in gate_ids

    def test_nikto_tool_label(self):
        events = parse_nikto(NIKTO_OUTPUT)
        for e in events:
            assert e.tool == "nikto"

    def test_nikto_empty_text(self):
        events = parse_nikto("")
        assert events == []

    def test_nikto_deterministic(self):
        t = 1_000_000.0
        assert parse_nikto(NIKTO_OUTPUT, ts=t) == parse_nikto(NIKTO_OUTPUT, ts=t)


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
        pearls = adapter.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c03", target="TARGET-HP")
        gate_ids = [p.gate_id for p in pearls]
        assert any("cred_" in g for g in gate_ids)

    def test_ingest_enum4linux_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_enum4linux(ENUM4LINUX_OUTPUT, cycle_id="c02")
        gate_ids = [p.gate_id for p in pearls]
        assert "discover_smb_shares" in gate_ids

    def test_ingest_powerup_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_powerup(POWERUP_OUTPUT, cycle_id="c04")
        gate_ids = [p.gate_id for p in pearls]
        assert any("persist_" in g for g in gate_ids)

    def test_ingest_nikto_pearls(self):
        adapter = MeasurementAdapter("eng-01", node_key="TARGET-HP")
        pearls = adapter.ingest_nikto(NIKTO_OUTPUT, cycle_id="c05")
        gate_ids = [p.gate_id for p in pearls]
        assert "discover_nikto_vuln" in gate_ids

    def test_pearl_fields_correct(self):
        adapter = MeasurementAdapter("eng-42", node_key="HP-WIN11")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="recon-01")
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
        for p in pearls:
            assert "mimikatz" in p.instrument_id

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
        all_p = adapter.pearls()
        assert len(all_p) > 1

    def test_snapshot(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        archive, pl = adapter.snapshot()
        assert isinstance(archive, PearlArchive)
        assert len(pl) == len(adapter.pearls())
        assert len(archive.pearls) == len(pl)

    def test_cycle_override(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="operator-recon")
        for p in pearls:
            assert p.cycle_id == "operator-recon"

    def test_auto_cycle_discovery(self):
        adapter = MeasurementAdapter("eng-01", node_key="HOST")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC)
        assert len(pearls) > 0
        assert pearls[0].cycle_id.startswith("auto_")

    def test_node_key_from_adapter(self):
        """Explicit adapter node_key takes precedence over event target."""
        adapter = MeasurementAdapter("eng-01", node_key="FIXED-HOST")
        pearls = adapter.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
        for p in pearls:
            assert p.node_key == "FIXED-HOST"

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
            a.ingest_nmap(NMAP_XML_BASIC, cycle_id="c01")
            a.ingest_mimikatz(MIMIKATZ_SEKURLSA, cycle_id="c03")
            return [(p.gate_id, p.cycle_id) for p in a.pearls()]
        assert run() == run()
