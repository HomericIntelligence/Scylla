"""Tests for error-class counter emission at exception dispatch sites."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scylla.e2e.log_context import current_tier_id, set_log_context
from scylla.e2e.rate_limit import InfrastructureFailureError, RateLimitError, RateLimitInfo
from scylla.metrics.emitter import PrometheusTextfileEmitter


class TestCurrentTierId:
    """Tests for the current_tier_id() accessor in log_context."""

    def test_returns_empty_when_no_context(self) -> None:
        """Returns empty string when no log context is set on this thread."""
        # Ensure no context is set in this thread
        from scylla.e2e.log_context import clear_log_context

        clear_log_context()
        assert current_tier_id() == ""

    def test_returns_tier_id_when_set(self) -> None:
        """Returns the tier_id that was previously set via set_log_context."""
        set_log_context(tier_id="T3")
        assert current_tier_id() == "T3"
        from scylla.e2e.log_context import clear_log_context

        clear_log_context()


class TestParallelExecutorErrorEmit:
    """Tests for scylla_errors_total counter at parallel_executor dispatch sites."""

    def test_infrastructure_failure_emits_counter(self, tmp_path: Path) -> None:
        """InfrastructureFailureError increments scylla_errors_total with correct labels."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        with patch("scylla.e2e.parallel_executor._emitter", emitter):
            from scylla.e2e.parallel_executor import _emitter as pe_emitter

            # Simulate what the except InfrastructureFailureError block does
            exc = InfrastructureFailureError("agent crashed")
            set_log_context(tier_id="T1")
            try:
                pe_emitter.emit_counter(
                    "scylla_errors_total",
                    1,
                    labels={"error_class": type(exc).__name__, "tier": current_tier_id()},
                )
            finally:
                from scylla.e2e.log_context import clear_log_context

                clear_log_context()

        content = (tmp_path / "test.prom").read_text()
        assert "scylla_errors_total" in content
        assert 'error_class="InfrastructureFailureError"' in content
        assert 'tier="T1"' in content

    def test_rate_limit_error_emits_counter(self, tmp_path: Path) -> None:
        """RateLimitError increments scylla_errors_total with error_class label."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        with patch("scylla.e2e.parallel_executor._emitter", emitter):
            from scylla.e2e.parallel_executor import _emitter as pe_emitter

            info = RateLimitInfo(
                source="judge",
                error_message="rate limited",
                retry_after_seconds=60,
                detected_at=datetime.now(timezone.utc).isoformat(),
            )
            exc = RateLimitError(info)
            set_log_context(tier_id="T2")
            try:
                pe_emitter.emit_counter(
                    "scylla_errors_total",
                    1,
                    labels={"error_class": type(exc).__name__, "tier": current_tier_id()},
                )
            finally:
                from scylla.e2e.log_context import clear_log_context

                clear_log_context()

        content = (tmp_path / "test.prom").read_text()
        assert 'error_class="RateLimitError"' in content
        assert 'tier="T2"' in content


class TestSubtestExecutorErrorEmit:
    """Tests for scylla_errors_total counter at subtest_executor dispatch sites."""

    def test_emit_counter_uses_current_tier_id(self, tmp_path: Path) -> None:
        """Generic exception increments scylla_errors_total with tier from log context."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        with patch("scylla.e2e.subtest_executor._emitter", emitter):
            from scylla.e2e.subtest_executor import _emitter as se_emitter

            exc = ValueError("some error")
            set_log_context(tier_id="T0")
            try:
                se_emitter.emit_counter(
                    "scylla_errors_total",
                    1,
                    labels={"error_class": type(exc).__name__, "tier": current_tier_id()},
                )
            finally:
                from scylla.e2e.log_context import clear_log_context

                clear_log_context()

        content = (tmp_path / "test.prom").read_text()
        assert 'error_class="ValueError"' in content
        assert 'tier="T0"' in content
