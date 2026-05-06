"""Data models for E2E testing framework.

This module defines the core data structures used throughout the E2E
testing pipeline, including configurations, results, and aggregations.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scylla.config.constants import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_JUDGE_MODEL,
    normalize_model_id,
)
from scylla.core.results import RunResultBase
from scylla.e2e.rate_limit import RateLimitInfo

# Grade ordering for min/max calculations (F=worst, S=best)
GRADE_ORDER: list[str] = ["F", "D", "C", "B", "A", "S"]


class TokenStats(BaseModel):
    """Detailed token usage statistics.

    Tracks all token types including cache operations for
    accurate cost analysis and efficiency metrics.

    Attributes:
        input_tokens: Fresh input tokens (not from cache)
        output_tokens: Generated output tokens
        cache_creation_tokens: Tokens written to cache
        cache_read_tokens: Tokens read from cache (cheaper)

    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_input(self) -> int:
        """Total input tokens including cache reads."""
        return self.input_tokens + self.cache_read_tokens

    @property
    def total_tokens(self) -> int:
        """Total all tokens processed."""
        return self.total_input + self.output_tokens + self.cache_creation_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenStats:
        """Create from dictionary."""
        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            cache_creation_tokens=data.get("cache_creation_tokens", 0),
            cache_read_tokens=data.get("cache_read_tokens", 0),
        )

    def __add__(self, other: TokenStats) -> TokenStats:
        """Enable summing TokenStats."""
        return TokenStats(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )


class RunState(str, Enum):
    """Fine-grained states for a single run within a subtest.

    Each state represents a discrete, resumable checkpoint in the run lifecycle.
    The state machine advances through these states sequentially, saving the
    checkpoint after each transition to enable resume from any point.

    Sequential states (16):
      PENDING -> DIR_STRUCTURE_CREATED -> WORKTREE_CREATED -> SYMLINKS_APPLIED
      -> CONFIG_COMMITTED -> BASELINE_CAPTURED -> PROMPT_WRITTEN -> REPLAY_GENERATED
      -> AGENT_COMPLETE -> AGENT_CHANGES_COMMITTED
      -> DIFF_CAPTURED -> PROMOTED_TO_COMPLETED -> JUDGE_PIPELINE_RUN -> JUDGE_PROMPT_BUILT
      -> JUDGE_COMPLETE -> RUN_FINALIZED -> REPORT_WRITTEN -> CHECKPOINTED -> WORKTREE_CLEANED
    Terminal (2): FAILED | RATE_LIMITED
    """

    PENDING = "pending"
    DIR_STRUCTURE_CREATED = "dir_structure_created"  # run_dir, agent/, judge/ created
    WORKTREE_CREATED = "worktree_created"  # git worktree created
    SYMLINKS_APPLIED = "symlinks_applied"  # tier resources symlinked to workspace
    CONFIG_COMMITTED = "config_committed"  # CLAUDE.md, settings.json, git commit
    BASELINE_CAPTURED = "baseline_captured"  # build pipeline baseline (first run only)
    PROMPT_WRITTEN = "prompt_written"  # task_prompt.md written, thinking keyword injected
    REPLAY_GENERATED = "replay_generated"  # adapter command built, replay.sh generated
    AGENT_COMPLETE = "agent_complete"  # agent executed, outputs saved
    AGENT_CHANGES_COMMITTED = "agent_changes_committed"  # agent changes committed to branch
    DIFF_CAPTURED = "diff_captured"  # git diff captured, workspace state saved
    PROMOTED_TO_COMPLETED = "promoted_to_completed"  # run dir moved to completed/
    JUDGE_PIPELINE_RUN = "judge_pipeline_run"  # build pipeline run on agent-modified workspace
    JUDGE_PROMPT_BUILT = "judge_prompt_built"  # full judge prompt assembled
    JUDGE_COMPLETE = "judge_complete"  # judge executed, consensus computed, results saved
    RUN_FINALIZED = "run_finalized"  # E2ERunResult built, run_result.json saved
    REPORT_WRITTEN = "report_written"  # report.md and report.json generated
    CHECKPOINTED = "checkpointed"  # checkpoint saved with this run's state
    WORKTREE_CLEANED = "worktree_cleaned"  # git worktree removed
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class SubtestState(str, Enum):
    """States for a single subtest's lifecycle."""

    PENDING = "pending"
    RUNS_IN_PROGRESS = "runs_in_progress"
    RUNS_COMPLETE = "runs_complete"
    AGGREGATED = "aggregated"
    FAILED = "failed"


