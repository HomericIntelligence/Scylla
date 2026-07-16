#!/usr/bin/env python3
"""Shared utilities and constants for Scylla scripts.

This module provides common functionality used across multiple scripts to avoid duplication.

Centralized Utilities:
- LABEL_COLORS: GitHub label colors for evaluation workflow
- get_repo_root(): Repository root finder (imported from hephaestus.utils.helpers)
- get_agents_dir(): .claude/agents path helper
- Colors: ANSI terminal colors with disable() method
"""

import sys
from pathlib import Path
from typing import Any

import tomllib
from hephaestus.utils.helpers import get_repo_root

# Label colors for GitHub issues (evaluation workflow)
LABEL_COLORS = {
    "research": "d4c5f9",  # Light purple
    "evaluation": "1d76db",  # Dark blue
    "metrics": "fbca04",  # Yellow
    "benchmark": "0075ca",  # Blue
    "analysis": "c2e0c6",  # Light green
    "documentation": "0075ca",  # Blue
}


def load_pyproject(repo_root: Path) -> dict[str, Any]:
    """Load and parse ``pyproject.toml`` from *repo_root*.

    Args:
        repo_root: Path to the repository root containing ``pyproject.toml``.

    Returns:
        Parsed TOML data as a dictionary.

    Raises:
        SystemExit: If ``pyproject.toml`` is missing or cannot be parsed.

    """
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        print(f"ERROR: pyproject.toml not found at {pyproject}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(pyproject, "rb") as f:
            data: dict[str, Any] = tomllib.load(f)
            return data
    except Exception as exc:
        print(f"ERROR: Failed to parse pyproject.toml: {exc}", file=sys.stderr)
        sys.exit(1)


def get_agents_dir() -> Path:
    """Get the .claude/agents directory path.

    Returns:
        Path to .claude/agents directory

    Raises:
        RuntimeError: If agents directory doesn't exist

    """
    repo_root = get_repo_root()
    agents_dir = repo_root / ".claude" / "agents"

    if not agents_dir.exists():
        raise RuntimeError(f"Agents directory not found: {agents_dir}")

    return agents_dir


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

    @staticmethod
    def disable() -> None:
        """Disable colors for non-terminal output.

        Sets all color codes to empty strings, useful for piping
        output to files or non-TTY streams.
        """
        Colors.HEADER = ""
        Colors.OKBLUE = ""
        Colors.OKCYAN = ""
        Colors.OKGREEN = ""
        Colors.WARNING = ""
        Colors.FAIL = ""
        Colors.ENDC = ""
        Colors.BOLD = ""
        Colors.UNDERLINE = ""
