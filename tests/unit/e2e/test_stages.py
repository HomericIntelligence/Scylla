"""Unit tests for scylla/e2e/stages.py.

Tests cover:
- RunContext construction
- build_actions_dict completeness (all RunState keys present)
- Individual stage functions with mocks (smoke tests)
- Heavy stage functions with real filesystem I/O
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scylla.e2e.models import (
    ExperimentConfig,
    RunState,
    SubTestConfig,
    TierConfig,
    TierID,
)
from scylla.e2e.stages import (
    RunContext,
    build_actions_dict,
    stage_apply_symlinks,
    stage_build_judge_prompt,
    stage_capture_baseline,
    stage_capture_diff,
    stage_cleanup_worktree,
    stage_commit_config,
    stage_create_dir_structure,
    stage_create_worktree,
    stage_execute_agent,
    stage_execute_judge,
    stage_finalize_run,
    stage_generate_replay,
    stage_run_judge_pipeline,
    stage_write_prompt,
    stage_write_report,
)
from scylla.e2e.state_machine import TRANSITION_REGISTRY


@pytest.fixture
def minimal_config() -> ExperimentConfig:
    """Minimal ExperimentConfig for stage tests."""
    return ExperimentConfig(
        experiment_id="test-stages",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=Path("/tmp/prompt.md"),
        language="python",
        models=["claude-sonnet-4-6"],
        runs_per_subtest=1,
        judge_models=["claude-opus-4-6"],
        timeout_seconds=60,
    )


@pytest.fixture
def minimal_subtest() -> SubTestConfig:
    """Minimal SubTestConfig for stage tests."""
    return SubTestConfig(
        id="00-empty",
        name="Empty",
        description="Empty subtest",
    )


@pytest.fixture
def minimal_tier_config(minimal_subtest: SubTestConfig) -> TierConfig:
    """Minimal TierConfig for stage tests."""
    return TierConfig(
        tier_id=TierID.T0,
        subtests=[minimal_subtest],
    )


@pytest.fixture
def run_context(
    tmp_path: Path,
    minimal_config: ExperimentConfig,
    minimal_subtest: SubTestConfig,
    minimal_tier_config: TierConfig,
) -> RunContext:
    """RunContext with mocked managers for stage testing."""
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()
    workspace = run_dir / "workspace"
    workspace.mkdir()

    tier_manager = MagicMock()
    workspace_manager = MagicMock()
    workspace_manager.base_repo = tmp_path / "repo"
    adapter = MagicMock()

    return RunContext(
        config=minimal_config,
        tier_id=TierID.T0,
        tier_config=minimal_tier_config,
        subtest=minimal_subtest,
        baseline=None,
        run_number=1,
        run_dir=run_dir,
        workspace=workspace,
        experiment_dir=tmp_path,
        tier_manager=tier_manager,
        workspace_manager=workspace_manager,
        adapter=adapter,
        task_prompt="Fix the bug",
    )


class TestRunContextConstruction:
    """Tests for RunContext dataclass construction."""

    def test_construction_with_required_fields(self, run_context: RunContext) -> None:
        """RunContext constructs with all required fields."""
        assert run_context.config.experiment_id == "test-stages"
        assert run_context.tier_id == TierID.T0
        assert run_context.run_number == 1
        assert run_context.task_prompt == "Fix the bug"

    def test_mutable_defaults(self, run_context: RunContext) -> None:
        """Mutable fields start as None/empty/False."""
        assert run_context.agent_result is None
        assert run_context.agent_duration == 0.0
        assert run_context.agent_ran is False
        assert run_context.diff_result is None
        assert run_context.judge_pipeline_result is None
        assert run_context.judge_prompt == ""
        assert run_context.judgment is None
        assert run_context.judges == []
        assert run_context.judge_duration == 0.0
        assert run_context.run_result is None

    def test_pipeline_baseline_defaults_to_none(self, run_context: RunContext) -> None:
        """pipeline_baseline defaults to None."""
        assert run_context.pipeline_baseline is None

    def test_coordinator_defaults_to_none(self, run_context: RunContext) -> None:
        """Coordinator defaults to None."""
        assert run_context.coordinator is None

    def test_checkpoint_defaults_to_none(self, run_context: RunContext) -> None:
        """Checkpoint defaults to None."""
        assert run_context.checkpoint is None


class TestBuildActionsDict:
    """Tests for build_actions_dict() factory function."""

    def test_returns_all_non_terminal_states(self, run_context: RunContext) -> None:
        """build_actions_dict contains entries for all non-terminal from_states.

        REPORT_WRITTEN is intentionally omitted — the StateMachine auto-saves
        the checkpoint after each transition, so no explicit action is needed.
        """
        from scylla.e2e.models import RunState

        actions = build_actions_dict(run_context)
        # Every transition in the registry should have a corresponding action,
        # except REPORT_WRITTEN which is handled by the StateMachine itself.
        expected_states = {t.from_state for t in TRANSITION_REGISTRY} - {RunState.REPORT_WRITTEN}
        assert set(actions.keys()) == expected_states

    def test_all_values_are_callable(self, run_context: RunContext) -> None:
        """Every action in the dict is callable."""
        actions = build_actions_dict(run_context)
        for state, action in actions.items():
            assert callable(action), f"Action for {state} is not callable"

    def test_pending_state_present(self, run_context: RunContext) -> None:
        """RunState.PENDING has an action entry."""
        actions = build_actions_dict(run_context)
        assert RunState.PENDING in actions

    def test_all_sequential_states_except_report_written_present(
        self, run_context: RunContext
    ) -> None:
        """Sequential RunStates have action entries; REPORT_WRITTEN is intentionally omitted.

        REPORT_WRITTEN is a no-op — the StateMachine auto-saves the checkpoint
        after each transition, so no explicit stage function is needed.
        """
        actions = build_actions_dict(run_context)
        sequential_states = [
            RunState.PENDING,
            RunState.DIR_STRUCTURE_CREATED,
            RunState.WORKTREE_CREATED,
            RunState.SYMLINKS_APPLIED,
            RunState.CONFIG_COMMITTED,
            RunState.BASELINE_CAPTURED,
            RunState.PROMPT_WRITTEN,
            RunState.REPLAY_GENERATED,
            RunState.AGENT_COMPLETE,
            RunState.DIFF_CAPTURED,
            RunState.JUDGE_PIPELINE_RUN,
            RunState.JUDGE_PROMPT_BUILT,
            RunState.JUDGE_COMPLETE,
            RunState.RUN_FINALIZED,
            RunState.CHECKPOINTED,
        ]
        for state in sequential_states:
            assert state in actions, f"Missing action for state {state}"
        # REPORT_WRITTEN is intentionally not in the actions dict
        assert RunState.REPORT_WRITTEN not in actions

    def test_action_count_matches_transition_registry(self, run_context: RunContext) -> None:
        """Number of actions matches number of TRANSITION_REGISTRY entries minus REPORT_WRITTEN.

        REPORT_WRITTEN is intentionally omitted from the actions dict since
        the StateMachine auto-saves the checkpoint after each transition.
        """
        actions = build_actions_dict(run_context)
        assert len(actions) == len(TRANSITION_REGISTRY) - 1


class TestStageCleanupWorktree:
    """Tests for stage_cleanup_worktree() — cleans up passed runs."""

    def test_completes_without_error_for_failed_run(self, run_context: RunContext) -> None:
        """stage_cleanup_worktree runs without error for failed runs (no-op)."""
        stage_cleanup_worktree(run_context)
        # No mutation expected for failed/unresolved runs
        assert run_context.run_result is None

    def test_cleans_up_workspace_for_passed_run(self, run_context: RunContext) -> None:
        """stage_cleanup_worktree calls workspace_manager.cleanup_worktree for passed runs."""
        from scylla.e2e.models import E2ERunResult

        # Set up a passed run_result
        mock_result = MagicMock(spec=E2ERunResult)
        mock_result.judge_passed = True
        run_context.run_result = mock_result

        stage_cleanup_worktree(run_context)

        run_context.workspace_manager.cleanup_worktree.assert_called_once_with(  # type: ignore[attr-defined]
            run_context.workspace
        )

    def test_cleans_up_failed_run_by_default(self, run_context: RunContext) -> None:
        """stage_cleanup_worktree cleans up failed runs by default (eager cleanup)."""
        from scylla.e2e.models import E2ERunResult

        mock_result = MagicMock(spec=E2ERunResult)
        mock_result.judge_passed = False
        run_context.run_result = mock_result

        stage_cleanup_worktree(run_context)

        run_context.workspace_manager.cleanup_worktree.assert_called_once()  # type: ignore[attr-defined]

    def test_skips_cleanup_for_failed_run_with_keep_flag(self, run_context: RunContext) -> None:
        """stage_cleanup_worktree skips failed runs when keep_failed_workspaces=True."""
        from scylla.e2e.models import E2ERunResult

        mock_result = MagicMock(spec=E2ERunResult)
        mock_result.judge_passed = False
        run_context.run_result = mock_result
        run_context.config.keep_failed_workspaces = True

        stage_cleanup_worktree(run_context)

        run_context.workspace_manager.cleanup_worktree.assert_not_called()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Heavy stage tests with real filesystem I/O
# ---------------------------------------------------------------------------


@pytest.fixture
def stage_config(tmp_path: Path) -> ExperimentConfig:
    """ExperimentConfig with a real prompt file on disk."""
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Fix the bug in the code")
    return ExperimentConfig(
        experiment_id="test-stages-heavy",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=prompt_file,
        language="python",
        models=["claude-sonnet-4-6"],
        runs_per_subtest=1,
        judge_models=["claude-opus-4-6"],
        timeout_seconds=60,
    )


@pytest.fixture
def stage_subtest() -> SubTestConfig:
    """Minimal SubTestConfig for heavy stage tests."""
    return SubTestConfig(
        id="00-empty",
        name="Empty",
        description="Empty subtest",
    )


@pytest.fixture
def stage_context(
    tmp_path: Path,
    stage_config: ExperimentConfig,
    stage_subtest: SubTestConfig,
) -> RunContext:
    """RunContext with mocked managers, real directories, and real prompt."""
    # Set up experiment dir with prompt.md
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    (experiment_dir / "prompt.md").write_text("Fix the bug in the code")

    # Subtest dir / run dirs
    subtest_dir = tmp_path / "T0" / "00-empty"
    run_dir = subtest_dir / "run_01"
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    workspace.mkdir()

    tier_config = TierConfig(tier_id=TierID.T0, subtests=[stage_subtest])
    tier_manager = MagicMock()
    workspace_manager = MagicMock()
    workspace_manager.base_repo = tmp_path / "repo"
    adapter = MagicMock()
    adapter._build_command.return_value = ["claude", "--model", "claude-sonnet-4-6"]

    return RunContext(
        config=stage_config,
        tier_id=TierID.T0,
        tier_config=tier_config,
        subtest=stage_subtest,
        baseline=None,
        run_number=1,
        run_dir=run_dir,
        workspace=workspace,
        experiment_dir=experiment_dir,
        tier_manager=tier_manager,
        workspace_manager=workspace_manager,
        adapter=adapter,
        task_prompt="Fix the bug in the code",
    )


class TestStageCreateDirStructure:
    """Tests for stage_create_dir_structure()."""

    def test_creates_run_workspace_agent_judge_dirs(self, stage_context: RunContext) -> None:
        """stage_create_dir_structure creates run_dir, workspace, agent/, and judge/."""
        stage_create_dir_structure(stage_context)
        assert stage_context.run_dir.exists()
        assert stage_context.workspace.exists()
        assert (stage_context.run_dir / "agent").exists()
        assert (stage_context.run_dir / "judge").exists()

    def test_idempotent_if_dirs_already_exist(self, stage_context: RunContext) -> None:
        """stage_create_dir_structure is idempotent — safe to call twice."""
        stage_create_dir_structure(stage_context)
        stage_create_dir_structure(stage_context)  # Should not raise
        assert stage_context.run_dir.exists()


class TestStageCreateWorktree:
    """Tests for stage_create_worktree()."""

    def test_calls_setup_workspace(self, stage_context: RunContext) -> None:
        """stage_create_worktree calls _setup_workspace."""
        # Ensure dirs exist (normally done by stage_create_dir_structure)
        stage_context.run_dir.mkdir(parents=True, exist_ok=True)
        stage_context.workspace.mkdir(parents=True, exist_ok=True)

        with patch("scylla.e2e.workspace_setup._setup_workspace") as mock_setup:
            stage_create_worktree(stage_context)
        mock_setup.assert_called_once()

    def test_skips_setup_if_already_passed(self, stage_context: RunContext) -> None:
        """If checkpoint says run passed, workspace is preserved without re-setup."""
        checkpoint = MagicMock()
        checkpoint.get_run_status.return_value = "passed"
        stage_context.checkpoint = checkpoint

        with patch("scylla.e2e.workspace_setup._setup_workspace") as mock_setup:
            stage_create_worktree(stage_context)

        mock_setup.assert_not_called()

    def test_calls_setup_if_not_passed(self, stage_context: RunContext) -> None:
        """If run status is not passed, _setup_workspace is called."""
        checkpoint = MagicMock()
        checkpoint.get_run_status.return_value = None
        stage_context.checkpoint = checkpoint

        with patch("scylla.e2e.workspace_setup._setup_workspace") as mock_setup:
            stage_create_worktree(stage_context)

        mock_setup.assert_called_once()


class TestStageApplySymlinks:
    """Tests for stage_apply_symlinks()."""

    def test_calls_prepare_workspace(self, stage_context: RunContext) -> None:
        """stage_apply_symlinks calls prepare_workspace with correct args."""
        stage_apply_symlinks(stage_context)

        stage_context.tier_manager.prepare_workspace.assert_called_once_with(  # type: ignore[attr-defined]
            workspace=stage_context.workspace,
            tier_id=TierID.T0,
            subtest_id="00-empty",
            baseline=None,
            merged_resources=None,
            thinking_enabled=False,
        )

    def test_no_merged_resources_for_non_t5(self, stage_context: RunContext) -> None:
        """For non-T5 tiers, merged_resources is None."""
        stage_apply_symlinks(stage_context)

        call_kwargs = stage_context.tier_manager.prepare_workspace.call_args[1]  # type: ignore[attr-defined]
        assert call_kwargs["merged_resources"] is None


class TestStageCommitConfig:
    """Tests for stage_commit_config()."""

    def test_calls_commit_test_config(self, stage_context: RunContext) -> None:
        """stage_commit_config calls _commit_test_config with workspace."""
        with patch("scylla.e2e.workspace_setup._commit_test_config") as mock_commit:
            stage_commit_config(stage_context)

        mock_commit.assert_called_once_with(stage_context.workspace)


class TestStageCaptureBaseline:
    """Tests for stage_capture_baseline()."""

    def test_skips_if_pipeline_baseline_already_set(self, stage_context: RunContext) -> None:
        """If ctx.pipeline_baseline is already set, stage is a no-op."""
        existing = MagicMock()
        stage_context.pipeline_baseline = existing

        with patch("scylla.e2e.build_pipeline._run_build_pipeline") as mock_pipeline:
            stage_capture_baseline(stage_context)

        mock_pipeline.assert_not_called()
        assert stage_context.pipeline_baseline is existing

    def test_loads_from_experiment_dir_if_available(self, stage_context: RunContext) -> None:
        """Load pipeline baseline from experiment dir without re-running pipeline.

        Checks that if pipeline_baseline.json exists at experiment level, it is loaded
        instead of running the pipeline again.
        """
        from scylla.e2e.llm_judge_models import BuildPipelineResult

        # experiment_dir is the preferred location for the baseline
        assert stage_context.experiment_dir is not None
        stage_context.experiment_dir.mkdir(parents=True, exist_ok=True)

        baseline_data = BuildPipelineResult(
            language="python",
            build_passed=True,
            build_output="",
            format_passed=True,
            test_passed=True,
            all_passed=True,
        )
        (stage_context.experiment_dir / "pipeline_baseline.json").write_text(
            json.dumps(baseline_data.model_dump())
        )

        with patch("scylla.e2e.build_pipeline._run_build_pipeline") as mock_pipeline:
            stage_capture_baseline(stage_context)

        mock_pipeline.assert_not_called()
        assert stage_context.pipeline_baseline is not None
        assert stage_context.pipeline_baseline.all_passed is True

    def test_loads_from_subtest_dir_as_backward_compat(self, stage_context: RunContext) -> None:
        """If no experiment-level baseline but subtest-level exists, loads it (backward compat)."""
        from scylla.e2e.llm_judge_models import BuildPipelineResult

        # Ensure experiment_dir has NO baseline (simulate old checkpoint)
        assert stage_context.experiment_dir is not None
        stage_context.experiment_dir.mkdir(parents=True, exist_ok=True)

        subtest_dir = stage_context.run_dir.parent
        subtest_dir.mkdir(parents=True, exist_ok=True)

        baseline_data = BuildPipelineResult(
            language="python",
            build_passed=True,
            build_output="",
            format_passed=True,
            test_passed=True,
            all_passed=True,
        )
        (subtest_dir / "pipeline_baseline.json").write_text(json.dumps(baseline_data.model_dump()))

        with patch("scylla.e2e.build_pipeline._run_build_pipeline") as mock_pipeline:
            stage_capture_baseline(stage_context)

        mock_pipeline.assert_not_called()
        assert stage_context.pipeline_baseline is not None
        assert stage_context.pipeline_baseline.all_passed is True

    def test_runs_pipeline_and_saves_if_not_cached(self, stage_context: RunContext) -> None:
        """If no cached baseline anywhere, runs pipeline and saves to subtest dir."""
        from scylla.e2e.llm_judge_models import BuildPipelineResult

        mock_result = BuildPipelineResult(
            language="python",
            build_passed=True,
            build_output="",
            format_passed=False,
            test_passed=False,
            all_passed=False,
        )
        # Ensure both experiment_dir and subtest_dir exist but have no baseline
        assert stage_context.experiment_dir is not None
        stage_context.experiment_dir.mkdir(parents=True, exist_ok=True)
        subtest_dir = stage_context.run_dir.parent
        subtest_dir.mkdir(parents=True, exist_ok=True)

        with patch("scylla.e2e.build_pipeline._run_build_pipeline", return_value=mock_result):
            stage_capture_baseline(stage_context)

        assert stage_context.pipeline_baseline is mock_result
        # Saved to subtest dir when running inline
        saved_path = subtest_dir / "pipeline_baseline.json"
        assert saved_path.exists()
        saved_data = json.loads(saved_path.read_text())
        assert saved_data["all_passed"] is False


class TestStageWritePrompt:
    """Tests for stage_write_prompt()."""

    def test_writes_task_prompt_file(self, stage_context: RunContext) -> None:
        """stage_write_prompt writes task_prompt.md to run_dir."""
        stage_write_prompt(stage_context)

        prompt_file = stage_context.run_dir / "task_prompt.md"
        assert prompt_file.exists() or prompt_file.is_symlink()

    def test_links_to_experiment_prompt(self, stage_context: RunContext) -> None:
        """When experiment_dir has prompt.md, task_prompt.md is a symlink."""
        stage_write_prompt(stage_context)

        prompt_file = stage_context.run_dir / "task_prompt.md"
        assert prompt_file.exists() or prompt_file.is_symlink()

    def test_writes_directly_if_no_experiment_prompt(self, stage_context: RunContext) -> None:
        """When no experiment prompt, writes task_prompt directly."""
        stage_context.experiment_dir = None

        stage_write_prompt(stage_context)

        prompt_file = stage_context.run_dir / "task_prompt.md"
        assert prompt_file.exists()
        assert prompt_file.read_text() == "Fix the bug in the code"


class TestStageGenerateReplay:
    """Tests for stage_generate_replay()."""

    def test_creates_replay_script(self, stage_context: RunContext) -> None:
        """stage_generate_replay generates replay.sh in agent/."""
        stage_create_dir_structure(stage_context)  # creates agent/ dir
        stage_write_prompt(stage_context)
        stage_generate_replay(stage_context)

        agent_dir = stage_context.run_dir / "agent"
        assert (agent_dir / "replay.sh").exists()

    def test_creates_agent_prompt_file(self, stage_context: RunContext) -> None:
        """stage_generate_replay writes prompt.md to agent/ dir."""
        stage_create_dir_structure(stage_context)  # creates agent/ dir
        stage_write_prompt(stage_context)
        stage_generate_replay(stage_context)

        agent_dir = stage_context.run_dir / "agent"
        assert (agent_dir / "prompt.md").exists()

    def test_loads_existing_agent_result_on_resume(self, stage_context: RunContext) -> None:
        """If valid agent result exists on disk, stage loads it instead of re-running."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        existing_result = AdapterResult(
            exit_code=0,
            stdout="done",
            stderr="",
            token_stats=AdapterTokenStats(input_tokens=10, output_tokens=5),
            cost_usd=0.01,
            api_calls=1,
        )

        stage_create_dir_structure(stage_context)  # creates agent/ dir
        stage_write_prompt(stage_context)

        with patch("scylla.e2e.agent_runner._has_valid_agent_result", return_value=True):
            with patch("scylla.e2e.agent_runner._load_agent_result", return_value=existing_result):
                stage_generate_replay(stage_context)

        assert stage_context.agent_result is existing_result
        assert stage_context.agent_ran is False

    def test_sets_adapter_config_on_ctx(self, stage_context: RunContext) -> None:
        """stage_generate_replay stores adapter_config on ctx for stage_execute_agent."""
        stage_create_dir_structure(stage_context)  # creates agent/ dir
        stage_write_prompt(stage_context)
        stage_generate_replay(stage_context)
        assert stage_context.adapter_config is not None


