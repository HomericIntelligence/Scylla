"""Main E2E experiment runner.

This module provides the main entry point for running E2E experiments,
coordinating tier execution, inheritance, result aggregation, and report generation.

This module is a thin facade — its implementation lives in
:mod:`scylla.e2e.runner_internals`. The public API (every name listed in
``__all__``) is preserved for backward compatibility.
"""

from __future__ import annotations

# Shutdown coordination is re-exported from scylla.e2e.shutdown for backward
# compatibility (see __all__ below). Callers needing only these symbols should
# import scylla.e2e.shutdown directly.
from scylla.e2e.runner_internals.experiment_entrypoint import (
    run_experiment as run_experiment,
)
from scylla.e2e.runner_internals.runner_core import (
    E2ERunner as E2ERunner,
)
from scylla.e2e.runner_internals.tier_context import (
    TierContext as TierContext,
)
from scylla.e2e.shutdown import (
    ShutdownInterruptedError as ShutdownInterruptedError,
)
from scylla.e2e.shutdown import (
    is_shutdown_requested as is_shutdown_requested,
)
from scylla.e2e.shutdown import (
    request_shutdown as request_shutdown,
)

__all__ = [
    "E2ERunner",
    "ShutdownInterruptedError",
    "TierContext",
    "is_shutdown_requested",
    "request_shutdown",
    "run_experiment",
]
