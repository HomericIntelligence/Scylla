"""Pydantic models for ProjectScylla configuration.

This module defines the configuration schema for test cases, rubrics,
tier configurations, and model configurations used by the evaluation framework.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from scylla.config.constants import DEFAULT_AGENT_MODEL, DEFAULT_JUDGE_MODEL
from scylla.core.thresholds import DEFAULT_PASS_THRESHOLD
from scylla.nats.config import NATSConfig


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""

    pass


# -----------------------------------------------------------------------------
# Test Case Models
# -----------------------------------------------------------------------------


class SourceConfig(BaseModel):
    """Source repository configuration for a test case."""

    repo: str = Field(..., description="GitHub repository URL")
    hash: str = Field(..., description="Commit hash to checkout")


class TaskConfig(BaseModel):
    """Task configuration within a test case."""

    prompt_file: str = Field(..., description="Path to prompt file relative to test dir")
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class ValidationConfig(BaseModel):
    """Validation configuration for a test case."""

    criteria_file: str = Field(
        default="expected/criteria.md",
        description="Path to criteria file relative to test dir",
    )
    rubric_file: str = Field(
        default="expected/rubric.yaml",
        description="Path to rubric file relative to test dir",
    )


class EvalCase(BaseModel):
    """Configuration for a test case.

    Maps to tests/<id>/test.yaml
    """

    id: str = Field(..., description="Unique test identifier")
    name: str = Field(..., description="Human-readable test name")
    description: str = Field(..., description="Detailed test description")
    source: SourceConfig
    task: TaskConfig
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    language: str = Field(
        ..., description="Programming language for build pipeline ('python' or 'mojo')"
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate test ID format."""
        if not v or not v.strip():
            raise ValueError("Test ID cannot be empty")
        return v.strip()


# -----------------------------------------------------------------------------
# Rubric Models
# -----------------------------------------------------------------------------


class Requirement(BaseModel):
    """A single requirement in the rubric."""

    id: str = Field(..., description="Requirement identifier (e.g., R001)")
    description: str = Field(..., description="What this requirement evaluates")
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    evaluation: Literal["binary", "scaled"] = Field(default="binary")


class GradingConfig(BaseModel):
    """Grading configuration for a rubric.

    Uses industry-aligned defaults where pass_threshold=0.60 corresponds
    to the B grade (Good - functional, minor improvements possible).

    Grade assignment is handled by scylla.metrics.grading.assign_letter_grade().
    See docs/design/grading-scale.md for full specification.
    """

    pass_threshold: float = Field(default=DEFAULT_PASS_THRESHOLD, ge=0.0, le=1.0)


class Rubric(BaseModel):
    """Rubric for evaluating test results.

    Maps to tests/<id>/expected/rubric.yaml
    """

    requirements: list[Requirement] = Field(default_factory=list)
    grading: GradingConfig = Field(default_factory=GradingConfig)

    def total_weight(self) -> float:
        """Calculate total weight of all requirements."""
        return sum(r.weight for r in self.requirements)

    def weighted_score(self, scores: dict[str, float]) -> float:
        """Calculate weighted score from requirement scores.

        Args:
            scores: Dict mapping requirement IDs to scores (0.0 to 1.0)

        Returns:
            Weighted score between 0.0 and 1.0

        """
        total = self.total_weight()
        if total == 0:
            return 0.0

        weighted_sum = 0.0
        for req in self.requirements:
            if req.id in scores:
                weighted_sum += scores[req.id] * req.weight

        return weighted_sum / total


# -----------------------------------------------------------------------------
# Model Configuration
# -----------------------------------------------------------------------------


class ModelConfig(BaseModel):
    """Configuration for a specific model.

    Maps to config/models/<model_id>.yaml
    """

    model_id: str = Field(..., description="Model identifier")
    name: str = Field(default="", description="Human-readable model name")
    provider: str = Field(default="", description="Model provider (e.g., anthropic, openai)")
    adapter: str = Field(default="claude_code", description="Adapter to use")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=1, le=200000)
    cost_per_1k_input: float = Field(default=0.0, ge=0.0)
    cost_per_1k_output: float = Field(default=0.0, ge=0.0)

    # Optional overrides
    timeout_seconds: int | None = Field(default=None, ge=60, le=86400)
    max_cost_usd: float | None = Field(default=None, ge=0.0)


# -----------------------------------------------------------------------------
# Tier Configuration
# -----------------------------------------------------------------------------


class TierConfig(BaseModel):
    """Configuration for a testing tier.

    Maps to tests/claude-code/shared/tiers.yaml tier entries
    """

    tier: str = Field(..., description="Tier identifier (e.g., t0, t1)")
    name: str = Field(..., description="Human-readable tier name")
    description: str = Field(default="", description="Tier description")

    # Tier-specific settings
    system_prompt: str | None = Field(default=None, description="System prompt for this tier")
    skills: list[str] = Field(default_factory=list, description="Skills enabled for this tier")
    tools: list[str] = Field(default_factory=list, description="Tools enabled for this tier")

    # Tier capabilities
    uses_tools: bool = Field(default=False)
    uses_delegation: bool = Field(default=False)
    uses_hierarchy: bool = Field(default=False)

    @field_validator("tier")
    @classmethod
    def validate_tier_format(cls, v: str) -> str:
        """Validate tier format (t0-t6)."""
        v = v.lower().strip()
        if not v.startswith("t") or not v[1:].isdigit():
            raise ValueError(f"Tier must be in format 't<n>' (e.g., t0, t1), got: {v}")
        tier_num = int(v[1:])
        if tier_num < 0 or tier_num > 6:
            raise ValueError(f"Tier number must be 0-6, got: {tier_num}")
        return v

    @model_validator(mode="after")
    def validate_hierarchy_requires_delegation(self) -> "TierConfig":
        """Enforce that uses_hierarchy=True requires uses_delegation=True."""
        if self.uses_hierarchy and not self.uses_delegation:
            raise ValueError(
                f"uses_hierarchy=true requires uses_delegation=true (tier={self.tier!r})"
            )
        return self


