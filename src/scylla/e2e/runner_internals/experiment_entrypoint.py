"""Top-level run_experiment function — public entry point for executing an experiment."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.models import ExperimentConfig, ExperimentResult
from scylla.e2e.runner_internals.runner_core import E2ERunner

if TYPE_CHECKING:
    from scylla.e2e.resource_manager import ResourceManager

logger = logging.getLogger(__name__)


def run_experiment(
    config: ExperimentConfig,
    tiers_dir: Path,
    results_dir: Path,
    fresh: bool = False,
    resource_manager: ResourceManager | None = None,
) -> ExperimentResult:
    """Run an experiment with the given configuration.

    Args:
        config: Experiment configuration
        tiers_dir: Path to tier configurations
        results_dir: Path to results directory
        fresh: If True, ignore existing checkpoints and start fresh
        resource_manager: Optional shared ResourceManager for concurrency control.
            When running in batch mode, all experiments share the same instance.

    Returns:
        ExperimentResult with all results.

    """
    try:
        runner = E2ERunner(config, tiers_dir, results_dir, fresh=fresh)
        runner._resource_manager = resource_manager
        return runner.run()
    except (
        Exception
    ) as e:  # broad catch: public API boundary; provides rate-limit diagnostics before re-raising
        # Check if this is a rate limit error that needs handling
        if "rate limit" in str(e).lower() or "you've hit your limit" in str(e).lower():
            logger.error(f"Experiment failed due to rate limit: {e}")
            logger.error("The experiment encountered a Claude API rate limit.")
            logger.error(
                "Rate limits are automatically handled by the system when checkpoints are enabled."
            )
            logger.error(
                "Please run with checkpoint support (default) and the experiment "
                "will resume after the rate limit expires."
            )
            logger.error("If this persists, try reducing runs_per_subtest in your config.")

            # Re-raise with context
            raise RuntimeError(
                f"Experiment failed due to Claude API rate limit. "
                f"This indicates the API usage limit has been reached. "
                f"The system will automatically resume after the rate limit expires "
                f"when using checkpoints. "
                f"Error details: {e}"
            ) from e
        else:
            # Re-raise other errors as-is
            raise
