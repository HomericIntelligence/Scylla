"""Tests for DockerExecutor observability instrumentation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from scylla.executor.docker import ContainerConfig, DockerExecutor
from scylla.metrics.emitter import PrometheusTextfileEmitter


def _make_config(image: str = "test-image:latest") -> ContainerConfig:
    """Build a minimal ContainerConfig for testing."""
    return ContainerConfig(image=image)


class TestDockerRunObservability:
    """Tests for span and metric emission in DockerExecutor lifecycle methods."""

    def test_run_emits_start_and_stop_counter(self, tmp_path: Path) -> None:
        """DockerExecutor.run emits start and stop lifecycle counters."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        executor = DockerExecutor.__new__(DockerExecutor)
        with (
            patch("scylla.executor.docker._emitter", emitter),
            patch("scylla.executor.docker.subprocess.run") as mock_run,
            patch.object(executor, "_get_last_container_id", return_value="abc123"),
        ):
            mock_run.return_value = mock_result
            config = _make_config()
            executor.run(config)

        content = (tmp_path / "test.prom").read_text()
        assert 'scylla_container_lifecycle_total{event="start"' in content
        assert 'scylla_container_lifecycle_total{event="stop"' in content

    def test_run_emits_histogram(self, tmp_path: Path) -> None:
        """DockerExecutor.run emits scylla_container_run_seconds histogram."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        executor = DockerExecutor.__new__(DockerExecutor)
        with (
            patch("scylla.executor.docker._emitter", emitter),
            patch("scylla.executor.docker.subprocess.run") as mock_run,
            patch.object(executor, "_get_last_container_id", return_value="abc123"),
        ):
            mock_run.return_value = mock_result
            config = _make_config()
            executor.run(config)

        content = (tmp_path / "test.prom").read_text()
        assert "scylla_container_run_seconds_bucket" in content
        assert "scylla_container_run_seconds_count" in content

    def test_run_timeout_emits_fail_counter(self, tmp_path: Path) -> None:
        """TimeoutExpired in DockerExecutor.run emits the fail lifecycle counter."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        executor = DockerExecutor.__new__(DockerExecutor)
        with (
            patch("scylla.executor.docker._emitter", emitter),
            patch("scylla.executor.docker.subprocess.run") as mock_run,
            patch.object(executor, "_get_last_container_id", return_value="abc123"),
            patch.object(executor, "stop"),
        ):
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["docker"], timeout=10)
            config = _make_config()
            result = executor.run(config)

        assert result.timed_out is True
        content = (tmp_path / "test.prom").read_text()
        assert 'scylla_container_lifecycle_total{event="fail"' in content

    def test_run_detached_emits_start_counter(self, tmp_path: Path) -> None:
        """DockerExecutor.run_detached emits a start lifecycle counter."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "container-id-123\n"
        mock_result.stderr = ""

        executor = DockerExecutor.__new__(DockerExecutor)
        with (
            patch("scylla.executor.docker._emitter", emitter),
            patch("scylla.executor.docker.subprocess.run") as mock_run,
        ):
            mock_run.return_value = mock_result
            config = _make_config()
            container_id = executor.run_detached(config)

        assert container_id == "container-id-123"
        content = (tmp_path / "test.prom").read_text()
        assert 'scylla_container_lifecycle_total{event="start"' in content

    def test_stop_emits_stop_counter_and_histogram(self, tmp_path: Path) -> None:
        """DockerExecutor.stop emits a stop lifecycle counter and duration histogram."""
        emitter = PrometheusTextfileEmitter(tmp_path / "test.prom")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        executor = DockerExecutor.__new__(DockerExecutor)
        with (
            patch("scylla.executor.docker._emitter", emitter),
            patch("scylla.executor.docker.subprocess.run") as mock_run,
        ):
            mock_run.return_value = mock_result
            executor.stop("abc123")

        content = (tmp_path / "test.prom").read_text()
        assert 'scylla_container_lifecycle_total{event="stop"' in content
        assert "scylla_container_stop_seconds_count" in content
