"""Tests for judge rerun functionality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scylla.e2e.agent_runner import _has_valid_agent_result
from scylla.e2e.models import ExperimentConfig, SubTestConfig, TierConfig, TierID
from scylla.e2e.rerun_judges import (
    JudgeSlotStatus,
    JudgeSlotToRerun,
    RerunJudgeStats,
    _classify_judge_slots,
    _is_valid_judgment,
    _regenerate_consensus,
    scan_judges_needing_rerun,
)
from scylla.e2e.tier_manager import TierManager


def test_is_valid_judgment_missing_file(tmp_path: Path) -> None:
    """Test _is_valid_judgment with missing file."""
    judgment_file = tmp_path / "judgment.json"
    assert not _is_valid_judgment(judgment_file)


def test_is_valid_judgment_with_score_and_valid_true(tmp_path: Path) -> None:
    """Test _is_valid_judgment with score and is_valid=True."""
    judgment_file = tmp_path / "judgment.json"
    judgment_file.write_text(
        json.dumps(
            {
                "score": 0.8,
                "passed": True,
                "grade": "B",
                "reasoning": "Good work",
                "is_valid": True,
            }
        )
    )
    assert _is_valid_judgment(judgment_file)


def test_is_valid_judgment_with_score_and_valid_false(tmp_path: Path) -> None:
    """Test _is_valid_judgment with score but is_valid=False."""
    judgment_file = tmp_path / "judgment.json"
    judgment_file.write_text(
        json.dumps(
            {
                "score": 0.0,
                "passed": False,
                "grade": "F",
                "reasoning": "Heuristic fallback",
                "is_valid": False,
            }
        )
    )
    assert not _is_valid_judgment(judgment_file)


def test_is_valid_judgment_backward_compat_no_is_valid_field(tmp_path: Path) -> None:
    """Test _is_valid_judgment with score but no is_valid field (backward compat)."""
    judgment_file = tmp_path / "judgment.json"
    judgment_file.write_text(
        json.dumps(
            {
                "score": 0.9,
                "passed": True,
                "grade": "A",
                "reasoning": "Excellent",
            }
        )
    )
    # Should return True when is_valid is missing (backward compatibility)
    assert _is_valid_judgment(judgment_file)


def test_is_valid_judgment_no_score(tmp_path: Path) -> None:
    """Test _is_valid_judgment with no score field."""
    judgment_file = tmp_path / "judgment.json"
    judgment_file.write_text(json.dumps({"reasoning": "No score"}))
    assert not _is_valid_judgment(judgment_file)


def test_is_valid_judgment_invalid_json(tmp_path: Path) -> None:
    """Test _is_valid_judgment with invalid JSON."""
    judgment_file = tmp_path / "judgment.json"
    judgment_file.write_text("not valid json {")
    assert not _is_valid_judgment(judgment_file)


def test_regenerate_consensus_all_valid_judges(tmp_path: Path) -> None:
    """Test _regenerate_consensus with all valid judges."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Create two valid judge results
    for i in range(1, 3):
        judge_subdir = judge_dir / f"judge_{i:02d}"
        judge_subdir.mkdir(parents=True)
        judgment_file = judge_subdir / "judgment.json"
        judgment_file.write_text(
            json.dumps(
                {
                    "score": 0.8 + (i * 0.05),
                    "passed": True,
                    "grade": "B",
                    "reasoning": f"Judge {i} reasoning",
                    "is_valid": True,
                    "criteria_scores": {"accuracy": {"score": 0.9, "explanation": "Good"}},
                }
            )
        )

    models = ["claude-sonnet-4-6", "claude-opus-4-6"]
    assert _regenerate_consensus(run_dir, models)

    # Check that consensus was written with is_valid=True
    result_file = judge_dir / "result.json"
    assert result_file.exists()
    consensus = json.loads(result_file.read_text())
    assert "score" in consensus
    assert consensus["is_valid"] is True
    assert consensus["criteria_scores"] is not None
    # Average of 0.85 and 0.9
    assert abs(consensus["score"] - 0.875) < 0.001