class TestStageExecuteAgent:
    """Tests for stage_execute_agent()."""

    def test_noop_if_agent_result_already_set(self, stage_context: RunContext) -> None:
        """If ctx.agent_result is set (resumed), execution is skipped."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="existing",
            stderr="",
            token_stats=AdapterTokenStats(),
            cost_usd=0.0,
            api_calls=0,
        )

        with patch("scylla.e2e.stages.subprocess.Popen") as mock_popen:
            stage_execute_agent(stage_context)

        mock_popen.assert_not_called()
        assert stage_context.agent_result.stdout == "existing"

    def test_runs_subprocess_and_saves_result(self, stage_context: RunContext) -> None:
        """stage_execute_agent runs replay.sh and saves agent result to disk."""
        from scylla.adapters.base import AdapterTokenStats

        # Must first run dir structure, write_prompt, then generate_replay to set up adapter_config
        stage_create_dir_structure(stage_context)
        stage_write_prompt(stage_context)
        stage_generate_replay(stage_context)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("Agent output here", "")
        mock_proc.returncode = 0
        mock_proc.pid = 12345

        stage_context.adapter._parse_token_stats.return_value = AdapterTokenStats(  # type: ignore[attr-defined]
            input_tokens=100, output_tokens=50
        )
        stage_context.adapter._parse_api_calls.return_value = 1  # type: ignore[attr-defined]
        stage_context.adapter._parse_cost.return_value = 0.05  # type: ignore[attr-defined]

        with patch("scylla.e2e.stages.subprocess.Popen", return_value=mock_proc):
            stage_execute_agent(stage_context)

        assert stage_context.agent_result is not None
        assert stage_context.agent_result.stdout == "Agent output here"
        assert stage_context.agent_ran is True
        assert stage_context.agent_duration > 0.0

        # Result saved to disk
        agent_dir = stage_context.run_dir / "agent"
        assert (agent_dir / "result.json").exists()
        assert (agent_dir / "output.txt").exists()
        assert (agent_dir / "timing.json").exists()


class TestStageCaptureDiff:
    """Tests for stage_capture_diff()."""

    def test_captures_diff_when_agent_ran(self, stage_context: RunContext) -> None:
        """stage_capture_diff captures workspace diff when agent ran fresh."""
        stage_context.agent_ran = True  # agent ran fresh, cannot skip judge

        with patch("scylla.e2e.llm_judge._get_workspace_state", return_value="some state"):
            with patch("scylla.e2e.llm_judge._get_patchfile", return_value="some diff"):
                with patch("scylla.e2e.llm_judge._get_deleted_files", return_value=[]):
                    stage_capture_diff(stage_context)

        assert stage_context.diff_result is not None
        assert stage_context.diff_result["workspace_state"] == "some state"
        assert stage_context.diff_result["patchfile"] == "some diff"

    def test_loads_judge_result_on_resume(self, stage_context: RunContext) -> None:
        """If agent not rerun and valid judge exists, loads judge result."""
        mock_judgment = {
            "score": 0.8,
            "passed": True,
            "grade": "B",
            "reasoning": "Good job",
        }

        stage_context.agent_ran = False

        with patch("scylla.e2e.judge_runner._has_valid_judge_result", return_value=True):
            with patch("scylla.e2e.judge_runner._load_judge_result", return_value=mock_judgment):
                stage_capture_diff(stage_context)

        assert stage_context.judgment == mock_judgment


class TestStageRunJudgePipeline:
    """Tests for stage_run_judge_pipeline()."""

    def test_noop_if_judgment_already_set(self, stage_context: RunContext) -> None:
        """If judgment already loaded (resume), pipeline is skipped."""
        stage_context.judgment = {"score": 0.9, "passed": True, "grade": "A", "reasoning": "ok"}

        with patch("scylla.e2e.build_pipeline._run_build_pipeline") as mock_pipeline:
            stage_run_judge_pipeline(stage_context)

        mock_pipeline.assert_not_called()

    def test_runs_pipeline_and_sets_result(self, stage_context: RunContext) -> None:
        """stage_run_judge_pipeline runs pipeline and stores result."""
        from scylla.e2e.llm_judge_models import BuildPipelineResult

        mock_result = BuildPipelineResult(
            language="python",
            build_passed=True,
            build_output="",
            format_passed=True,
            test_passed=True,
            all_passed=True,
        )
        stage_context.diff_result = {"workspace_state": "", "patchfile": "", "deleted_files": []}

        with patch("scylla.e2e.build_pipeline._run_build_pipeline", return_value=mock_result):
            with patch("scylla.e2e.pipeline_scripts._save_pipeline_commands"):
                with patch("scylla.e2e.pipeline_scripts._save_pipeline_outputs"):
                    stage_run_judge_pipeline(stage_context)

        assert stage_context.judge_pipeline_result is mock_result


class TestStageBuildJudgePrompt:
    """Tests for stage_build_judge_prompt()."""

    def test_noop_if_judgment_already_set(self, stage_context: RunContext) -> None:
        """If judgment already loaded (resume), prompt building is skipped."""
        stage_context.judgment = {"score": 0.9, "passed": True, "grade": "A", "reasoning": "ok"}

        with patch("scylla.judge.prompts.build_task_prompt") as mock_build:
            stage_build_judge_prompt(stage_context)

        mock_build.assert_not_called()

    def test_builds_prompt_and_saves(self, stage_context: RunContext) -> None:
        """stage_build_judge_prompt builds prompt and saves to disk."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.diff_result = {
            "workspace_state": "some files",
            "patchfile": "some diff",
            "deleted_files": [],
        }
        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="agent output",
            stderr="",
            token_stats=AdapterTokenStats(),
            cost_usd=0.0,
            api_calls=0,
        )

        with patch("scylla.judge.prompts.build_task_prompt", return_value="JUDGE PROMPT"):
            stage_build_judge_prompt(stage_context)

        assert stage_context.judge_prompt == "JUDGE PROMPT"
        assert (stage_context.run_dir / "judge_prompt.md").exists()


