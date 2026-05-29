"""Thread-local logging context for E2E experiment execution.

Injects tier_id, subtest_id, and run_num into log records via a
logging.Filter, so parallel workers produce structured log output
without modifying every log call site.

Usage:
    # At entry points (stage functions, worker threads):
    set_log_context(tier_id="T0", subtest_id="00", run_num=1)

    # In logging config:
    handler.addFilter(ContextFilter())

    # In format string:
    "%(tier_id)s/%(subtest_id)s/%(run_num)s"
"""

from __future__ import annotations

import logging
import threading

_context = threading.local()


def set_log_context(
    *,
    tier_id: str = "",
    subtest_id: str = "",
    run_num: int | None = None,
) -> None:
    """Set thread-local logging context fields.

    Args:
        tier_id: Tier identifier (e.g., "T0", "T3").
        subtest_id: Subtest identifier (e.g., "00", "05").
        run_num: Run number (e.g., 1, 2, 3). None clears the field.

    """
    _context.tier_id = tier_id
    _context.subtest_id = subtest_id
    _context.run_num = run_num


def clear_log_context() -> None:
    """Clear all thread-local logging context fields."""
    _context.tier_id = ""
    _context.subtest_id = ""
    _context.run_num = None


def current_tier_id() -> str:
    """Return the tier_id from the current thread's log context, or empty string."""
    return getattr(_context, "tier_id", "")


class ContextFilter(logging.Filter):
    """Logging filter that injects thread-local tier/subtest/run context.

    Adds ``tier_id``, ``subtest_id``, and ``run_num`` attributes to every
    log record.  When no context has been set on the current thread, the
    attributes default to empty strings / empty string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject context fields into log record."""
        record.tier_id = getattr(_context, "tier_id", "")
        record.subtest_id = getattr(_context, "subtest_id", "")
        run_num = getattr(_context, "run_num", None)
        record.run_num = str(run_num) if run_num is not None else ""
        return True
