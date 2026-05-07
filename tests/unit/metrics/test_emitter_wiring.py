"""Tests that the runner / judge wire MetricEmitter correctly.

Default behavior must be unchanged when ``SCYLLA_METRICS_PATH`` is unset
(NoOpEmitter, no I/O). When a recording emitter is injected, expected
counters / gauges must be observed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scylla.e2e.judge_runner import _emit_judge_metric, _run_judge
from scylla.e2e.models import (
    E2ERunResult,
    ExperimentConfig,
    ExperimentResult,
    SubTestResult,
    TierID,
    TierResult,
    TokenStats,
)
from scylla.e2e.runner import E2ERunner
from scylla.metrics.emitter import (
    MetricEmitter,
    NoOpEmitter,
    PrometheusTextfileEmitter,
    get_default_emitter,
)


class RecordingEmitter(MetricEmitter):
    """Capture emit calls for assertions."""

    def __init__(self) -> None:
        """Initialize with empty call lists."""
        self.counters: list[tuple[str, int, dict[str, str] | None]] = []
        self.gauges: list[tuple[str, float, dict[str, str] | None]] = []

    def emit_counter(
        self,
        name: str,
        value: int,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a counter call."""
        self.counters.append((name, value, labels))

    def emit_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a gauge call."""
        self.gauges.append((name, value, labels))


def _make_run(passed: bool, cost: float = 0.1) -> E2ERunResult:
    return E2ERunResult(
        run_number=1,
        cost_usd=cost,
        duration_seconds=1.0,
        exit_code=0,
        token_stats=TokenStats(),
        agent_duration_seconds=1.0,
        judge_duration_seconds=0.5,
        judge_score=0.9 if passed else 0.0,
        judge_passed=passed,
        judge_grade="A" if passed else "F",
        judge_reasoning="ok",
        workspace_path=Path("/tmp/ws"),
        logs_path=Path("/tmp/logs"),
    )


def _make_tier_result(tier: TierID, pass_runs: int, fail_runs: int) -> TierResult:
    runs = [_make_run(True) for _ in range(pass_runs)] + [
        _make_run(False) for _ in range(fail_runs)
    ]
    total = pass_runs + fail_runs
    pass_rate = pass_runs / total if total else 0.0
    sub = SubTestResult(
        subtest_id="s1",
        tier_id=tier,
        runs=runs,
        pass_rate=pass_rate,
        mean_cost=0.1,
        total_cost=0.1 * total,
    )
    return TierResult(
        tier_id=tier,
        subtest_results={"s1": sub},
        best_subtest="s1",
        best_subtest_score=pass_rate,
        total_cost=sub.total_cost,
        total_duration=12.5,
    )


def _make_runner(emitter: MetricEmitter | None = None, tmp_path: Path | None = None) -> E2ERunner:
    config = ExperimentConfig(
        experiment_id="exp-test",
        task_repo="https://example/repo",
        task_commit="abc",
        task_prompt_file=Path("prompt.md"),
        language="python",
    )
    base = tmp_path or Path("/tmp")
    return E2ERunner(
        config=config,
        tiers_dir=base,
        results_base_dir=base,
        emitter=emitter,
    )


# ---------------------------------------------------------------------------
# Default behavior unchanged
# ---------------------------------------------------------------------------


def test_runner_default_emitter_is_noop_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With SCYLLA_METRICS_PATH unset, the runner uses NoOpEmitter and writes nothing."""
    monkeypatch.delenv("SCYLLA_METRICS_PATH", raising=False)
    runner = _make_runner(tmp_path=tmp_path)
    assert isinstance(runner._emitter, NoOpEmitter)
    # Sanity: emit a metric — no file should appear in tmp_path.
    tier_results = {TierID.T0: _make_tier_result(TierID.T0, 1, 0)}
    fake_result = MagicMock(spec=ExperimentResult)
    runner._emit_experiment_metrics(tier_results, fake_result)
    assert list(tmp_path.iterdir()) == []


