"""Base adapter class for agent implementations.

This module provides the abstract base class that all agent adapters inherit from.
Adapters bridge the Scylla test runner and specific AI agent implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from scylla.config.pricing import (
    calculate_cost as pricing_calculate_cost,
)
from scylla.core.token_stats import TokenStats

if TYPE_CHECKING:
    from scylla.executor.tier_config import TierConfig


class AdapterTokenStats(BaseModel):
    """Detailed token statistics for adapter results."""

    input_tokens: int = Field(default=0, description="Fresh input tokens")
    output_tokens: int = Field(default=0, description="Generated output tokens")
    cache_creation_tokens: int = Field(default=0, description="Tokens written to cache")
    cache_read_tokens: int = Field(default=0, description="Tokens read from cache")

    def to_token_stats(self) -> TokenStats:
        """Convert to E2E TokenStats dataclass."""
        return TokenStats(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_creation_tokens=self.cache_creation_tokens,
            cache_read_tokens=self.cache_read_tokens,
        )


class AdapterResult(BaseModel):
    """Result from adapter execution.

    Contains execution metrics and status information.
    """

    exit_code: int = Field(..., description="Process exit code (0 = success)")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    duration_seconds: float = Field(default=0.0, description="Execution duration")
    token_stats: AdapterTokenStats = Field(
        default_factory=AdapterTokenStats, description="Detailed token statistics"
    )
    cost_usd: float = Field(default=0.0, description="Estimated cost in USD")
    api_calls: int = Field(default=0, description="Number of API calls made")
    timed_out: bool = Field(default=False, description="Whether execution timed out")
    error_message: str | None = Field(default=None, description="Error message if failed")

    # Legacy properties for backwards compatibility
    @property
    def tokens_input(self) -> int:
        """Total input tokens (legacy)."""
        return self.token_stats.input_tokens + self.token_stats.cache_read_tokens

    @property
    def tokens_output(self) -> int:
        """Output tokens (legacy)."""
        return self.token_stats.output_tokens


@dataclass
class AdapterConfig:
    """Configuration for adapter execution.

    Contains settings passed to the adapter from the test runner.
    """

    model: str
    prompt_file: Path
    workspace: Path
    output_dir: Path
    timeout: int = 3600
    env_vars: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)


class AdapterError(Exception):
    """Base exception for adapter errors."""

    pass


class AdapterTimeoutError(AdapterError):
    """Raised when adapter execution times out."""

    pass


class AdapterValidationError(AdapterError):
    """Raised when adapter configuration is invalid."""

    pass


class BaseAdapter(ABC):
    """Abstract base class for all agent adapters.

    All concrete adapters must inherit from this class and implement
    the `run` method. The base class provides common functionality for:
    - Tier-specific prompt injection
    - Log writing utilities
    - Configuration validation

    Example:
        >>> class MyAdapter(BaseAdapter):
        ...     def run(self, config, tier_config):
        ...         # Implementation here
        ...         return AdapterResult(exit_code=0)

    """

    def __init__(self, adapter_config: dict[str, Any] | None = None) -> None:
        """Initialize the adapter.

        Args:
            adapter_config: Optional adapter-specific configuration.

        """
        self.adapter_config = adapter_config or {}

    @abstractmethod
    def run(
        self,
        config: AdapterConfig,
        tier_config: TierConfig | None = None,
    ) -> AdapterResult:
        """Execute the agent with the given configuration.

        Args:
            config: Adapter configuration with model, prompt, workspace, etc.
            tier_config: Optional tier-specific configuration for prompt injection.

        Returns:
            AdapterResult with execution details.

        Raises:
            AdapterError: If execution fails.
            AdapterTimeoutError: If execution times out.

        """
        ...

    def get_name(self) -> str:
        """Return adapter name for logging.

        Returns:
            Class name as string.

        """
        return self.__class__.__name__

    def validate_config(self, config: AdapterConfig) -> None:
        """Validate configuration before execution.

        Override in subclasses to add adapter-specific validation.

        Args:
            config: Configuration to validate.

        Raises:
            AdapterValidationError: If configuration is invalid.

        """
        if not config.prompt_file.exists():
            raise AdapterValidationError(f"Prompt file not found: {config.prompt_file}")
        if not config.workspace.exists():
            raise AdapterValidationError(f"Workspace directory not found: {config.workspace}")
        if config.timeout <= 0:
            raise AdapterValidationError(f"Invalid timeout: {config.timeout} (must be positive)")

    def inject_tier_prompt(
        self,
        task_prompt: str,
        tier_config: TierConfig | None,
    ) -> str:
        """Return the task prompt unchanged.

        Tier-specific prompt content is composed into CLAUDE.md at workspace
        preparation time (see TierManager), not injected here.

        Args:
            task_prompt: The original task prompt.
            tier_config: Tier configuration (unused, kept for API compatibility).

        Returns:
            The task prompt unchanged.

        """
        return task_prompt

    def get_tier_settings(
        self,
        tier_config: TierConfig | None,
    ) -> dict[str, bool | None]:
        """Get tier-specific settings for tool/delegation control.

        Args:
            tier_config: Tier configuration.

        Returns:
            Dictionary with tools_enabled and delegation_enabled settings.

        """
        if tier_config is None:
            return {"tools_enabled": None, "delegation_enabled": None}

        return {
            "tools_enabled": tier_config.tools_enabled,
            "delegation_enabled": tier_config.delegation_enabled,
        }

    def write_logs(
        self,
        output_dir: Path,
        stdout: str,
        stderr: str,
        agent_log: str | None = None,
    ) -> None:
        """Write captured logs directly to output directory.

        Files are written directly to output_dir (no logs/ subdirectory).

        Args:
            output_dir: Directory for log files.
            stdout: Standard output content.
            stderr: Standard error content.
            agent_log: Optional agent interaction log.

        """
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "stdout.log").write_text(stdout)
        (output_dir / "stderr.log").write_text(stderr)

        if agent_log:
            (output_dir / "agent.log").write_text(agent_log)

    def calculate_cost(
        self,
        tokens_input: int,
        tokens_output: int,
        model: str | None = None,
        tokens_cached: int = 0,
    ) -> float:
        """Calculate execution cost from token counts.

        Uses centralized pricing from scylla.config.pricing.

        Args:
            tokens_input: Number of input tokens.
            tokens_output: Number of output tokens.
            model: Optional model identifier for specific pricing.
            tokens_cached: Number of cached tokens (optional).

        Returns:
            Estimated cost in USD.

        """
        return pricing_calculate_cost(
            tokens_input, tokens_output, tokens_cached=tokens_cached, model=model
        )

    def load_prompt(self, prompt_file: Path) -> str:
        """Load prompt content from file.

        Args:
            prompt_file: Path to prompt markdown file.

        Returns:
            Prompt content as string.

        Raises:
            AdapterError: If file cannot be read.

        """
        try:
            return prompt_file.read_text()
        except OSError as e:
            raise AdapterError(f"Failed to read prompt file: {e}") from e
