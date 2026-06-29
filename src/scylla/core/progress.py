"""Neutral home for progress tracking types shared by e2e and cli layers.

All symbols here are pure stdlib — no Rich, no console frameworks, no scylla
layer imports.  ``scylla.cli.progress`` re-exports everything from here for
back-compat; ``scylla.e2e.progress`` imports from here directly so the
``e2e → cli`` layer violation is eliminated.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class RunStatus(Enum):
    """Status of a single run."""

    PENDING = "pending"
    EXECUTING = "executing"
    JUDGING = "judging"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class RunProgress:
    """Progress information for a single run."""

    run_number: int
    status: RunStatus = RunStatus.PENDING
    start_time: datetime | None = None
    end_time: datetime | None = None
    passed: bool | None = None
    grade: str | None = None
    cost_usd: float | None = None

    @property
    def elapsed(self) -> timedelta:
        """Get elapsed time for this run."""
        if self.start_time is None:
            return timedelta(0)
        end = self.end_time or datetime.now(timezone.utc)
        return end - self.start_time


@dataclass
class TierProgress:
    """Progress information for a tier."""

    tier_id: str
    total_runs: int
    runs: list[RunProgress] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize runs list if not provided."""
        if not self.runs:
            self.runs = [RunProgress(i + 1) for i in range(self.total_runs)]

    @property
    def completed_runs(self) -> int:
        """Count of completed runs."""
        return sum(1 for r in self.runs if r.status == RunStatus.COMPLETE)

    @property
    def passed_runs(self) -> int:
        """Count of passed runs."""
        return sum(1 for r in self.runs if r.passed is True)

    @property
    def pass_rate(self) -> float:
        """Pass rate as a percentage."""
        if self.completed_runs == 0:
            return 0.0
        return self.passed_runs / self.completed_runs

    @property
    def total_cost(self) -> float:
        """Total cost of completed runs."""
        return sum(r.cost_usd or 0.0 for r in self.runs if r.cost_usd is not None)

    @property
    def elapsed(self) -> timedelta:
        """Get elapsed time for this tier."""
        if self.start_time is None:
            return timedelta(0)
        end = self.end_time or datetime.now(timezone.utc)
        return end - self.start_time


@dataclass
class EvalProgress:
    """Progress information for a complete test."""

    test_id: str
    tiers: list[TierProgress] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None

    @property
    def total_runs(self) -> int:
        """Total number of runs across all tiers."""
        return sum(t.total_runs for t in self.tiers)

    @property
    def completed_runs(self) -> int:
        """Total completed runs across all tiers."""
        return sum(t.completed_runs for t in self.tiers)

    @property
    def completed_tiers(self) -> int:
        """Number of fully completed tiers."""
        return sum(1 for t in self.tiers if t.completed_runs == t.total_runs)

    @property
    def progress_percent(self) -> float:
        """Overall progress as percentage."""
        if self.total_runs == 0:
            return 0.0
        return (self.completed_runs / self.total_runs) * 100

    @property
    def elapsed(self) -> timedelta:
        """Get elapsed time for this test."""
        if self.start_time is None:
            return timedelta(0)
        end = self.end_time or datetime.now(timezone.utc)
        return end - self.start_time


def format_duration(td: timedelta) -> str:
    """Format a timedelta as HH:MM:SS.

    Args:
        td: Timedelta to format

    Returns:
        Formatted string

    """
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_progress_bar(percent: float, width: int = 20) -> str:
    """Create a text progress bar.

    Args:
        percent: Percentage complete (0-100)
        width: Width of the bar in characters

    Returns:
        Progress bar string

    """
    filled = int(width * percent / 100)
    empty = width - filled
    return f"{'█' * filled}{'░' * empty}"