def test_regenerate_consensus_with_invalid_judge(tmp_path: Path) -> None:
    """Test _regenerate_consensus with one invalid judge (heuristic fallback)."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Judge 1: valid
    judge_1_dir = judge_dir / "judge_01"
    judge_1_dir.mkdir(parents=True)
    (judge_1_dir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.9,
                "passed": True,
                "grade": "A",
                "reasoning": "Valid judgment",
                "is_valid": True,
                "criteria_scores": {"accuracy": {"score": 0.95, "explanation": "Great"}},
            }
        )
    )

    # Judge 2: invalid (heuristic fallback)
    judge_2_dir = judge_dir / "judge_02"
    judge_2_dir.mkdir(parents=True)
    (judge_2_dir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.0,
                "passed": False,
                "grade": "F",
                "reasoning": "Heuristic fallback: agent crashed",
                "is_valid": False,
            }
        )
    )

    models = ["claude-sonnet-4-6", "claude-haiku-4-5"]
    assert _regenerate_consensus(run_dir, models)

    # Check consensus - should only use valid judge for score but mark consensus as invalid
    result_file = judge_dir / "result.json"
    consensus = json.loads(result_file.read_text())
    assert consensus["score"] == 0.9  # Only from valid judge
    assert consensus["is_valid"] is False  # One judge was invalid
    # Should use reasoning from closest judge (only valid judge with score 0.9)
    assert consensus["reasoning"] == "Valid judgment"
    assert consensus["criteria_scores"]["accuracy"]["score"] == 0.95


def test_regenerate_consensus_all_invalid_judges(tmp_path: Path) -> None:
    """Test _regenerate_consensus when all judges are invalid."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Both judges invalid
    for i in range(1, 3):
        judge_subdir = judge_dir / f"judge_{i:02d}"
        judge_subdir.mkdir(parents=True)
        (judge_subdir / "judgment.json").write_text(
            json.dumps(
                {
                    "score": 0.0,
                    "passed": False,
                    "grade": "F",
                    "reasoning": f"Heuristic fallback {i}",
                    "is_valid": False,
                }
            )
        )

    models = ["claude-haiku-4-5", "claude-haiku-4-5"]
    # Should return False when all judges are invalid
    assert not _regenerate_consensus(run_dir, models)


def test_regenerate_consensus_no_judges(tmp_path: Path) -> None:
    """Test _regenerate_consensus with no judge results."""
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()

    models = ["claude-sonnet-4-6"]
    assert not _regenerate_consensus(run_dir, models)


def test_regenerate_consensus_backward_compat_no_is_valid(tmp_path: Path) -> None:
    """Test _regenerate_consensus with old judgments missing is_valid field."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Create judge result without is_valid field (old format)
    judge_subdir = judge_dir / "judge_01"
    judge_subdir.mkdir(parents=True)
    (judge_subdir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.75,
                "passed": True,
                "grade": "C",
                "reasoning": "Old format judgment",
            }
        )
    )

    models = ["claude-sonnet-4-6"]
    assert _regenerate_consensus(run_dir, models)

    # Should treat missing is_valid as True
    result_file = judge_dir / "result.json"
    consensus = json.loads(result_file.read_text())
    assert consensus["score"] == 0.75
    assert consensus["is_valid"] is True  # Defaults to True


def test_regenerate_consensus_representative_reasoning(tmp_path: Path) -> None:
    """Test _regenerate_consensus picks reasoning from judge closest to consensus."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Judge 1: score=0.5
    judge_1_dir = judge_dir / "judge_01"
    judge_1_dir.mkdir(parents=True)
    (judge_1_dir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.5,
                "passed": False,
                "grade": "F",
                "reasoning": "Agent failed completely",
                "is_valid": True,
            }
        )
    )

    # Judge 2: score=0.85 (closest to consensus of 0.675)
    judge_2_dir = judge_dir / "judge_02"
    judge_2_dir.mkdir(parents=True)
    (judge_2_dir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.85,
                "passed": True,
                "grade": "B",
                "reasoning": "Agent mostly succeeded",
                "is_valid": True,
                "criteria_scores": {"accuracy": {"score": 0.9, "explanation": "Good"}},
            }
        )
    )

    models = ["claude-sonnet-4-6", "claude-opus-4-6"]
    assert _regenerate_consensus(run_dir, models)

    # Check consensus - should use judge 2's reasoning (closer to 0.675 consensus)
    result_file = judge_dir / "result.json"
    consensus = json.loads(result_file.read_text())
    assert abs(consensus["score"] - 0.675) < 0.001  # Average of 0.5 and 0.85
    assert consensus["reasoning"] == "Agent mostly succeeded"
    assert consensus["criteria_scores"]["accuracy"]["score"] == 0.9


