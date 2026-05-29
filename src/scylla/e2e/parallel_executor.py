"""Sequential execution and rate limit coordination for E2E testing.

This module handles:
- Sequential execution of subtests
- Rate limit detection and coordination
- Retry logic for rate-limited subtests
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scylla.e2e.log_context import current_tier_id
from scylla.e2e.models import (
    ExperimentConfig,
    SubTestResult,
    TierConfig,
    TierID,
)
from scylla.e2e.rate_limit import (
    InfrastructureFailureError,
    RateLimitError,
    RateLimitInfo,
    detect_rate_limit,
    is_weekly_limit,
    wait_for_rate_limit,
)
from scylla.metrics.emitter import get_default_emitter

if TYPE_CHECKING:
    from scylla.e2e.models import SubTestConfig, TierBaseline
    from scylla.e2e.resource_manager import ResourceManager
    from scylla.e2e.tier_manager import TierManager
    from scylla.e2e.workspace_manager import WorkspaceManager
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)
_emitter = get_default_emitter()


class RateLimitCoordinator:
    """Coordinates rate limit pause across parallel worker threads.

    When ANY worker detects a rate limit, this coordinator:
    1. Signals all workers to pause
    2. Waits for the rate limit to expire
    3. Signals all workers to resume

    Uses threading primitives for in-process coordination.

    Example:
        >>> coordinator = RateLimitCoordinator()
        >>> # In worker thread:
        >>> if coordinator.check_if_paused():
        >>>     # Worker blocks here until resume
        >>>     pass

    """

    def __init__(self) -> None:
        """Initialize coordinator with shared state."""
        self._pause_event = threading.Event()
        self._resume_event = threading.Event()
        self._rate_limit_info: dict[str, Any] = {}
        self._shutdown_event = threading.Event()

    def signal_rate_limit(self, info: RateLimitInfo) -> None:
        """Signal that a rate limit was detected (called by worker).

        This sets the pause event, causing all workers to block.

        Args:
            info: Rate limit detection information

        """
        self._rate_limit_info.update(
            {
                "source": info.source,
                "retry_after_seconds": info.retry_after_seconds,
                "error_message": info.error_message,
                "detected_at": info.detected_at,
            }
        )
        self._pause_event.set()
        logger.info(f"Rate limit coordinator: pause signal from {info.source}")

    def check_if_paused(self) -> bool:
        """Check if pause is active and wait if needed (called by workers).

        Workers call this before each operation. If pause is active,
        they block here until resume signal.

        Returns:
            True if was paused and now resumed, False if never paused

        """
        if self._pause_event.is_set():
            logger.debug("Worker blocked on pause event, waiting for resume...")
            # Poll with timeout so shutdown can interrupt a stuck pause.
            # Do NOT clear _resume_event here — only the producer (main thread via
            # resume_all_workers()) should manage Event state to avoid a race where
            # one worker clears the event before other workers have woken up.
            while not self._resume_event.wait(timeout=2.0):
                if self._shutdown_event.is_set():
                    logger.info("Worker exiting pause due to shutdown signal")
                    return True
            logger.debug("Worker resumed after rate limit wait")
            return True
        return False

    def get_rate_limit_info(self) -> RateLimitInfo | None:
        """Get current rate limit info if available.

        Returns:
            RateLimitInfo if rate limit is active, None otherwise

        """
        if not self._pause_event.is_set():
            return None

        info_dict = dict(self._rate_limit_info)
        if not info_dict:
            return None

        return RateLimitInfo(
            source=info_dict["source"],
            retry_after_seconds=info_dict["retry_after_seconds"],
            error_message=info_dict["error_message"],
            detected_at=info_dict["detected_at"],
        )

    def resume_all_workers(self) -> None:
        """Signal all workers to resume (called by main thread after wait).

        Clears the pause event and sets resume event.
        """
        self._pause_event.clear()
        self._resume_event.set()
        logger.info("Rate limit coordinator: resume signal sent to all workers")

    def signal_shutdown(self) -> None:
        """Signal all workers to stop accepting new work and exit gracefully."""
        self._shutdown_event.set()
        logger.info("Shutdown signal sent to all workers")

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested.

        Returns:
            True if shutdown is requested, False otherwise

        """
        return self._shutdown_event.is_set()


