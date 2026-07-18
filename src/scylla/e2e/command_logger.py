"""Command logging for E2E test reproducibility.

This module provides command logging functionality that captures all
executed commands with their context, enabling full reproducibility
of test runs.
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _is_existing_file(candidate: str) -> bool:
    """Return True iff ``candidate`` names an existing regular file.

    Unlike a bare ``Path(candidate).is_file()`` this never raises when the
    string is not a usable path. Command arguments can be arbitrary content
    (e.g. a long inline prompt) that exceeds the OS filename limit or contains
    embedded NUL bytes; ``os.stat`` then raises ``OSError`` (ENAMETOOLONG,
    errno 36) or ``ValueError``. Python 3.14's ``Path.is_file()`` swallows
    these and returns False, but Python <= 3.13 lets them propagate, so we
    normalise the behaviour here.
    """
    try:
        return Path(candidate).is_file()
    except (OSError, ValueError):
        return False


class CommandLog(BaseModel):
    """A single logged command with full context.

    Captures everything needed to reproduce a command execution.

    Attributes:
        timestamp: ISO format timestamp of execution
        command: The command as a list of arguments
        cwd: Working directory when command was executed
        env_vars: Relevant environment variables
        exit_code: Process exit code
        stdout_file: Relative path to stdout log file
        stderr_file: Relative path to stderr log file
        duration_seconds: Execution duration in seconds

    """

    timestamp: str = Field(..., description="ISO format timestamp of execution")
    command: list[str] = Field(..., description="The command as a list of arguments")
    cwd: str = Field(..., description="Working directory when command was executed")
    env_vars: dict[str, str] = Field(..., description="Relevant environment variables")
    exit_code: int = Field(..., description="Process exit code")
    stdout_file: str = Field(..., description="Relative path to stdout log file")
    stderr_file: str = Field(..., description="Relative path to stderr log file")
    duration_seconds: float = Field(..., description="Execution duration in seconds")


# Environment variables relevant for reproducibility
RELEVANT_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "VIRTUAL_ENV",
]


class CommandLogger(BaseModel):
    """Logger that captures commands for reproducibility.

    Tracks all executed commands with their context and generates
    replay scripts for reproducing test runs.

    Example:
        >>> logger = CommandLogger(log_dir=Path("/results/run_01/logs"))
        >>> logger.log_command(
        ...     cmd=["claude", "--print", "hello"],
        ...     stdout="Hello!",
        ...     stderr="",
        ...     exit_code=0,
        ...     duration=1.5,
        ...     cwd="/workspace",
        ... )
        >>> logger.save()
        >>> replay_script = logger.save_replay_script()

    """

    log_dir: Path = Field(..., description="Directory for command logs")
    commands: list[CommandLog] = Field(default_factory=list, description="List of logged commands")

    model_config = {"arbitrary_types_allowed": True}

    def model_post_init(self, __context: Any) -> None:
        """Initialize the log directory."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _extract_relevant_env(self) -> dict[str, str]:
        """Extract relevant environment variables for reproducibility."""
        env_vars = {}
        for var in RELEVANT_ENV_VARS:
            value = os.environ.get(var)
            if value:
                # Mask sensitive values
                if "KEY" in var or "TOKEN" in var or "SECRET" in var:
                    env_vars[var] = "[REDACTED]"
                else:
                    env_vars[var] = value
        return env_vars

    def log_command(
        self,
        cmd: list[str],
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
        cwd: str | Path | None = None,
    ) -> CommandLog:
        """Log a command execution with all context.

        Args:
            cmd: The command as a list of arguments
            stdout: Standard output from the command
            stderr: Standard error from the command
            exit_code: Process exit code
            duration: Execution duration in seconds
            cwd: Working directory (defaults to current)

        Returns:
            The created CommandLog entry.

        """
        cmd_index = len(self.commands)
        stdout_file = f"cmd_{cmd_index:04d}_stdout.log"
        stderr_file = f"cmd_{cmd_index:04d}_stderr.log"

        # Write stdout/stderr to files
        (self.log_dir / stdout_file).write_text(stdout)
        (self.log_dir / stderr_file).write_text(stderr)

        log = CommandLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            command=cmd,
            cwd=str(cwd) if cwd else str(Path.cwd()),
            env_vars=self._extract_relevant_env(),
            exit_code=exit_code,
            stdout_file=stdout_file,
            stderr_file=stderr_file,
            duration_seconds=duration,
        )

        self.commands.append(log)
        return log

    def update_last_command(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration: float,
    ) -> None:
        """Update the most recently logged command with execution results.

        This is useful when a command is logged before execution (to generate
        replay.sh), then updated with actual results after execution.

        Args:
            stdout: Standard output from the command
            stderr: Standard error from the command
            exit_code: Process exit code
            duration: Execution duration in seconds

        """
        if not self.commands:
            raise ValueError("No commands to update")

        last_cmd = self.commands[-1]

        # Update log files
        (self.log_dir / last_cmd.stdout_file).write_text(stdout)
        (self.log_dir / last_cmd.stderr_file).write_text(stderr)

        # Update command metadata
        last_cmd.exit_code = exit_code
        last_cmd.duration_seconds = duration
        last_cmd.timestamp = datetime.now(timezone.utc).isoformat()

    def save(self) -> Path:
        """Save the command log to JSON file.

        Returns:
            Path to the saved JSON file.

        """
        log_path = self.log_dir / "command_log.json"
        with open(log_path, "w") as f:
            json.dump(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_commands": len(self.commands),
                    "commands": [c.model_dump() for c in self.commands],
                },
                f,
                indent=2,
            )
        return log_path

    def save_replay_script(self) -> Path:
        """Generate an executable bash script to replay all commands.

        The script includes environment setup, directory navigation,
        and all commands in execution order. For Claude Code commands with
        prompts, extracts the prompt to a separate prompt.md file and
        references it in the replay script.

        Returns:
            Path to the generated replay.sh script.

        """
        script_path = self.log_dir / "replay.sh"
        prompt_path = self.log_dir / "replay_prompt.md"

        lines = [
            "#!/bin/bash",
            f"# Generated: {datetime.now(timezone.utc).isoformat()}",
            f"# Total commands: {len(self.commands)}",
            "#",
            "# This script executes commands for the test run.",
            "# All output is captured to stdout/stderr logs.",
            "#",
            "set -e  # Exit on first error",
            "set -x  # Print commands as they execute",
            "",
            "# Environment variables (secrets redacted)",
            "# Uncomment and fill in as needed:",
        ]

        # Add env var placeholders
        for var in RELEVANT_ENV_VARS:
            if "KEY" in var or "TOKEN" in var or "SECRET" in var:
                lines.append(f"# export {var}='your-{var.lower().replace('_', '-')}-here'")

        lines.append("")
        lines.append("# Commands")
        lines.append("")

        for i, log in enumerate(self.commands):
            lines.append(f"# Command {i + 1}/{len(self.commands)} at {log.timestamp}")
            lines.append(f"# Duration: {log.duration_seconds:.2f}s, Exit: {log.exit_code}")
            lines.append(f"cd {shlex.quote(log.cwd)}")

            # Check if this is a claude command with a prompt argument
            if len(log.command) > 0 and "claude" in log.command[0].lower() and len(log.command) > 1:
                prompt = log.command[-1]
                # If last arg is already a file path, use it directly.
                # `prompt` is arbitrary command content, not necessarily a
                # valid path: an inline prompt can exceed the OS filename
                # limit (NAME_MAX, typically 255 bytes) or contain embedded
                # NUL bytes. On Python <= 3.13 `Path(...).is_file()` lets the
                # resulting OSError/ValueError propagate (e.g. ENAMETOOLONG,
                # errno 36); Python 3.14 swallows it. Guard explicitly so the
                # check means "an existing file" on every interpreter.
                if _is_existing_file(prompt):
                    cmd_without_prompt = log.command[:-1]
                    cmd_str = " ".join(shlex.quote(arg) for arg in cmd_without_prompt)
                    lines.append(f"{cmd_str} {shlex.quote(prompt)}")
                    lines.append("")
                    continue
                # Only extract if it looks like a multi-line prompt
                if len(prompt) > 100 or "\n" in prompt:
                    prompt_path.write_text(prompt)
                    # Build command referencing replay_prompt.md with absolute path
                    # replay.sh is in agent/, replay_prompt.md is also in agent/
                    # But command runs from workspace/, so use absolute path
                    cmd_without_prompt = log.command[:-1]
                    cmd_str = " ".join(shlex.quote(arg) for arg in cmd_without_prompt)
                    abs_prompt_path = prompt_path.resolve()
                    lines.append(f"{cmd_str} {shlex.quote(str(abs_prompt_path))}")
                    lines.append("")
                    continue

            # Default: quote each argument properly
            cmd_str = " ".join(shlex.quote(arg) for arg in log.command)
            lines.append(cmd_str)
            lines.append("")

        script_content = "\n".join(lines)
        script_path.write_text(script_content)

        # Make executable
        script_path.chmod(0o755)

        return script_path

    @classmethod
    def load(cls, log_dir: Path) -> CommandLogger:
        """Load a command logger from a saved JSON file.

        Args:
            log_dir: Directory containing command_log.json

        Returns:
            CommandLogger with loaded commands.

        """
        log_path = log_dir / "command_log.json"
        with open(log_path) as f:
            data = json.load(f)

        logger = cls(log_dir=log_dir)
        logger.commands = [CommandLog.model_validate(c) for c in data["commands"]]
        return logger