def test_regenerate_consensus_writes_criteria_scores_to_run_result_json(
    tmp_path: Path,
) -> None:
    """Test that _regenerate_consensus updates criteria_scores in run_result.json."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Create a valid judge result with criteria_scores
    judge_subdir = judge_dir / "judge_01"
    judge_subdir.mkdir(parents=True)
    (judge_subdir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.8,
                "passed": True,
                "grade": "B",
                "reasoning": "Good work",
                "is_valid": True,
                "criteria_scores": {"accuracy": {"score": 0.9, "explanation": "Accurate"}},
            }
        )
    )

    # Create a run_result.json WITHOUT criteria_scores (simulating stale data)
    run_result_file = run_dir / "run_result.json"
    run_result_file.write_text(
        json.dumps(
            {
                "run_number": 1,
                "judge_score": 0.0,
                "judge_passed": False,
                "judge_grade": "F",
                "judge_reasoning": "old",
            }
        )
    )

    models = ["claude-sonnet-4-6"]
    assert _regenerate_consensus(run_dir, models)

    # Verify run_result.json was updated with criteria_scores
    run_data = json.loads(run_result_file.read_text())
    assert "criteria_scores" in run_data
    assert run_data["criteria_scores"] == {"accuracy": {"score": 0.9, "explanation": "Accurate"}}
    assert run_data["judge_score"] == 0.8


def test_regenerate_consensus_writes_empty_criteria_scores_when_null(
    tmp_path: Path,
) -> None:
    """Test _regenerate_consensus writes {} to run_result.json when criteria_scores is null."""
    run_dir = tmp_path / "run_01"
    judge_dir = run_dir / "judge"

    # Create a valid judge result WITHOUT criteria_scores (null)
    judge_subdir = judge_dir / "judge_01"
    judge_subdir.mkdir(parents=True)
    (judge_subdir / "judgment.json").write_text(
        json.dumps(
            {
                "score": 0.7,
                "passed": True,
                "grade": "C",
                "reasoning": "Adequate",
                "is_valid": True,
                "criteria_scores": None,
            }
        )
    )

    run_result_file = run_dir / "run_result.json"
    run_result_file.write_text(json.dumps({"run_number": 1, "judge_score": 0.0}))

    models = ["claude-sonnet-4-6"]
    assert _regenerate_consensus(run_dir, models)

    run_data = json.loads(run_result_file.read_text())
    # Should write {} not null
    assert run_data["criteria_scores"] == {}


class TestHasValidAgentResult:
    """Tests for _has_valid_agent_result() (canonical version from agent_runner)."""

    def test_valid_agent_result(self, tmp_path: Path) -> None:
        """Test with valid agent result."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        assert _has_valid_agent_result(run_dir)

    def test_missing_result_json(self, tmp_path: Path) -> None:
        """Test with missing result.json."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        (agent_dir / "output.txt").write_text("Agent output")

        assert not _has_valid_agent_result(run_dir)

    def test_missing_agent_dir(self, tmp_path: Path) -> None:
        """Test with missing agent directory."""
        run_dir = tmp_path / "run_01"
        run_dir.mkdir()

        assert not _has_valid_agent_result(run_dir)


class TestClassifyJudgeSlots:
    """Tests for _classify_judge_slots()."""

    def test_all_complete(self, tmp_path: Path) -> None:
        """Test classification when all judge slots are complete."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        # Valid agent result
        (agent_dir / "output.txt").write_text("Agent output")
        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        # Create valid judge results
        judge_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
        for i, _model in enumerate(judge_models, start=1):
            judge_dir = run_dir / "judge" / f"judge_{i:02d}"
            judge_dir.mkdir(parents=True)
            (judge_dir / "judgment.json").write_text(
                json.dumps(
                    {
                        "score": 0.8,
                        "passed": True,
                        "grade": "B",
                        "reasoning": "Good",
                        "is_valid": True,
                    }
                )
            )

        results = _classify_judge_slots(run_dir, judge_models)

        assert len(results) == 2
        assert all(status == JudgeSlotStatus.COMPLETE for _, _, status in results)

    def test_missing_judge_slots(self, tmp_path: Path) -> None:
        """Test classification when judge slots are missing."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        # Valid agent result
        (agent_dir / "output.txt").write_text("Agent output")
        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        judge_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
        results = _classify_judge_slots(run_dir, judge_models)

        assert len(results) == 2
        assert all(status == JudgeSlotStatus.MISSING for _, _, status in results)

    def test_failed_judge_slots(self, tmp_path: Path) -> None:
        """Test classification when judge slots failed."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        # Valid agent result
        (agent_dir / "output.txt").write_text("Agent output")
        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        # Create judge directories without valid judgment.json
        judge_models = ["claude-opus-4-6"]
        judge_dir = run_dir / "judge" / "judge_01"
        judge_dir.mkdir(parents=True)
        (judge_dir / "judgment.json").write_text(json.dumps({"score": 0.0, "is_valid": False}))

        results = _classify_judge_slots(run_dir, judge_models)

        assert len(results) == 1
        assert results[0][2] == JudgeSlotStatus.FAILED

    def test_agent_failed(self, tmp_path: Path) -> None:
        """Test classification when agent failed."""
        run_dir = tmp_path / "run_01"
        run_dir.mkdir()

        judge_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
        results = _classify_judge_slots(run_dir, judge_models)

        assert len(results) == 2
        assert all(status == JudgeSlotStatus.AGENT_FAILED for _, _, status in results)

    def test_mixed_statuses(self, tmp_path: Path) -> None:
        """Test classification with mixed judge slot statuses."""
        run_dir = tmp_path / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)

        # Valid agent result
        (agent_dir / "output.txt").write_text("Agent output")
        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        judge_models = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"]

        # Judge 1: Complete
        judge_1_dir = run_dir / "judge" / "judge_01"
        judge_1_dir.mkdir(parents=True)
        (judge_1_dir / "judgment.json").write_text(json.dumps({"score": 0.8, "is_valid": True}))

        # Judge 2: Missing (no directory)

        # Judge 3: Failed (invalid judgment)
        judge_3_dir = run_dir / "judge" / "judge_03"
        judge_3_dir.mkdir(parents=True)
        (judge_3_dir / "judgment.json").write_text("invalid json")

        results = _classify_judge_slots(run_dir, judge_models)

        assert len(results) == 3
        assert results[0][2] == JudgeSlotStatus.COMPLETE
        assert results[1][2] == JudgeSlotStatus.MISSING
        assert results[2][2] == JudgeSlotStatus.FAILED


