"""Unit tests for Docker container orchestration.

Tests cover:
- Docker availability checking
- Container configuration building
- Container lifecycle (run, stop, remove)
- Environment variable handling (including API keys)
- Workspace mounting
- Output capture (stdout/stderr)
- Timeout handling
- Error conditions
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scylla.executor import (
    ContainerConfig,
    ContainerError,
    ContainerResult,
    ContainerTimeoutError,
    DockerError,
    DockerExecutor,
    DockerNotAvailableError,
)


class TestDockerAvailability:
    """Tests for Docker availability checking."""

    @patch("subprocess.run")
    def test_docker_available(self, mock_run: MagicMock) -> None:
        """DockerExecutor initializes successfully when Docker is available."""
        mock_run.return_value = MagicMock(returncode=0)

        executor = DockerExecutor()

        mock_run.assert_called_once()
        assert "docker" in mock_run.call_args[0][0]
        assert executor is not None

    @patch("subprocess.run")
    def test_docker_not_running(self, mock_run: MagicMock) -> None:
        """DockerExecutor raises error when Docker daemon is not running."""
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Cannot connect to the Docker daemon"
        )

        with pytest.raises(DockerNotAvailableError, match="not running"):
            DockerExecutor()

    @patch("subprocess.run")
    def test_docker_not_installed(self, mock_run: MagicMock) -> None:
        """DockerExecutor raises error when Docker is not installed."""
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(DockerNotAvailableError, match="not installed"):
            DockerExecutor()

    @patch("subprocess.run")
    def test_docker_info_timeout(self, mock_run: MagicMock) -> None:
        """DockerExecutor raises error when docker info times out."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=30)

        with pytest.raises(DockerNotAvailableError, match="timed out"):
            DockerExecutor()


class TestContainerConfig:
    """Tests for ContainerConfig dataclass."""

    def test_minimal_config(self) -> None:
        """Create config with only required fields."""
        config = ContainerConfig(image="python:3.12-slim")

        assert config.image == "python:3.12-slim"
        assert config.name is None
        assert config.workspace_path is None
        assert config.workspace_mount == "/workspace"
        assert config.env_vars == {}
        assert config.command == []
        assert config.timeout_seconds == 3600
        assert config.working_dir is None
        assert config.network == "none"

    def test_full_config(self) -> None:
        """Create config with all fields."""
        config = ContainerConfig(
            image="python:3.12-slim",
            name="test-container",
            workspace_path=Path("/tmp/workspace"),
            workspace_mount="/app",
            env_vars={"KEY": "value"},
            command=["python", "main.py"],
            timeout_seconds=600,
            working_dir="/app",
            network="bridge",
        )

        assert config.image == "python:3.12-slim"
        assert config.name == "test-container"
        assert config.workspace_path == Path("/tmp/workspace")
        assert config.workspace_mount == "/app"
        assert config.env_vars == {"KEY": "value"}
        assert config.command == ["python", "main.py"]
        assert config.timeout_seconds == 600
        assert config.working_dir == "/app"
        assert config.network == "bridge"


class TestContainerResult:
    """Tests for ContainerResult dataclass."""

    def test_successful_result(self) -> None:
        """Create result for successful container execution."""
        result = ContainerResult(
            container_id="abc123",
            exit_code=0,
            stdout="output",
            stderr="",
        )

        assert result.container_id == "abc123"
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.timed_out is False

    def test_failed_result(self) -> None:
        """Create result for failed container execution."""
        result = ContainerResult(
            container_id="abc123",
            exit_code=1,
            stdout="",
            stderr="error message",
        )

        assert result.exit_code == 1
        assert result.stderr == "error message"

    def test_timeout_result(self) -> None:
        """Create result for timed out container."""
        result = ContainerResult(
            container_id="abc123",
            exit_code=-1,
            stdout="partial output",
            stderr="",
            timed_out=True,
        )

        assert result.exit_code == -1
        assert result.timed_out is True