class TestStageExecuteJudge:
    """Tests for stage_execute_judge()."""

    def test_noop_if_judgment_already_set(self, stage_context: RunContext) -> None:
        """If ctx.judgment is set (resumed), judge execution is skipped."""
        stage_context.judgment = {"score": 0.9, "passed": True, "grade": "A", "reasoning": "ok"}

        with patch("scylla.e2e.llm_judge._call_claude_judge") as mock_judge:
            stage_execute_judge(stage_context)

        mock_judge.assert_not_called()

    def test_runs_judge_and_saves_result(self, stage_context: RunContext) -> None:
        """stage_execute_judge calls Claude judge and persists results to disk."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats
        from scylla.e2e.llm_judge_models import JudgeResult

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="Agent output",
            stderr="",
            token_stats=AdapterTokenStats(),
            cost_usd=0.01,
            api_calls=1,
        )
        stage_context.judge_prompt = "Judge this work"

        mock_judge_result = JudgeResult(
            score=0.8,
            passed=True,
            grade="B",
            reasoning="Good job",
            is_valid=True,
        )

        with patch(
            "scylla.e2e.llm_judge._call_claude_judge", return_value=("stdout", "stderr", "response")
        ):
            with patch(
                "scylla.e2e.llm_judge._parse_judge_response", return_value=mock_judge_result
            ):
                with patch("scylla.e2e.pipeline_scripts._save_judge_logs"):
                    with patch("scylla.e2e.judge_runner._save_judge_result"):
                        stage_execute_judge(stage_context)

        assert stage_context.judgment is not None
        assert stage_context.judgment["score"] == 0.8
        assert stage_context.judge_duration >= 0.0


class TestStageFinalizeRun:
    """Tests for stage_finalize_run()."""

    def _set_up_context_for_finalize(self, stage_context: RunContext) -> RunContext:
        """Set up a RunContext with agent_result and judgment for finalize_run."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="Agent output",
            stderr="",
            token_stats=AdapterTokenStats(
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=0,
                cache_creation_tokens=0,
            ),
            cost_usd=0.05,
            api_calls=1,
        )
        stage_context.agent_duration = 5.0
        stage_context.judgment = {
            "score": 0.9,
            "passed": True,
            "grade": "A",
            "reasoning": "Excellent work",
            "criteria_scores": {},
        }
        stage_context.judge_duration = 2.0
        return stage_context

    def test_builds_run_result_and_saves_json(self, stage_context: RunContext) -> None:
        """stage_finalize_run builds E2ERunResult and saves run_result.json."""
        ctx = self._set_up_context_for_finalize(stage_context)

        stage_finalize_run(ctx)

        assert ctx.run_result is not None
        assert ctx.run_result.judge_score == 0.9
        assert ctx.run_result.judge_passed is True
        assert ctx.run_result.judge_grade == "A"

        run_result_json = ctx.run_dir / "run_result.json"
        assert run_result_json.exists()
        data = json.loads(run_result_json.read_text())
        assert data["run_number"] == 1
        assert data["exit_code"] == 0

    def test_does_not_generate_report_files(self, stage_context: RunContext) -> None:
        """stage_finalize_run does NOT generate reports (moved to stage_write_report)."""
        ctx = self._set_up_context_for_finalize(stage_context)

        stage_finalize_run(ctx)

        # Reports are written by stage_write_report, not here
        assert not (ctx.run_dir / "report.md").exists()

    def test_raises_on_rate_limit(self, stage_context: RunContext) -> None:
        """stage_finalize_run raises RateLimitError if rate limit detected in output."""
        from scylla.e2e.rate_limit import RateLimitError, RateLimitInfo

        ctx = self._set_up_context_for_finalize(stage_context)
        rate_limit_info = RateLimitInfo(
            source="agent",
            retry_after_seconds=60,
            error_message="Rate limit exceeded",
            detected_at="2026-01-01T00:00:00Z",
        )

        with patch("scylla.e2e.rate_limit.detect_rate_limit", return_value=rate_limit_info):
            with pytest.raises(RateLimitError):
                stage_finalize_run(ctx)

    def test_pre_seeds_checkpoint_with_correct_status(self, stage_context: RunContext) -> None:
        """stage_finalize_run pre-seeds completed_runs with passed/failed status."""
        ctx = self._set_up_context_for_finalize(stage_context)

        checkpoint = MagicMock()
        ctx.checkpoint = checkpoint

        stage_finalize_run(ctx)

        checkpoint.mark_run_completed.assert_called_once_with("T0", "00-empty", 1, status="passed")

    def test_pre_seeds_failed_status_for_failed_run(self, stage_context: RunContext) -> None:
        """stage_finalize_run pre-seeds 'failed' status when judge_passed=False."""
        ctx = self._set_up_context_for_finalize(stage_context)
        ctx.judgment["passed"] = False  # type: ignore[index]
        ctx.judgment["score"] = 0.2  # type: ignore[index]
        ctx.judgment["grade"] = "F"  # type: ignore[index]

        checkpoint = MagicMock()
        ctx.checkpoint = checkpoint

        stage_finalize_run(ctx)

        checkpoint.mark_run_completed.assert_called_once_with("T0", "00-empty", 1, status="failed")


