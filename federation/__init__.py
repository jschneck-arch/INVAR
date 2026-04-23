"""INVAR federation layer — multi-core orchestration."""
from .core import (
    FederationCore,
    FederationHarness,
    FederationSnapshot,
    classify_regime,
    REGIME_ISOLATION,
    REGIME_ALIGNMENT,
    REGIME_STABLE_SPLIT,
    REGIME_DRIFT_BOUNDARY,
    REGIME_UNCERTAIN,
)
from .scenarios import (
    scenario_no_overlap,
    scenario_partial_overlap,
    scenario_strong_overlap,
    ALL_SCENARIOS,
)
