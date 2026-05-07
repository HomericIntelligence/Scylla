"""Result models for E2E runs, sub-tests, tiers, and experiments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scylla.core.results import RunResultBase
from scylla.e2e.models_internals.configs import ExperimentConfig
from scylla.e2e.models_internals.state_enums import TierID
from scylla.e2e.models_internals.token_stats import TokenStats
from scylla.e2e.rate_limit import RateLimitInfo


class JudgeResultSummary(BaseModel):
    """Summary of a single judge's evaluation.

    Used when multiple judges evaluate the same run.

    Attributes:
        model: Model ID of the judge
        score: Judge's score (0.0-1.0)
        passed: Whether the run passed
        grade: Letter grade (S-F)
        reasoning: Judge's reasoning text
        judge_number: Judge number for directory linking (1-indexed)
        is_valid: Whether the evaluation was successfully completed
        criteria_scores: Individual criterion evaluations with score and explanation

    """

    model: str
    score: float | None = None
    passed: bool | None = None
    grade: str | None = None
    reasoning: str | None = None
    judge_number: int = 1
    is_valid: bool = True
    criteria_scores: dict[str, dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


class E2ERunResult(RunResultBase):
    """Result from a single run of a sub-test.

    Captures all execution details, metrics, and judge evaluation
    for one run of an agent against the canonical task.

    This is the E2E testing result with detailed paths and judge fields.
    Inherits common fields (run_number, cost_usd, duration_seconds) from RunResultBase.

    For other RunResult types in the hierarchy, see:
    - RunResultBase (core/results.py) - Base Pydantic model
    - ExecutorRunResult (executor/runner.py) - Execution tracking with status
    - ReportingRunResult (reporting/result.py) - Persistence with nested info
    - MetricsRunResult (metrics/aggregator.py) - Statistical aggregation

    Attributes:
        exit_code: Process exit code
        token_stats: Detailed token usage statistics
        agent_duration_seconds: Agent execution time
        judge_duration_seconds: Judge evaluation time
        judge_score: Consensus score from all judges (0.0 - 1.0)
        judge_passed: Consensus passed from majority vote
        judge_grade: Letter grade (S-F) from consensus score
        judge_reasoning: Primary judge's reasoning text
        judges: Individual judge results (for multi-judge runs)
        workspace_path: Path to preserved workspace
        logs_path: Path to execution logs
        command_log_path: Path to command log JSON
        criteria_scores: Per-criterion scores from judge

    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # E2E-specific fields (common fields inherited from RunResultBase)
    exit_code: int
    token_stats: TokenStats
    agent_duration_seconds: float
    judge_duration_seconds: float
    judge_score: float
    judge_passed: bool
    judge_grade: str
    judge_reasoning: str
    workspace_path: Path
    logs_path: Path
    judges: list[JudgeResultSummary] = Field(default_factory=list)
    command_log_path: Path | None = None
    criteria_scores: dict[str, dict[str, Any]] = Field(default_factory=dict)
    baseline_pipeline_summary: dict[str, Any] | None = None

    @field_validator("criteria_scores", mode="before")
    @classmethod
    def coerce_none_criteria_scores(cls, v: Any) -> dict[str, Any]:
        """Coerce None to empty dict — judges may return None for criteria_scores."""
        return v if v is not None else {}

    # Legacy properties for backwards compatibility
    @property
    def tokens_input(self) -> int:
        """Total input tokens (legacy compatibility)."""
        return self.token_stats.total_input

    @property
    def tokens_output(self) -> int:
        """Output tokens (legacy compatibility)."""
        return self.token_stats.output_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = self.model_dump(mode="json")
        # Inject legacy properties for backwards compatibility (not stored as model fields)
        d["tokens_input"] = self.tokens_input
        d["tokens_output"] = self.tokens_output
        return d


