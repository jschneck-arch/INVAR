"""
skg.core.envelope
=================
The two-envelope boundary between domain adapters and the SKG substrate.

Domain code never touches the substrate directly. It produces an ObsGateEnvelope
and the substrate produces a DispatchEnvelope. These two types are the complete
interface. All identifiers are opaque strings at this boundary — the substrate
never branches on domain labels.

Chain of custody is explicit and complete:
  domain instrument → adapter → ObsGateEnvelope → SupportEngine → gate state
  gravity field → Dispatch → DispatchEnvelope → adapter → domain instrument

Decay class controls decoherence rate per Definition 3 of Work 5:
    φ(t) = φ₀ · exp(-λ · (t - t₀))
    structural:  λ = 1e-4 s⁻¹   (days-scale half-life)
    operational: λ = 1e-3 s⁻¹   (hours-scale)
    ephemeral:   λ = 1e-2 s⁻¹   (minutes-scale)
"""
from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


# ---------------------------------------------------------------------------
# Decay classes (decoherence rates)
# ---------------------------------------------------------------------------

class DecayClass(str, Enum):
    STRUCTURAL  = "structural"    # λ = 1e-4 s⁻¹ — configuration facts
    OPERATIONAL = "operational"   # λ = 1e-3 s⁻¹ — runtime state
    EPHEMERAL   = "ephemeral"     # λ = 1e-2 s⁻¹ — wire-level observations

_LAMBDA: Dict[DecayClass, float] = {
    DecayClass.STRUCTURAL:  1e-4,
    DecayClass.OPERATIONAL: 1e-3,
    DecayClass.EPHEMERAL:   1e-2,
}


def coherence(phi0: float, decay_class: DecayClass, t0: float, t: Optional[float] = None) -> float:
    """
    φ(t) = φ₀ · exp(-λ · (t - t₀))

    Applied at read time. The stored φ₀ is never modified (immutable observation
    record). Returns the present coherence of a support contribution.
    """
    if t is None:
        t = time.time()
    lam = _LAMBDA[decay_class]
    return phi0 * math.exp(-lam * (t - t0))


# ---------------------------------------------------------------------------
# ObsGateEnvelope — domain → substrate
# ---------------------------------------------------------------------------

@dataclass
class SupportContribution:
    """
    A single support contribution from one instrument observation.

    The adapter translates raw instrument output into (gate_id, φ_R, φ_B,
    decay_class). This is the universal currency of the field. The substrate
    only ever sees SupportContributions — never domain-specific output.

    φ_R and φ_B are the raw (undecayed) values. Decay is applied at read
    time by the SupportEngine using t0 and decay_class.
    """
    gate_id:     str             # opaque gate identifier (e.g. "CVE-2021-44228:host")
    phi_R:       float           # support for Realized (0.0 – 1.0)
    phi_B:       float           # support for Blocked  (0.0 – 1.0)
    decay_class: DecayClass = DecayClass.OPERATIONAL
    t0:          float = field(default_factory=time.time)

    def current_phi_R(self, t: Optional[float] = None) -> float:
        return coherence(self.phi_R, self.decay_class, self.t0, t)

    def current_phi_B(self, t: Optional[float] = None) -> float:
        return coherence(self.phi_B, self.decay_class, self.t0, t)


@dataclass
class ObsGateEnvelope:
    """
    The inbound envelope: one instrument observation cycle → N gate contributions.

    Fields:
      instrument_id  — opaque instrument identifier (e.g. "skg_nmap")
      workload_id    — opaque workload identifier (e.g. "CVE-2021-44228")
      node_key       — opaque node identifier (e.g. "192.168.1.1")
      cycle_id       — unique per observation cycle (auto-generated if not given)
      contributions  — list of support contributions for individual gates
      raw_evidence   — optional passthrough of raw instrument output for pearls

    The substrate reads contributions and nothing else. raw_evidence is
    archived for audit but never influences gate state.
    """
    instrument_id:  str
    workload_id:    str
    node_key:       str
    contributions:  list[SupportContribution] = field(default_factory=list)
    cycle_id:       str = field(default_factory=lambda: str(uuid4()))
    ts:             float = field(default_factory=time.time)
    raw_evidence:   Optional[Any] = None

    def add(
        self,
        gate_id:     str,
        phi_R:       float,
        phi_B:       float,
        decay_class: DecayClass = DecayClass.OPERATIONAL,
    ) -> "ObsGateEnvelope":
        """Fluent builder: add a support contribution and return self."""
        self.contributions.append(
            SupportContribution(
                gate_id=gate_id,
                phi_R=phi_R,
                phi_B=phi_B,
                decay_class=decay_class,
                t0=self.ts,
            )
        )
        return self


# ---------------------------------------------------------------------------
# DispatchEnvelope — substrate → domain
# ---------------------------------------------------------------------------

@dataclass
class InstrumentTarget:
    """One (instrument, node, priority) tuple in a dispatch envelope."""
    instrument_id: str          # which instrument to dispatch
    node_key:      str          # which node to act on
    workload_id:   str          # which workload context
    priority:      float        # Φ value from gravity field (entropy-reduction potential)
    reason:        str = ""     # human-readable gravity rationale (for operators)
    args:          Dict[str, Any] = field(default_factory=dict)  # instrument-specific args


@dataclass
class DispatchEnvelope:
    """
    The outbound envelope: substrate → domain adapter.

    Gravity produces a ranked list of InstrumentTargets. The domain adapter
    translates each into a concrete instrument invocation.

    The substrate never decides how to invoke an instrument — it only decides
    which instruments to invoke, on which nodes, in which order. That decision
    is the gravity field. The how is the adapter's domain knowledge.
    """
    targets:  list[InstrumentTarget] = field(default_factory=list)
    cycle_id: str = field(default_factory=lambda: str(uuid4()))
    ts:       float = field(default_factory=time.time)
    field_energy: float = 0.0  # L(F) at time of dispatch

    def ranked(self) -> list[InstrumentTarget]:
        """Return targets sorted by priority descending."""
        return sorted(self.targets, key=lambda t: t.priority, reverse=True)