class TestStageExecuteAgentGuard:
    """Tests for stage_execute_agent resume behavior when adapter_config is None."""

    def test_reconstructs_adapter_config_when_none_on_resume(
        self, stage_context: RunContext
    ) -> None:
        """stage_execute_agent lazily reconstructs adapter_config on resume.

        When resuming a run already at replay_generated, stage_generate_replay
        is skipped so ctx.adapter_config is never set. The stage must reconstruct
        it from ctx.config rather than raising.
        """
        from unittest.mock import patch

        stage_context.adapter_config = None

        # Create the agent dir and replay.sh so the stage can proceed
        agent_dir = stage_context.run_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        replay_sh = agent_dir / "replay.sh"
        replay_sh.write_text("#!/bin/bash\necho done")

        with patch("subprocess.run") as mock_run:
            import subprocess

            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            with patch.object(
                stage_context.adapter, "_parse_token_stats", return_value=MagicMock()
            ):
                with patch.object(stage_context.adapter, "_parse_api_calls", return_value=0):
                    with patch.object(stage_context.adapter, "_parse_cost", return_value=0.0):
                        stage_execute_agent(stage_context)

        # adapter_config must have been reconstructed (not None)
        assert stage_context.adapter_config is not None


class TestStageFinalizeRunGuards:
    """Tests for RuntimeError guards in stage_finalize_run."""

    @pytest.mark.parametrize(
        "field,expected_match",
        [
            ("agent_result", r"agent_result"),
            ("judgment", r"judgment"),
        ],
    )
    def test_raises_when_field_is_none(
        self, stage_context: RunContext, field: str, expected_match: str
    ) -> None:
        """stage_finalize_run raises RuntimeError when the required field is None."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="output",
            stderr="",
            token_stats=AdapterTokenStats(),
            cost_usd=0.0,
            api_calls=0,
        )
        stage_context.judgment = {
            "score": 0.9,
            "passed": True,
            "grade": "A",
            "reasoning": "ok",
            "criteria_scores": {},
        }
        setattr(stage_context, field, None)

        with pytest.raises(RuntimeError, match=expected_match):
            stage_finalize_run(stage_context)


class TestStageWriteReport:
    """Tests for stage_write_report()."""

    def _set_up_context_for_write_report(self, stage_context: RunContext) -> RunContext:
        """Set up a RunContext with run_result for write_report."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="Agent output",
            stderr="",
            token_stats=AdapterTokenStats(
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=0,
                cache_creation_tokens=0,
            ),
            cost_usd=0.05,
            api_calls=1,
        )
        stage_context.agent_duration = 5.0
        stage_context.judgment = {
            "score": 0.9,
            "passed": True,
            "grade": "A",
            "reasoning": "Excellent work",
            "criteria_scores": {},
        }
        stage_context.judge_duration = 2.0

        # Build run_result via finalize_run
        stage_finalize_run(stage_context)
        return stage_context

    def test_generates_report_files(self, stage_context: RunContext) -> None:
        """stage_write_report generates report.md and report.json."""
        ctx = self._set_up_context_for_write_report(stage_context)

        stage_write_report(ctx)

        assert (ctx.run_dir / "report.md").exists()
        assert (ctx.run_dir / "report.json").exists()