class TierState(str, Enum):
    """States for a single tier's lifecycle."""

    PENDING = "pending"
    CONFIG_LOADED = "config_loaded"
    SUBTESTS_RUNNING = "subtests_running"
    SUBTESTS_COMPLETE = "subtests_complete"
    BEST_SELECTED = "best_selected"
    REPORTS_GENERATED = "reports_generated"
    COMPLETE = "complete"
    FAILED = "failed"


class ExperimentState(str, Enum):
    """States for the overall experiment lifecycle."""

    INITIALIZING = "initializing"
    DIR_CREATED = "dir_created"  # Experiment directory tree created
    REPO_CLONED = "repo_cloned"
    TIERS_RUNNING = "tiers_running"
    TIERS_COMPLETE = "tiers_complete"
    REPORTS_GENERATED = "reports_generated"
    COMPLETE = "complete"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class TierID(Enum):
    """Tier identifiers for the evaluation framework.

    Tiers represent increasing levels of agent capability:
    - T0: Prompts - System prompt ablation (empty → full CLAUDE.md)
    - T1: Skills - Domain expertise via installed skills
    - T2: Tooling - External tools and MCP servers
    - T3: Delegation - Flat multi-agent with specialist agents
    - T4: Hierarchy - Nested orchestration with orchestrators
    - T5: Hybrid - Best combinations and permutations
    - T6: Super - Everything enabled at maximum capability
    """

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"

    @classmethod
    def from_string(cls, value: str) -> TierID:
        """Create TierID from string value."""
        return cls(value.upper())

    def __lt__(self, other: TierID) -> bool:
        """Enable sorting of tiers."""
        order = list(TierID)
        return order.index(self) < order.index(other)


# Tier dependency map for parallel execution
# T0-T4 are independent (can run in parallel)
# T5 depends on T0-T4 (inherits from best result)
# T6 depends on T5 (inherits from T5)
TIER_DEPENDENCIES: dict[TierID, list[TierID]] = {
    TierID.T0: [],
    TierID.T1: [],
    TierID.T2: [],
    TierID.T3: [],
    TierID.T4: [],
    TierID.T5: [TierID.T0, TierID.T1, TierID.T2, TierID.T3, TierID.T4],
    TierID.T6: [TierID.T5],
}


class SubTestConfig(BaseModel):
    """Configuration for a single sub-test within a tier.

    Each sub-test represents a variation of the tier configuration,
    such as different levels of CLAUDE.md complexity.

    Attributes:
        id: Numeric identifier (e.g., "01", "02")
        name: Human-readable name
        description: Description of what this sub-test tests
        claude_md_path: Path to CLAUDE.md for this sub-test (legacy mode)
        claude_dir_path: Path to .claude/ directory for this sub-test (legacy mode)
        extends_previous: Whether to inherit from best previous tier
        resources: Resource specification for symlink-based fixtures.
            When specified, symlinks are created to shared/ at runtime
            instead of copying files. Format:
            {
                "skills": {"categories": ["agent", "github"], "names": ["skill-name"]},
                "agents": {"levels": [0, 1, 3], "names": ["chief-architect.md"]},
                "claude_md": {"blocks": ["B02", "B05"]}
            }
        inherit_best_from: List of tier IDs to inherit best configurations from.
            Used in T5 subtests to dynamically inherit from winning configurations
            in completed lower tiers (T0-T4).

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: str
    description: str
    claude_md_path: Path | None = None
    claude_dir_path: Path | None = None
    extends_previous: bool = True
    resources: dict[str, Any] = Field(default_factory=dict)
    inherit_best_from: list[TierID] = Field(default_factory=list)
    agent_teams: bool = False  # Enable experimental agent teams feature
    system_prompt_mode: str = "custom"  # "none", "default", "custom"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


class TierConfig(BaseModel):
    """Configuration for a tier including all sub-tests.

    Attributes:
        tier_id: The tier identifier
        subtests: List of sub-test configurations
        tools_enabled: Whether tools are enabled for this tier
        delegation_enabled: Whether delegation is enabled for this tier

    Note:
        system_prompt_mode is determined per-subtest, not per-tier.
        See SubTestConfig.system_prompt_mode for the actual configuration.

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier_id: TierID
    subtests: list[SubTestConfig]
    tools_enabled: bool | None = None
    delegation_enabled: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


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