# -----------------------------------------------------------------------------
# Global/Default Configuration
# -----------------------------------------------------------------------------


class NatsConfig(BaseModel):
    """NATS messaging configuration.

    Supports environment variable overrides applied after YAML loading:
    - NATS_ENABLED: truthy string ("1", "true", "yes") to enable
    - NATS_URL, NATS_STREAM, NATS_DURABLE_NAME: string overrides
    """

    enabled: bool = Field(default=False, description="Whether NATS messaging is enabled")
    url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    stream: str = Field(default="scylla", description="NATS stream name")
    durable_name: str = Field(default="scylla-consumer", description="NATS durable consumer name")

    @field_validator("enabled", mode="before")
    @classmethod
    def coerce_none_to_false(cls, v: object) -> object:
        """Defense-in-depth: coerce None to False."""
        if v is None:
            return False
        return v


class JudgeConfig(BaseModel):
    """Judge model configuration."""

    model: str = Field(default=DEFAULT_JUDGE_MODEL)
    adapter: str = Field(default="claude_code")


class AdaptersConfig(BaseModel):
    """Adapters configuration."""

    default: str = Field(default="claude_code")
    available: list[str] = Field(
        default_factory=lambda: ["claude_code", "openai_codex", "cline", "opencode"]
    )


class CleanupConfig(BaseModel):
    """Workspace cleanup configuration."""

    delete_workspace: bool = Field(default=True)
    keep_logs: bool = Field(default=True)


class EvaluationConfig(BaseModel):
    """Evaluation settings from defaults."""

    runs_per_tier: int = Field(default=10, ge=1, le=100, alias="runs_per_eval")
    timeout: int = Field(default=300, ge=60, le=86400)
    seed: int | None = Field(default=None)

    model_config = {"populate_by_name": True}


class MetricsConfig(BaseModel):
    """Metrics configuration."""

    quality: list[str] = Field(
        default_factory=lambda: ["pass_rate", "impl_rate", "progress_rate", "consistency"]
    )
    economic: list[str] = Field(
        default_factory=lambda: ["cost_of_pass", "token_distribution", "change_fail_percentage"]
    )


class OutputConfig(BaseModel):
    """Output directory configuration."""

    runs_dir: str = Field(default="runs")
    summaries_dir: str = Field(default="summaries")
    reports_dir: str = Field(default="reports")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


class RetryConfig(BaseModel):
    """Retry configuration for resilience patterns."""

    max_retries: int = Field(default=3, ge=0, le=10)
    initial_delay: float = Field(default=1.0, ge=0.1)
    backoff_factor: int = Field(default=2, ge=1)
    max_delay: float = Field(default=30.0, ge=1.0)
    jitter: bool = Field(default=True)


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for fail-fast behavior."""

    failure_threshold: int = Field(default=5, ge=1, le=100)
    recovery_timeout: int = Field(default=60, ge=1, le=3600)
    half_open_max_calls: int = Field(default=1, ge=1)


class TimeoutsConfig(BaseModel):
    """Timeout configuration for various operations."""

    api_call: int = Field(default=60, ge=5, le=3600)
    benchmark_run: int = Field(default=300, ge=30, le=86400)
    analysis: int = Field(default=120, ge=30, le=3600)
    judge: int = Field(default=1200, ge=60, le=86400)


class ResilienceConfig(BaseModel):
    """Resilience configuration including retry, circuit breaker, and timeouts.

    Configures resilience patterns for handling transient failures,
    fail-fast behavior on repeated failures, and operation-specific timeouts.

    Maps to config/defaults.yaml resilience: section.
    """

    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)


class DefaultsConfig(BaseModel):
    """Global defaults configuration.

    Maps to config/defaults.yaml
    """

    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    default_model: str = Field(
        default=DEFAULT_AGENT_MODEL,
        description="Default model ID when none is specified",
    )

    # Optional extended settings (for executor)
    runs_per_tier: int = Field(default=10, ge=1, le=100)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    max_cost_usd: float = Field(default=10.0, ge=0.0)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    nats: NATSConfig = Field(default_factory=NATSConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)


# -----------------------------------------------------------------------------
# Merged Runtime Configuration
# -----------------------------------------------------------------------------


class ScyllaConfig(BaseModel):
    """Complete merged configuration for a test run.

    This represents the final, validated configuration after merging:
    1. config/defaults.yaml (base)
    2. config/models/<model_id>.yaml (optional model overrides)
    3. tests/<test_id>/config.yaml (optional test overrides)

    Priority: test > model > defaults
    """

    # From defaults
    runs_per_tier: int = Field(default=10, ge=1, le=100)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    max_cost_usd: float = Field(default=10.0, ge=0.0)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    nats: NATSConfig = Field(default_factory=NATSConfig)

    # From model config (optional)
    model: ModelConfig | None = Field(default=None)

    # Context
    test_id: str | None = Field(default=None)
    model_id: str | None = Field(default=None)

    model_config = {"frozen": True}