def run_tier_subtests_parallel(
    config: ExperimentConfig,
    tier_id: TierID,
    tier_config: TierConfig,
    tier_manager: TierManager,
    workspace_manager: WorkspaceManager,
    baseline: TierBaseline | None,
    results_dir: Path,
    checkpoint: E2ECheckpoint | None = None,
    checkpoint_path: Path | None = None,
    experiment_dir: Path | None = None,
    resource_manager: ResourceManager | None = None,
) -> dict[str, SubTestResult]:
    """Run all sub-tests for a tier sequentially with rate limit handling.

    Args:
        config: Experiment configuration
        tier_id: The tier being executed
        tier_config: Tier configuration with sub-tests
        tier_manager: Tier configuration manager
        workspace_manager: Workspace manager for git worktrees
        baseline: Previous tier's winning baseline
        results_dir: Base directory for tier results
        checkpoint: Optional checkpoint for resume capability
        checkpoint_path: Path to checkpoint file for saving
        experiment_dir: Path to experiment directory (needed for T5 inheritance)
        resource_manager: Optional resource limiter for concurrency control

    Returns:
        Dict mapping sub-test ID to results.

    """
    # Import here to avoid circular dependency
    from scylla.e2e.subtest_executor import SubTestExecutor

    results: dict[str, SubTestResult] = {}
    executor = SubTestExecutor(
        config, tier_manager, workspace_manager, resource_manager=resource_manager
    )

    total_subtests = len(tier_config.subtests)
    start_time = time.time()
    completed_count = 0

    from scylla.e2e.log_context import set_log_context

    set_log_context(tier_id=tier_id.value)

    for subtest in tier_config.subtests:
        # Check for shutdown before starting subtest
        from scylla.e2e.shutdown import is_shutdown_requested

        if is_shutdown_requested():
            logger.warning("Shutdown requested, stopping subtest execution...")
            break

        # Wait for off-peak hours if configured
        if config.off_peak:
            from scylla.e2e.scheduling import wait_for_off_peak

            wait_for_off_peak()

        subtest_dir = results_dir / subtest.id
        set_log_context(tier_id=tier_id.value, subtest_id=subtest.id)

        try:
            results[subtest.id] = executor.run_subtest(
                tier_id=tier_id,
                tier_config=tier_config,
                subtest=subtest,
                baseline=baseline,
                results_dir=subtest_dir,
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                coordinator=None,
                experiment_dir=experiment_dir,
            )
            completed_count += 1

            elapsed = time.time() - start_time
            remaining = total_subtests - completed_count
            logger.info(
                f"[PROGRESS] Tier {tier_id.value}: "
                f"{completed_count}/{total_subtests} complete, "
                f"{remaining} remaining, elapsed: {elapsed:.0f}s"
            )
        except InfrastructureFailureError as e:
            # Agent crashed before making API calls — skip this subtest and continue.
            # The run has already been archived to .failed/ by stage_commit_agent_changes().
            logger.warning(
                f"[SKIP] Subtest {subtest.id} skipped due to infrastructure failure: {e}"
            )
            try:
                _emitter.emit_counter(
                    "scylla_errors_total",
                    1,
                    labels={"error_class": type(e).__name__, "tier": current_tier_id()},
                )
            except Exception as _me:
                logger.warning(f"Error metric emission failed (non-fatal): {_me}")
            completed_count += 1
        except RateLimitError as e:
            try:
                _emitter.emit_counter(
                    "scylla_errors_total",
                    1,
                    labels={"error_class": type(e).__name__, "tier": current_tier_id()},
                )
            except Exception as _me:
                logger.warning(f"Error metric emission failed (non-fatal): {_me}")
            completed_count = _handle_rate_limit(
                e,
                executor=executor,
                tier_id=tier_id,
                tier_config=tier_config,
                subtest=subtest,
                baseline=baseline,
                results_dir=subtest_dir,
                results=results,
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                experiment_dir=experiment_dir,
                completed_count=completed_count,
            )

    return results