class TestBuildRunCommand:
    """Tests for building docker run command."""

    @patch("subprocess.run")
    def test_minimal_command(self, mock_run: MagicMock) -> None:
        """Build command with minimal configuration."""
        mock_run.return_value = MagicMock(returncode=0)
        executor = DockerExecutor()

        config = ContainerConfig(image="python:3.12-slim")
        cmd = executor._build_run_command(config)

        assert cmd[0:2] == ["docker", "run"]
        assert "--network" in cmd
        assert "none" in cmd
        assert "python:3.12-slim" in cmd

    @patch("subprocess.run")
    def test_command_with_name(self, mock_run: MagicMock) -> None:
        """Build command with container name."""
        mock_run.return_value = MagicMock(returncode=0)
        executor = DockerExecutor()

        config = ContainerConfig(image="python:3.12-slim", name="test-container")
        cmd = executor._build_run_command(config)

        name_idx = cmd.index("--name")
        assert cmd[name_idx + 1] == "test-container"

    @patch("subprocess.run")
    def test_command_with_workspace(self, mock_run: MagicMock) -> None:
        """Build command with workspace mount."""
        mock_run.return_value = MagicMock(returncode=0)
        executor = DockerExecutor()

        config = ContainerConfig(
            image="python:3.12-slim",
            workspace_path=Path("/tmp/workspace"),
        )
        cmd = executor._build_run_command(config)

        assert "-v" in cmd
        v_idx = cmd.index("-v")
        assert "/tmp/workspace:/workspace" in cmd[v_idx + 1]

    @patch("subprocess.run")
    def test_command_with_env_vars(self, mock_run: MagicMock) -> None:
        """Build command with environment variables."""
        mock_run.return_value = MagicMock(returncode=0)
        executor = DockerExecutor()

        config = ContainerConfig(
            image="python:3.12-slim",
            env_vars={"API_KEY": "secret", "DEBUG": "true"},
        )
        cmd = executor._build_run_command(config)

        # Check that -e flags are present for each env var
        e_indices = [i for i, x in enumerate(cmd) if x == "-e"]
        assert len(e_indices) == 2

        # Check env var values follow -e flags
        env_values = [cmd[i + 1] for i in e_indices]
        assert "API_KEY=secret" in env_values
        assert "DEBUG=true" in env_values

    @patch("subprocess.run")
    def test_command_with_custom_command(self, mock_run: MagicMock) -> None:
        """Build command with custom command to run."""
        mock_run.return_value = MagicMock(returncode=0)
        executor = DockerExecutor()

        config = ContainerConfig(
            image="python:3.12-slim",
            command=["python", "-c", "print('hello')"],
        )
        cmd = executor._build_run_command(config)

        # Command should be at the end after image
        img_idx = cmd.index("python:3.12-slim")
        assert cmd[img_idx + 1 :] == ["python", "-c", "print('hello')"]


class TestContainerRun:
    """Tests for running containers."""

    @patch("subprocess.run")
    def test_run_successful(self, mock_run: MagicMock) -> None:
        """Run container successfully."""
        # First call for docker info, second for docker run
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="output", stderr=""),  # docker run
        ]

        executor = DockerExecutor()
        config = ContainerConfig(
            image="python:3.12-slim",
            name="test-container",
            command=["echo", "hello"],
        )
        result = executor.run(config)

        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.timed_out is False

    @patch("subprocess.run")
    def test_run_with_failure(self, mock_run: MagicMock) -> None:
        """Run container that exits with error."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=1, stdout="", stderr="command not found"),
        ]

        executor = DockerExecutor()
        config = ContainerConfig(image="python:3.12-slim", name="test-container")
        result = executor.run(config)

        assert result.exit_code == 1
        assert result.stderr == "command not found"

    @patch("subprocess.run")
    def test_run_timeout(self, mock_run: MagicMock) -> None:
        """Run container that times out."""
        import subprocess

        # Create TimeoutExpired and set stdout/stderr as attributes
        # (Python 3.14 doesn't accept these as constructor kwargs)
        timeout_error = subprocess.TimeoutExpired(cmd="docker", timeout=60)
        timeout_error.stdout = b"partial"
        timeout_error.stderr = b""

        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            timeout_error,
            MagicMock(returncode=0),  # docker stop
        ]

        executor = DockerExecutor()
        config = ContainerConfig(
            image="python:3.12-slim",
            name="test-container",
            timeout_seconds=60,
        )
        result = executor.run(config)

        assert result.exit_code == -1
        assert result.timed_out is True
        assert result.stdout == "partial"


class TestContainerStop:
    """Tests for stopping containers."""

    @patch("subprocess.run")
    def test_stop_running_container(self, mock_run: MagicMock) -> None:
        """Stop a running container."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0),  # docker stop
        ]

        executor = DockerExecutor()
        executor.stop("test-container")

        # Verify docker stop was called
        stop_call = mock_run.call_args_list[1]
        assert "docker" in stop_call[0][0]
        assert "stop" in stop_call[0][0]
        assert "test-container" in stop_call[0][0]

    @patch("subprocess.run")
    def test_stop_nonexistent_container(self, mock_run: MagicMock) -> None:
        """Stop non-existent container doesn't raise error."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=1, stderr="No such container"),
        ]

        executor = DockerExecutor()
        # Should not raise
        executor.stop("nonexistent-container")


class TestContainerRemove:
    """Tests for removing containers."""

    @patch("subprocess.run")
    def test_remove_stopped_container(self, mock_run: MagicMock) -> None:
        """Remove a stopped container."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0),  # docker rm
        ]

        executor = DockerExecutor()
        executor.remove("test-container")

        rm_call = mock_run.call_args_list[1]
        assert "rm" in rm_call[0][0]

    @patch("subprocess.run")
    def test_remove_force(self, mock_run: MagicMock) -> None:
        """Force remove a container."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0),  # docker rm -f
        ]

        executor = DockerExecutor()
        executor.remove("test-container", force=True)

        rm_call = mock_run.call_args_list[1]
        assert "-f" in rm_call[0][0]


class TestContainerLogs:
    """Tests for getting container logs."""

    @patch("subprocess.run")
    def test_get_logs(self, mock_run: MagicMock) -> None:
        """Get logs from container."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="log output", stderr="log errors"),
        ]

        executor = DockerExecutor()
        stdout, stderr = executor.logs("test-container")

        assert stdout == "log output"
        assert stderr == "log errors"

    @patch("subprocess.run")
    def test_get_logs_with_tail(self, mock_run: MagicMock) -> None:
        """Get last N lines of logs."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="last lines", stderr=""),
        ]

        executor = DockerExecutor()
        executor.logs("test-container", tail=10)

        logs_call = mock_run.call_args_list[1]
        assert "--tail" in logs_call[0][0]
        assert "10" in logs_call[0][0]


class TestContainerWait:
    """Tests for waiting on containers."""

    @patch("subprocess.run")
    def test_wait_for_exit(self, mock_run: MagicMock) -> None:
        """Wait for container to exit."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="0\n"),  # docker wait
        ]

        executor = DockerExecutor()
        exit_code = executor.wait("test-container")

        assert exit_code == 0

    @patch("subprocess.run")
    def test_wait_timeout(self, mock_run: MagicMock) -> None:
        """Wait times out."""
        import subprocess

        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            subprocess.TimeoutExpired(cmd="docker", timeout=60),
        ]

        executor = DockerExecutor()

        with pytest.raises(ContainerTimeoutError, match="did not exit"):
            executor.wait("test-container", timeout=60)