class TestScanJudgesNeedingRerun:
    """Tests for scan_judges_needing_rerun()."""

    @pytest.fixture
    def experiment_setup(self, tmp_path: Path) -> tuple[Path, ExperimentConfig, TierManager]:
        """Create a minimal experiment setup for testing."""
        # Create experiment directory structure
        experiment_dir = tmp_path / "experiment"
        experiment_dir.mkdir()

        # Create tier directory
        tier_dir = experiment_dir / "T0"
        subtest_dir = tier_dir / "00"
        subtest_dir.mkdir(parents=True)

        # Create run directory with valid agent
        run_dir = subtest_dir / "run_01"
        agent_dir = run_dir / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "output.txt").write_text("Agent output")
        (agent_dir / "result.json").write_text(
            '{"exit_code": 0, "token_stats": {"input_tokens": 100}, "cost_usd": 0.01}'
        )

        # Create config
        config = ExperimentConfig(
            experiment_id="test-scan",
            task_repo="https://github.com/test/repo",
            task_commit="abc123",
            task_prompt_file=Path("/tmp/prompt.md"),
            language="python",
            models=["claude-sonnet-4-6"],
            runs_per_subtest=1,
            tiers_to_run=[TierID.T0],
            judge_models=["claude-opus-4-6", "claude-sonnet-4-6"],
            timeout_seconds=300,
        )

        # Create tier manager
        tiers_dir = tmp_path / "tiers"
        tiers_dir.mkdir()
        tier_manager = TierManager(tiers_dir)

        return experiment_dir, config, tier_manager

    def test_scan_finds_missing_judges(
        self, experiment_setup: tuple[Path, ExperimentConfig, TierManager]
    ) -> None:
        """Test scanning finds missing judge slots."""
        experiment_dir, config, tier_manager = experiment_setup

        with patch.object(tier_manager, "load_tier_config") as mock_load:
            mock_load.return_value = TierConfig(
                tier_id=TierID.T0,
                subtests=[SubTestConfig(id="00", name="Test", description="Test", resources={})],
            )

            stats = RerunJudgeStats()
            slots_by_status = scan_judges_needing_rerun(
                experiment_dir=experiment_dir,
                config=config,
                tier_manager=tier_manager,
                stats=stats,
            )

            # Should find missing judge slots
            assert len(slots_by_status[JudgeSlotStatus.MISSING]) == 2
            assert stats.missing == 2
            assert stats.total_expected_slots == 2

    def test_scan_with_tier_filter(
        self, experiment_setup: tuple[Path, ExperimentConfig, TierManager]
    ) -> None:
        """Test scanning with tier filter."""
        experiment_dir, config, tier_manager = experiment_setup

        with patch.object(tier_manager, "load_tier_config") as mock_load:
            mock_load.return_value = TierConfig(
                tier_id=TierID.T0,
                subtests=[SubTestConfig(id="00", name="Test", description="Test", resources={})],
            )

            # Filter to non-existent tier
            stats = RerunJudgeStats()
            scan_judges_needing_rerun(
                experiment_dir=experiment_dir,
                config=config,
                tier_manager=tier_manager,
                tier_filter=["T1"],
                stats=stats,
            )

            # Should find nothing
            assert stats.total_expected_slots == 0

    def test_scan_with_status_filter(
        self, experiment_setup: tuple[Path, ExperimentConfig, TierManager]
    ) -> None:
        """Test scanning with status filter."""
        experiment_dir, config, tier_manager = experiment_setup

        with patch.object(tier_manager, "load_tier_config") as mock_load:
            mock_load.return_value = TierConfig(
                tier_id=TierID.T0,
                subtests=[SubTestConfig(id="00", name="Test", description="Test", resources={})],
            )

            # Filter to only COMPLETE status
            stats = RerunJudgeStats()
            slots_by_status = scan_judges_needing_rerun(
                experiment_dir=experiment_dir,
                config=config,
                tier_manager=tier_manager,
                status_filter=[JudgeSlotStatus.COMPLETE],
                stats=stats,
            )

            # Should find slots but not include them in results (filtered)
            assert len(slots_by_status[JudgeSlotStatus.COMPLETE]) == 0
            assert stats.total_expected_slots == 2

    def test_scan_with_run_filter(
        self, experiment_setup: tuple[Path, ExperimentConfig, TierManager]
    ) -> None:
        """Test scanning with run filter."""
        experiment_dir, config, tier_manager = experiment_setup

        with patch.object(tier_manager, "load_tier_config") as mock_load:
            mock_load.return_value = TierConfig(
                tier_id=TierID.T0,
                subtests=[SubTestConfig(id="00", name="Test", description="Test", resources={})],
            )

            # Filter to run 2 (doesn't exist)
            stats = RerunJudgeStats()
            scan_judges_needing_rerun(
                experiment_dir=experiment_dir,
                config=config,
                tier_manager=tier_manager,
                run_filter=[2],
                stats=stats,
            )

            # Should skip all runs
            assert stats.total_expected_slots == 0
            assert stats.runs_skipped_by_filter == 1


