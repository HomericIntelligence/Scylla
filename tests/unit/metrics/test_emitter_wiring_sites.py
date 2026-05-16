"""Tests for the 5 high-value call sites instrumented in #1949.

Validates that each instrumentation point emits the expected metric name(s)
to the default :class:`MetricEmitter`, and that emission failures are
swallowed (never break the wrapped operation).

Sites covered:
    1. Tier start/end             -> ``scylla_tier_duration_seconds``
    2. Subtest start/end          -> ``scylla_subtest_duration_seconds`` +
                                     ``scylla_subtest_outcome_total``
    3. Judge call                 -> ``scylla_judge_call_duration_seconds``
    4. Adapter call               -> ``scylla_adapter_call_duration_seconds`` +
                                     ``scylla_adapter_tokens_total``
    5. Checkpoint save            -> ``scylla_checkpoint_save_duration_seconds`` +
                                     ``scylla_checkpoint_save_total``
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from scylla.metrics.emitter import MetricEmitter, NoOpEmitter

if TYPE_CHECKING:
    pass


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


# ---------------------------------------------------------------------------
# Subtest site
# ---------------------------------------------------------------------------


def test_subtest_metrics_emit_duration_and_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_emit_subtest_metrics`` writes duration + outcome via default emitter."""
    from scylla.e2e import subtest_executor

    rec = RecordingEmitter()
    monkeypatch.setattr(subtest_executor, "get_default_emitter", lambda: rec)

    subtest_executor._emit_subtest_metrics(
        tier_id="T0",
        subtest_id="s1",
        duration_seconds=1.5,
        outcome="pass",
    )

    gauge_names = {g[0] for g in rec.gauges}
    counter_names = {c[0] for c in rec.counters}
    assert "scylla_subtest_duration_seconds" in gauge_names
    assert "scylla_subtest_outcome_total" in counter_names

    # Outcome label present.
    outcome_calls = [c for c in rec.counters if c[0] == "scylla_subtest_outcome_total"]
    assert outcome_calls[0][2] == {"tier": "T0", "subtest": "s1", "outcome": "pass"}


def test_subtest_metrics_swallow_emitter_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Emitter exceptions inside ``_emit_subtest_metrics`` must not propagate."""
    from scylla.e2e import subtest_executor

    class Boom(NoOpEmitter):
        def emit_gauge(self, *a: object, **k: object) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(subtest_executor, "get_default_emitter", lambda: Boom())
    # Should not raise.
    subtest_executor._emit_subtest_metrics(
        tier_id="T0", subtest_id="s1", duration_seconds=0.1, outcome="fail"
    )


# ---------------------------------------------------------------------------
# Adapter (stages) site
# ---------------------------------------------------------------------------


def test_adapter_metrics_emit_duration_and_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_emit_adapter_metrics`` emits duration gauge + input/output token counters."""
    from scylla.adapters.base import AdapterResult, AdapterTokenStats
    from scylla.e2e import stages

    rec = RecordingEmitter()
    monkeypatch.setattr(stages, "get_default_emitter", lambda: rec)

    # Build a minimal stand-in for RunContext with just the fields the emitter reads.
    ctx = MagicMock()
    ctx.tier_id.value = "T0"
    ctx.subtest.id = "s1"
    ctx.config.models = ["claude-sonnet-4-6"]
    ctx.agent_duration = 12.34
    ctx.agent_result = AdapterResult(
        exit_code=0,
        token_stats=AdapterTokenStats(input_tokens=100, output_tokens=50),
    )

    stages._emit_adapter_metrics(ctx)

    gauge_names = {g[0] for g in rec.gauges}
    assert "scylla_adapter_call_duration_seconds" in gauge_names

    token_calls = [c for c in rec.counters if c[0] == "scylla_adapter_tokens_total"]
    kinds = {(c[2] or {}).get("kind") for c in token_calls}
    assert kinds == {"input", "output"}


