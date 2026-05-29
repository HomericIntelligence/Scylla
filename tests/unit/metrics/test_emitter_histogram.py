"""Tests for PrometheusTextfileEmitter.emit_histogram."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from scylla.metrics.emitter import (
    MetricEmitter,
    NoOpEmitter,
    PrometheusTextfileEmitter,
)


def _read_prom(path: Path) -> str:
    """Read the Prometheus textfile at path."""
    return path.read_text()


def _parse_prom(path: Path) -> dict[str, str]:
    """Parse a Prometheus textfile into a dict mapping metric+labels -> value."""
    content = path.read_text()
    return {
        line.split(" ")[0]: line.split(" ")[1]
        for line in content.strip().splitlines()
        if " " in line
    }


class TestEmitHistogram:
    """Tests for PrometheusTextfileEmitter.emit_histogram and NoOpEmitter."""

    def test_basic_observation_writes_buckets(self, tmp_path: Path) -> None:
        """A single observation renders _bucket, _sum, and _count lines."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        emitter.emit_histogram("scylla_latency_seconds", 1.5)
        content = _read_prom(tmp_path / "test.prom")
        assert "scylla_latency_seconds_bucket" in content
        assert "scylla_latency_seconds_sum" in content
        assert "scylla_latency_seconds_count" in content

    def test_bucket_arithmetic_correct(self, tmp_path: Path) -> None:
        """Value 0.3 lands in le=0.5 and all larger buckets including +Inf."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        # Value 0.3 should fall in buckets >= 0.5 (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, +Inf)
        emitter.emit_histogram("latency", 0.3)
        prom_lines = _parse_prom(tmp_path / "test.prom")
        # Bucket le=0.1 should be 0 (0.3 > 0.1)
        assert prom_lines['latency_bucket{le="0.1"}'] == "0"
        # Bucket le=0.5 should be 1 (0.3 <= 0.5)
        assert prom_lines['latency_bucket{le="0.5"}'] == "1"
        # +Inf always 1
        assert prom_lines['latency_bucket{le="+Inf"}'] == "1"

    def test_sum_and_count_correct(self, tmp_path: Path) -> None:
        """Two observations produce count=2 and sum equal to both values."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        emitter.emit_histogram("scylla_h", 1.0)
        emitter.emit_histogram("scylla_h", 3.0)
        prom_lines = _parse_prom(tmp_path / "test.prom")
        assert prom_lines["scylla_h_count"] == "2"
        assert float(prom_lines["scylla_h_sum"]) == pytest.approx(4.0)

    def test_no_duplicate_bucket_lines_on_multiple_observations(self, tmp_path: Path) -> None:
        """Five observations produce exactly one +Inf bucket line per series."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        for _ in range(5):
            emitter.emit_histogram("scylla_h", 1.0)
        content = _read_prom(tmp_path / "test.prom")
        # +Inf bucket should appear exactly once per (name, labels) pair
        inf_lines = [line for line in content.splitlines() if 'le="+Inf"' in line]
        assert len(inf_lines) == 1

    def test_labels_included_in_bucket_lines(self, tmp_path: Path) -> None:
        """Label key/value and le= appear in rendered histogram."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        emitter.emit_histogram("scylla_h", 1.0, labels={"event": "start"})
        content = _read_prom(tmp_path / "test.prom")
        assert 'event="start"' in content
        assert "le=" in content

    def test_different_label_sets_render_separately(self, tmp_path: Path) -> None:
        """Two distinct label sets each produce their own +Inf bucket line."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        emitter.emit_histogram("scylla_h", 1.0, labels={"event": "start"})
        emitter.emit_histogram("scylla_h", 2.0, labels={"event": "stop"})
        content = _read_prom(tmp_path / "test.prom")
        # Both label sets should produce +Inf lines
        inf_lines = [line for line in content.splitlines() if 'le="+Inf"' in line]
        assert len(inf_lines) == 2

    def test_thread_safety_cumulative_counts(self, tmp_path: Path) -> None:
        """10 threads x 100 observations each sum to 1000 under self._lock."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        n_threads = 10
        obs_per_thread = 100

        def observe() -> None:
            """Emit obs_per_thread histogram observations."""
            for _ in range(obs_per_thread):
                emitter.emit_histogram("scylla_h", 1.0)

        threads = [threading.Thread(target=observe) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        content = _read_prom(tmp_path / "test.prom")
        prom_lines = {
            line.split(" ")[0]: line.split(" ")[1] for line in content.strip().splitlines()
        }
        assert int(prom_lines["scylla_h_count"]) == n_threads * obs_per_thread
        assert prom_lines['scylla_h_bucket{le="+Inf"}'] == str(n_threads * obs_per_thread)

    def test_noop_emitter_emit_histogram_drops(self) -> None:
        """NoOpEmitter.emit_histogram returns without error or side-effects."""
        emitter = NoOpEmitter()
        # Should not raise
        emitter.emit_histogram("scylla_h", 1.0, labels={"event": "start"})

    def test_base_class_default_pass_body_callable(self, tmp_path: Path) -> None:
        """A subclass that doesn't override emit_histogram uses the base no-op."""

        class MinimalEmitter(MetricEmitter):
            """Minimal concrete emitter that omits emit_histogram."""

            def emit_counter(
                self, name: str, value: int, labels: dict[str, str] | None = None
            ) -> None:
                """No-op counter."""

            def emit_gauge(
                self, name: str, value: float, labels: dict[str, str] | None = None
            ) -> None:
                """No-op gauge."""

        emitter = MinimalEmitter()
        # Should not raise — default implementation is a silent no-op
        emitter.emit_histogram("scylla_h", 1.0)

    def test_plus_inf_bucket_literal_in_output(self, tmp_path: Path) -> None:
        """The +Inf bucket label uses the exact Prometheus literal string."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        emitter.emit_histogram("scylla_h", 999.0)
        content = _read_prom(tmp_path / "test.prom")
        # Prometheus requires the literal string +Inf (not inf or Inf)
        assert 'le="+Inf"' in content

    def test_inf_value_observation(self, tmp_path: Path) -> None:
        """float('inf') observation lands in the +Inf bucket with count=1."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")
        # A value of float('inf') should land in all buckets including +Inf
        emitter.emit_histogram("scylla_h", float("inf"))
        content = _read_prom(tmp_path / "test.prom")
        prom_lines = {
            line.split(" ")[0]: line.split(" ")[1] for line in content.strip().splitlines()
        }
        assert prom_lines['scylla_h_bucket{le="+Inf"}'] == "1"
        assert int(prom_lines["scylla_h_count"]) == 1