class TestStageWriteReportGuards:
    """Tests for RuntimeError guards in stage_write_report."""

    @pytest.mark.parametrize(
        "field,expected_match",
        [
            ("run_result", r"run_result"),
            ("agent_result", r"agent_result"),
            ("judgment", r"judgment"),
        ],
    )
    def test_raises_when_field_is_none(
        self, stage_context: RunContext, field: str, expected_match: str
    ) -> None:
        """stage_write_report raises RuntimeError when the required field is None."""
        from scylla.adapters.base import AdapterResult, AdapterTokenStats

        stage_context.agent_result = AdapterResult(
            exit_code=0,
            stdout="output",
            stderr="",
            token_stats=AdapterTokenStats(),
            cost_usd=0.0,
            api_calls=0,
        )
        stage_context.judgment = {
            "score": 0.9,
            "passed": True,
            "grade": "A",
            "reasoning": "ok",
            "criteria_scores": {},
        }
        # Build a valid run_result via finalize_run
        stage_context.agent_duration = 1.0
        stage_context.judge_duration = 1.0
        stage_finalize_run(stage_context)

        setattr(stage_context, field, None)

        with pytest.raises(RuntimeError, match=expected_match):
            stage_write_report(stage_context)


# ---------------------------------------------------------------------------
# TestCommunicateWithShutdownCheck
# ---------------------------------------------------------------------------


