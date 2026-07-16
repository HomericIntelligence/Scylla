"""Scylla - AI agent testing and optimization framework.

This package provides tools for measuring, evaluating, and improving
the performance and cost-efficiency of agentic AI workflows.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

try:
    __version__: str = _get_version("scylla")
except PackageNotFoundError:
    __version__ = "0.0.0"  # fallback when package is not installed

__all__ = [
    "adapters",
    "cli",
    "config",
    "e2e",
    "executor",
    "judge",
    "metrics",
    "nats",
    "reporting",
]