def test_runner_uses_textfile_emitter_when_env_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With SCYLLA_METRICS_PATH set, the runner uses PrometheusTextfileEmitter."""
    out = tmp_path / "scylla.prom"
    monkeypatch.setenv("SCYLLA_METRICS_PATH", str(out))
    runner = _make_runner(tmp_path=tmp_path)
    assert isinstance(runner._emitter, PrometheusTextfileEmitter)


# ---------------------------------------------------------------------------
# DI: recording emitter records calls
# ---------------------------------------------------------------------------


def test_runner_emits_per_tier_counters_and_gauges() -> None:
    """A recording emitter sees the expected metric names and labels."""
    rec = RecordingEmitter()
    runner = _make_runner(emitter=rec)
    tier_results = {
        TierID.T0: _make_tier_result(TierID.T0, pass_runs=3, fail_runs=1),
        TierID.T1: _make_tier_result(TierID.T1, pass_runs=0, fail_runs=2),
    }
    fake_result = MagicMock(spec=ExperimentResult)
    runner._emit_experiment_metrics(tier_results, fake_result)

    counter_names = {c[0] for c in rec.counters}
    gauge_names = {g[0] for g in rec.gauges}

    assert "scylla_tier_runs_total" in counter_names
    assert "scylla_subtest_runs_total" in counter_names
    assert "scylla_experiment_pass_rate" in gauge_names
    assert "scylla_experiment_latency_seconds" in gauge_names
    assert "scylla_experiment_cost_of_pass_usd" in gauge_names

    # T0 tier counter outcome=pass; T1 counter outcome=fail.
    tier_outcomes = {
        (c[2] or {}).get("tier"): (c[2] or {}).get("outcome")
        for c in rec.counters
        if c[0] == "scylla_tier_runs_total"
    }
    assert tier_outcomes["T0"] == "pass"
    assert tier_outcomes["T1"] == "fail"

    # Subtest counters split by outcome.
    subtest_pass = sum(
        c[1]
        for c in rec.counters
        if c[0] == "scylla_subtest_runs_total" and (c[2] or {}).get("outcome") == "pass"
    )
    subtest_fail = sum(
        c[1]
        for c in rec.counters
        if c[0] == "scylla_subtest_runs_total" and (c[2] or {}).get("outcome") == "fail"
    )
    assert subtest_pass == 3  # only T0 has passing runs
    assert subtest_fail == 3  # T0 (1) + T1 (2)


def test_runner_emits_to_textfile(tmp_path: Path) -> None:
    """A PrometheusTextfileEmitter produces the expected lines after a tier completes."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    runner = _make_runner(emitter=emitter)
    tier_results = {TierID.T0: _make_tier_result(TierID.T0, pass_runs=2, fail_runs=0)}
    fake_result = MagicMock(spec=ExperimentResult)
    runner._emit_experiment_metrics(tier_results, fake_result)

    content = out.read_text()
    assert "scylla_tier_runs_total" in content
    assert "scylla_subtest_runs_total" in content
    assert "scylla_experiment_pass_rate" in content
    assert "scylla_experiment_latency_seconds" in content
    assert 'tier="T0"' in content
    assert 'experiment="exp-test"' in content


def test_runner_emit_metrics_swallows_emitter_errors() -> None:
    """An emitter that raises must not propagate out of _emit_experiment_metrics."""

    class BoomEmitter(NoOpEmitter):
        """Emitter that raises on every counter emit."""

        def emit_counter(
            self,
            name: str,
            value: int,
            labels: dict[str, str] | None = None,
        ) -> None:
            """Raise unconditionally."""
            raise RuntimeError("boom")

    runner = _make_runner(emitter=BoomEmitter())
    tier_results = {TierID.T0: _make_tier_result(TierID.T0, 1, 0)}
    fake_result = MagicMock(spec=ExperimentResult)
    # Should not raise.
    runner._emit_experiment_metrics(tier_results, fake_result)