def _handle_rate_limit(
    error: RateLimitError,
    *,
    executor: Any,
    tier_id: TierID,
    tier_config: TierConfig,
    subtest: SubTestConfig,
    baseline: TierBaseline | None,
    results_dir: Path,
    results: dict[str, SubTestResult],
    checkpoint: E2ECheckpoint | None,
    checkpoint_path: Path | None,
    experiment_dir: Path | None,
    completed_count: int,
) -> int:
    """Handle a rate limit error by waiting and retrying.

    Args:
        error: The RateLimitError that was caught.
        executor: SubTestExecutor instance.
        tier_id: Current tier identifier.
        tier_config: Tier configuration.
        subtest: The subtest that hit the rate limit.
        baseline: Previous tier's winning baseline.
        results_dir: Results directory for this subtest.
        results: Mutable dict collecting subtest results.
        checkpoint: Optional checkpoint for resume.
        checkpoint_path: Path to checkpoint file.
        experiment_dir: Experiment directory (for T5 inheritance).
        completed_count: Current count of completed subtests.

    Returns:
        Updated completed_count.

    Raises:
        RateLimitError: If no checkpoint is available to handle the error.

    """
    if not (checkpoint and checkpoint_path):
        raise error

    if is_weekly_limit(error.info):
        logger.warning(
            "Weekly usage limit detected from %s — waiting until reset. Resume after: %s",
            error.info.source,
            error.info.error_message,
        )
    else:
        logger.info("Rate limit detected from %s, waiting...", error.info.source)

    wait_for_rate_limit(error.info.retry_after_seconds, checkpoint, checkpoint_path)

    results[subtest.id] = executor.run_subtest(
        tier_id=tier_id,
        tier_config=tier_config,
        subtest=subtest,
        baseline=baseline,
        results_dir=results_dir,
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        coordinator=None,
        experiment_dir=experiment_dir,
    )
    return completed_count + 1


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous code.

    Uses the running event loop when available (e.g., inside an async
    framework), otherwise creates a new loop via ``asyncio.run``.

    Args:
        coro: Awaitable coroutine to execute.

    Returns:
        The coroutine's return value.

    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Schedule on the existing loop; block until complete.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _detect_rate_limit_from_results(
    results: dict[str, SubTestResult],
    results_dir: Path,
) -> RateLimitInfo | None:
    """Detect rate limit from completed results OR .failed/ directories.

    Checks:
    1. SubTestResult.rate_limit_info field (from safe wrapper)
    2. SubTestResult.selection_reason for "RateLimitError:" prefix
    3. .failed/*/agent/result.json for rate limit patterns in stderr

    Args:
        results: Dictionary of completed subtest results
        results_dir: Base directory for tier results

    Returns:
        RateLimitInfo if rate limit detected, None otherwise

    """
    # Check structured results first (from safe wrapper)
    for subtest_id, result in results.items():
        if result.rate_limit_info:
            logger.debug(f"Rate limit found in {subtest_id}.rate_limit_info")
            return result.rate_limit_info
        if result.selection_reason.startswith("RateLimitError:"):
            # Parse from selection_reason if rate_limit_info not available
            logger.debug(f"Rate limit found in {subtest_id}.selection_reason")
            return RateLimitInfo(
                source="agent",
                retry_after_seconds=None,  # Will use default
                error_message=result.selection_reason,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )

    # Check .failed/ directories for crashed workers
    for failed_dir in results_dir.rglob(".failed/*/agent/result.json"):
        try:
            import json

            data = json.loads(failed_dir.read_text())
            stderr = data.get("stderr", "")
            stdout = data.get("stdout", "")

            rate_info = detect_rate_limit(stdout, stderr, source="agent")
            if rate_info:
                logger.debug(f"Rate limit found in failed run: {failed_dir}")
                return rate_info
        except Exception as e:
            logger.debug(f"Failed to check {failed_dir} for rate limit: {e}")
            continue

    return None


def _run_subtest(
    config: ExperimentConfig,
    tier_id: TierID,
    tier_config: TierConfig,
    subtest: SubTestConfig,
    baseline: TierBaseline | None,
    results_dir: Path,
    tier_manager: TierManager,
    workspace_manager: WorkspaceManager,
    checkpoint: E2ECheckpoint | None = None,
    checkpoint_path: Path | None = None,
    coordinator: RateLimitCoordinator | None = None,
    experiment_dir: Path | None = None,
) -> SubTestResult:
    """Run a sub-test.

    Args:
        config: Experiment configuration
        tier_id: Tier ID
        tier_config: Tier configuration
        subtest: Subtest configuration
        baseline: Baseline from previous tier
        results_dir: Results directory for this subtest
        tier_manager: Tier configuration manager (shared from parent thread)
        workspace_manager: Workspace manager (shared from parent thread)
        checkpoint: Optional checkpoint for resume
        checkpoint_path: Path to checkpoint file
        coordinator: Optional rate limit coordinator
        experiment_dir: Path to experiment directory (needed for T5 inheritance)

    Returns:
        SubTestResult

    """
    # Import here to avoid circular dependency
    from scylla.e2e.log_context import set_log_context
    from scylla.e2e.subtest_executor import SubTestExecutor

    set_log_context(tier_id=tier_id.value, subtest_id=subtest.id)
    executor = SubTestExecutor(config, tier_manager, workspace_manager)
    return executor.run_subtest(
        tier_id=tier_id,
        tier_config=tier_config,
        subtest=subtest,
        baseline=baseline,
        results_dir=results_dir,
        checkpoint=checkpoint,
        checkpoint_path=checkpoint_path,
        coordinator=coordinator,
        experiment_dir=experiment_dir,
    )