class SubTestResult(BaseModel):
    """Aggregated results for a sub-test across all runs.

    Contains statistics computed from all runs of a single sub-test.

    Attributes:
        subtest_id: The sub-test identifier
        tier_id: The tier identifier
        runs: List of individual run results
        pass_rate: Fraction of runs that passed
        mean_score: Mean judge score across runs
        median_score: Median judge score
        std_dev_score: Standard deviation of scores
        mean_cost: Mean cost per run
        total_cost: Total cost across all runs
        token_stats: Aggregated token statistics across all runs
        consistency: Score consistency (1 - coefficient of variation)
        grade_distribution: Distribution of letter grades across runs
        modal_grade: Most common grade across runs
        min_grade: Worst grade across runs
        max_grade: Best grade across runs
        selected_as_best: Whether this sub-test was selected as best
        selection_reason: Reason for selection (if selected)

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    subtest_id: str
    tier_id: TierID
    runs: list[E2ERunResult]
    pass_rate: float = 0.0
    mean_score: float = 0.0
    median_score: float = 0.0
    std_dev_score: float = 0.0
    mean_cost: float = 0.0
    total_cost: float = 0.0
    token_stats: TokenStats = Field(default_factory=TokenStats)
    consistency: float = 0.0
    # Grade aggregation across runs
    grade_distribution: dict[str, int] | None = None
    modal_grade: str | None = None
    min_grade: str | None = None
    max_grade: str | None = None
    selected_as_best: bool = False
    selection_reason: str = ""
    # Rate limit info for retry logic (None if not rate-limited)
    rate_limit_info: RateLimitInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


class TierBaseline(BaseModel):
    """Reference to a tier's best configuration for inheritance.

    Used to track which sub-test configuration should be inherited
    by the next tier.

    Attributes:
        tier_id: The tier this baseline is from
        subtest_id: The winning sub-test ID
        claude_md_path: Path to the CLAUDE.md to inherit (legacy mode)
        claude_dir_path: Path to the .claude/ directory to inherit (legacy mode)
        resources: Resource specification for symlink recreation.
            When specified, symlinks are recreated from this spec rather
            than copying files from paths.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier_id: TierID
    subtest_id: str
    claude_md_path: Path | None
    claude_dir_path: Path | None
    resources: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


class TierResult(BaseModel):
    """Complete results for a tier including all sub-tests.

    Attributes:
        tier_id: The tier identifier
        subtest_results: Mapping of sub-test ID to results
        best_subtest: ID of the winning sub-test
        best_subtest_score: Score of the winning sub-test
        inherited_from: Baseline this tier inherited from
        tiebreaker_needed: Whether a tie-breaker was needed
        total_cost: Total cost for this tier
        total_duration: Total duration for this tier
        token_stats: Aggregated token statistics across all subtests

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier_id: TierID
    subtest_results: dict[str, SubTestResult]
    best_subtest: str | None = None
    best_subtest_score: float = 0.0
    inherited_from: TierBaseline | None = None
    tiebreaker_needed: bool = False
    total_cost: float = 0.0
    total_duration: float = 0.0
    token_stats: TokenStats = Field(default_factory=TokenStats)

    @property
    def cost_of_pass(self) -> float:
        """Calculate cost-of-pass for this tier's best subtest.

        Returns:
            Cost per successful pass (mean_cost / pass_rate), or infinity if no passes.

        """
        if not self.best_subtest or self.best_subtest not in self.subtest_results:
            return float("inf")

        best = self.subtest_results[self.best_subtest]
        if best.pass_rate <= 0:
            return float("inf")

        return best.mean_cost / best.pass_rate

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = self.model_dump(mode="json")
        # Inject computed property (not stored as a model field)
        d["cost_of_pass"] = self.cost_of_pass
        return d


class ExperimentResult(BaseModel):
    """Complete experiment results.

    Contains all results and analysis from running the full experiment.

    Attributes:
        config: The experiment configuration
        tier_results: Mapping of tier ID to results
        best_overall_tier: Tier with best cost-of-pass
        best_overall_subtest: Sub-test with best performance
        frontier_cop: Best cost-of-pass across all tiers
        frontier_cop_tier: Tier achieving frontier cost-of-pass
        total_cost: Total experiment cost
        total_duration_seconds: Total experiment duration
        token_stats: Aggregated token statistics across all tiers
        started_at: Experiment start timestamp
        completed_at: Experiment completion timestamp

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: ExperimentConfig
    tier_results: dict[TierID, TierResult]
    best_overall_tier: TierID | None = None
    best_overall_subtest: str | None = None
    frontier_cop: float = float("inf")
    frontier_cop_tier: TierID | None = None
    total_cost: float = 0.0
    total_duration_seconds: float = 0.0
    token_stats: TokenStats = Field(default_factory=TokenStats)
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = self.model_dump(mode="json")
        # config.to_dict() omits ephemeral fields; replace the full model_dump of config with it
        d["config"] = self.config.to_dict()
        return d

    def save(self, path: Path) -> None:
        """Save results to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


# Resolve forward references after all models are defined. The
# RateLimitInfo import is at the top of this module since
# scylla.e2e.rate_limit only imports from stdlib + scylla.e2e.paths
# (a leaf module), so no cycle exists.
SubTestResult.model_rebuild()