class ProgressDisplay:
    """Displays progress during test execution."""

    def __init__(
        self,
        quiet: bool = False,
        verbose: bool = False,
        no_progress: bool = False,
    ) -> None:
        """Initialize progress display.

        Args:
            quiet: Minimal output for CI
            verbose: Detailed output
            no_progress: Disable progress bar

        """
        self.quiet = quiet
        self.verbose = verbose
        self.no_progress = no_progress
        self._current_progress: EvalProgress | None = None

    def _write(self, message: str, newline: bool = True) -> None:
        """Write a message to stdout."""
        if self.quiet:
            return
        end = "\n" if newline else ""
        sys.stdout.write(message + end)
        sys.stdout.flush()

    def start_test(self, test_id: str, tiers: list[str], runs_per_tier: int) -> EvalProgress:
        """Start tracking a new test.

        Args:
            test_id: Test identifier
            tiers: List of tier IDs
            runs_per_tier: Number of runs per tier

        Returns:
            EvalProgress object

        """
        progress = EvalProgress(
            test_id=test_id,
            tiers=[TierProgress(t, runs_per_tier) for t in tiers],
            start_time=datetime.now(timezone.utc),
        )
        self._current_progress = progress

        self._write(f"\n[{test_id}] Running tests...")
        self._write("")

        return progress

    def start_tier(self, tier_id: str) -> None:
        """Mark a tier as started.

        Args:
            tier_id: Tier identifier

        """
        if self._current_progress is None:
            return

        for tier in self._current_progress.tiers:
            if tier.tier_id == tier_id:
                tier.start_time = datetime.now(timezone.utc)
                break

        self._write(f"Tier: {tier_id}")

    def start_run(self, tier_id: str, run_number: int) -> None:
        """Mark a run as started.

        Args:
            tier_id: Tier identifier
            run_number: Run number (1-indexed)

        """
        if self._current_progress is None:
            return

        tier: TierProgress | None = None
        for t in self._current_progress.tiers:
            if t.tier_id == tier_id:
                tier = t
                break

        if tier is None:
            return

        run = tier.runs[run_number - 1]
        run.status = RunStatus.EXECUTING
        run.start_time = datetime.now(timezone.utc)

        elapsed = format_duration(self._current_progress.elapsed)
        self._write(f"  Run {run_number}/{tier.total_runs}: Executing... [{elapsed}]")

    def update_run_status(self, tier_id: str, run_number: int, status: RunStatus) -> None:
        """Update the status of a run.

        Args:
            tier_id: Tier identifier
            run_number: Run number (1-indexed)
            status: New status

        """
        if self._current_progress is None:
            return

        tier: TierProgress | None = None
        for t in self._current_progress.tiers:
            if t.tier_id == tier_id:
                tier = t
                break

        if tier is None:
            return

        run = tier.runs[run_number - 1]
        run.status = status

        if status == RunStatus.JUDGING:
            self._write(f"  Run {run_number}/{tier.total_runs}: Judging...")

    def complete_run(
        self,
        tier_id: str,
        run_number: int,
        passed: bool,
        grade: str,
        cost_usd: float,
    ) -> None:
        """Mark a run as complete.

        Args:
            tier_id: Tier identifier
            run_number: Run number (1-indexed)
            passed: Whether the run passed
            grade: Letter grade
            cost_usd: Cost in USD

        """
        if self._current_progress is None:
            return

        tier: TierProgress | None = None
        for t in self._current_progress.tiers:
            if t.tier_id == tier_id:
                tier = t
                break

        if tier is None:
            return

        run = tier.runs[run_number - 1]
        run.status = RunStatus.COMPLETE
        run.end_time = datetime.now(timezone.utc)
        run.passed = passed
        run.grade = grade
        run.cost_usd = cost_usd

        status = "PASS" if passed else "FAIL"
        self._write(
            f"  Run {run_number}/{tier.total_runs}: Complete "
            f"({status}, Grade: {grade}, Cost: ${cost_usd:.2f})"
        )

    def complete_tier(self, tier_id: str) -> None:
        """Mark a tier as complete and show summary.

        Args:
            tier_id: Tier identifier

        """
        if self._current_progress is None:
            return

        tier: TierProgress | None = None
        for t in self._current_progress.tiers:
            if t.tier_id == tier_id:
                t.end_time = datetime.now(timezone.utc)
                tier = t
                break

        if tier is None:
            return

        # Find median grade
        grades = [r.grade for r in tier.runs if r.grade is not None]
        median_grade = grades[len(grades) // 2] if grades else "N/A"

        self._write("")
        self._write(f"Tier {tier_id} Summary:")
        self._write(
            f"  Pass Rate: {tier.pass_rate * 100:.0f}% ({tier.passed_runs}/{tier.completed_runs})"
        )
        self._write(f"  Median Grade: {median_grade}")
        self._write(f"  Total Cost: ${tier.total_cost:.2f}")
        self._write(f"  Total Time: {format_duration(tier.elapsed)}")
        self._write("")

    def show_overall_progress(self) -> None:
        """Show overall progress bar."""
        if self._current_progress is None or self.no_progress:
            return

        progress = self._current_progress
        bar = format_progress_bar(progress.progress_percent)
        completed_tiers = progress.completed_tiers
        total_tiers = len(progress.tiers)

        self._write(
            f"Overall Progress: {bar} {progress.progress_percent:.0f}% "
            f"({completed_tiers}/{total_tiers} tiers, "
            f"{progress.completed_runs}/{progress.total_runs} runs)"
        )

    def complete_test(self) -> None:
        """Mark the test as complete."""
        if self._current_progress is None:
            return

        self._current_progress.end_time = datetime.now(timezone.utc)

        self._write("")
        self._write(f"Test completed in {format_duration(self._current_progress.elapsed)}")


__all__ = [
    "EvalProgress",
    "ProgressDisplay",
    "RunProgress",
    "RunStatus",
    "TierProgress",
    "format_duration",
    "format_progress_bar",
]