class ResourceManifest(BaseModel):
    """Records which resources were used for a subtest run.

    Enables reproducibility without copying files. Instead of duplicating
    CLAUDE.md and .claude/ to results directories, this manifest records
    exactly what was used so runs can be reproduced by re-reading the
    fixture config.

    Attributes:
        tier_id: The tier identifier
        subtest_id: The subtest identifier
        fixture_config_path: Path to original config.yaml in fixtures/
        resources: The resolved resource specification
        composed_at: ISO timestamp when config was composed
        claude_md_hash: SHA256 of composed CLAUDE.md for verification
        inherited_from: Previous tier's resources (for inheritance chain)

    """

    tier_id: str
    subtest_id: str
    fixture_config_path: str
    resources: dict[str, Any]
    composed_at: str
    claude_md_hash: str | None = None
    inherited_from: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> ResourceManifest:
        """Load manifest from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            tier_id=data["tier_id"],
            subtest_id=data["subtest_id"],
            fixture_config_path=data["fixture_config_path"],
            resources=data["resources"],
            composed_at=data["composed_at"],
            claude_md_hash=data.get("claude_md_hash"),
            inherited_from=data.get("inherited_from"),
        )


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


class TestFixture(BaseModel):
    """Complete test fixture definition.

    This is the output schema that a benchmark generator must produce.
    Represents all materials needed to run a test across all tiers.

    Attributes:
        id: Unique test identifier (e.g., "test-001")
        name: Human-readable test name
        description: Test description
        language: Programming language ("python" or "mojo")
        source_repo: Git repository URL
        source_hash: Git commit hash
        task_prompt: Content of prompt.md
        criteria: Content of expected/criteria.md
        rubric: Parsed expected/rubric.yaml
        tiers: List of tier IDs to run (e.g., ["T0", "T1", "T2"])
        timeout_seconds: Timeout per run in seconds

    """

    id: str
    name: str
    description: str
    language: str
    source_repo: str
    source_hash: str
    task_prompt: str
    criteria: str
    rubric: dict[str, Any]
    tiers: list[str] = Field(default_factory=list)
    timeout_seconds: int = 3600

    @classmethod
    def from_directory(cls, path: Path) -> TestFixture:
        """Load test fixture from directory structure.

        Expected directory structure:
            path/
                test.yaml          # Main config
                prompt.md          # Task prompt
                expected/
                    criteria.md    # Grading criteria
                    rubric.yaml    # Rubric specification

        Args:
            path: Path to test fixture directory

        Returns:
            TestFixture instance

        Raises:
            FileNotFoundError: If required files are missing
            ValueError: If required fields are missing from config

        """
        test_yaml = path / "test.yaml"
        if not test_yaml.exists():
            raise FileNotFoundError(f"test.yaml not found in {path}")

        with open(test_yaml) as f:
            config = yaml.safe_load(f) or {}

        # Load task prompt
        prompt_file = path / (config.get("task", {}).get("prompt_file") or "prompt.md")
        if not prompt_file.exists():
            raise FileNotFoundError(f"Task prompt not found: {prompt_file}")
        task_prompt = prompt_file.read_text()

        # Load criteria
        criteria_file = path / "expected" / "criteria.md"
        if not criteria_file.exists():
            raise FileNotFoundError(f"Criteria not found: {criteria_file}")
        criteria = criteria_file.read_text()

        # Load rubric
        rubric_file = path / "expected" / "rubric.yaml"
        if not rubric_file.exists():
            raise FileNotFoundError(f"Rubric not found: {rubric_file}")
        with open(rubric_file) as f:
            rubric = yaml.safe_load(f) or {}

        # Extract required fields
        test_id = config.get("id")
        if not test_id:
            raise ValueError("Missing required field: id")

        language = config.get("language")
        if not language:
            raise ValueError("Missing required field: language")

        source = config.get("source", {})
        source_repo = source.get("repo")
        source_hash = source.get("hash")
        if not source_repo or not source_hash:
            raise ValueError("Missing required fields: source.repo and source.hash")

        return cls(
            id=test_id,
            name=config.get("name", test_id),
            description=config.get("description", ""),
            language=language,
            source_repo=source_repo,
            source_hash=source_hash,
            task_prompt=task_prompt,
            criteria=criteria,
            rubric=rubric,
            tiers=config.get("tiers", []),
            timeout_seconds=config.get("task", {}).get("timeout_seconds", 3600),
        )

    def to_directory(self, path: Path) -> None:
        """Write test fixture to directory structure.

        Creates the standard test fixture directory layout.

        Args:
            path: Target directory path

        """
        path.mkdir(parents=True, exist_ok=True)

        # Write test.yaml
        test_config = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "language": self.language,
            "source": {
                "repo": self.source_repo,
                "hash": self.source_hash,
            },
            "task": {
                "prompt_file": "prompt.md",
                "timeout_seconds": self.timeout_seconds,
            },
            "tiers": self.tiers,
        }
        with open(path / "test.yaml", "w") as f:
            yaml.dump(test_config, f, default_flow_style=False, sort_keys=False)

        # Write prompt.md
        (path / "prompt.md").write_text(self.task_prompt)

        # Write expected/criteria.md
        expected_dir = path / "expected"
        expected_dir.mkdir(exist_ok=True)
        (expected_dir / "criteria.md").write_text(self.criteria)

        # Write expected/rubric.yaml
        with open(expected_dir / "rubric.yaml", "w") as f:
            yaml.dump(self.rubric, f, default_flow_style=False, sort_keys=False)


class ExperimentConfig(BaseModel):
    """Complete experiment configuration.

    Defines all parameters for running an E2E experiment.

    Attributes:
        experiment_id: Unique identifier for this experiment
        task_repo: Git repository URL for the task
        task_commit: Git commit hash to checkout
        task_prompt_file: Path to the task prompt file
        models: List of model identifiers to test
        runs_per_subtest: Number of runs per sub-test (default: 10)
        tiers_to_run: List of tiers to evaluate
        judge_models: List of models to use for judging (consensus voting)
        timeout_seconds: Timeout per run in seconds
        max_turns: Maximum conversation turns for agent (None = unlimited)
        max_subtests: Maximum sub-tests per tier for testing (None = all)
        language: Programming language for build pipeline ('python' or 'mojo')
        thinking_mode: Thinking mode for agent execution (None, Low, High, UltraThink)
        use_containers: Run agents and judges in isolated Docker containers (default: False)
        criteria_file: Optional path to criteria.md
            (default: tiers_dir/../expected/criteria.md)
        rubric_file: Optional path to rubric.yaml
            (default: tiers_dir/../expected/rubric.yaml)

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    experiment_id: str
    task_repo: str
    task_commit: str
    task_prompt_file: Path
    language: str  # REQUIRED: Programming language for build pipeline
    models: list[str] = Field(default_factory=lambda: [DEFAULT_AGENT_MODEL])
    runs_per_subtest: int = 10
    tiers_to_run: list[TierID] = Field(default_factory=lambda: list(TierID))
    judge_models: list[str] = Field(default_factory=lambda: [DEFAULT_JUDGE_MODEL])
    timeout_seconds: int = 3600
    max_turns: int | None = None  # Max conversation turns for agent (None = unlimited)
    max_subtests: int | None = None  # Max sub-tests per tier (None = all)
    skip_agent_teams: bool = False  # Skip agent teams sub-tests (default: False)
    thinking_mode: str = "None"  # Thinking mode: None (default), Low, High, UltraThink
    use_containers: bool = (
        False  # DEPRECATED: Container isolation now at experiment level, not per-agent
    )
    criteria_file: Path | None = None  # Optional explicit path to criteria.md
    rubric_file: Path | None = None  # Optional explicit path to rubric.yaml
    # Ephemeral --until controls (not saved to experiment.json / not in config_hash)
    until_run_state: RunState | None = None
    until_tier_state: TierState | None = None
    until_experiment_state: ExperimentState | None = None
    # Ephemeral --from controls (not saved to experiment.json / not in config_hash)
    from_run_state: RunState | None = None
    from_tier_state: TierState | None = None
    from_experiment_state: ExperimentState | None = None
    # Ephemeral filters for --from (not saved to experiment.json / not in config_hash)
    filter_tiers: list[str] | None = None
    filter_subtests: list[str] | None = None
    filter_runs: list[int] | None = None
    filter_statuses: list[str] | None = None
    filter_judge_slots: list[int] | None = None
    # Resource management (ephemeral, not saved to experiment.json)
    keep_failed_workspaces: bool = False  # Preserve workspaces for failed runs
    max_concurrent_workspaces: int | None = None  # Limit live workspaces (None = auto)
    max_concurrent_agents: int | None = None  # Limit concurrent claude CLI processes (None = auto)
    off_peak: bool = False  # Wait for off-peak hours before each subtest run

    @field_validator("models", mode="before")
    @classmethod
    def _normalize_models(cls, v: list[str]) -> list[str]:
        return [normalize_model_id(m) for m in v]

    @field_validator("judge_models", mode="before")
    @classmethod
    def _normalize_judge_models(cls, v: list[str]) -> list[str]:
        return [normalize_model_id(m) for m in v]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Ephemeral runtime-only fields (resume/filter controls) are excluded so
        that the serialized form matches what is written to experiment.json.
        """
        # These fields control resume/filter behaviour and must not appear in
        # the persisted config.  Keep this list in sync with the model fields
        # that are annotated "Ephemeral" in the class docstring.
        _ephemeral: set[str] = {
            "criteria_file",
            "rubric_file",
            "until_run_state",
            "until_tier_state",
            "until_experiment_state",
            "from_run_state",
            "from_tier_state",
            "from_experiment_state",
            "filter_tiers",
            "filter_subtests",
            "filter_runs",
            "filter_statuses",
            "filter_judge_slots",
            "keep_failed_workspaces",
            "max_concurrent_workspaces",
            "max_concurrent_agents",
            "off_peak",
        }
        return self.model_dump(mode="json", exclude=_ephemeral)

    def save(self, path: Path) -> None:
        """Save configuration to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> ExperimentConfig:
        """Load configuration from JSON file."""
        with open(path) as f:
            data = json.load(f)

        # Backward compatibility: convert old judge_model to judge_models
        if "judge_model" in data and "judge_models" not in data:
            judge_models = [data["judge_model"]]
        else:
            judge_models = data.get("judge_models", [DEFAULT_JUDGE_MODEL])

        return cls(
            experiment_id=data["experiment_id"],
            task_repo=data["task_repo"],
            task_commit=data["task_commit"],
            task_prompt_file=Path(data["task_prompt_file"]),
            language=data["language"],
            models=data.get("models", [DEFAULT_AGENT_MODEL]),
            runs_per_subtest=data.get("runs_per_subtest", 10),
            tiers_to_run=[TierID.from_string(t) for t in data.get("tiers_to_run", [])],
            judge_models=judge_models,
            timeout_seconds=data.get("timeout_seconds", 3600),
            max_turns=data.get("max_turns"),
            max_subtests=data.get("max_subtests"),
            skip_agent_teams=data.get("skip_agent_teams", False),
            thinking_mode=data.get("thinking_mode", "None"),
            use_containers=data.get("use_containers", False),
        )


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
