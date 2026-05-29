"""Scorecard generator for model-level result aggregation."""

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class EvalResult(BaseModel):
    """Summary of a model's performance on a single test."""

    runs_completed: int = Field(..., description="Number of completed runs")
    grade: str = Field(..., description="Letter grade")
    median_pass_rate: float = Field(..., description="Median pass rate")
    median_impl_rate: float = Field(..., description="Median implementation rate")
    median_cost_usd: float = Field(..., description="Median cost in USD")
    median_duration_seconds: float = Field(..., description="Median duration in seconds")


class OverallStats(BaseModel):
    """Overall statistics for a model across all tests."""

    tests_completed: int = Field(..., description="Number of completed tests")
    average_grade: str = Field(..., description="Average letter grade")
    total_cost_usd: float = Field(..., description="Total cost in USD")
    total_runs: int = Field(..., description="Total number of runs")


class ModelScorecard(BaseModel):
    """Scorecard aggregating all test results for a single model."""

    model_id: str = Field(..., description="Model identifier")
    model_name: str = Field(..., description="Human-readable model name")
    updated: str = Field(..., description="ISO timestamp of last update")
    overall: OverallStats = Field(..., description="Overall statistics")
    tests: dict[str, EvalResult] = Field(default_factory=dict, description="Test results")

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(indent=indent)

    def write(self, output_dir: Path) -> Path:
        """Write scorecard.json to output directory.

        Args:
            output_dir: Directory to write scorecard.json

        Returns:
            Path to written file

        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "scorecard.json"
        output_path.write_text(self.to_json())
        return output_path


def _grade_to_points(grade: str) -> float:
    """Convert letter grade to point value for averaging.

    Uses industry-aligned scale where S is the highest grade.

    Args:
        grade: Letter grade (S, A, B, C, D, F with optional +/-)

    Returns:
        Numeric point value (0.0 to 5.0)

    """
    base_points = {"S": 5.0, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}

    if not grade:
        return 0.0

    base = grade[0].upper()
    points = base_points.get(base, 0.0)

    if len(grade) > 1:
        modifier = grade[1]
        if modifier == "+":
            points += 0.3
        elif modifier == "-":
            points -= 0.3

    return max(0.0, min(5.0, points))


_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (4.85, "S"),
    (3.85, "A"),
    (3.50, "A-"),
    (3.15, "B+"),
    (2.85, "B"),
    (2.50, "B-"),
    (2.15, "C+"),
    (1.85, "C"),
    (1.50, "C-"),
    (1.15, "D+"),
    (0.85, "D"),
    (0.50, "D-"),
]


def _points_to_grade(points: float) -> str:
    """Convert point value back to letter grade.

    Uses industry-aligned scale where S is the highest grade.

    Args:
        points: Numeric point value (0.0 to 5.0)

    Returns:
        Letter grade string (S, A, B, C, D, or F with optional +/-)

    """
    for threshold, grade in _GRADE_THRESHOLDS:
        if points >= threshold:
            return grade
    return "F"


class ScorecardGenerator:
    """Generates model scorecards by aggregating test results."""

    def __init__(self, base_dir: Path) -> None:
        """Initialize scorecard generator.

        Args:
            base_dir: Base directory for scorecards (e.g., 'summaries/by-model/')

        """
        self.base_dir = base_dir

    def get_scorecard_dir(self, model_id: str) -> Path:
        """Get the directory path for a model scorecard.

        Args:
            model_id: Model identifier

        Returns:
            Path to scorecard directory

        """
        return self.base_dir / model_id

    def calculate_overall(self, tests: dict[str, EvalResult]) -> OverallStats:
        """Calculate overall statistics from test results.

        Args:
            tests: Dictionary of test_id -> EvalResult

        Returns:
            OverallStats with aggregated values

        """
        if not tests:
            return OverallStats(
                tests_completed=0,
                average_grade="F",
                total_cost_usd=0.0,
                total_runs=0,
            )

        tests_completed = len(tests)
        total_runs = sum(t.runs_completed for t in tests.values())
        total_cost = sum(t.median_cost_usd * t.runs_completed for t in tests.values())

        # Calculate average grade
        total_points = sum(_grade_to_points(t.grade) for t in tests.values())
        avg_points = total_points / tests_completed if tests_completed > 0 else 0.0
        average_grade = _points_to_grade(avg_points)

        return OverallStats(
            tests_completed=tests_completed,
            average_grade=average_grade,
            total_cost_usd=total_cost,
            total_runs=total_runs,
        )

    def generate_scorecard(
        self,
        model_id: str,
        model_name: str,
        tests: dict[str, EvalResult],
        timestamp: str | None = None,
    ) -> ModelScorecard:
        """Generate a model scorecard from test results.

        Args:
            model_id: Model identifier
            model_name: Human-readable model name
            tests: Dictionary of test_id -> EvalResult
            timestamp: Optional timestamp (auto-generated if not provided)

        Returns:
            ModelScorecard object

        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        overall = self.calculate_overall(tests)

        return ModelScorecard(
            model_id=model_id,
            model_name=model_name,
            updated=timestamp,
            overall=overall,
            tests=tests,
        )

    def write_scorecard(self, scorecard: ModelScorecard) -> Path:
        """Write a model scorecard to the appropriate directory.

        Args:
            scorecard: ModelScorecard to write

        Returns:
            Path to written scorecard.json

        """
        scorecard_dir = self.get_scorecard_dir(scorecard.model_id)
        return scorecard.write(scorecard_dir)

    def read_scorecard(self, model_id: str) -> ModelScorecard | None:
        """Read a model scorecard from the file system.

        Args:
            model_id: Model identifier

        Returns:
            ModelScorecard if found, None otherwise

        """
        scorecard_dir = self.get_scorecard_dir(model_id)
        scorecard_path = scorecard_dir / "scorecard.json"

        if not scorecard_path.exists():
            return None

        data = json.loads(scorecard_path.read_text())
        return ModelScorecard.model_validate(data)


def create_test_result(
    runs_completed: int,
    grade: str,
    median_pass_rate: float,
    median_impl_rate: float,
    median_cost_usd: float,
    median_duration_seconds: float,
) -> EvalResult:
    """Create an EvalResult from evaluation metrics.

    Args:
        runs_completed: Number of completed runs
        grade: Letter grade
        median_pass_rate: Median pass rate
        median_impl_rate: Median implementation rate
        median_cost_usd: Median cost in USD
        median_duration_seconds: Median duration in seconds

    Returns:
        EvalResult object

    """
    return EvalResult(
        runs_completed=runs_completed,
        grade=grade,
        median_pass_rate=median_pass_rate,
        median_impl_rate=median_impl_rate,
        median_cost_usd=median_cost_usd,
        median_duration_seconds=median_duration_seconds,
    )