# ---------------------------------------------------------------------------
# Judge wiring
# ---------------------------------------------------------------------------


def test_emit_judge_metric_outcomes() -> None:
    """_emit_judge_metric maps (is_valid, passed) -> outcome label correctly."""
    rec = RecordingEmitter()
    _emit_judge_metric(rec, "claude-haiku-4-5", is_valid=True, passed=True)
    _emit_judge_metric(rec, "claude-haiku-4-5", is_valid=True, passed=False)
    _emit_judge_metric(rec, "claude-haiku-4-5", is_valid=False, passed=False)

    assert len(rec.counters) == 3
    outcomes = [(c[2] or {}).get("outcome") for c in rec.counters]
    assert outcomes == ["pass", "fail", "error"]
    for c in rec.counters:
        assert c[0] == "scylla_judge_evaluations_total"
        assert (c[2] or {}).get("model") == "claude-haiku-4-5"


def test_run_judge_emits_counter_per_judge(tmp_path: Path) -> None:
    """_run_judge emits one scylla_judge_evaluations_total per configured judge."""
    rec = RecordingEmitter()

    fake_judge_result = MagicMock()
    fake_judge_result.score = 0.9
    fake_judge_result.passed = True
    fake_judge_result.grade = "A"
    fake_judge_result.reasoning = "good"
    fake_judge_result.is_valid = True
    fake_judge_result.criteria_scores = {}

    judge_dir = tmp_path / "judge"
    judge_dir.mkdir()
    with patch("scylla.e2e.judge_runner.run_llm_judge", return_value=fake_judge_result):
        consensus, judges = _run_judge(
            workspace=tmp_path,
            task_prompt="t",
            stdout="s",
            judge_dir=judge_dir,
            judge_models=["claude-haiku-4-5", "claude-sonnet-4-5"],
            emitter=rec,
        )
    assert consensus["passed"] is True
    assert len(judges) == 2
    judge_counters = [c for c in rec.counters if c[0] == "scylla_judge_evaluations_total"]
    assert len(judge_counters) == 2
    models = {(c[2] or {}).get("model") for c in judge_counters}
    assert models == {"claude-haiku-4-5", "claude-sonnet-4-5"}


def test_run_judge_default_emitter_is_noop_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When emitter not passed and SCYLLA_METRICS_PATH unset, no file is written."""
    monkeypatch.delenv("SCYLLA_METRICS_PATH", raising=False)
    fake_judge_result = MagicMock()
    fake_judge_result.score = 0.9
    fake_judge_result.passed = True
    fake_judge_result.grade = "A"
    fake_judge_result.reasoning = "good"
    fake_judge_result.is_valid = True
    fake_judge_result.criteria_scores = {}

    judge_dir = tmp_path / "judge"
    judge_dir.mkdir()
    sentinel_dir = tmp_path / "sentinel"
    sentinel_dir.mkdir()
    with patch("scylla.e2e.judge_runner.run_llm_judge", return_value=fake_judge_result):
        _run_judge(
            workspace=tmp_path,
            task_prompt="t",
            stdout="s",
            judge_dir=judge_dir,
            judge_models=["claude-haiku-4-5"],
        )
    # Nothing leaked into the sentinel directory.
    assert list(sentinel_dir.iterdir()) == []


def test_get_default_emitter_picks_textfile_when_env_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """get_default_emitter is read at runtime, not import time."""
    monkeypatch.delenv("SCYLLA_METRICS_PATH", raising=False)
    assert isinstance(get_default_emitter(), NoOpEmitter)
    monkeypatch.setenv("SCYLLA_METRICS_PATH", str(tmp_path / "out.prom"))
    assert isinstance(get_default_emitter(), PrometheusTextfileEmitter)
