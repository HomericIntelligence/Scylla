"""Docker container orchestration for isolated test execution.

This module provides Docker container lifecycle management for running agent
evaluations in isolated, reproducible environments.
capture (Mojo stdlib limitation - cannot capture stdout/stderr from subprocesses).

Design Decisions (from plan review):
- Docker is REQUIRED - fail with error if unavailable (no fallback)
- API keys passed via environment variables (docker -e flags)
- Containers stopped but preserved for analysis (not removed)
- Agent and judge containers are separate
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.config.models import ResourceLimitsConfig
from scylla.metrics.emitter import get_default_emitter
from scylla.utils.tracing import get_tracer

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)
_tracer = get_tracer(__name__)
_emitter = get_default_emitter()


def _emit_container_lifecycle(event: str, image: str) -> None:
    """Emit container lifecycle counter. Best-effort, never raises."""
    try:
        _emitter.emit_counter(
            "scylla_container_lifecycle_total",
            1,
            labels={"event": event, "image": image},
        )
    except Exception as _e:
        logger.warning(f"Container lifecycle metric emission failed (non-fatal): {_e}")


def _emit_container_run_duration(elapsed: float, image: str) -> None:
    """Emit container run duration histogram. Best-effort, never raises."""
    try:
        _emitter.emit_histogram(
            "scylla_container_run_seconds",
            elapsed,
            labels={"image": image},
        )
    except Exception as _e:
        logger.warning(f"Container run duration metric emission failed (non-fatal): {_e}")


class DockerError(Exception):
    """Base exception for Docker-related errors."""

    pass


class DockerNotAvailableError(DockerError):
    """Raised when Docker is not available on the system."""

    pass


class ContainerError(DockerError):
    """Raised when a container operation fails."""

    pass


class ContainerTimeoutError(ContainerError):
    """Raised when a container operation times out."""

    pass


@dataclass
class ContainerConfig:
    """Configuration for creating a Docker container.

    Attributes:
        image: Docker image to use (e.g., "python:3.12-slim").
        name: Optional container name (auto-generated if not provided).
        workspace_path: Host path to mount as workspace.
        workspace_mount: Container path where workspace is mounted.
        env_vars: Environment variables to pass to container.
        command: Command to run in container.
        timeout_seconds: Maximum execution time in seconds.
        working_dir: Working directory inside container.
        network: Docker network mode (default: "none" for isolation).
        resource_limits: Docker resource limits (memory, CPU, pids).
            Defaults to the framework defaults (8g RAM, 2.0 CPUs, 512 pids).

    """

    image: str
    name: str | None = None
    workspace_path: Path | None = None
    workspace_mount: str = "/workspace"
    env_vars: dict[str, str] = field(default_factory=dict)
    command: list[str] = field(default_factory=list)
    timeout_seconds: int = 3600
    working_dir: str | None = None
    network: str = "none"
    resource_limits: ResourceLimitsConfig = field(default_factory=ResourceLimitsConfig)


@dataclass
class ContainerResult:
    """Result from running a container.

    Attributes:
        container_id: Docker container ID.
        exit_code: Container exit code (0 = success).
        stdout: Captured standard output.
        stderr: Captured standard error.
        timed_out: Whether the container was killed due to timeout.

    """

    container_id: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class DockerExecutor:
    """Manages Docker container lifecycle for test execution.

    This class provides methods to:
    - Check Docker availability
    - Create and run containers with specific configurations
    - Mount workspaces into containers
    - Pass environment variables (including API keys)
    - Capture container output (stdout/stderr)
    - Stop containers (preserved for analysis)

    Example:
        >>> executor = DockerExecutor()
        >>> config = ContainerConfig(
        ...     image="python:3.12-slim",
        ...     workspace_path=Path("/path/to/workspace"),
        ...     env_vars={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        ...     command=["python", "run_test.py"],
        ... )
        >>> result = executor.run(config)
        >>> print(f"Exit code: {result.exit_code}")

    """

    # Common API key environment variable names
    API_KEY_VARS: tuple[str, ...] = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
    )

    # Suffix-based fallback for catching secret-bearing env vars whose names
    # are not in the explicit ``API_KEY_VARS`` enumeration. This provides
    # defense-in-depth so a new provider's credential (e.g., ``FOO_API_KEY``,
    # ``BAR_TOKEN``) is forwarded into containers without code changes.
    #
    # The bare ``_KEY`` suffix is intentionally excluded because it has a high
    # false-positive rate (e.g., ``PUBLIC_KEY_PATH``, ``SSH_KEY_FILE`` would
    # never end in ``_KEY`` themselves but ``OBJECT_STORE_KEY``/``CACHE_KEY``
    # might be non-secret). Callers needing those can pass an explicit
    # ``var_names`` list to :meth:`get_api_keys_from_env`.
    API_KEY_SUFFIXES: tuple[str, ...] = (
        "_API_KEY",
        "_SECRET",
        "_TOKEN",
        "_PASSWORD",
    )

    @classmethod
    def is_secret_var(cls, name: str) -> bool:
        """Check whether an env var name looks like it carries a secret.

        Returns ``True`` if ``name`` is in :attr:`API_KEY_VARS` or ends with
        any suffix in :attr:`API_KEY_SUFFIXES`.

        Args:
            name: Environment variable name (case-sensitive).

        Returns:
            True if the name should be treated as secret-bearing.

        """
        if name in cls.API_KEY_VARS:
            return True
        return any(name.endswith(suffix) for suffix in cls.API_KEY_SUFFIXES)

    def __init__(self) -> None:
        """Initialize DockerExecutor and verify Docker is available."""
        self._check_docker_available()

    def _check_docker_available(self) -> None:
        """Check if Docker is available and running.

        Raises:
            DockerNotAvailableError: If Docker is not installed or not running.

        """
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise DockerNotAvailableError(f"Docker is not running: {result.stderr.strip()}")
        except FileNotFoundError:
            raise DockerNotAvailableError(
                "Docker is not installed. Please install Docker to run evaluations."
            ) from None
        except subprocess.TimeoutExpired:
            raise DockerNotAvailableError(
                "Docker command timed out. Docker may be unresponsive."
            ) from None

    def _build_run_command(self, config: ContainerConfig) -> list[str]:
        """Build the docker run command from configuration.

        Args:
            config: Container configuration.

        Returns:
            List of command arguments for subprocess.

        """
        cmd = ["docker", "run"]

        # Container name
        if config.name:
            cmd.extend(["--name", config.name])

        # Network isolation
        cmd.extend(["--network", config.network])

        # Resource limits — always applied to prevent runaway containers from
        # exhausting host RAM, CPU, or process-table entries.
        limits = config.resource_limits
        cmd.extend(["--memory", limits.memory_limit])
        cmd.extend(["--cpus", str(limits.cpu_limit)])
        cmd.extend(["--pids-limit", str(limits.pids_limit)])

        # Working directory
        if config.working_dir:
            cmd.extend(["--workdir", config.working_dir])
        elif config.workspace_path:
            cmd.extend(["--workdir", config.workspace_mount])

        # Mount workspace
        if config.workspace_path:
            abs_path = config.workspace_path.resolve()
            cmd.extend(["-v", f"{abs_path}:{config.workspace_mount}"])

        # Environment variables
        for key, value in config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Image
        cmd.append(config.image)

        # Command to run
        if config.command:
            cmd.extend(config.command)

        return cmd

    def run(self, config: ContainerConfig) -> ContainerResult:
        """Run a container with the given configuration.

        Args:
            config: Container configuration specifying image, mounts, env vars, etc.

        Returns:
            ContainerResult with exit code, stdout, stderr, and container ID.

        Raises:
            ContainerError: If container creation or execution fails.
            ContainerTimeoutError: If container exceeds timeout.

        """
        cmd = self._build_run_command(config)
        _run_start = time.monotonic()

        with _tracer.start_as_current_span("scylla.container.run") as _span:
            _span.set_attribute("scylla.image", config.image)
            try:
                _emit_container_lifecycle("start", config.image)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=config.timeout_seconds,
                )

                # Extract container ID from output (for named containers, use name)
                container_id = config.name or self._get_last_container_id()
                _span.set_attribute("scylla.container_id", container_id or "unknown")
                _span.set_attribute("scylla.exit_code", result.returncode)
                _emit_container_lifecycle("stop", config.image)
                _emit_container_run_duration(time.monotonic() - _run_start, config.image)

                return ContainerResult(
                    container_id=container_id or "unknown",
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    timed_out=False,
                )

            except subprocess.TimeoutExpired as e:
                _span.record_exception(e)
                _emit_container_lifecycle("fail", config.image)
                _emit_container_run_duration(time.monotonic() - _run_start, config.image)
                # Container is still running - stop it
                container_id = config.name or self._get_last_container_id()
                if container_id:
                    self.stop(container_id)

                return ContainerResult(
                    container_id=container_id or "unknown",
                    exit_code=-1,
                    stdout=e.stdout.decode() if e.stdout else "",
                    stderr=e.stderr.decode() if e.stderr else "",
                    timed_out=True,
                )

            except subprocess.SubprocessError as e:
                _span.record_exception(e)
                _emit_container_lifecycle("fail", config.image)
                _emit_container_run_duration(time.monotonic() - _run_start, config.image)
                raise ContainerError(f"Failed to run container: {e}") from e

    def run_detached(self, config: ContainerConfig) -> str:
        """Run a container in detached mode.

        Args:
            config: Container configuration.

        Returns:
            Container ID.

        Raises:
            ContainerError: If container creation fails.

        """
        cmd = self._build_run_command(config)
        # Insert -d flag after "docker run"
        cmd.insert(2, "-d")

        with _tracer.start_as_current_span("scylla.container.run_detached") as _span:
            _span.set_attribute("scylla.image", config.image)
            try:
                _emit_container_lifecycle("start", config.image)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    raise ContainerError(f"Failed to start container: {result.stderr.strip()}")

                container_id = result.stdout.strip()
                _span.set_attribute("scylla.container_id", container_id)
                return container_id

            except subprocess.TimeoutExpired as e:
                _span.record_exception(e)
                _emit_container_lifecycle("fail", config.image)
                raise ContainerError("Timed out starting container") from None
            except subprocess.SubprocessError as e:
                _span.record_exception(e)
                _emit_container_lifecycle("fail", config.image)
                raise ContainerError(f"Failed to start container: {e}") from e

    def stop(self, container_id: str, timeout: int = 10) -> None:
        """Stop a running container (preserves container for analysis).

        Args:
            container_id: Container ID or name to stop.
            timeout: Seconds to wait before killing.

        Raises:
            ContainerError: If stop operation fails.

        """
        _stop_start = time.monotonic()
        with _tracer.start_as_current_span("scylla.container.stop") as _span:
            _span.set_attribute("scylla.container_id", container_id)
            try:
                result = subprocess.run(
                    ["docker", "stop", "-t", str(timeout), container_id],
                    capture_output=True,
                    text=True,
                    timeout=timeout + 30,  # Allow extra time for graceful shutdown
                )

                if result.returncode != 0 and "No such container" not in result.stderr:
                    raise ContainerError(
                        f"Failed to stop container {container_id}: {result.stderr.strip()}"
                    )

            except subprocess.TimeoutExpired:
                # Force kill if stop times out
                self._kill(container_id)
            except subprocess.SubprocessError as e:
                raise ContainerError(f"Failed to stop container: {e}") from e

        try:
            _emitter.emit_counter("scylla_container_lifecycle_total", 1, labels={"event": "stop"})
            _emitter.emit_histogram(
                "scylla_container_stop_seconds",
                time.monotonic() - _stop_start,
                labels={"event": "stop"},
            )
        except Exception as _me:
            logger.warning(f"Container stop metric emission failed (non-fatal): {_me}")

    def _kill(self, container_id: str) -> None:
        """Force kill a container.

        Args:
            container_id: Container ID or name.

        """
        with contextlib.suppress(subprocess.TimeoutExpired, subprocess.SubprocessError):
            subprocess.run(
                ["docker", "kill", container_id],
                capture_output=True,
                text=True,
                timeout=30,
            )

    def remove(self, container_id: str, force: bool = False) -> None:
        """Remove a container.

        Note: Per design decisions, containers are typically preserved for analysis.
        Use this only when explicit cleanup is needed.

        Args:
            container_id: Container ID or name to remove.
            force: Force removal of running container.

        Raises:
            ContainerError: If removal fails.

        """
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(container_id)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 and "No such container" not in result.stderr:
                raise ContainerError(
                    f"Failed to remove container {container_id}: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired:
            raise ContainerError(f"Timed out removing container {container_id}") from None
        except subprocess.SubprocessError as e:
            raise ContainerError(f"Failed to remove container: {e}") from e

    def logs(self, container_id: str, tail: int | None = None) -> tuple[str, str]:
        """Get logs from a container.

        Args:
            container_id: Container ID or name.
            tail: Number of lines to return from end (None = all).

        Returns:
            Tuple of (stdout, stderr).

        Raises:
            ContainerError: If log retrieval fails.

        """
        cmd = ["docker", "logs"]
        if tail is not None:
            cmd.extend(["--tail", str(tail)])
        cmd.append(container_id)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise ContainerError(
                    f"Failed to get logs for {container_id}: {result.stderr.strip()}"
                )

            return result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            raise ContainerError(f"Timed out getting logs for {container_id}") from None
        except subprocess.SubprocessError as e:
            raise ContainerError(f"Failed to get logs: {e}") from e

    def wait(self, container_id: str, timeout: int | None = None) -> int:
        """Wait for a container to exit.

        Args:
            container_id: Container ID or name.
            timeout: Maximum seconds to wait (None = wait forever).

        Returns:
            Container exit code.

        Raises:
            ContainerTimeoutError: If wait exceeds timeout.
            ContainerError: If wait operation fails.

        """
        cmd = ["docker", "wait", container_id]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                raise ContainerError(f"Failed to wait for {container_id}: {result.stderr.strip()}")

            return int(result.stdout.strip())

        except subprocess.TimeoutExpired:
            raise ContainerTimeoutError(
                f"Container {container_id} did not exit within {timeout} seconds"
            ) from None
        except subprocess.SubprocessError as e:
            raise ContainerError(f"Failed to wait for container: {e}") from e
        except ValueError:
            raise ContainerError(f"Invalid exit code from container: {result.stdout}") from None

    def is_running(self, container_id: str) -> bool:
        """Check if a container is currently running.

        Args:
            container_id: Container ID or name.

        Returns:
            True if container is running, False otherwise.

        """
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "-f",
                    "{{.State.Running}}",
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            return result.returncode == 0 and result.stdout.strip() == "true"

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def _get_last_container_id(self) -> str | None:
        """Get the ID of the most recently created container.

        Returns:
            Container ID or None if no containers exist.

        """
        try:
            result = subprocess.run(
                ["docker", "ps", "-lq"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        return None

    @classmethod
    def get_api_keys_from_env(cls, var_names: Sequence[str] | None = None) -> dict[str, str]:
        """Get API keys from environment variables.

        This helper method extracts API keys from the host environment
        for passing to containers via environment variables.

        Args:
            var_names: Variable names to extract. When ``None`` (the default),
                returns every host env var that satisfies
                :meth:`is_secret_var` — that is, any name in
                :attr:`API_KEY_VARS` plus any name ending with one of
                :attr:`API_KEY_SUFFIXES`. Pass an explicit list to restrict
                extraction to those names.

        Returns:
            Dict of variable names to values (only includes set variables).

        """
        if var_names is None:
            return {name: value for name, value in os.environ.items() if cls.is_secret_var(name)}

        return {name: os.environ[name] for name in var_names if name in os.environ}

    def image_exists(self, image: str) -> bool:
        """Check if a Docker image exists locally.

        Args:
            image: Image name with optional tag.

        Returns:
            True if image exists locally, False otherwise.

        """
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                text=True,
                timeout=30,
            )

            return result.returncode == 0

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return False

    def pull_image(self, image: str) -> None:
        """Pull a Docker image from registry.

        Args:
            image: Image name with optional tag.

        Raises:
            ContainerError: If pull fails.

        """
        try:
            result = subprocess.run(
                ["docker", "pull", image],
                capture_output=True,
                text=True,
                timeout=600,  # Images can be large
            )

            if result.returncode != 0:
                raise ContainerError(f"Failed to pull image {image}: {result.stderr.strip()}")

        except subprocess.TimeoutExpired:
            raise ContainerError(f"Timed out pulling image {image}") from None
        except subprocess.SubprocessError as e:
            raise ContainerError(f"Failed to pull image: {e}") from e
