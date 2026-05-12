"""Unit tests for E2E runner token aggregation logic and state machine methods."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from scylla.e2e.experiment_result_writer import ExperimentResultWriter
from scylla.e2e.models import (
    ExperimentConfig,
    SubTestResult,
    TierBaseline,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.parallel_tier_runner import ParallelTierRunner
from scylla.e2e.runner import E2ERunner


@pytest.fixture
def mock_config() -> ExperimentConfig:
    """Create a mock ExperimentConfig for testing (no T5)."""
    return ExperimentConfig(
        experiment_id="test-exp",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=Path("/tmp/prompt.md"),
        language="python",
        tiers_to_run=[TierID.T0, TierID.T1],
    )


@pytest.fixture
def mock_tier_manager() -> MagicMock:
    """Create a mock TierManager for testing."""
    return MagicMock()


class TestTokenStatsAggregation:
    """Tests for aggregate_token_stats (now in ExperimentResultWriter)."""

    def _writer(self) -> ExperimentResultWriter:
        return ExperimentResultWriter(experiment_dir=None, tier_manager=MagicMock())

    def test_empty_tier_results(self) -> None:
        """Test aggregation with empty tier results."""
        result = self._writer().aggregate_token_stats({})

        assert isinstance(result, TokenStats)
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.cache_creation_tokens == 0
        assert result.cache_read_tokens == 0

    def test_single_tier_result(self) -> None:
        """Test aggregation with single tier."""
        tier_results = {
            TierID.T0: TierResult(
                tier_id=TierID.T0,
                subtest_results={},
                token_stats=TokenStats(
                    input_tokens=100,
                    output_tokens=50,
                    cache_creation_tokens=20,
                    cache_read_tokens=10,
                ),
            )
        }

        result = self._writer().aggregate_token_stats(tier_results)

        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_creation_tokens == 20
        assert result.cache_read_tokens == 10

    def test_multiple_tier_results(self) -> None:
        """Test aggregation with multiple tiers."""
        tier_results = {
            TierID.T0: TierResult(
                tier_id=TierID.T0,
                subtest_results={},
                token_stats=TokenStats(
                    input_tokens=100,
                    output_tokens=50,
                    cache_creation_tokens=20,
                    cache_read_tokens=10,
                ),
            ),
            TierID.T1: TierResult(
                tier_id=TierID.T1,
                subtest_results={},
                token_stats=TokenStats(
                    input_tokens=200,
                    output_tokens=75,
                    cache_creation_tokens=30,
                    cache_read_tokens=15,
                ),
            ),
            TierID.T2: TierResult(
                tier_id=TierID.T2,
                subtest_results={},
                token_stats=TokenStats(
                    input_tokens=150,
                    output_tokens=60,
                    cache_creation_tokens=25,
                    cache_read_tokens=12,
                ),
            ),
        }

        result = self._writer().aggregate_token_stats(tier_results)

        assert result.input_tokens == 450  # 100 + 200 + 150
        assert result.output_tokens == 185  # 50 + 75 + 60
        assert result.cache_creation_tokens == 75  # 20 + 30 + 25
        assert result.cache_read_tokens == 37  # 10 + 15 + 12

    def test_zero_token_stats(self) -> None:
        """Test aggregation with tiers that have zero tokens."""
        tier_results = {
            TierID.T0: TierResult(
                tier_id=TierID.T0,
                subtest_results={},
                token_stats=TokenStats(),  # All zeros
            ),
            TierID.T1: TierResult(
                tier_id=TierID.T1,
                subtest_results={},
                token_stats=TokenStats(
                    input_tokens=100,
                    output_tokens=50,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                ),
            ),
        }

        result = self._writer().aggregate_token_stats(tier_results)

        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.cache_creation_tokens == 0
        assert result.cache_read_tokens == 0


class TestLogCheckpointResume:
    """Tests for _log_checkpoint_resume helper method."""

    def test_logs_checkpoint_path(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Test that _log_checkpoint_resume logs the checkpoint path."""
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        runner.checkpoint = MagicMock()
        runner.checkpoint.get_completed_run_count.return_value = 5

        checkpoint_path = Path("/tmp/checkpoint.json")
        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._log_checkpoint_resume(checkpoint_path)

        mock_logger.info.assert_any_call(f"📂 Resuming from checkpoint: {checkpoint_path}")

    def test_logs_completed_run_count(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Test that _log_checkpoint_resume logs the completed run count."""
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        runner.checkpoint = MagicMock()
        runner.checkpoint.get_completed_run_count.return_value = 7

        checkpoint_path = Path("/tmp/checkpoint.json")
        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._log_checkpoint_resume(checkpoint_path)

        mock_logger.info.assert_any_call("   Previously completed: 7 runs")

    def test_logs_both_messages_in_order(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Test that both log messages are emitted in order."""
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        runner.checkpoint = MagicMock()
        runner.checkpoint.get_completed_run_count.return_value = 3

        checkpoint_path = Path("/tmp/exp/checkpoint.json")
        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._log_checkpoint_resume(checkpoint_path)

        assert mock_logger.info.call_count == 2
        mock_logger.info.assert_has_calls(
            [
                call(f"📂 Resuming from checkpoint: {checkpoint_path}"),
                call("   Previously completed: 3 runs"),
            ]
        )

    def test_load_checkpoint_success_path_calls_helper(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test that _load_checkpoint_and_config calls helper in success path."""
        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        # Set up a valid checkpoint and config directory
        exp_dir = tmp_path / "experiment"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "experiment.json"
        config_file.write_text(mock_config.model_dump_json())

        mock_checkpoint = MagicMock()
        mock_checkpoint.experiment_dir = str(exp_dir)
        mock_checkpoint.get_completed_run_count.return_value = 2

        checkpoint_path = tmp_path / "checkpoint.json"

        with (
            patch(
                "scylla.e2e.runner_internals.runner_core.load_checkpoint",
                return_value=mock_checkpoint,
            ),
            patch.object(runner, "_log_checkpoint_resume") as mock_log,
        ):
            runner._load_checkpoint_and_config(checkpoint_path)

        mock_log.assert_called_once_with(checkpoint_path)

    def test_load_checkpoint_fallback_path_calls_helper(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test that _load_checkpoint_and_config calls helper in fallback path."""
        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        # Experiment dir exists but config file does not
        exp_dir = tmp_path / "experiment"
        exp_dir.mkdir(parents=True)

        mock_checkpoint = MagicMock()
        mock_checkpoint.experiment_dir = str(exp_dir)
        mock_checkpoint.get_completed_run_count.return_value = 4

        checkpoint_path = tmp_path / "checkpoint.json"

        with (
            patch(
                "scylla.e2e.runner_internals.runner_core.load_checkpoint",
                return_value=mock_checkpoint,
            ),
            patch(
                "scylla.e2e.runner_internals.runner_core.validate_checkpoint_config",
                return_value=True,
            ),
            patch.object(runner, "_log_checkpoint_resume") as mock_log,
        ):
            runner._load_checkpoint_and_config(checkpoint_path)

        mock_log.assert_called_once_with(checkpoint_path)


@pytest.fixture
def mock_config_with_t5() -> ExperimentConfig:
    """Create a mock ExperimentConfig that includes TierID.T5."""
    return ExperimentConfig(
        experiment_id="test-exp-t5",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=Path("/tmp/prompt.md"),
        language="python",
        tiers_to_run=[TierID.T0, TierID.T1, TierID.T5],
    )


def _make_tier_result(
    tier_id: TierID,
    subtest_id: str,
    mean_cost: float,
    pass_rate: float,
) -> TierResult:
    """Build a TierResult with the given CoP parameters."""
    subtest = SubTestResult(
        subtest_id=subtest_id,
        tier_id=tier_id,
        runs=[],
        pass_rate=pass_rate,
        mean_cost=mean_cost,
    )
    return TierResult(
        tier_id=tier_id,
        subtest_results={subtest_id: subtest},
        best_subtest=subtest_id,
    )


class TestSelectBestBaselineFromGroup:
    """Tests for select_best_baseline_from_group (now in ParallelTierRunner)."""

    def _make_parallel_runner(
        self,
        config: ExperimentConfig,
        tier_manager: MagicMock,
        experiment_dir: Path,
    ) -> ParallelTierRunner:
        return ParallelTierRunner(
            config=config,
            tier_manager=tier_manager,
            experiment_dir=experiment_dir,
            run_tier_fn=MagicMock(),
            save_tier_result_fn=MagicMock(),
        )

    def test_returns_none_when_t5_not_in_config(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Returns None immediately when T5 is not in tiers_to_run."""
        runner = self._make_parallel_runner(mock_config, mock_tier_manager, Path("/tmp/exp"))
        tier_results = {
            TierID.T0: _make_tier_result(TierID.T0, "sub0", mean_cost=1.0, pass_rate=0.5),
            TierID.T1: _make_tier_result(TierID.T1, "sub1", mean_cost=2.0, pass_rate=0.5),
        }

        result = runner.select_best_baseline_from_group([TierID.T0, TierID.T1], tier_results)

        assert result is None
        mock_tier_manager.get_baseline_for_subtest.assert_not_called()

    def test_selects_tier_with_lowest_cop(
        self, mock_config_with_t5: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Selects the tier with the lowest cost-of-pass and returns its baseline."""
        exp_dir = Path("/tmp/exp")
        runner = self._make_parallel_runner(mock_config_with_t5, mock_tier_manager, exp_dir)
        # T0 CoP = 2.0 / 0.5 = 4.0, T1 CoP = 1.0 / 0.5 = 2.0 — T1 should win
        tier_results = {
            TierID.T0: _make_tier_result(TierID.T0, "sub0", mean_cost=2.0, pass_rate=0.5),
            TierID.T1: _make_tier_result(TierID.T1, "sub1", mean_cost=1.0, pass_rate=0.5),
        }
        mock_baseline = TierBaseline(
            tier_id=TierID.T1, subtest_id="sub1", claude_md_path=None, claude_dir_path=None
        )
        mock_tier_manager.get_baseline_for_subtest.return_value = mock_baseline

        result = runner.select_best_baseline_from_group([TierID.T0, TierID.T1], tier_results)

        assert result is mock_baseline
        mock_tier_manager.get_baseline_for_subtest.assert_called_once_with(
            tier_id=TierID.T1,
            subtest_id="sub1",
            results_dir=exp_dir / "completed" / TierID.T1.value / "sub1",
        )

    def test_returns_none_when_best_subtest_is_none(
        self, mock_config_with_t5: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """Returns None when the best tier has no best_subtest."""
        runner = self._make_parallel_runner(
            mock_config_with_t5, mock_tier_manager, Path("/tmp/exp")
        )
        tier_result = TierResult(
            tier_id=TierID.T0,
            subtest_results={},
            best_subtest=None,
        )

        result = runner.select_best_baseline_from_group([TierID.T0], {TierID.T0: tier_result})

        assert result is None
        mock_tier_manager.get_baseline_for_subtest.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_experiment_interrupt tests (Phase 5B)
# ---------------------------------------------------------------------------


class TestHandleExperimentInterrupt:
    """Tests for _handle_experiment_interrupt() — verifies both status and experiment_state."""

    def test_sets_status_to_interrupted(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """After interrupt, checkpoint.status is set to 'interrupted'."""
        from scylla.e2e.checkpoint import E2ECheckpoint, load_checkpoint, save_checkpoint

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        # Write a checkpoint file to disk
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="abc123",
            started_at="2024-01-01T00:00:00+00:00",
            last_updated_at="2024-01-01T00:00:00+00:00",
            status="running",
        )
        checkpoint_path = tmp_path / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        runner._handle_experiment_interrupt(checkpoint_path)

        updated = load_checkpoint(checkpoint_path)
        assert updated.status == "interrupted"

    def test_sets_experiment_state_to_interrupted(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """After interrupt, checkpoint.experiment_state is set to lowercase 'interrupted'.

        Regression: previously written as 'INTERRUPTED' (uppercase), which caused STEP 3
        in _initialize_or_resume_experiment to skip the state reset on resume (it only
        matched lowercase 'interrupted').
        """
        from scylla.e2e.checkpoint import E2ECheckpoint, load_checkpoint, save_checkpoint

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="abc123",
            started_at="2024-01-01T00:00:00+00:00",
            last_updated_at="2024-01-01T00:00:00+00:00",
            status="running",
            experiment_state="TIERS_RUNNING",  # Previously would remain stale
        )
        checkpoint_path = tmp_path / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        runner._handle_experiment_interrupt(checkpoint_path)

        updated = load_checkpoint(checkpoint_path)
        assert updated.experiment_state == "interrupted", (
            "experiment_state must be lowercase 'interrupted' so STEP 3 in "
            "_initialize_or_resume_experiment matches it and resets the state on resume."
        )

    def test_does_nothing_when_checkpoint_missing(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """_handle_experiment_interrupt is a no-op when checkpoint file doesn't exist."""
        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        # Should not raise even when checkpoint file is absent
        runner._handle_experiment_interrupt(tmp_path / "nonexistent.json")

    def test_does_nothing_when_checkpoint_path_is_none(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """_handle_experiment_interrupt is a no-op when checkpoint_path is None."""
        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        # Should not raise with None checkpoint_path
        runner._handle_experiment_interrupt(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _validate_filesystem_on_resume tests (Phase 5B)
# ---------------------------------------------------------------------------


class TestValidateFilesystemOnResume:
    """Tests for _validate_filesystem_on_resume() — warnings-only validation."""

    def test_no_warning_when_dirs_exist(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """No warning logged when experiment_dir and repos/ both exist."""
        from scylla.e2e.models import ExperimentState

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        runner.experiment_dir = tmp_path / "experiment"
        runner.experiment_dir.mkdir()
        (tmp_path / "repos").mkdir()

        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._validate_filesystem_on_resume(ExperimentState.TIERS_RUNNING)

        # No warnings should have been emitted
        for warning_call in mock_logger.warning.call_args_list:
            assert "Resuming from TIERS_RUNNING" not in str(warning_call)

    def test_warns_when_experiment_dir_missing(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Warning is logged when experiment_dir doesn't exist during TIERS_RUNNING."""
        from scylla.e2e.models import ExperimentState

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        runner.experiment_dir = tmp_path / "nonexistent_experiment"
        # Don't create it — should trigger warning

        with patch("scylla.e2e.checkpoint_finalizer.logger") as mock_logger:
            runner._validate_filesystem_on_resume(ExperimentState.TIERS_RUNNING)

        warning_messages = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("experiment_dir missing" in msg for msg in warning_messages)

    def test_noop_for_non_tiers_running_state(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """No validation is performed for states other than TIERS_RUNNING."""
        from scylla.e2e.models import ExperimentState

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        runner.experiment_dir = tmp_path / "nonexistent"  # Would cause warning in TIERS_RUNNING

        with patch("scylla.e2e.runner_internals.runner_core.logger") as mock_logger:
            runner._validate_filesystem_on_resume(ExperimentState.INITIALIZING)

        # No filesystem warnings for INITIALIZING state
        for warning_call in mock_logger.warning.call_args_list:
            assert "experiment_dir missing" not in str(warning_call)

    def test_noop_when_experiment_dir_is_none(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock, tmp_path: Path
    ) -> None:
        """No validation when experiment_dir is None/falsy."""
        from scylla.e2e.models import ExperimentState

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)
        runner.experiment_dir = None

        # Should not raise
        runner._validate_filesystem_on_resume(ExperimentState.TIERS_RUNNING)


# ---------------------------------------------------------------------------
# _last_experiment_result initialization tests (Phase 5B)
# ---------------------------------------------------------------------------


class TestLastExperimentResultInit:
    """Tests for _last_experiment_result field — declared in __init__."""

    def test_last_experiment_result_initialized_to_none(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """E2ERunner initializes _last_experiment_result to None in __init__."""
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        assert hasattr(runner, "_last_experiment_result")
        assert runner._last_experiment_result is None

    def test_no_type_ignore_comment_needed(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """_last_experiment_result declared in __init__ — no attr-defined needed.

        This is a code quality regression guard to ensure the attribute is properly
        declared in __init__ rather than dynamically set (which would require
        # type: ignore[attr-defined] suppression).
        """
        import inspect

        from scylla.e2e.runner import E2ERunner

        source = inspect.getsource(E2ERunner.__init__)
        assert "_last_experiment_result" in source, (
            "_last_experiment_result must be declared in E2ERunner.__init__() "
            "to avoid attr-defined type errors"
        )


class TestResumeTierConfigPreload:
    """Tests for the resume tier-config pre-load fix (dryrun3 Bug 2).

    When a tier resumes from a checkpoint at CONFIG_LOADED or later state,
    action_pending() is skipped.  _run_tier() must pre-populate tier_ctx with
    the loaded config/dir so that subsequent action_config_loaded() and
    action_subtests_complete() assertions do not fail.
    """

    def _make_runner(
        self,
        mock_config: ExperimentConfig,
        experiment_dir: Path,
    ) -> tuple[E2ERunner, MagicMock]:
        """Return (runner, mock_tier_manager) with runner.tier_manager already patched."""
        runner = E2ERunner(mock_config, experiment_dir, experiment_dir)
        runner.experiment_dir = experiment_dir
        mock_tm = MagicMock()
        mock_tier_config = MagicMock()
        mock_tier_config.subtests = []
        mock_tm.load_tier_config.return_value = mock_tier_config
        runner.tier_manager = mock_tm  # Replace real TierManager with mock
        return runner, mock_tm

    def test_tier_ctx_populated_when_resuming_from_config_loaded(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """tier_ctx.tier_config is set before actions run when resuming from CONFIG_LOADED."""
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint
        from scylla.e2e.tier_state_machine import TierStateMachine

        experiment_dir = tmp_path / "exp"
        experiment_dir.mkdir()
        runner, mock_tm = self._make_runner(mock_config, experiment_dir)

        # Build a checkpoint that says T0 is at CONFIG_LOADED
        checkpoint = E2ECheckpoint(
            experiment_id="resume-test",
            experiment_dir=str(experiment_dir),
            config_hash="abc",
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            tier_states={"T0": "config_loaded"},
        )
        runner.checkpoint = checkpoint

        def noop_complete(tier_id_str: str, actions: dict[str, Any], until_state: Any) -> None:
            pass

        with patch.object(TierStateMachine, "advance_to_completion", side_effect=noop_complete):
            with patch(
                "scylla.e2e.tier_action_builder.run_tier_subtests_parallel", return_value={}
            ):
                with contextlib.suppress(Exception):
                    runner._run_tier(TierID.T0, baseline=None)
                    # We only care that tier_manager.load_tier_config was called

        # load_tier_config must be called once for the pre-load (resume path)
        mock_tm.load_tier_config.assert_called_once_with(TierID.T0, mock_config.skip_agent_teams)

    def test_tier_ctx_not_preloaded_for_pending_state(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When tier is at PENDING, pre-load is skipped (action_pending handles it)."""
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint
        from scylla.e2e.tier_state_machine import TierStateMachine

        experiment_dir = tmp_path / "exp"
        experiment_dir.mkdir()
        runner, mock_tm = self._make_runner(mock_config, experiment_dir)

        # Checkpoint at PENDING state
        checkpoint = E2ECheckpoint(
            experiment_id="pending-test",
            experiment_dir=str(experiment_dir),
            config_hash="abc",
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            tier_states={"T0": "pending"},
        )
        runner.checkpoint = checkpoint

        def noop_complete(tier_id_str: str, actions: dict[str, Any], until_state: Any) -> None:
            pass

        with patch.object(TierStateMachine, "advance_to_completion", side_effect=noop_complete):
            with patch(
                "scylla.e2e.tier_action_builder.run_tier_subtests_parallel", return_value={}
            ):
                with contextlib.suppress(Exception):
                    runner._run_tier(TierID.T0, baseline=None)

        # load_tier_config should NOT have been called (pre-load skipped for PENDING)
        mock_tm.load_tier_config.assert_not_called()

    def test_tier_ctx_not_preloaded_for_complete_state(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """When tier is COMPLETE, pre-load is skipped (tier is already done)."""
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint
        from scylla.e2e.tier_state_machine import TierStateMachine

        experiment_dir = tmp_path / "exp"
        experiment_dir.mkdir()
        runner, mock_tm = self._make_runner(mock_config, experiment_dir)

        checkpoint = E2ECheckpoint(
            experiment_id="complete-test",
            experiment_dir=str(experiment_dir),
            config_hash="abc",
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
            tier_states={"T0": "complete"},
        )
        runner.checkpoint = checkpoint

        def noop_complete(tier_id_str: str, actions: dict[str, Any], until_state: Any) -> None:
            pass

        with patch.object(TierStateMachine, "advance_to_completion", side_effect=noop_complete):
            with patch(
                "scylla.e2e.tier_action_builder.run_tier_subtests_parallel", return_value={}
            ):
                with contextlib.suppress(Exception):
                    runner._run_tier(TierID.T0, baseline=None)

        mock_tm.load_tier_config.assert_not_called()


# ---------------------------------------------------------------------------
# _initialize_or_resume_experiment: FAILED/INTERRUPTED state reset tests
# ---------------------------------------------------------------------------


class TestInitializeOrResumeExperimentFailedReset:
    """Tests that _initialize_or_resume_experiment resets FAILED/INTERRUPTED experiments.

    When resuming a checkpoint with experiment_state='failed' or 'interrupted',
    the state machine would immediately exit because these are terminal states.
    The runner must reset them to 'tiers_running' before handing off to the ESM.
    """

    def _make_runner(
        self,
        mock_config: ExperimentConfig,
        tmp_path: Path,
    ) -> E2ERunner:
        """Return a fresh E2ERunner with no workspace manager."""
        return E2ERunner(mock_config, Path("/tmp/tiers"), tmp_path)

    def _run_resume(
        self,
        mock_config: ExperimentConfig,
        tmp_path: Path,
        checkpoint_state: str,
        tier_states: dict[str, str] | None = None,
        subtest_states: dict[str, dict[str, str]] | None = None,
    ) -> E2ERunner:
        """Create runner and run _initialize_or_resume_experiment with a pre-set checkpoint.

        Mocks _load_checkpoint_and_config to directly inject the checkpoint,
        bypassing config-hash validation and filesystem requirements.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, save_checkpoint

        runner = self._make_runner(mock_config, tmp_path)

        exp_dir = tmp_path / mock_config.experiment_id
        exp_dir.mkdir(parents=True)

        checkpoint = E2ECheckpoint(
            experiment_id=mock_config.experiment_id,
            experiment_dir=str(exp_dir),
            config_hash="abc123",
            experiment_state=checkpoint_state,
            tier_states=tier_states or {},
            subtest_states=subtest_states or {},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status=checkpoint_state,
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        def fake_load(path: Path) -> tuple[Any, Path]:
            runner.checkpoint = checkpoint
            runner.experiment_dir = exp_dir
            return checkpoint, exp_dir

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_load_checkpoint_and_config", side_effect=fake_load),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        return runner

    def test_resume_failed_experiment_resets_to_tiers_running(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """experiment_state='failed' is reset to 'tiers_running' on resume."""
        runner = self._run_resume(mock_config, tmp_path, checkpoint_state="failed")

        assert runner.checkpoint is not None
        assert runner.checkpoint.experiment_state == "tiers_running"

    def test_resume_failed_experiment_resets_failed_tier_states_to_pending(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed tier states are reset to 'pending' when experiment resumes from 'failed'."""
        runner = self._run_resume(
            mock_config,
            tmp_path,
            checkpoint_state="failed",
            tier_states={"T0": "failed", "T1": "complete", "T2": "failed"},
        )

        assert runner.checkpoint is not None
        # Failed tiers reset to pending
        assert runner.checkpoint.tier_states["T0"] == "pending"
        assert runner.checkpoint.tier_states["T2"] == "pending"
        # Complete tier is untouched
        assert runner.checkpoint.tier_states["T1"] == "complete"

    def test_resume_failed_experiment_resets_failed_subtest_states_to_pending(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Failed subtest states are reset to 'pending' when experiment resumes from 'failed'."""
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, save_checkpoint

        runner = self._make_runner(mock_config, tmp_path)

        exp_dir = tmp_path / mock_config.experiment_id
        exp_dir.mkdir(parents=True)

        # Provide run_states for subtest "01" so orphan detector doesn't reset it
        checkpoint = E2ECheckpoint(
            experiment_id=mock_config.experiment_id,
            experiment_dir=str(exp_dir),
            config_hash="abc123",
            experiment_state="failed",
            tier_states={},
            subtest_states={"T0": {"00": "failed", "01": "aggregated"}},
            run_states={"T0": {"01": {"1": "worktree_cleaned"}}},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="failed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        def fake_load(path: Path) -> tuple[Any, Path]:
            runner.checkpoint = checkpoint
            runner.experiment_dir = exp_dir
            return checkpoint, exp_dir

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_load_checkpoint_and_config", side_effect=fake_load),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        # Failed subtest reset to pending
        assert runner.checkpoint.subtest_states["T0"]["00"] == "pending"
        # Aggregated subtest with backing run_states is untouched
        assert runner.checkpoint.subtest_states["T0"]["01"] == "aggregated"

    def test_resume_interrupted_experiment_resets_to_tiers_running(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """experiment_state='interrupted' is also reset to 'tiers_running' on resume."""
        runner = self._run_resume(mock_config, tmp_path, checkpoint_state="interrupted")

        assert runner.checkpoint is not None
        assert runner.checkpoint.experiment_state == "tiers_running"

    def test_resume_complete_experiment_same_tiers_stays_complete(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """experiment_state='complete' stays 'complete' when no new/incomplete tiers are requested.

        mock_config has tiers_to_run=[T0, T1]. The checkpoint already has T0 and T1 in
        tier_states (complete) and no run_states → _check_tiers_need_execution returns an
        empty set, so the experiment state is left untouched.
        """
        runner = self._run_resume(
            mock_config,
            tmp_path,
            checkpoint_state="complete",
            tier_states={"T0": "complete", "T1": "complete"},
        )

        assert runner.checkpoint is not None
        # complete state is preserved — no new/incomplete tiers detected
        assert runner.checkpoint.experiment_state == "complete"

    def test_resume_failed_merges_cli_tiers_into_saved_config(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CLI tiers not in the saved experiment.json are merged in when resuming from 'failed'.

        Scenario: original run had tiers_to_run=[T0] (saved in experiment.json).
        New CLI command requests tiers_to_run=[T0, T1]. On resume, T1 must be
        added to self.config.tiers_to_run so it will execute in this run.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig

        # Build a CLI config with T0 + T1
        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0, TierID.T1],
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        # Saved experiment.json has ONLY T0
        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="failed",
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="failed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        assert runner.checkpoint.experiment_state == "tiers_running"
        # T1 must have been added to tiers_to_run
        tier_ids = {t.value for t in runner.config.tiers_to_run}
        assert "T0" in tier_ids
        assert "T1" in tier_ids

    def test_resume_complete_experiment_with_new_tiers_resets_to_tiers_running(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """experiment_state='complete' is reset to 'tiers_running' when new CLI tiers are added.

        Scenario: saved experiment.json has T0 only (complete). CLI requests T0+T1.
        T1 is new so _check_tiers_need_execution returns {"T1"}, which triggers a
        reset to 'tiers_running' and T1 is added to tiers_to_run.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig

        # CLI config requests T0 + T1
        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0, TierID.T1],
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        # Saved experiment.json has ONLY T0
        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="complete",
            tier_states={"T0": "complete"},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        # Experiment must be reset so T1 can execute
        assert runner.checkpoint.experiment_state == "tiers_running"
        tier_ids = {t.value for t in runner.config.tiers_to_run}
        assert "T0" in tier_ids
        assert "T1" in tier_ids

    def test_resume_preserves_ephemeral_cli_args(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CLI --until and --max-subtests survive the config reload from checkpoint.

        Scenario: saved experiment.json has no until_run_state. CLI passes
        until_run_state='replay_generated' and max_subtests=2.  After resume, the
        loaded config must reflect the CLI values, not the saved (None) values.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig, RunState

        # CLI config with ephemeral overrides
        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
            until_run_state=RunState.REPLAY_GENERATED,
            max_subtests=2,
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        # Saved config has no until_run_state or max_subtests
        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="tiers_running",
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        # CLI ephemeral values must survive the reload
        assert runner.config.until_run_state == RunState.REPLAY_GENERATED
        assert runner.config.max_subtests == 2

    def test_resume_complete_with_incomplete_runs_resets_for_reentry(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Tier/subtest/experiment states reset when runs are not in terminal state.

        Scenario: experiment is 'complete', T0 is 'complete', subtest 00 is
        'aggregated' — but run 1 is in 'replay_generated' (not terminal).
        Re-running with --tiers T0 must reset experiment→tiers_running,
        T0→config_loaded (so action_config_loaded re-runs the subtests),
        subtest 00→runs_in_progress.

        NOTE: tier resets to 'config_loaded', NOT 'subtests_running'.
        'subtests_running' is the "select best subtest" phase and expects
        run_tier_subtests_parallel() to have already produced results.
        Skipping config_loaded causes "No sub-test results to select from".
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig

        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        # Run 1 is mid-sequence (replay_generated is not a terminal state)
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="complete",
            tier_states={"T0": "complete"},
            subtest_states={"T0": {"00": "aggregated"}},
            run_states={"T0": {"00": {"1": "replay_generated"}}},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        assert runner.checkpoint.experiment_state == "tiers_running"
        # config_loaded so action_config_loaded() re-runs subtests before selection
        assert runner.checkpoint.tier_states["T0"] == "config_loaded"
        assert runner.checkpoint.subtest_states["T0"]["00"] == "runs_in_progress"

    def test_resume_complete_with_runs_complete_subtest_resets_to_runs_in_progress(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A 'runs_complete' subtest with incomplete runs is reset to 'runs_in_progress'.

        Defense-in-depth for the --until UntilHaltError bug: if a checkpoint somehow
        reaches 'runs_complete' while runs are still incomplete (pre-fix checkpoint),
        the runner must reset it to 'runs_in_progress' when re-entering from a terminal
        experiment state — just like it does for 'aggregated' subtests.

        Scenario: experiment is 'complete', T0 is 'complete', subtest 00 is
        'runs_complete' (incorrectly saved pre-fix) — but run 1 is in 'replay_generated'
        (not terminal). Re-running must reset subtest 00 to 'runs_in_progress'.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig

        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        # Experiment is 'complete', T0 is 'complete', but subtest 00 is 'runs_complete'
        # with run 1 still at 'replay_generated' (not terminal) — the pre-fix bug state.
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="complete",
            tier_states={"T0": "complete"},
            subtest_states={"T0": {"00": "runs_complete"}},
            run_states={"T0": {"00": {"1": "replay_generated"}}},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        # 'runs_complete' with incomplete runs must be reset to 'runs_in_progress'
        assert runner.checkpoint.subtest_states["T0"]["00"] == "runs_in_progress"


class TestLogCheckpointResumeGuard:
    """Tests for the RuntimeError guard in _log_checkpoint_resume."""

    def test_raises_when_checkpoint_is_none(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """_log_checkpoint_resume raises RuntimeError when self.checkpoint is None."""
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        runner.checkpoint = None

        with pytest.raises(RuntimeError, match=r"checkpoint"):
            runner._log_checkpoint_resume(Path("/tmp/checkpoint.json"))


class TestInitializeOrResumeExperimentGuard:
    """Tests for the RuntimeError guard in _initialize_or_resume_experiment."""

    def test_raises_when_experiment_dir_is_none_after_create(
        self, mock_config: ExperimentConfig, mock_tier_manager: MagicMock
    ) -> None:
        """_initialize_or_resume_experiment raises RuntimeError when experiment_dir stays None.

        The guard fires when _create_fresh_experiment is a no-op (patched) so
        self.experiment_dir remains None after the creation step.
        """
        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        # No existing checkpoint so it will try to create a fresh experiment.
        # Patch _create_fresh_experiment to be a no-op so experiment_dir stays None.
        with patch.object(runner, "_find_existing_checkpoint", return_value=None):
            with patch.object(runner, "_create_fresh_experiment"):
                with patch.object(runner, "_write_pid_file"):
                    with pytest.raises(RuntimeError, match=r"experiment_dir"):
                        runner._initialize_or_resume_experiment()


class TestInitializeOrResumeExperimentMaxSubtests:
    """Tests that _initialize_or_resume_experiment handles max_subtests correctly on resume."""

    def test_resume_clears_max_subtests_when_cli_provides_none(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CLI max_subtests=None clears a saved max_subtests value on resume.

        Scenario: first run used --max-subtests 2 (saved to checkpoint config).
        Second run omits --max-subtests (CLI provides None). After resume,
        config.max_subtests must be None (no limit), not the saved 2.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig

        # CLI config has no max_subtests (None)
        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
            max_subtests=None,
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        # Saved config has max_subtests=2
        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
            max_subtests=2,
        )
        saved_config.save(config_dir / "experiment.json")

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="tiers_running",
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        # max_subtests must be None (cleared by CLI None)
        assert runner.config.max_subtests is None, (
            "CLI max_subtests=None must override the saved max_subtests=2 on resume. "
            "Without this, a second run without --max-subtests would be capped at the "
            "saved value."
        )

    def test_resume_detects_missing_subtests_and_resets_tier_to_pending(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Tier resets to 'pending' when config has subtests absent from checkpoint.

        Scenario: first run used --max-subtests 2 → checkpoint has T0/00, T0/01.
        Second run omits --max-subtests → config has T0/00..T0/N-1.
        check_tiers_need_execution detects missing subtests, tier state resets
        from 'complete' to 'pending' so action_pending() reloads the full list.
        """
        from datetime import datetime, timezone

        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint
        from scylla.e2e.models import ExperimentConfig, SubTestConfig, TierConfig, TierID

        # CLI config has no max_subtests (None) — wants all subtests
        cli_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
            max_subtests=None,
        )
        runner = E2ERunner(cli_config, Path("/tmp/tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)

        saved_config = ExperimentConfig(
            experiment_id="test-exp",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=tmp_path / "prompt.md",
            language="python",
            tiers_to_run=[TierID.T0],
        )
        saved_config.save(config_dir / "experiment.json")

        # Checkpoint has only 2 subtests (simulating --max-subtests 2 was used)
        # Include run_states so orphan detector doesn't reset aggregated subtests
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(saved_config),
            experiment_state="complete",
            tier_states={"T0": "complete"},
            subtest_states={"T0": {"00": "aggregated", "01": "aggregated"}},
            run_states={"T0": {"00": {"1": "worktree_cleaned"}, "01": {"1": "worktree_cleaned"}}},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="completed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        # tier_manager returns 4 subtests (more than the 2 in checkpoint)
        full_tier_config = TierConfig(
            tier_id=TierID.T0,
            subtests=[
                SubTestConfig(id="00", name="Sub 00", description=""),
                SubTestConfig(id="01", name="Sub 01", description=""),
                SubTestConfig(id="02", name="Sub 02", description=""),
                SubTestConfig(id="03", name="Sub 03", description=""),
            ],
        )
        runner.tier_manager = MagicMock()
        runner.tier_manager.load_tier_config.return_value = full_tier_config

        with (
            patch.object(runner, "_find_existing_checkpoint", return_value=checkpoint_path),
            patch.object(runner, "_write_pid_file"),
            patch("scylla.e2e.resume_manager.is_zombie", return_value=False),
        ):
            runner._initialize_or_resume_experiment()

        assert runner.checkpoint is not None
        # Experiment must be reset so missing subtests can execute
        assert runner.checkpoint.experiment_state == "tiers_running"
        # T0 must be reset to 'pending' (not 'subtests_running') so action_pending()
        # reloads the full subtest list
        assert runner.checkpoint.tier_states.get("T0") == "pending", (
            "T0 must be reset to 'pending' when config subtests exceed checkpoint subtests, "
            "so that action_pending() re-runs with the full subtest list."
        )


# ---------------------------------------------------------------------------
# _build_experiment_actions guards
# ---------------------------------------------------------------------------


class TestBuildExperimentActionsGuards:
    """Tests for None-guard in action_tiers_complete closure inside _build_experiment_actions."""

    def test_action_tiers_complete_raises_when_experiment_dir_none(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
    ) -> None:
        """action_tiers_complete raises RuntimeError when experiment_dir is None."""
        from datetime import datetime, timezone

        from scylla.e2e.models import ExperimentState

        runner = E2ERunner(mock_config, mock_tier_manager, Path("/tmp"))
        runner.experiment_dir = None

        tier_results: dict[TierID, TierResult] = {}
        actions = runner._build_experiment_actions(
            tier_groups=[[TierID.T0]],
            tier_results=tier_results,
            start_time=datetime.now(timezone.utc),
        )

        with pytest.raises(
            RuntimeError, match="experiment_dir must be set before aggregating tier results"
        ):
            actions[ExperimentState.TIERS_COMPLETE]()


# ---------------------------------------------------------------------------
# run() inline checkpoint guards
# ---------------------------------------------------------------------------


class TestRunCheckpointGuards:
    """Tests for checkpoint None-guards inlined in E2ERunner.run().

    Two guards fire before the ExperimentStateMachine is built:
    1.  "checkpoint must be set before starting heartbeat thread"  (line ~688)
    2.  "checkpoint must be set before creating experiment state machine"  (line ~730)

    Guard 1 is triggered when _initialize_or_resume_experiment completes but
    leaves self.checkpoint as None.

    Guard 2 is triggered when self.checkpoint is None at the ESM-creation
    point; for this test we reset it to None after the heartbeat guard is
    passed by providing a real checkpoint initially and then clearing it just
    before ESM construction, using a patched HeartbeatThread whose start()
    side-effect nullifies the checkpoint.
    """

    def test_heartbeat_guard_raises_when_checkpoint_none(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run() raises RuntimeError when checkpoint is None at heartbeat creation."""
        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        # Patch _initialize_or_resume_experiment to return a path but NOT set checkpoint
        def fake_init() -> Path:
            # runner.checkpoint remains None
            return tmp_path / "checkpoint.json"

        with (
            patch.object(runner, "_initialize_or_resume_experiment", side_effect=fake_init),
            pytest.raises(
                RuntimeError,
                match="checkpoint must be set before starting heartbeat thread",
            ),
        ):
            runner.run()

    def test_esm_guard_raises_when_checkpoint_none_at_esm_creation(
        self,
        mock_config: ExperimentConfig,
        mock_tier_manager: MagicMock,
        tmp_path: Path,
    ) -> None:
        """run() raises RuntimeError when checkpoint is None at ESM creation.

        The heartbeat guard (earlier in run()) is bypassed by providing a
        non-None checkpoint initially; the HeartbeatThread.start side-effect
        then clears runner.checkpoint so the ESM guard fires.
        """
        from scylla.e2e.checkpoint import E2ECheckpoint

        runner = E2ERunner(mock_config, mock_tier_manager, tmp_path)

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="abc123",
            started_at="2024-01-01T00:00:00+00:00",
            last_updated_at="2024-01-01T00:00:00+00:00",
            status="running",
        )

        def fake_init() -> Path:
            runner.checkpoint = checkpoint
            return tmp_path / "checkpoint.json"

        mock_heartbeat = MagicMock()

        def clear_checkpoint_on_start() -> None:
            """Simulate checkpoint becoming None between heartbeat start and ESM creation."""
            runner.checkpoint = None

        mock_heartbeat.start.side_effect = clear_checkpoint_on_start

        with (
            patch.object(runner, "_initialize_or_resume_experiment", side_effect=fake_init),
            patch("scylla.e2e.health.HeartbeatThread", return_value=mock_heartbeat),
            pytest.raises(
                RuntimeError,
                match="checkpoint must be set before creating experiment state machine",
            ),
        ):
            runner.run()


# ---------------------------------------------------------------------------
# run() early-exit for already-complete experiments
# ---------------------------------------------------------------------------


class TestRunAlreadyCompleteEarlyExit:
    """Tests that run() exits immediately when the experiment is already complete."""

    def test_already_complete_skips_rehydrate(
        self,
        mock_config: ExperimentConfig,
        tmp_path: Path,
    ) -> None:
        """run() returns immediately without rehydrating when experiment is already complete."""
        from scylla.e2e.checkpoint import E2ECheckpoint, compute_config_hash, save_checkpoint

        runner = E2ERunner(mock_config, Path(tmp_path / "tiers"), tmp_path)

        exp_dir = tmp_path / "test-exp"
        config_dir = exp_dir / "config"
        config_dir.mkdir(parents=True)
        mock_config.save(config_dir / "experiment.json")

        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(exp_dir),
            config_hash=compute_config_hash(mock_config),
            experiment_state="complete",
            tier_states={"T0": "complete", "T1": "complete"},
            subtest_states={
                "T0": {"00": "aggregated"},
                "T1": {"00": "aggregated"},
            },
            run_states={
                "T0": {"00": {"1": "worktree_cleaned"}},
                "T1": {"00": {"1": "worktree_cleaned"}},
            },
            started_at="2024-01-01T00:00:00+00:00",
            last_updated_at="2024-01-01T00:00:00+00:00",
            status="completed",
        )
        checkpoint_path = exp_dir / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        def fake_init() -> Path:
            runner.checkpoint = checkpoint
            runner.experiment_dir = exp_dir
            return checkpoint_path

        mock_heartbeat = MagicMock()

        with (
            patch.object(runner, "_initialize_or_resume_experiment", side_effect=fake_init),
            patch("scylla.e2e.health.HeartbeatThread", return_value=mock_heartbeat),
            patch("scylla.persistence.rehydrate.load_experiment_tier_results") as mock_rehydrate,
        ):
            result = runner.run()

        assert result is not None
        mock_rehydrate.assert_not_called()