class TestCommunicateWithShutdownCheck:
    """Tests for _communicate_with_shutdown_check shutdown behavior."""

    def test_raises_shutdown_interrupted_on_shutdown(self, stage_context: RunContext) -> None:
        """Raises ShutdownInterruptedError when shutdown is requested."""
        import subprocess

        from scylla.e2e.runner import ShutdownInterruptedError
        from scylla.e2e.stages import _communicate_with_shutdown_check

        # Create a mock Popen whose communicate() always times out
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired("cmd", 2.0)

        with (
            patch("scylla.e2e.shutdown.is_shutdown_requested", return_value=True),
            patch("scylla.e2e.stages._kill_process_group"),
            pytest.raises(ShutdownInterruptedError),
        ):
            _communicate_with_shutdown_check(mock_proc, timeout=10.0, ctx=stage_context)


# ---------------------------------------------------------------------------
# TestStageExecuteAgentStdinDevNull — AST regression guard
# ---------------------------------------------------------------------------


class TestStageExecuteAgentStdinDevNull:
    """AST regression guard: stage_execute_agent must use stdin=subprocess.DEVNULL."""

    def test_popen_uses_stdin_devnull(self) -> None:
        """stage_execute_agent source contains 'stdin=subprocess.DEVNULL'.

        This prevents the agent subprocess from inheriting stdin, which would
        cause the TTY to be shared and lead to signal delivery issues (SIGTSTP,
        SIGTTIN) that hang the parent process.
        """
        import inspect

        # stage_execute_agent is a thin tracing/metrics wrapper; the Popen call
        # lives in _stage_execute_agent_body. Inspect both to guard against drift.
        from scylla.e2e.stages import _stage_execute_agent_body

        source = inspect.getsource(stage_execute_agent) + inspect.getsource(
            _stage_execute_agent_body
        )
        assert "stdin=subprocess.DEVNULL" in source, (
            "stage_execute_agent must use stdin=subprocess.DEVNULL in Popen "
            "to prevent TTY sharing and signal delivery issues"
        )
