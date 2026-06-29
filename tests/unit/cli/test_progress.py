"""Tests for scylla.cli.progress module."""

import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from unittest.mock import patch

from scylla.cli.progress import (
    EvalProgress,
    ProgressDisplay,
    RunProgress,
    RunStatus,
    TierProgress,
    format_duration,
    format_progress_bar,
)


class TestRunProgress:
    """Tests for RunProgress dataclass."""

    def test_create(self) -> None:
        """Test default construction."""
        run = RunProgress(run_number=1)
        assert run.run_number == 1
        assert run.status == RunStatus.PENDING

    def test_elapsed_not_started(self) -> None:
        """Elapsed returns zero when not started."""
        run = RunProgress(run_number=1)
        assert run.elapsed == timedelta(0)

    def test_elapsed_running(self) -> None:
        """Elapsed uses mocked datetime.now to avoid wall-clock flakiness."""
        fixed_now = datetime(2024, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
        fixed_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        run = RunProgress(
            run_number=1,
            status=RunStatus.EXECUTING,
            start_time=fixed_start,
        )
        with patch("scylla.core.progress.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            assert run.elapsed == timedelta(seconds=10)

    def test_elapsed_complete(self) -> None:
        """Elapsed returns start-to-end delta when complete."""
        start = datetime(2024, 1, 1, 12, 0, 0)
        end = datetime(2024, 1, 1, 12, 0, 20)
        run = RunProgress(
            run_number=1,
            status=RunStatus.COMPLETE,
            start_time=start,
            end_time=end,
        )
        assert run.elapsed == timedelta(seconds=20)


class TestTierProgress:
    """Tests for TierProgress dataclass."""

    def test_create(self) -> None:
        """Test default construction populates runs list."""
        tier = TierProgress(tier_id="T0", total_runs=10)
        assert tier.tier_id == "T0"
        assert tier.total_runs == 10
        assert len(tier.runs) == 10

    def test_completed_runs(self) -> None:
        """Completed runs counts only COMPLETE status."""
        tier = TierProgress(tier_id="T0", total_runs=5)
        tier.runs[0].status = RunStatus.COMPLETE
        tier.runs[1].status = RunStatus.COMPLETE
        tier.runs[2].status = RunStatus.EXECUTING

        assert tier.completed_runs == 2

    def test_passed_runs(self) -> None:
        """Passed runs counts only runs with passed=True."""
        tier = TierProgress(tier_id="T0", total_runs=5)
        tier.runs[0].status = RunStatus.COMPLETE
        tier.runs[0].passed = True
        tier.runs[1].status = RunStatus.COMPLETE
        tier.runs[1].passed = False
        tier.runs[2].status = RunStatus.COMPLETE
        tier.runs[2].passed = True

        assert tier.passed_runs == 2

    def test_pass_rate(self) -> None:
        """Pass rate is passed / completed."""
        tier = TierProgress(tier_id="T0", total_runs=4)
        for i in range(4):
            tier.runs[i].status = RunStatus.COMPLETE
        tier.runs[0].passed = True
        tier.runs[1].passed = False
        tier.runs[2].passed = True
        tier.runs[3].passed = True

        assert tier.pass_rate == 0.75

    def test_pass_rate_empty(self) -> None:
        """Pass rate is 0.0 when no runs are completed."""
        tier = TierProgress(tier_id="T0", total_runs=5)
        assert tier.pass_rate == 0.0

    def test_total_cost(self) -> None:
        """Total cost sums non-None cost_usd values."""
        tier = TierProgress(tier_id="T0", total_runs=3)
        tier.runs[0].cost_usd = 1.0
        tier.runs[1].cost_usd = 2.5
        tier.runs[2].cost_usd = None

        assert tier.total_cost == 3.5


class TestEvalProgress:
    """Tests for EvalProgress dataclass."""

    def test_create(self) -> None:
        """Test default construction."""
        progress = EvalProgress(test_id="001-test")
        assert progress.test_id == "001-test"
        assert progress.tiers == []

    def test_total_runs(self) -> None:
        """Total runs sums across tiers."""
        progress = EvalProgress(
            test_id="001-test",
            tiers=[
                TierProgress("T0", 10),
                TierProgress("T1", 10),
            ],
        )
        assert progress.total_runs == 20

    def test_completed_runs(self) -> None:
        """Completed runs sums across tiers."""
        progress = EvalProgress(
            test_id="001-test",
            tiers=[
                TierProgress("T0", 5),
                TierProgress("T1", 5),
            ],
        )
        progress.tiers[0].runs[0].status = RunStatus.COMPLETE
        progress.tiers[0].runs[1].status = RunStatus.COMPLETE
        progress.tiers[1].runs[0].status = RunStatus.COMPLETE

        assert progress.completed_runs == 3

    def test_completed_tiers(self) -> None:
        """Completed tiers counts only fully-completed tiers."""
        progress = EvalProgress(
            test_id="001-test",
            tiers=[
                TierProgress("T0", 2),
                TierProgress("T1", 2),
            ],
        )
        for run in progress.tiers[0].runs:
            run.status = RunStatus.COMPLETE
        progress.tiers[1].runs[0].status = RunStatus.COMPLETE

        assert progress.completed_tiers == 1

    def test_progress_percent(self) -> None:
        """Progress percent is (completed / total) * 100."""
        progress = EvalProgress(
            test_id="001-test",
            tiers=[
                TierProgress("T0", 4),
            ],
        )
        progress.tiers[0].runs[0].status = RunStatus.COMPLETE
        progress.tiers[0].runs[1].status = RunStatus.COMPLETE

        assert progress.progress_percent == 50.0


class TestFormatDuration:
    """Tests for format_duration function."""

    def test_zero(self) -> None:
        """Zero timedelta formats as 00:00:00."""
        assert format_duration(timedelta(0)) == "00:00:00"

    def test_seconds(self) -> None:
        """Seconds-only timedelta."""
        assert format_duration(timedelta(seconds=45)) == "00:00:45"

    def test_minutes(self) -> None:
        """Minutes and seconds."""
        assert format_duration(timedelta(minutes=5, seconds=30)) == "00:05:30"

    def test_hours(self) -> None:
        """Hours, minutes, and seconds."""
        assert format_duration(timedelta(hours=2, minutes=30, seconds=15)) == "02:30:15"


class TestFormatProgressBar:
    """Tests for format_progress_bar function."""

    def test_zero_percent(self) -> None:
        """Zero percent is all empty."""
        bar = format_progress_bar(0, width=10)
        assert len(bar) == 10

    def test_fifty_percent(self) -> None:
        """Fifty percent is half filled."""
        bar = format_progress_bar(50, width=10)
        assert len(bar) == 10

    def test_hundred_percent(self) -> None:
        """Hundred percent is all filled."""
        bar = format_progress_bar(100, width=10)
        assert len(bar) == 10

    def test_custom_width(self) -> None:
        """Custom width is respected."""
        bar = format_progress_bar(25, width=8)
        assert len(bar) == 8


class TestProgressDisplay:
    """Tests for ProgressDisplay class."""

    def test_quiet_mode_no_output(self) -> None:
        """Quiet mode suppresses output."""
        display = ProgressDisplay(quiet=True)
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        display._write("test message")

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        assert output == ""

    def test_start_test(self) -> None:
        """start_test returns configured EvalProgress."""
        display = ProgressDisplay(quiet=True)
        progress = display.start_test("001-test", ["T0", "T1"], runs_per_tier=5)

        assert progress.test_id == "001-test"
        assert len(progress.tiers) == 2
        assert progress.tiers[0].total_runs == 5
        assert progress.start_time is not None

    def test_start_tier(self) -> None:
        """start_tier records start time."""
        display = ProgressDisplay(quiet=True)
        progress = display.start_test("001-test", ["T0"], runs_per_tier=5)
        display.start_tier("T0")

        assert progress.tiers[0].start_time is not None

    def test_start_run(self) -> None:
        """start_run sets EXECUTING status and start time."""
        display = ProgressDisplay(quiet=True)
        display.start_test("001-test", ["T0"], runs_per_tier=5)
        display.start_tier("T0")
        display.start_run("T0", 1)

        progress = display._current_progress
        assert progress is not None
        assert progress.tiers[0].runs[0].status == RunStatus.EXECUTING
        assert progress.tiers[0].runs[0].start_time is not None

    def test_update_run_status(self) -> None:
        """update_run_status changes run status."""
        display = ProgressDisplay(quiet=True)
        display.start_test("001-test", ["T0"], runs_per_tier=5)
        display.start_run("T0", 1)
        display.update_run_status("T0", 1, RunStatus.JUDGING)

        progress = display._current_progress
        assert progress is not None
        assert progress.tiers[0].runs[0].status == RunStatus.JUDGING

    def test_complete_run(self) -> None:
        """complete_run records result details."""
        display = ProgressDisplay(quiet=True)
        display.start_test("001-test", ["T0"], runs_per_tier=5)
        display.start_run("T0", 1)
        display.complete_run("T0", 1, passed=True, grade="A", cost_usd=1.5)

        progress = display._current_progress
        assert progress is not None
        run = progress.tiers[0].runs[0]
        assert run.status == RunStatus.COMPLETE
        assert run.passed is True
        assert run.grade == "A"
        assert run.cost_usd == 1.5

    def test_complete_tier(self) -> None:
        """complete_tier records end time."""
        display = ProgressDisplay(quiet=True)
        display.start_test("001-test", ["T0"], runs_per_tier=2)
        display.start_tier("T0")
        display.complete_run("T0", 1, passed=True, grade="A", cost_usd=1.0)
        display.complete_run("T0", 2, passed=True, grade="B", cost_usd=1.5)
        display.complete_tier("T0")

        progress = display._current_progress
        assert progress is not None
        assert progress.tiers[0].end_time is not None

    def test_complete_test(self) -> None:
        """complete_test records end time."""
        display = ProgressDisplay(quiet=True)
        display.start_test("001-test", ["T0"], runs_per_tier=1)
        display.complete_test()

        progress = display._current_progress
        assert progress is not None
        assert progress.end_time is not None


class TestBackwardCompatImport:
    """Verify that the e2e.progress shim still works."""

    def test_import_from_e2e(self) -> None:
        """Importing from scylla.e2e.progress yields the same objects."""
        from scylla.e2e.progress import (
            EvalProgress as E2eEvalProgress,
        )
        from scylla.e2e.progress import (
            ProgressDisplay as E2eProgressDisplay,
        )
        from scylla.e2e.progress import (
            RunStatus as E2eRunStatus,
        )

        assert E2eRunStatus is RunStatus
        assert E2eEvalProgress is EvalProgress
        assert E2eProgressDisplay is ProgressDisplay
