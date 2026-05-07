"""TierContext dataclass — mutable namespace for inter-action state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scylla.e2e.judge_selection import JudgeSelection
    from scylla.e2e.models import SubTestResult, TierConfig, TierResult


@dataclass
class TierContext:
    """Mutable namespace for inter-action state within a single tier execution.

    Passed via closure to each action in _build_tier_actions(). Fields are
    populated progressively as the TierStateMachine advances through states.

    Attributes:
        start_time: When the tier started (set in action_pending)
        tier_config: Loaded tier configuration (set in action_pending)
        tier_dir: Tier results directory (set in action_pending)
        subtest_results: Results from parallel subtest execution (set in action_config_loaded)
        selection: Best subtest selection (set in action_subtests_running)
        tier_result: Final aggregated TierResult (set in action_subtests_complete)

    """

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier_config: TierConfig | None = None
    tier_dir: Path | None = None
    subtest_results: dict[str, SubTestResult] = field(default_factory=dict)
    selection: JudgeSelection | None = None
    tier_result: TierResult | None = None
