"""Unit tests for E2ERunner extracted experiment action private methods.

Tests each _action_exp_* method directly, without invoking the full state machine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scylla.e2e.models import (
    ExperimentConfig,
    ExperimentResult,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.runner import E2ERunner


@pytest.fixture
def runner(tmp_path: Path) -> E2ERunner:
    """Create an E2ERunner with a minimal ExperimentConfig for unit testing."""
    config = ExperimentConfig(
        experiment_id="test",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=tmp_path / "prompt.md",
        language="python",
        tiers_to_run=[TierID.T0],
    )
    return E2ERunner(config, tmp_path / "tiers", tmp_path)


def _make_tier_result(tier_id: TierID) -> TierResult:
    """Create a minimal TierResult for testing."""
    return TierResult(
        tier_id=tier_id,
        subtest_results={},
        token_stats=TokenStats(),
    )


class TestActionExpInitializing:
    """Tests for _action_exp_initializing — no-op action."""

    def test_is_noop(self, runner: E2ERunner) -> None:
        """Calling _action_exp_initializing raises nothing and does nothing."""
        runner._action_exp_initializing()  # should not raise


class TestActionExpDirCreated:
    """Tests for _action_exp_dir_created — workspace setup and baseline capture."""

    def test_calls_setup_and_baseline(self, runner: E2ERunner) -> None:
        """Calls _setup_workspace and _capture_experiment_baseline."""
        with (
            patch.object(runner, "_setup_workspace") as mock_setup,
            patch.object(runner, "_capture_experiment_baseline") as mock_baseline,
        ):
            runner._action_exp_dir_created()

        mock_setup.assert_called_once()
        mock_baseline.assert_called_once()

    def test_setup_called_before_baseline(self, runner: E2ERunner) -> None:
        """_setup_workspace is invoked before _capture_experiment_baseline."""
        call_order: list[str] = []

        def fake_setup() -> None:
            call_order.append("setup")

        def fake_baseline() -> None:
            call_order.append("baseline")

        with (
            patch.object(runner, "_setup_workspace", side_effect=fake_setup),
            patch.object(runner, "_capture_experiment_baseline", side_effect=fake_baseline),
        ):
            runner._action_exp_dir_created()

        assert call_order == ["setup", "baseline"]


class TestActionExpRepoCloned:
    """Tests for _action_exp_repo_cloned — logs tier groups."""

    def test_logs_tier_groups(self, runner: E2ERunner) -> None:
        """_action_exp_repo_cloned emits an info log containing the tier groups."""
        tier_groups = [[TierID.T0], [TierID.T1]]

        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._action_exp_repo_cloned(tier_groups)

        mock_logger.info.assert_called_once()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "tier groups" in logged_msg.lower()

    def test_logs_correct_tier_groups(self, runner: E2ERunner) -> None:
        """The logged message includes the actual tier_groups value."""
        tier_groups = [[TierID.T0, TierID.T1]]

        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._action_exp_repo_cloned(tier_groups)

        logged_msg = mock_logger.info.call_args[0][0]
        assert str(tier_groups) in logged_msg


class TestActionExpTiersRunning:
    """Tests for _action_exp_tiers_running — executes tier groups."""

    def test_calls_execute_tier_groups(self, runner: E2ERunner) -> None:
        """_action_exp_tiers_running calls _execute_tier_groups with the given args."""
        tier_groups = [[TierID.T0]]
        tier_results: dict[TierID, TierResult] = {}

        with patch.object(runner, "_execute_tier_groups", return_value={}) as mock_exec:
            runner._action_exp_tiers_running(tier_groups, tier_results)

        mock_exec.assert_called_once_with(tier_groups)

    def test_updates_tier_results(self, runner: E2ERunner) -> None:
        """_action_exp_tiers_running merges execution results into tier_results."""
        tier_groups = [[TierID.T0]]
        tier_result = _make_tier_result(TierID.T0)
        tier_results: dict[TierID, TierResult] = {}

        with patch.object(runner, "_execute_tier_groups", return_value={TierID.T0: tier_result}):
            runner._action_exp_tiers_running(tier_groups, tier_results)

        assert TierID.T0 in tier_results
        assert tier_results[TierID.T0] is tier_result


class TestActionExpTiersComplete:
    """Tests for _action_exp_tiers_complete — aggregation, saving, and report generation."""

    def test_raises_when_experiment_dir_none(self, runner: E2ERunner) -> None:
        """_action_exp_tiers_complete raises RuntimeError when experiment_dir is None."""
        runner.experiment_dir = None
        start_time = datetime.now(timezone.utc)

        with pytest.raises(RuntimeError, match="experiment_dir must be set"):
            runner._action_exp_tiers_complete({}, start_time)

    def test_calls_aggregate_and_save(self, runner: E2ERunner, tmp_path: Path) -> None:
        """Calls _aggregate_results, _save_final_results, and _generate_report."""
        runner.experiment_dir = tmp_path
        tier_results = {TierID.T0: _make_tier_result(TierID.T0)}
        start_time = datetime.now(timezone.utc)
        mock_result = MagicMock(spec=ExperimentResult)

        with (
            patch.object(runner, "_aggregate_results", return_value=mock_result) as mock_agg,
            patch.object(runner, "_save_final_results") as mock_save,
            patch.object(runner, "_generate_report") as mock_report,
        ):
            runner._action_exp_tiers_complete(tier_results, start_time)

        mock_agg.assert_called_once_with(tier_results, start_time)
        mock_save.assert_called_once_with(mock_result)
        mock_report.assert_called_once_with(mock_result)

    def test_stores_last_result(self, runner: E2ERunner, tmp_path: Path) -> None:
        """_action_exp_tiers_complete stores the aggregated result in _last_experiment_result."""
        runner.experiment_dir = tmp_path
        start_time = datetime.now(timezone.utc)
        mock_result = MagicMock(spec=ExperimentResult)

        with (
            patch.object(runner, "_aggregate_results", return_value=mock_result),
            patch.object(runner, "_save_final_results"),
            patch.object(runner, "_generate_report"),
        ):
            runner._action_exp_tiers_complete({}, start_time)

        assert runner._last_experiment_result is mock_result


class TestActionExpReportsGenerated:
    """Tests for _action_exp_reports_generated — marks checkpoint complete and logs."""

    def test_calls_mark_checkpoint_completed(self, runner: E2ERunner) -> None:
        """_action_exp_reports_generated calls _mark_checkpoint_completed."""
        runner._last_experiment_result = None

        with patch.object(runner, "_mark_checkpoint_completed") as mock_mark:
            runner._action_exp_reports_generated()

        mock_mark.assert_called_once()

    def test_logs_when_result_exists(self, runner: E2ERunner) -> None:
        """Emits a completion log when _last_experiment_result is set."""
        mock_result = MagicMock(spec=ExperimentResult)
        mock_result.total_duration_seconds = 42.5
        mock_result.total_cost = 1.23
        runner._last_experiment_result = mock_result

        with (
            patch.object(runner, "_mark_checkpoint_completed"),
            patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger,
        ):
            runner._action_exp_reports_generated()

        mock_logger.info.assert_called_once()
        logged_msg = mock_logger.info.call_args[0][0]
        assert "42.5" in logged_msg
        assert "1.23" in logged_msg

    def test_no_log_when_result_is_none(self, runner: E2ERunner) -> None:
        """_action_exp_reports_generated does not log when _last_experiment_result is None."""
        runner._last_experiment_result = None

        with (
            patch.object(runner, "_mark_checkpoint_completed"),
            patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger,
        ):
            runner._action_exp_reports_generated()

        mock_logger.info.assert_not_called()


class TestBuildExperimentActions:
    """Tests for _build_experiment_actions — verifies thin builder delegates to private methods."""

    def test_returns_all_six_states(self, runner: E2ERunner) -> None:
        """_build_experiment_actions returns a dict with all six ExperimentState keys."""
        from scylla.e2e.models import ExperimentState

        start_time = datetime.now(timezone.utc)
        actions = runner._build_experiment_actions(
            tier_groups=[[TierID.T0]],
            tier_results={},
            start_time=start_time,
        )

        expected_states = {
            ExperimentState.INITIALIZING,
            ExperimentState.DIR_CREATED,
            ExperimentState.REPO_CLONED,
            ExperimentState.TIERS_RUNNING,
            ExperimentState.TIERS_COMPLETE,
            ExperimentState.REPORTS_GENERATED,
        }
        assert set(actions.keys()) == expected_states

    def test_all_values_are_callable(self, runner: E2ERunner) -> None:
        """Each value in the action dict is callable."""
        start_time = datetime.now(timezone.utc)
        actions = runner._build_experiment_actions(
            tier_groups=[[TierID.T0]],
            tier_results={},
            start_time=start_time,
        )

        for state, action in actions.items():
            assert callable(action), f"Action for {state} is not callable"

    def test_dir_created_calls_setup_and_baseline(self, runner: E2ERunner) -> None:
        """The DIR_CREATED action calls setup and baseline capture."""
        from scylla.e2e.models import ExperimentState

        start_time = datetime.now(timezone.utc)
        tier_results: dict[TierID, TierResult] = {}

        actions = runner._build_experiment_actions(
            tier_groups=[[TierID.T0]],
            tier_results=tier_results,
            start_time=start_time,
        )

        with (
            patch.object(runner, "_setup_workspace") as mock_setup,
            patch.object(runner, "_capture_experiment_baseline") as mock_baseline,
        ):
            actions[ExperimentState.DIR_CREATED]()
            mock_setup.assert_called_once()
            mock_baseline.assert_called_once()