class TestRerunJudgeStats:
    """Tests for RerunJudgeStats dataclass."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        stats = RerunJudgeStats()
        assert stats.total_expected_slots == 0
        assert stats.complete == 0
        assert stats.missing == 0
        assert stats.failed == 0
        assert stats.agent_failed == 0
        assert stats.per_slot_stats == {}

    def test_print_summary(self, caplog: Any) -> None:
        """Test print_summary logs the expected output."""
        import logging

        stats = RerunJudgeStats(
            total_expected_slots=10,
            complete=5,
            missing=3,
            failed=2,
            slots_rerun_success=4,
            slots_rerun_failed=1,
            consensus_regenerated=3,
        )
        stats.per_slot_stats = {
            1: {"complete": 3, "missing": 2, "failed": 0},
            2: {"complete": 2, "missing": 1, "failed": 2},
        }

        judge_models = ["claude-opus-4-6", "claude-sonnet-4-6"]
        with caplog.at_level(logging.INFO, logger="scylla.e2e.rerun_judges"):
            stats.print_summary(judge_models)

        log_text = "\n".join(caplog.messages)
        assert "Total expected judge slots: 10" in log_text
        assert "Judge slots rerun successfully:  4" in log_text
        assert "Consensus regenerated (runs):    3" in log_text


class TestJudgeSlotToRerun:
    """Tests for JudgeSlotToRerun dataclass."""

    def test_initialization(self) -> None:
        """Test JudgeSlotToRerun initialization."""
        run_dir = Path("/tmp/run_01")
        slot = JudgeSlotToRerun(
            tier_id="T0",
            subtest_id="00",
            run_number=1,
            run_dir=run_dir,
            judge_number=1,
            judge_model="claude-opus-4-6",
            status=JudgeSlotStatus.MISSING,
            reason="Never ran",
        )

        assert slot.tier_id == "T0"
        assert slot.subtest_id == "00"
        assert slot.run_number == 1
        assert slot.run_dir == run_dir
        assert slot.judge_number == 1
        assert slot.judge_model == "claude-opus-4-6"
        assert slot.status == JudgeSlotStatus.MISSING
        assert slot.reason == "Never ran"


class TestJudgeSlotStatus:
    """Tests for JudgeSlotStatus enum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert JudgeSlotStatus.COMPLETE.value == "complete"
        assert JudgeSlotStatus.MISSING.value == "missing"
        assert JudgeSlotStatus.FAILED.value == "failed"
        assert JudgeSlotStatus.AGENT_FAILED.value == "agent_failed"

    def test_enum_membership(self) -> None:
        """Test enum membership."""
        assert JudgeSlotStatus.COMPLETE in JudgeSlotStatus
        assert JudgeSlotStatus.MISSING in JudgeSlotStatus
        assert JudgeSlotStatus.FAILED in JudgeSlotStatus
        assert JudgeSlotStatus.AGENT_FAILED in JudgeSlotStatus
