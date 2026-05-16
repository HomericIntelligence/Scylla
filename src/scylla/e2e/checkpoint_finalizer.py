"""Checkpoint lifecycle management at experiment boundaries.

Encapsulates checkpoint discovery, interrupt handling, filesystem validation
on resume, and completion marking from E2ERunner.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from scylla.e2e.models import ExperimentConfig, ExperimentState
from scylla.persistence.checkpoint import E2ECheckpoint, load_checkpoint, save_checkpoint

logger = logging.getLogger(__name__)

# Checkpoint status constants (kept as strings for JSON serialization compatibility)
_STATUS_INTERRUPTED = "interrupted"
_STATUS_COMPLETED = "completed"


class CheckpointFinalizer:
    """Manages checkpoint lifecycle at experiment boundaries.

    Encapsulates the cluster of methods from E2ERunner that handle checkpoint
    state at experiment boundaries: discovery, interrupt handling, filesystem
    validation on resume, and completion marking.

    Args:
        config: Experiment configuration (provides experiment_id).
        results_base_dir: Root directory containing experiment dirs.

    """

    def __init__(self, config: ExperimentConfig, results_base_dir: Path) -> None:
        """Initialize with experiment configuration.

        Args:
            config: Experiment configuration.
            results_base_dir: Root directory containing experiment dirs.

        """
        self.config = config
        self.results_base_dir = results_base_dir

    def find_existing_checkpoint(self) -> Path | None:
        """Find existing checkpoint file in results directory.

        Searches for most recent experiment directory with matching experiment_id
        that has a checkpoint.json file.

        Returns:
            Path to checkpoint file if found, None otherwise.

        """
        if not self.results_base_dir.exists():
            return None

        # Find directories matching: *-{experiment_id}
        pattern = f"*-{self.config.experiment_id}"
        matching_dirs = sorted(
            [d for d in self.results_base_dir.glob(pattern) if d.is_dir()],
            key=lambda d: d.name,  # Sort by timestamp prefix
            reverse=True,  # Most recent first
        )

        for exp_dir in matching_dirs:
            checkpoint_file = exp_dir / "checkpoint.json"
            if checkpoint_file.exists():
                return checkpoint_file

        return None

    def handle_experiment_interrupt(
        self,
        checkpoint: E2ECheckpoint | None,
        checkpoint_path: Path,
    ) -> None:
        """Handle graceful shutdown on interrupt.

        Args:
            checkpoint: In-memory checkpoint (used as fallback if disk reload fails).
            checkpoint_path: Path to checkpoint file.

        Side effects:
            - Reloads checkpoint from disk
            - Updates status to 'interrupted'
            - Saves checkpoint

        """
        if checkpoint_path and checkpoint_path.exists():
            # CRITICAL: Reload checkpoint from disk to preserve worker-saved completions
            # Workers save their progress to the checkpoint file, but the main process
            # has a stale copy. We must reload to avoid overwriting worker progress.
            try:
                logger.info("Reloading checkpoint from disk to preserve worker progress...")
                current_checkpoint = load_checkpoint(checkpoint_path)
                current_checkpoint.status = _STATUS_INTERRUPTED
                current_checkpoint.experiment_state = ExperimentState.INTERRUPTED.value
                current_checkpoint.last_updated_at = datetime.now(timezone.utc).isoformat()
                save_checkpoint(current_checkpoint, checkpoint_path)
                logger.warning("Checkpoint saved after interrupt")
            except (
                Exception
            ) as reload_error:  # broad catch: interrupt handler; must not mask interrupt
                # If reload fails, save what we have (better than nothing)
                logger.error(f"Failed to reload checkpoint: {reload_error}")
                logger.warning("Saving checkpoint from memory (may lose some worker progress)")
                if checkpoint:
                    checkpoint.status = _STATUS_INTERRUPTED
                    checkpoint.experiment_state = ExperimentState.INTERRUPTED.value
                    checkpoint.last_updated_at = datetime.now(timezone.utc).isoformat()
                    save_checkpoint(checkpoint, checkpoint_path)
                    logger.warning("Checkpoint saved after interrupt")

    def validate_filesystem_on_resume(
        self,
        experiment_dir: Path,
        current_state: ExperimentState,
    ) -> None:
        """Cross-validate filesystem against checkpoint state on resume.

        Logs warnings when checkpoint says we're mid-execution but expected
        directories or files are missing. Never fails — warnings only.

        Args:
            experiment_dir: Experiment directory to validate.
            current_state: Current ExperimentState being resumed from.

        """
        if current_state == ExperimentState.TIERS_RUNNING:
            repos_dir = self.results_base_dir / "repos"
            if not experiment_dir.exists():
                logger.warning(
                    f"Resuming from TIERS_RUNNING but experiment_dir missing: {experiment_dir}"
                )
            if not repos_dir.exists():
                logger.warning(f"Resuming from TIERS_RUNNING but repos/ dir missing: {repos_dir}")

    def mark_checkpoint_completed(
        self,
        checkpoint: E2ECheckpoint,
        experiment_dir: Path,
    ) -> None:
        """Mark checkpoint as completed.

        With ThreadPoolExecutor, all worker threads share the same in-memory
        checkpoint object, so no disk-merge is needed — the checkpoint is
        already up-to-date.

        Args:
            checkpoint: In-memory checkpoint object to update in-place.
            experiment_dir: Experiment directory containing checkpoint.json.

        """
        checkpoint.status = _STATUS_COMPLETED
        logger.debug("Checkpoint marked as completed")
