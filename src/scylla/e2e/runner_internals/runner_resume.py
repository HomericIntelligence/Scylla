"""RunnerResume collaborator — resume-from-checkpoint orchestration.

Owns: locating an existing checkpoint, validating its config, merging CLI
flags back into the resumed configuration, and orchestrating the
fresh-vs-resume decision.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.models import ExperimentConfig
from scylla.e2e.resume_manager import ResumeManager

if TYPE_CHECKING:
    from scylla.persistence.checkpoint import E2ECheckpoint
    from scylla.e2e.runner_internals.runner_core import E2ERunner

logger = logging.getLogger(__name__)


class RunnerResume:
    """Resume-from-checkpoint logic plus fresh fallback."""

    def __init__(self, runner: E2ERunner) -> None:
        """Bind this collaborator to the owning :class:`E2ERunner`."""
        self._runner = runner

    def find_existing_checkpoint(self) -> Path | None:
        """Locate an existing checkpoint file in the results directory."""
        return self._runner.finalization.finalizer().find_existing_checkpoint()

    def log_checkpoint_resume(self, checkpoint_path: Path) -> None:
        """Log checkpoint resume status with completed run count."""
        from scylla.e2e.runner_internals import runner_core as _rc

        runner = self._runner
        if runner.checkpoint is None:
            raise RuntimeError("checkpoint must be set before logging resume status")
        _rc.logger.info(f"📂 Resuming from checkpoint: {checkpoint_path}")
        _rc.logger.info(
            f"   Previously completed: {runner.checkpoint.get_completed_run_count()} runs"
        )

    def load_checkpoint_and_config(self, checkpoint_path: Path) -> tuple[E2ECheckpoint, Path]:
        """Load and validate checkpoint and configuration from existing checkpoint.

        Args:
            checkpoint_path: Path to checkpoint.json file.

        Returns:
            Tuple of (checkpoint, experiment_dir).

        Raises:
            ValueError: If config validation fails or experiment directory missing.

        """
        # Delegate to the same loaders that the runner_core module previously imported,
        # via the runner_core module namespace — preserves existing test patches.
        from scylla.e2e.runner_internals import runner_core as _rc

        runner = self._runner
        runner.checkpoint = _rc.load_checkpoint(checkpoint_path)
        runner.experiment_dir = Path(runner.checkpoint.experiment_dir)

        saved_config_path = runner.experiment_dir / "config" / "experiment.json"
        if saved_config_path.exists():
            runner._log_checkpoint_resume(checkpoint_path)
            _rc.logger.info(f"📋 Loading config from checkpoint: {saved_config_path}")
            runner.config = ExperimentConfig.load(saved_config_path)
        else:
            _rc.logger.warning(
                f"⚠️  Checkpoint config not found at {saved_config_path}, using CLI config"
            )
            if not _rc.validate_checkpoint_config(runner.checkpoint, runner.config):
                raise ValueError(
                    f"Config has changed since checkpoint. Use --fresh to start over.\n"
                    f"Checkpoint: {checkpoint_path}"
                )
            runner._log_checkpoint_resume(checkpoint_path)

        if not runner.experiment_dir.exists():
            raise ValueError(
                f"Checkpoint references non-existent directory: {runner.experiment_dir}"
            )

        return runner.checkpoint, runner.experiment_dir

    def initialize_or_resume_experiment(self) -> Path:
        """Initialize fresh experiment or resume from checkpoint.

        Returns:
            Path to the checkpoint file for this experiment.

        """
        runner = self._runner
        # Route through runner._find_existing_checkpoint and runner._load_checkpoint_and_config
        # so tests can patch these methods on the runner instance.
        checkpoint_path = runner._find_existing_checkpoint()

        if checkpoint_path and not runner._fresh:
            # STEP 1: Capture CLI fields before load_checkpoint_and_config overwrites config
            _cli_tiers = list(runner.config.tiers_to_run)
            _cli_ephemeral = {
                "until_run_state": runner.config.until_run_state,
                "until_tier_state": runner.config.until_tier_state,
                "until_experiment_state": runner.config.until_experiment_state,
                "max_subtests": runner.config.max_subtests,
            }

            try:
                runner._load_checkpoint_and_config(checkpoint_path)

                if runner.checkpoint:
                    rm = ResumeManager(runner.checkpoint, runner.config, runner.tier_manager)

                    runner.config, runner.checkpoint = rm.handle_zombie(
                        checkpoint_path, runner.experiment_dir
                    )
                    runner.config, runner.checkpoint = rm.restore_cli_args(_cli_ephemeral)
                    runner.config, runner.checkpoint = rm.reset_failed_states()
                    runner.config, runner.checkpoint = rm.merge_cli_tiers_and_reset_incomplete(
                        _cli_tiers, checkpoint_path
                    )

            except Exception as e:  # broad: JSON/IO/state errors during resume
                from scylla.e2e.runner_internals import runner_core as _rc

                _rc.logger.warning(f"Failed to resume from checkpoint: {e}")
                _rc.logger.warning("Starting fresh experiment instead")
                runner.checkpoint = None
                runner.experiment_dir = None

        if not runner.experiment_dir:
            checkpoint_path = runner._create_fresh_experiment()

        runner._write_pid_file()

        if runner.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before getting checkpoint path")
        return runner.experiment_dir / "checkpoint.json"