def test_adapter_metrics_skip_when_no_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """When agent_result is None, only duration may be emitted (no token counters)."""
    from scylla.e2e import stages

    rec = RecordingEmitter()
    monkeypatch.setattr(stages, "get_default_emitter", lambda: rec)

    ctx = MagicMock()
    ctx.tier_id.value = "T0"
    ctx.subtest.id = "s1"
    ctx.config.models = ["m"]
    ctx.agent_duration = None
    ctx.agent_result = None

    stages._emit_adapter_metrics(ctx)

    # No token counters when no result.
    assert not [c for c in rec.counters if c[0] == "scylla_adapter_tokens_total"]


# ---------------------------------------------------------------------------
# Checkpoint save site
# ---------------------------------------------------------------------------


def test_checkpoint_save_emits_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``save_checkpoint`` emits duration + outcome on success."""
    from scylla.persistence import checkpoint as checkpoint_mod
    from scylla.persistence.checkpoint import E2ECheckpoint, save_checkpoint

    rec = RecordingEmitter()
    monkeypatch.setattr(checkpoint_mod, "get_default_emitter", lambda: rec)

    ckpt = E2ECheckpoint(
        experiment_id="exp-test",
        experiment_dir=str(tmp_path),
        config_hash="abc",
        completed_runs={},
        started_at="2026-01-01T00:00:00+00:00",
        last_updated_at="2026-01-01T00:00:00+00:00",
        status="running",
        rate_limit_source=None,
        rate_limit_until=None,
        pause_count=0,
        pid=1234,
    )
    save_checkpoint(ckpt, tmp_path / "checkpoint.json")

    gauge_names = {g[0] for g in rec.gauges}
    counter_names = {c[0] for c in rec.counters}
    assert "scylla_checkpoint_save_duration_seconds" in gauge_names
    assert "scylla_checkpoint_save_total" in counter_names

    save_calls = [c for c in rec.counters if c[0] == "scylla_checkpoint_save_total"]
    assert (save_calls[0][2] or {}).get("outcome") == "ok"


# ---------------------------------------------------------------------------
# Tier site
# ---------------------------------------------------------------------------


def test_tier_duration_emitted_in_run_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_run_tier`` emits ``scylla_tier_duration_seconds`` via ``self._emitter``.

    We exercise the duration emission path by invoking ``_run_tier`` with a
    stubbed ``_run_tier_body``.
    """
    from scylla.e2e.models import ExperimentConfig, TierID
    from scylla.e2e.runner import E2ERunner

    rec = RecordingEmitter()
    config = ExperimentConfig(
        experiment_id="exp-test",
        task_repo="https://example/repo",
        task_commit="abc",
        task_prompt_file=Path("prompt.md"),
        language="python",
    )
    runner = E2ERunner(
        config=config,
        tiers_dir=Path("/tmp"),
        results_base_dir=Path("/tmp"),
        emitter=rec,
    )

    # Stub the body so we don't need real tier execution.
    monkeypatch.setattr(runner, "_run_tier_body", lambda tier, baseline: MagicMock())

    runner._run_tier(TierID.T0, baseline=None)

    gauge_names = {g[0] for g in rec.gauges}
    assert "scylla_tier_duration_seconds" in gauge_names
    duration_calls = [g for g in rec.gauges if g[0] == "scylla_tier_duration_seconds"]
    assert (duration_calls[0][2] or {}).get("tier") == "T0"


# ---------------------------------------------------------------------------
# Judge call site (duration metric is emitted via the existing _emitter)
# ---------------------------------------------------------------------------


def test_judge_call_duration_metric_name_used() -> None:
    """The judge_runner module references the correct duration metric name.

    Source-level guard against rename drift — a full end-to-end exercise of
    ``_run_judge`` is covered elsewhere in ``test_emitter_wiring.py``.
    """
    from scylla.e2e import judge_runner

    source = Path(judge_runner.__file__).read_text()
    assert "scylla_judge_call_duration_seconds" in source
    assert "scylla.judge.call" in source
