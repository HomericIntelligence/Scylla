"""Data models for E2E testing framework.

This module defines the core data structures used throughout the E2E
testing pipeline, including configurations, results, and aggregations.

This module is a thin facade — its implementation lives in
:mod:`scylla.e2e.models_internals`. The public API (every name listed
in ``__all__``) is preserved for backward compatibility.
"""

from __future__ import annotations

from scylla.core.token_stats import (
    TokenStats as TokenStats,
)
from scylla.e2e.models_internals.configs import (
    ExperimentConfig as ExperimentConfig,
)
from scylla.e2e.models_internals.configs import (
    SubTestConfig as SubTestConfig,
)
from scylla.e2e.models_internals.configs import (
    TestFixture as TestFixture,
)
from scylla.e2e.models_internals.configs import (
    TierConfig as TierConfig,
)
from scylla.e2e.models_internals.resources import (
    ResourceManifest as ResourceManifest,
)
from scylla.e2e.models_internals.results import (
    E2ERunResult as E2ERunResult,
)
from scylla.e2e.models_internals.results import (
    ExperimentResult as ExperimentResult,
)
from scylla.e2e.models_internals.results import (
    JudgeResultSummary as JudgeResultSummary,
)
from scylla.e2e.models_internals.results import (
    SubTestResult as SubTestResult,
)
from scylla.e2e.models_internals.results import (
    TierBaseline as TierBaseline,
)
from scylla.e2e.models_internals.results import (
    TierResult as TierResult,
)
from scylla.e2e.models_internals.state_enums import (
    GRADE_ORDER as GRADE_ORDER,
)
from scylla.e2e.models_internals.state_enums import (
    TIER_DEPENDENCIES as TIER_DEPENDENCIES,
)
from scylla.e2e.models_internals.state_enums import (
    ExperimentState as ExperimentState,
)
from scylla.e2e.models_internals.state_enums import (
    RunState as RunState,
)
from scylla.e2e.models_internals.state_enums import (
    SubtestState as SubtestState,
)
from scylla.e2e.models_internals.state_enums import (
    TierID as TierID,
)
from scylla.e2e.models_internals.state_enums import (
    TierState as TierState,
)

__all__ = [
    "GRADE_ORDER",
    "TIER_DEPENDENCIES",
    "E2ERunResult",
    "ExperimentConfig",
    "ExperimentResult",
    "ExperimentState",
    "JudgeResultSummary",
    "ResourceManifest",
    "RunState",
    "SubTestConfig",
    "SubTestResult",
    "SubtestState",
    "TestFixture",
    "TierBaseline",
    "TierConfig",
    "TierID",
    "TierResult",
    "TierState",
    "TokenStats",
]
