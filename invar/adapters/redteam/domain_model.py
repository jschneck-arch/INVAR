"""
invar.adapters.redteam.domain_model
=====================================
Red team domain concretization layer — read-only, operator-mediated.

RedTeamDomainModel maps generic Invar artifacts and cycles into red team
operational primitives for lab use.  This is an interpretation layer only:
domain labels are never written into Pearl or any core Invar truth surface.

All outputs are derived on demand from existing adapter-layer objects.
Nothing is executed, triggered, or stored as new canonical state.

ArtifactType constants (adapter-local only):
    UNKNOWN, EXECUTION_ARTIFACT, PERSISTENCE_ARTIFACT, CREDENTIAL_ARTIFACT,
    DISCOVERY_ARTIFACT, LATERAL_ARTIFACT, COLLECTION_ARTIFACT, C2_ARTIFACT

OperationPrimitive constants (adapter-local only):
    UNCLASSIFIED, EXECUTION, PERSISTENCE, CREDENTIAL_ACCESS, DISCOVERY,
    LATERAL_MOVEMENT, COLLECTION, COMMAND_AND_CONTROL, MULTI_STAGE

Classification rules (deterministic, first-match, rule-based):
    artifact_type  — first-match substring scan of gate_id (case-insensitive).
                     Rule order handles known conflicts (e.g. "psexec" → LATERAL
                     before EXECUTION can match "exec"; "autorun" → PERSISTENCE
                     before EXECUTION can match "run").
    cycle_primitive — derived from the set of distinct non-UNKNOWN artifact types
                      in the cycle's gate inventory.

API:
    model.artifact_type(gate_key)       → ArtifactType str
    model.cycle_primitive(cycle_id)     → OperationPrimitive str
    model.cycle_artifacts(cycle_id)     → {cycle_id, artifacts: [{gate_key, artifact_type}]}
    model.operational_summary(cycle_id) → full dict
    model.lab_queue()                   → prioritized operator-facing items

Constraints:
    - No Layer 0 modification
    - No mutation of any input layer
    - Domain labels are adapter-local: never written to Pearl or Invar core
    - Deterministic: same inputs → same outputs
    - Discardable: zero side-effects
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from invar.adapters.redteam.acknowledgment import AcknowledgmentStore
from invar.adapters.redteam.action_proposal import ActionProposalEngine
from invar.adapters.redteam.feedback import FeedbackEngine
from invar.adapters.redteam.observer import RedTeamObserver
from invar.adapters.redteam.workflow import WorkflowView

GateKey = Tuple[str, str, str]  # (workload_id, node_key, gate_id)


# ---------------------------------------------------------------------------
# Domain type namespaces
# ---------------------------------------------------------------------------

class ArtifactType:
    """Adapter-local artifact classification constants. Never written to Pearl."""
    UNKNOWN              = "UNKNOWN"
    EXECUTION_ARTIFACT   = "EXECUTION_ARTIFACT"
    PERSISTENCE_ARTIFACT = "PERSISTENCE_ARTIFACT"
    CREDENTIAL_ARTIFACT  = "CREDENTIAL_ARTIFACT"
    DISCOVERY_ARTIFACT   = "DISCOVERY_ARTIFACT"
    LATERAL_ARTIFACT     = "LATERAL_ARTIFACT"
    COLLECTION_ARTIFACT  = "COLLECTION_ARTIFACT"
    C2_ARTIFACT          = "C2_ARTIFACT"


class OperationPrimitive:
    """Adapter-local cycle classification constants. Never written to Pearl."""
    UNCLASSIFIED        = "UNCLASSIFIED"
    EXECUTION           = "EXECUTION"
    PERSISTENCE         = "PERSISTENCE"
    CREDENTIAL_ACCESS   = "CREDENTIAL_ACCESS"
    DISCOVERY           = "DISCOVERY"
    LATERAL_MOVEMENT    = "LATERAL_MOVEMENT"
    COLLECTION          = "COLLECTION"
    COMMAND_AND_CONTROL = "COMMAND_AND_CONTROL"
    MULTI_STAGE         = "MULTI_STAGE"


# ---------------------------------------------------------------------------
# Classification rules
# ---------------------------------------------------------------------------

# Ordered: more-specific / longer patterns before those that are substrings of
# them.  LATERAL before EXECUTION avoids "psexec"→EXECUTION false match.
# PERSISTENCE before EXECUTION avoids "autorun"→EXECUTION false match.
# DISCOVERY before EXECUTION: "discover" must precede short patterns like "exec"
# that could match substrings of discovery gate_ids.
# "ps" removed from EXECUTION — too short, causes false matches on "groups",
# "https", etc.  PowerShell gate_ids use "exec_" prefix, which "exec" catches.
_ARTIFACT_RULES: List[Tuple[Tuple[str, ...], str]] = [
    (("psexec", "wmiexec", "smb", "winrm", "pivot", "lateral"), ArtifactType.LATERAL_ARTIFACT),
    (("persist", "autorun", "svc", "schtask"),                   ArtifactType.PERSISTENCE_ARTIFACT),
    (("enum", "scan", "recon", "discover"),                      ArtifactType.DISCOVERY_ARTIFACT),
    (("exec", "run", "cmd", "powershell"),                       ArtifactType.EXECUTION_ARTIFACT),
    (("cred", "hash", "ticket", "token"),                        ArtifactType.CREDENTIAL_ARTIFACT),
    (("loot", "collect", "exfil"),                               ArtifactType.COLLECTION_ARTIFACT),
    (("beacon", "c2", "callback", "channel"),                    ArtifactType.C2_ARTIFACT),
]

_ARTIFACT_TO_PRIMITIVE: Dict[str, str] = {
    ArtifactType.EXECUTION_ARTIFACT:   OperationPrimitive.EXECUTION,
    ArtifactType.PERSISTENCE_ARTIFACT: OperationPrimitive.PERSISTENCE,
    ArtifactType.CREDENTIAL_ARTIFACT:  OperationPrimitive.CREDENTIAL_ACCESS,
    ArtifactType.DISCOVERY_ARTIFACT:   OperationPrimitive.DISCOVERY,
    ArtifactType.LATERAL_ARTIFACT:     OperationPrimitive.LATERAL_MOVEMENT,
    ArtifactType.COLLECTION_ARTIFACT:  OperationPrimitive.COLLECTION,
    ArtifactType.C2_ARTIFACT:          OperationPrimitive.COMMAND_AND_CONTROL,
}

_ALL_WORKFLOW_STATES = ("open", "reviewed-valid", "reviewed-irrelevant", "needs-investigation")


def classify_gate_id(gate_id: str) -> str:
    """Public: first-match substring classification of gate_id (case-insensitive)."""
    return _classify_gate_id(gate_id)


def _classify_gate_id(gate_id: str) -> str:
    """First-match substring classification of gate_id (case-insensitive)."""
    lower = gate_id.lower()
    for patterns, artifact_type in _ARTIFACT_RULES:
        for pattern in patterns:
            if pattern in lower:
                return artifact_type
    return ArtifactType.UNKNOWN


def _derive_primitive(artifact_types: List[str]) -> str:
    """Derive OperationPrimitive from the artifact types present in a cycle."""
    non_unknown = {t for t in artifact_types if t != ArtifactType.UNKNOWN}
    if not non_unknown:
        return OperationPrimitive.UNCLASSIFIED
    if len(non_unknown) == 1:
        return _ARTIFACT_TO_PRIMITIVE.get(
            next(iter(non_unknown)), OperationPrimitive.UNCLASSIFIED
        )
    return OperationPrimitive.MULTI_STAGE


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

class RedTeamDomainModel:
    """
    Read-only red team domain concretization over existing adapter-layer objects.

    Derives artifact classifications and operational primitives from the L1/L2
    stack.  Nothing is executed or stored as new canonical state.  Domain labels
    are adapter-local — never written to Pearl or Invar core.
    """

    def __init__(
        self,
        observer: RedTeamObserver,
        engine: FeedbackEngine,
        store: AcknowledgmentStore,
        workflow: WorkflowView,
        action_engine: ActionProposalEngine,
    ) -> None:
        self._observer = observer
        self._engine = engine
        self._store = store
        self._workflow = workflow
        self._action_engine = action_engine

    # ------------------------------------------------------------------
    # Artifact typing
    # ------------------------------------------------------------------

    def artifact_type(self, gate_key: GateKey) -> str:
        """
        Return the ArtifactType for a gate key.

        Classification uses only the gate_id component via first-match
        substring rules (case-insensitive).  The workload_id and node_key
        components are not used for classification.
        Returns ArtifactType.UNKNOWN if no rule matches.
        """
        _, _, gate_id = gate_key
        return _classify_gate_id(gate_id)

    # ------------------------------------------------------------------
    # Cycle classification
    # ------------------------------------------------------------------

    def cycle_primitive(self, cycle_id: str) -> str:
        """
        Return the OperationPrimitive for a cycle.

        Derived from the distinct non-UNKNOWN artifact types in the cycle's
        gate inventory.  Returns UNCLASSIFIED if no artifacts or all are
        UNKNOWN.  Returns MULTI_STAGE if two or more distinct non-UNKNOWN
        types are present.
        """
        pearls = self._observer._windows.get(cycle_id) or []
        types = [_classify_gate_id(p.gate_id) for p in pearls]
        return _derive_primitive(types)

    # ------------------------------------------------------------------
    # Cycle artifact inventory
    # ------------------------------------------------------------------

    def cycle_artifacts(self, cycle_id: str) -> Dict:
        """
        Return the annotated gate inventory for a cycle.

        Returns:
            {
                "cycle_id": str,
                "artifacts": [{"gate_key": GateKey, "artifact_type": str}, ...]
            }
        Returns empty artifacts list for unknown cycle_id.
        """
        pearls = self._observer._windows.get(cycle_id) or []
        return {
            "cycle_id": cycle_id,
            "artifacts": [
                {
                    "gate_key":      (p.workload_id, p.node_key, p.gate_id),
                    "artifact_type": _classify_gate_id(p.gate_id),
                }
                for p in pearls
            ],
        }

    # ------------------------------------------------------------------
    # Operational summary
    # ------------------------------------------------------------------

    def operational_summary(self, cycle_id: str) -> Dict:
        """
        Return a structured operational summary for a cycle.

        Keys:
            cycle_id              — requested cycle identifier
            primitive             — OperationPrimitive str
            activity              — normalized causal field value ∈ [0,1]
            artifact_count        — total pearl count for this cycle
            artifact_types        — sorted list of unique ArtifactType strs
            incoming_links        — count of proto-causal links into this cycle
            outgoing_links        — count of proto-causal links out of this cycle
            workflow_state_counts — {state: int} for all four workflow states,
                                    counting suggestions referencing this cycle
        Returns zeroed summary for an unknown cycle_id.
        """
        pearls = self._observer._windows.get(cycle_id) or []
        types = [_classify_gate_id(p.gate_id) for p in pearls]
        obs = self._observer.summary(cycle_id)

        item_state: Dict[str, str] = {
            item["suggestion_id"]: item["state"]
            for item in self._workflow.items()
        }
        state_counts: Dict[str, int] = {s: 0 for s in _ALL_WORKFLOW_STATES}
        for s in self._engine.by_cycle(cycle_id):
            state = item_state.get(s.suggestion_id, "open")
            state_counts[state] += 1

        return {
            "cycle_id":              cycle_id,
            "primitive":             _derive_primitive(types),
            "activity":              obs["activity"],
            "artifact_count":        len(pearls),
            "artifact_types":        sorted(set(types)),
            "incoming_links":        obs["incoming_links"],
            "outgoing_links":        obs["outgoing_links"],
            "workflow_state_counts": state_counts,
        }

    # ------------------------------------------------------------------
    # Lab queue
    # ------------------------------------------------------------------

    def lab_queue(self) -> List[Dict]:
        """
        Return operator-facing prioritized items enriched with domain context.

        Ordering follows WorkflowView.queue() (needs-investigation first,
        then open, then reviewed; within each tier: confidence desc, then
        suggestion_id asc).

        Each item contains:
            suggestion_id  — from FeedbackEngine
            type           — suggestion type
            cycle_id       — primary cycle (or None for cross-cycle suggestions)
            confidence     — float ∈ [0,1]
            state          — workflow state str
            action_type    — from ActionProposalEngine (None if not eligible)
            proposal_id    — from ActionProposalEngine (None if not eligible)
            primitive      — OperationPrimitive for cycle_id (None if no cycle)
        """
        result = []
        for item in self._workflow.queue():
            cycle_id = item["cycle_id"]
            proposal = self._action_engine.for_suggestion(item["suggestion_id"])
            result.append({
                "suggestion_id": item["suggestion_id"],
                "type":          item["type"],
                "cycle_id":      cycle_id,
                "confidence":    item["confidence"],
                "state":         item["state"],
                "action_type":   proposal.action_type if proposal else None,
                "proposal_id":   proposal.proposal_id if proposal else None,
                "primitive":     self.cycle_primitive(cycle_id) if cycle_id else None,
            })
        return result
