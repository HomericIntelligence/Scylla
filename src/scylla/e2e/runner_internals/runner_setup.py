"""RunnerSetup collaborator — experiment initialization and workspace prep.

Owns: experiment directory creation, fresh checkpoint creation, workspace
manager setup, baseline capture, PID file lifecycle.

E2ERunner delegates these responsibilities here. State lives on the runner;
this collaborator reaches back into it via the bound ``runner`` reference.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.experiment_setup_manager import ExperimentSetupManager
from scylla.e2e.runner_internals.constants import _STATUS_RUNNING
from scylla.e2e.workspace_manager import WorkspaceManager
from scylla.persistence.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint

if TYPE_CHECKING:
    from scylla.e2e.runner_internals.runner_core import E2ERunner

logger = logging.getLogger(__name__)


class RunnerSetup:
    """Initialization, configuration validation, and workspace preparation."""

    def __init__(self, runner: E2ERunner) -> None:
        """Bind this collaborator to the owning :class:`E2ERunner`."""
        self._runner = runner

    def setup_manager(self) -> ExperimentSetupManager:
        """Create an ExperimentSetupManager bound to current state."""
        return ExperimentSetupManager(self._runner.config, self._runner.results_base_dir)

    def create_fresh_experiment(self) -> Path:
        """Create new experiment directory and initialize checkpoint.

        Returns:
            Path to the created checkpoint file.

        """
        runner = self._runner
        setup = self.setup_manager()
        runner.experiment_dir = setup.create_experiment_dir()
        setup.save_config(runner.experiment_dir)

        runner.checkpoint = E2ECheckpoint(
            experiment_id=runner.config.experiment_id,
            experiment_dir=str(runner.experiment_dir),
            config_hash=compute_config_hash(runner.config),
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status=_STATUS_RUNNING,
            rate_limit_source=None,
            rate_limit_until=None,
            pause_count=0,
            pid=os.getpid(),
        )

        checkpoint_path = runner.experiment_dir / "checkpoint.json"
        save_checkpoint(runner.checkpoint, checkpoint_path)
        logger.info(f"💾 Created checkpoint: {checkpoint_path}")

        return checkpoint_path

    def setup_workspace(self) -> None:
        """Set up the WorkspaceManager if not already initialized."""
        runner = self._runner
        if runner.workspace_manager is not None:
            return
        if runner.experiment_dir is None:
            raise RuntimeError("experiment_dir must be set before initializing workspace manager")
        repos_dir = runner.results_base_dir / "repos"
        wm = WorkspaceManager(
            experiment_dir=runner.experiment_dir,
            repo_url=runner.config.task_repo,
            commit=runner.config.task_commit,
            repos_dir=repos_dir,
        )
        wm.setup_base_repo()
        runner.workspace_manager = wm

    def capture_experiment_baseline(self) -> None:
        """Capture pipeline baseline once at experiment level from a clean repo state."""
        runner = self._runner
        assert runner.experiment_dir is not None  # noqa: S101
        assert runner.workspace_manager is not None  # noqa: S101
        self.setup_manager().capture_baseline(runner.experiment_dir, runner.workspace_manager)

    def write_pid_file(self) -> None:
        """Write PID file for status monitoring."""
        runner = self._runner
        if runner.experiment_dir:
            self.setup_manager().write_pid_file(runner.experiment_dir)

    def cleanup_pid_file(self) -> None:
        """Remove PID file on completion."""
        runner = self._runner
        if runner.experiment_dir:
            self.setup_manager().cleanup_pid_file(runner.experiment_dir)
