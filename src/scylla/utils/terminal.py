"""Shared terminal and signal handling utilities.

Provides:
- restore_terminal(): Run stty sane to fix terminal corruption
- install_signal_handlers(): Double-Ctrl+C escalation pattern
- terminal_guard(): Context manager combining both
"""

from __future__ import annotations

import atexit
import contextlib
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager


def restore_terminal() -> None:
    """Restore terminal to sane state using stty.

    No-ops when stdin is not a TTY or when called from a non-main thread
    (stty requires the controlling terminal, which only the main thread owns).
    Swallows all exceptions — safe to call in signal handlers and atexit callbacks.
    """
    with contextlib.suppress(Exception):
        if threading.current_thread() is not threading.main_thread():
            return
        if sys.stdin.isatty():
            subprocess.run(["stty", "sane"], stdin=sys.stdin, check=False)
    # Best effort — never raise during cleanup


# Register as atexit defense-in-depth so the terminal is restored even if
# stop() / terminal_guard().__exit__ never runs (e.g., daemon thread exit).
atexit.register(restore_terminal)

_shutdown_requested = False


def install_signal_handlers(shutdown_fn: Callable[[], None]) -> None:
    """Install SIGINT/SIGTERM handlers with double-Ctrl+C escalation.

    First signal: calls shutdown_fn() and prints a "press Ctrl+C again"
    message — cooperative shutdown.

    Second signal: restores terminal and calls sys.exit(128 + signum) —
    forceful exit.

    Args:
        shutdown_fn: Callable that requests graceful shutdown (sets a flag,
                     cancels futures, etc.).  Must be safe to call from a
                     signal handler (no locks, no I/O other than print).

    """
    global _shutdown_requested
    _shutdown_requested = False

    def _handler(signum: int, frame: object) -> None:
        global _shutdown_requested
        if _shutdown_requested:
            # Second signal — force exit immediately
            restore_terminal()
            sys.exit(128 + signum)
        else:
            _shutdown_requested = True
            print(  # noqa: T201
                f"\nReceived signal {signum}. Shutting down gracefully… "
                "(press Ctrl+C again to force quit)",
                flush=True,
            )
            shutdown_fn()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    # Note: SIGTSTP (Ctrl+Z) is intentionally NOT handled here.
    # It is a job-control signal; callers (e.g., cmd_run) register their
    # own SIGTSTP handler for forceful process-group kill.


@contextmanager
def terminal_guard(shutdown_fn: Callable[[], None] | None = None) -> Generator[None, None, None]:
    """Context manager that installs signal handlers and restores the terminal.

    On enter: installs SIGINT/SIGTERM handlers with double-Ctrl+C escalation
              (if shutdown_fn is provided).
    On exit:  calls restore_terminal() unconditionally.

    Args:
        shutdown_fn: Optional callable for graceful shutdown.  When None,
                     only terminal restoration is set up (no signal handlers).

    Example::

        def request_shutdown() -> None:
            _stop_event.set()

        with terminal_guard(request_shutdown):
            run_workers()

    """
    if shutdown_fn is not None:
        install_signal_handlers(shutdown_fn)
    try:
        yield
    finally:
        restore_terminal()
