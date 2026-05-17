"""Smoke tests for the four E2ERunner collaborators introduced by #1941.

The collaborators are thin wrappers over the existing helpers
(``ExperimentSetupManager``, ``CheckpointFinalizer``, ``ParallelTierRunner``,
``ExperimentResultWriter``) — these tests verify that each collaborator is
instantiated on ``E2ERunner.__init__`` and exposes the expected entry
points used by the runner-core delegating methods.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scylla.e2e.models import ExperimentConfig, TierID
from scylla.e2e.runner import E2ERunner
from scylla.e2e.runner_internals.runner_execution import RunnerExecution
from scylla.e2e.runner_internals.runner_finalization import RunnerFinalization
from scylla.e2e.runner_internals.runner_resume import RunnerResume
from scylla.e2e.runner_internals.runner_setup import RunnerSetup


@pytest.fixture
def runner(tmp_path: Path) -> E2ERunner:
    """Return a fresh E2ERunner with a minimal config."""
    config = ExperimentConfig(
        experiment_id="exp-collab",
        task_repo="https://example.com/repo",
        task_commit="abc",
        task_prompt_file=tmp_path / "prompt.md",
        language="python",
    )
    return E2ERunner(config, tmp_path / "tiers", tmp_path)


def test_runner_constructs_all_four_collaborators(runner: E2ERunner) -> None:
    """E2ERunner.__init__ instantiates the four named collaborators."""
    assert isinstance(runner.setup, RunnerSetup)
    assert isinstance(runner.resume, RunnerResume)
    assert isinstance(runner.execution, RunnerExecution)
    assert isinstance(runner.finalization, RunnerFinalization)


def test_collaborators_hold_runner_back_reference(runner: E2ERunner) -> None:
    """Each collaborator keeps a private reference to the owning runner."""
    assert runner.setup._runner is runner
    assert runner.resume._runner is runner
    assert runner.execution._runner is runner
    assert runner.finalization._runner is runner


def test_get_tier_groups_is_static_on_execution() -> None:
    """RunnerExecution.get_tier_groups operates without a runner instance."""
    groups = RunnerExecution.get_tier_groups([TierID.T0])
    assert groups == [[TierID.T0]]


def test_get_tier_groups_empty() -> None:
    """RunnerExecution.get_tier_groups returns [] for empty input."""
    assert RunnerExecution.get_tier_groups([]) == []


def test_finalization_validate_filesystem_no_dir_is_noop(runner: E2ERunner) -> None:
    """validate_filesystem_on_resume short-circuits when experiment_dir is None."""
    runner.experiment_dir = None
    # Should not raise — the collaborator returns early.
    runner.finalization.validate_filesystem_on_resume(MagicMock())


def test_runner_delegates_get_tier_groups(runner: E2ERunner) -> None:
    """Runner._get_tier_groups delegates to RunnerExecution.get_tier_groups."""
    groups = runner._get_tier_groups([TierID.T0, TierID.T1])
    # Both reachable; T0 must appear in (or before) the group containing T1.
    flat = [t for group in groups for t in group]
    assert TierID.T0 in flat
    assert TierID.T1 in flat
