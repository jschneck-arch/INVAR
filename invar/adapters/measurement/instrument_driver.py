"""
invar.adapters.measurement.instrument_driver
============================================
Tool execution layer — runs external measurement instruments against a target,
captures raw output, and feeds it directly into MeasurementAdapter.

Invar is the primary driver of the engagement.  The operator is a second
observer who can also feed output in via receive().

Supported instruments (executed locally against the target):
    nmap        — port/service/OS discovery (-sV -sC -oX)
    nikto       — web vulnerability scanner
    enum4linux  — SMB/NetBIOS enumeration

Post-exploitation instruments (run on-target, output retrieved):
    mimikatz    — credential harvesting (operator-retrieved or C2-pulled)
    powerup     — privilege escalation enumeration (operator-retrieved)
    msf         — Metasploit console output (operator-retrieved or msfrpc)

Architecture constraints:
    - All subprocess execution is isolated to this module
    - MeasurementAdapter (and below) never sees a subprocess call
    - Tool-not-found → logged, empty pearl list returned, never raises
    - Deterministic audit log: every invocation is recorded with ts, cmd, exit_code
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from invar.adapters.measurement.tool_normalizer import MeasurementAdapter
from invar.core.support_engine import Pearl


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------

@dataclass
class ToolRun:
    """Immutable record of one tool invocation."""
    ts:         float
    source:     str
    target:     str
    cmd:        List[str]
    exit_code:  int
    stdout_len: int
    stderr:     str
    pearls:     int
    cycle_id:   str
    note:       str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


# ---------------------------------------------------------------------------
# InstrumentDriver
# ---------------------------------------------------------------------------

class InstrumentDriver:
    """
    Executes external measurement tools and feeds output to a MeasurementAdapter.

    Each run_*() method:
        1. Checks tool availability (shutil.which)
        2. Invokes via subprocess with a timeout
        3. Passes raw stdout to adapter.ingest(source, raw, ...)
        4. Returns the emitted Pearl list
        5. Appends a ToolRun record to the audit log

    receive() accepts operator-provided or C2-retrieved output for tools
    that run on the target (mimikatz, PowerUp, custom scripts).
    """

    def __init__(
        self,
        adapter:       MeasurementAdapter,
        timeout:       int  = 300,
        verbose:       bool = True,
    ) -> None:
        self._adapter  = adapter
        self._timeout  = timeout
        self._verbose  = verbose
        self._log:     List[ToolRun] = []

    # ------------------------------------------------------------------
    # Network recon — execute locally against target
    # ------------------------------------------------------------------

    def run_nmap(
        self,
        target:   str,
        ports:    str           = "1-65535",
        flags:    Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """
        Run nmap against target and return Pearls.

        Default: -sV -sC -T4 --open -oX -
        Caller may override with flags= (replaces defaults entirely).
        """
        if not shutil.which("nmap"):
            return self._skip("nmap", target, cycle_id, "nmap not found in PATH")

        cmd = ["nmap"]
        if flags:
            cmd += flags.split()
        else:
            cmd += ["-sV", "-sC", "-T4", "--open", "-p", ports, "-oX", "-"]
        cmd.append(target)

        return self._run("nmap", target, cmd, cycle_id)

    def run_nikto(
        self,
        target:   str,
        port:     int           = 80,
        ssl:      bool          = False,
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """Run nikto against target:port."""
        if not shutil.which("nikto"):
            return self._skip("nikto", target, cycle_id, "nikto not found in PATH")

        cmd = ["nikto", "-h", target, "-p", str(port)]
        if ssl:
            cmd += ["-ssl"]

        return self._run("nikto", target, cmd, cycle_id)

    def run_enum4linux(
        self,
        target:   str,
        flags:    Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """Run enum4linux -a against target."""
        tool = shutil.which("enum4linux") or shutil.which("enum4linux-ng")
        if not tool:
            return self._skip("enum4linux", target, cycle_id, "enum4linux not found in PATH")

        cmd = [tool]
        if flags:
            cmd += flags.split()
        else:
            cmd += ["-a"]
        cmd.append(target)

        return self._run("enum4linux", target, cmd, cycle_id)

    # ------------------------------------------------------------------
    # Post-exploitation — operator-retrieved or C2-pulled output
    # ------------------------------------------------------------------

    def receive(
        self,
        source:   str,
        content:  str,
        target:   str           = "",
        cycle_id: Optional[str] = None,
    ) -> List[Pearl]:
        """
        Accept operator-provided tool output (mimikatz, PowerUp, msf, etc.).

        source must match a registered normalizer: "mimikatz", "powerup", "msf".
        content is the raw tool output string.
        """
        ts = time.time()
        pearls = self._adapter.ingest(source, content, cycle_id, target or "")
        cid = pearls[0].cycle_id if pearls else (cycle_id or "unknown")
        self._log.append(ToolRun(
            ts=ts, source=source, target=target or self._adapter._node_key,
            cmd=["[received]"], exit_code=0,
            stdout_len=len(content), stderr="",
            pearls=len(pearls), cycle_id=cid,
            note="operator-provided",
        ))
        if self._verbose:
            print(f"[driver] receive {source:<12}  {len(pearls)} pearls  cycle={cid}")
        return pearls

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def run_log(self) -> List[ToolRun]:
        """Return the immutable audit log of all tool invocations."""
        return list(self._log)

    def available(self, tool: str) -> bool:
        """Return True if the tool binary is on PATH."""
        return shutil.which(tool) is not None

    def available_tools(self) -> Dict[str, bool]:
        """Return availability map for all supported recon tools."""
        return {
            "nmap":       self.available("nmap"),
            "nikto":      self.available("nikto"),
            "enum4linux": self.available("enum4linux") or self.available("enum4linux-ng"),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(
        self,
        source:   str,
        target:   str,
        cmd:      List[str],
        cycle_id: Optional[str],
    ) -> List[Pearl]:
        ts = time.time()
        if self._verbose:
            print(f"[driver] run  {source:<12}  {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                errors="replace",
            )
            stdout = result.stdout
            stderr = result.stderr.strip()
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            stdout, stderr, exit_code = "", f"timeout after {self._timeout}s", -1
        except Exception as exc:
            stdout, stderr, exit_code = "", str(exc), -1

        pearls = []
        if stdout.strip():
            pearls = self._adapter.ingest(source, stdout, cycle_id, target)

        cid = pearls[0].cycle_id if pearls else (cycle_id or "unknown")
        self._log.append(ToolRun(
            ts=ts, source=source, target=target, cmd=cmd,
            exit_code=exit_code, stdout_len=len(stdout), stderr=stderr[:500],
            pearls=len(pearls), cycle_id=cid,
        ))
        if self._verbose:
            status = "ok" if exit_code == 0 else f"exit={exit_code}"
            print(f"[driver]      {source:<12}  {status}  {len(pearls)} pearls  cycle={cid}")
            if stderr and exit_code != 0:
                print(f"[driver]      stderr: {stderr[:120]}")

        return pearls

    def _skip(
        self,
        source:   str,
        target:   str,
        cycle_id: Optional[str],
        note:     str,
    ) -> List[Pearl]:
        if self._verbose:
            print(f"[driver] skip {source:<12}  {note}")
        self._log.append(ToolRun(
            ts=time.time(), source=source, target=target,
            cmd=[], exit_code=-1, stdout_len=0, stderr="",
            pearls=0, cycle_id=cycle_id or "none", note=note,
        ))
        return []
