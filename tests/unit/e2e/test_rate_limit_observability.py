"""Tests for rate limit observability instrumentation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scylla.e2e.rate_limit import wait_for_rate_limit
from scylla.metrics.emitter import PrometheusTextfileEmitter


def _make_checkpoint(source: str = "agent") -> MagicMock:
    """Build a minimal checkpoint mock with rate_limit_source set."""
    checkpoint = MagicMock()
    checkpoint.experiment_id = "test-exp"
    checkpoint.status = "running"
    checkpoint.rate_limit_until = None
    checkpoint.rate_limit_source = source
    checkpoint.pause_count = 0
    return checkpoint


class TestRateLimitObservability:
    """Tests for span and metric emission in wait_for_rate_limit()."""

    def test_emits_pause_counter(self, tmp_path: Path) -> None:
        """wait_for_rate_limit emits scylla_rate_limit_pauses_total with reason label."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        checkpoint = _make_checkpoint(source="agent")

        with (
            patch("scylla.e2e.rate_limit._emitter", emitter),
            patch("scylla.e2e.rate_limit.time.sleep"),
            # is_shutdown_requested is imported lazily inside the function body
            patch("scylla.e2e.shutdown.is_shutdown_requested", return_value=False),
            patch("scylla.persistence.checkpoint.save_checkpoint"),
        ):
            wait_for_rate_limit(
                retry_after=1.0,
                checkpoint=checkpoint,
                checkpoint_path=tmp_path / "cp.json",
            )

        content = (tmp_path / "test.prom").read_text()
        assert "scylla_rate_limit_pauses_total" in content
        assert 'reason="agent"' in content

    def test_emits_pause_histogram(self, tmp_path: Path) -> None:
        """wait_for_rate_limit emits scylla_rate_limit_pause_seconds histogram."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        checkpoint = _make_checkpoint(source="judge")

        with (
            patch("scylla.e2e.rate_limit._emitter", emitter),
            patch("scylla.e2e.rate_limit.time.sleep"),
            patch("scylla.e2e.shutdown.is_shutdown_requested", return_value=False),
            patch("scylla.persistence.checkpoint.save_checkpoint"),
        ):
            wait_for_rate_limit(
                retry_after=0.5,
                checkpoint=checkpoint,
                checkpoint_path=tmp_path / "cp.json",
            )

        content = (tmp_path / "test.prom").read_text()
        assert "scylla_rate_limit_pause_seconds_bucket" in content
        assert "scylla_rate_limit_pause_seconds_count" in content
        assert 'reason="judge"' in content

    def test_span_attributes_set(self, tmp_path: Path) -> None:
        """wait_for_rate_limit sets scylla.reason and scylla.retry_after_seconds on span."""
        checkpoint = _make_checkpoint(source="agent")
        span_attrs: dict[str, object] = {}

        class _FakeSpan:
            def set_attribute(self, k: str, v: object) -> None:
                """Record span attribute."""
                span_attrs[k] = v

            def record_exception(self, exc: Exception) -> None:
                """No-op record_exception."""

            def __enter__(self) -> _FakeSpan:
                """Return self as context manager."""
                return self

            def __exit__(self, *args: object) -> None:
                """No-op exit."""

        class _FakeTracer:
            def start_as_current_span(self, name: str, **kwargs: object) -> _FakeSpan:
                """Return a fake span."""
                return _FakeSpan()

        with (
            patch("scylla.e2e.rate_limit._tracer", _FakeTracer()),
            patch("scylla.e2e.rate_limit.time.sleep"),
            patch("scylla.e2e.shutdown.is_shutdown_requested", return_value=False),
            patch("scylla.persistence.checkpoint.save_checkpoint"),
        ):
            wait_for_rate_limit(
                retry_after=2.0,
                checkpoint=checkpoint,
                checkpoint_path=tmp_path / "cp.json",
            )

        assert span_attrs.get("scylla.reason") == "agent"
        assert "scylla.retry_after_seconds" in span_attrs

    def test_unknown_source_when_none(self, tmp_path: Path) -> None:
        """Reason label falls back to 'unknown' when rate_limit_source is None."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        checkpoint = _make_checkpoint()
        checkpoint.rate_limit_source = None

        with (
            patch("scylla.e2e.rate_limit._emitter", emitter),
            patch("scylla.e2e.rate_limit.time.sleep"),
            patch("scylla.e2e.shutdown.is_shutdown_requested", return_value=False),
            patch("scylla.persistence.checkpoint.save_checkpoint"),
        ):
            wait_for_rate_limit(
                retry_after=1.0,
                checkpoint=checkpoint,
                checkpoint_path=tmp_path / "cp.json",
            )

        content = (tmp_path / "test.prom").read_text()
        assert 'reason="unknown"' in content