class TestContainerStatus:
    """Tests for checking container status."""

    @patch("subprocess.run")
    def test_is_running_true(self, mock_run: MagicMock) -> None:
        """Check if container is running (true case)."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="true"),  # docker inspect
        ]

        executor = DockerExecutor()
        assert executor.is_running("test-container") is True

    @patch("subprocess.run")
    def test_is_running_false(self, mock_run: MagicMock) -> None:
        """Check if container is running (false case)."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="false"),  # docker inspect
        ]

        executor = DockerExecutor()
        assert executor.is_running("test-container") is False


class TestAPIKeyHandling:
    """Tests for API key environment variable handling."""

    def test_get_api_keys_from_env(self) -> None:
        """Get API keys from environment."""
        with patch.dict(
            "os.environ",
            {"ANTHROPIC_API_KEY": "ant-key", "OPENAI_API_KEY": "oai-key"},
            clear=True,
        ):
            keys = DockerExecutor.get_api_keys_from_env()

            assert "ANTHROPIC_API_KEY" in keys
            assert keys["ANTHROPIC_API_KEY"] == "ant-key"
            assert "OPENAI_API_KEY" in keys
            assert keys["OPENAI_API_KEY"] == "oai-key"

    def test_get_api_keys_missing(self) -> None:
        """Get API keys when some are missing."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "ant-key"}, clear=True):
            keys = DockerExecutor.get_api_keys_from_env()

            assert "ANTHROPIC_API_KEY" in keys
            assert "OPENAI_API_KEY" not in keys

    def test_get_api_keys_custom_vars(self) -> None:
        """Get custom environment variables."""
        with patch.dict("os.environ", {"MY_API_KEY": "my-key", "OTHER_KEY": "other"}, clear=True):
            keys = DockerExecutor.get_api_keys_from_env(["MY_API_KEY", "OTHER_KEY"])

            assert keys == {"MY_API_KEY": "my-key", "OTHER_KEY": "other"}

    def test_is_secret_var_explicit_match(self) -> None:
        """Names in API_KEY_VARS are treated as secrets."""
        assert DockerExecutor.is_secret_var("ANTHROPIC_API_KEY") is True
        assert DockerExecutor.is_secret_var("OPENAI_API_KEY") is True

    def test_is_secret_var_suffix_match(self) -> None:
        """Names ending with an API_KEY_SUFFIXES entry are treated as secrets."""
        assert DockerExecutor.is_secret_var("FOO_API_KEY") is True
        assert DockerExecutor.is_secret_var("DATABASE_PASSWORD") is True
        assert DockerExecutor.is_secret_var("GITHUB_TOKEN") is True
        assert DockerExecutor.is_secret_var("STRIPE_SECRET") is True

    def test_is_secret_var_negative_cases(self) -> None:
        """Names without an exact match or qualifying suffix are not secrets."""
        # Bare ``_KEY`` was deliberately excluded due to false-positive risk.
        assert DockerExecutor.is_secret_var("PUBLIC_KEY_PATH") is False
        assert DockerExecutor.is_secret_var("CACHE_KEY") is False
        # Affixes elsewhere in the name don't count.
        assert DockerExecutor.is_secret_var("TOKEN_PATH") is False
        assert DockerExecutor.is_secret_var("PASSWORD_FILE") is False
        # Empty / unrelated.
        assert DockerExecutor.is_secret_var("") is False
        assert DockerExecutor.is_secret_var("HOME") is False

    def test_get_api_keys_from_env_includes_suffix_matches(self) -> None:
        """Default extraction picks up suffix-matching names not in API_KEY_VARS."""
        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "ant-key",
                "FOO_API_KEY": "foo-key",
                "GITHUB_TOKEN": "gh-tok",
                "DATABASE_PASSWORD": "pw",
                "STRIPE_SECRET": "ss",
                "CACHE_KEY": "ck",
                "HOME": "/home/test",
            },
            clear=True,
        ):
            keys = DockerExecutor.get_api_keys_from_env()

            assert keys == {
                "ANTHROPIC_API_KEY": "ant-key",
                "FOO_API_KEY": "foo-key",
                "GITHUB_TOKEN": "gh-tok",
                "DATABASE_PASSWORD": "pw",
                "STRIPE_SECRET": "ss",
            }

    def test_get_api_keys_explicit_var_names_unaffected(self) -> None:
        """Explicit var_names argument is unchanged by suffix logic."""
        with patch.dict(
            "os.environ",
            {"FOO_API_KEY": "foo-key", "OTHER": "other"},
            clear=True,
        ):
            keys = DockerExecutor.get_api_keys_from_env(["OTHER"])
            assert keys == {"OTHER": "other"}


class TestImageOperations:
    """Tests for Docker image operations."""

    @patch("subprocess.run")
    def test_image_exists_true(self, mock_run: MagicMock) -> None:
        """Check if image exists (true case)."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0),  # docker image inspect
        ]

        executor = DockerExecutor()
        assert executor.image_exists("python:3.12-slim") is True

    @patch("subprocess.run")
    def test_image_exists_false(self, mock_run: MagicMock) -> None:
        """Check if image exists (false case)."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=1),  # docker image inspect
        ]

        executor = DockerExecutor()
        assert executor.image_exists("nonexistent:latest") is False

    @patch("subprocess.run")
    def test_pull_image_success(self, mock_run: MagicMock) -> None:
        """Pull image successfully."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0),  # docker pull
        ]

        executor = DockerExecutor()
        executor.pull_image("python:3.12-slim")

        pull_call = mock_run.call_args_list[1]
        assert "pull" in pull_call[0][0]
        assert "python:3.12-slim" in pull_call[0][0]

    @patch("subprocess.run")
    def test_pull_image_failure(self, mock_run: MagicMock) -> None:
        """Pull image fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=1, stderr="image not found"),
        ]

        executor = DockerExecutor()

        with pytest.raises(ContainerError, match="Failed to pull"):
            executor.pull_image("nonexistent:latest")


class TestDetachedMode:
    """Tests for running containers in detached mode."""

    @patch("subprocess.run")
    def test_run_detached(self, mock_run: MagicMock) -> None:
        """Run container in detached mode."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=0, stdout="abc123def456"),  # docker run -d
        ]

        executor = DockerExecutor()
        config = ContainerConfig(image="python:3.12-slim")
        container_id = executor.run_detached(config)

        assert container_id == "abc123def456"

        run_call = mock_run.call_args_list[1]
        assert "-d" in run_call[0][0]

    @patch("subprocess.run")
    def test_run_detached_failure(self, mock_run: MagicMock) -> None:
        """Run detached fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # docker info
            MagicMock(returncode=1, stderr="error starting container"),
        ]

        executor = DockerExecutor()
        config = ContainerConfig(image="python:3.12-slim")

        with pytest.raises(ContainerError, match="Failed to start"):
            executor.run_detached(config)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_docker_error_is_exception(self) -> None:
        """DockerError inherits from Exception."""
        assert issubclass(DockerError, Exception)

    def test_docker_not_available_is_docker_error(self) -> None:
        """DockerNotAvailableError inherits from DockerError."""
        assert issubclass(DockerNotAvailableError, DockerError)

    def test_container_error_is_docker_error(self) -> None:
        """ContainerError inherits from DockerError."""
        assert issubclass(ContainerError, DockerError)

    def test_container_timeout_is_container_error(self) -> None:
        """ContainerTimeoutError inherits from ContainerError."""
        assert issubclass(ContainerTimeoutError, ContainerError)
