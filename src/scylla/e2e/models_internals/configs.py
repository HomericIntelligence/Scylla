"""Configuration models for E2E experiments, tiers, sub-tests, and fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from scylla.config.constants import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_JUDGE_MODEL,
    normalize_model_id,
)
from scylla.e2e.models_internals.state_enums import (
    ExperimentState,
    RunState,
    TierID,
    TierState,
)


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
    # Abort instead of warn when log_resource_preflight() finds RAM/disk
    # below the warning thresholds. Critical-threshold breaches always abort
    # regardless of this flag. Wired from --fail-on-resource-check.
    fail_on_resource_check: bool = False

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
            "fail_on_resource_check",
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
