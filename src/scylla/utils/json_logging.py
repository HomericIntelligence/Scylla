"""Opt-in structured JSON logging for Scylla.

This module provides a stdlib-only :class:`JsonFormatter` and a
:func:`configure_json_logging` helper that installs it on the root logger.

Default behaviour of the application is unchanged. To opt in, set the
environment variable ``SCYLLA_JSON_LOGS=1`` before invoking the CLI, or
call :func:`configure_json_logging` directly from a programmatic entry
point.

Example::

    SCYLLA_JSON_LOGS=1 uv run scylla run-tier T0

Each emitted record is a single JSON object on its own line with the
fields ``timestamp`` (ISO-8601 UTC), ``level``, ``name``, and
``message``. Any keyword arguments passed via ``logger.info(..., extra=...)``
are merged into the object. Exception information, when present, is
serialised under the ``traceback`` key.

No third-party dependencies are introduced; this is intentional so the
foundation can be adopted incrementally without touching existing
``logger.info(...)`` call sites.

When the OpenTelemetry API is importable AND a recording span is active
at log time, the formatter additionally injects ``trace_id`` (32-char
lowercase hex) and ``span_id`` (16-char lowercase hex) fields, matching
the OpenTelemetry log-correlation convention. OpenTelemetry remains an
optional dependency: when not installed, these fields are silently
omitted.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, TextIO

__all__ = [
    "JsonFormatter",
    "configure_json_logging",
    "is_json_logging_enabled",
]

# Module-level lazy probe for the OpenTelemetry trace API. Cached on first
# use of :meth:`JsonFormatter.format` so the import attempt happens at most
# once per process. The sentinel ``_OTEL_PROBED`` distinguishes "not yet
# probed" from "probed and unavailable" (``_OTEL_TRACE_MODULE is None``).
_OTEL_TRACE_MODULE: Any = None
_OTEL_PROBED: bool = False

# Standard LogRecord attributes that should NOT be copied into the
# JSON payload as "extras". See logging.LogRecord docs.
_RESERVED_LOGRECORD_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_ENV_VAR = "SCYLLA_JSON_LOGS"
_CONFIGURED_FLAG = "_scylla_json_logging_configured"


def _extract_otel_trace_ids() -> dict[str, str]:
    """Return ``{"trace_id": ..., "span_id": ...}`` for the current OTel span.

    Returns an empty dict when the OpenTelemetry API is not importable, when
    no span is active, or when the active span context is not valid. The
    trace_id is rendered as a 32-char lowercase hex string and the span_id
    as 16-char lowercase hex, matching the OpenTelemetry log-correlation
    convention.
    """
    global _OTEL_TRACE_MODULE, _OTEL_PROBED
    if not _OTEL_PROBED:
        try:
            from opentelemetry import trace as _otel_trace
        except ImportError:
            _OTEL_TRACE_MODULE = None
        else:
            _OTEL_TRACE_MODULE = _otel_trace
        _OTEL_PROBED = True

    trace_mod = _OTEL_TRACE_MODULE
    if trace_mod is None:
        return {}

    span = trace_mod.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return {}
    return {
        "trace_id": f"{ctx.trace_id:032x}",
        "span_id": f"{ctx.span_id:016x}",
    }


class JsonFormatter(logging.Formatter):
    """Format :class:`logging.LogRecord` instances as a single JSON line.

    The formatter is dependency-free and emits a deterministic field
    ordering: ``timestamp``, ``level``, ``name``, ``message``, then any
    extras supplied via ``logger.info(..., extra={...})``. When the
    record carries exception info, a ``traceback`` field is appended.
    """

    # Context fields injected by ``scylla.e2e.log_context.ContextFilter``
    # are omitted from the JSON payload when their value is empty/None, to
    # keep logs clean when no thread-local context is set.
    _OMIT_IF_EMPTY: frozenset[str] = frozenset({"tier_id", "subtest_id", "run_num"})

    def format(self, record: logging.LogRecord) -> str:
        """Render *record* as a single-line JSON string."""
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Merge user-provided extras (anything not in the reserved set).
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS or key.startswith("_"):
                continue
            if key in self._OMIT_IF_EMPTY and not value:
                continue
            payload[key] = value

        # OTel trace correlation (best-effort; absent when OTel is not
        # installed or no recording span is active).
        payload.update(_extract_otel_trace_ids())

        if record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["traceback"] = record.exc_text

        return json.dumps(payload, default=str)


def configure_json_logging(
    level: str = "INFO",
    *,
    stream: TextIO | None = None,
) -> None:
    """Install :class:`JsonFormatter` on the root logger.

    Idempotent: calling this multiple times will replace the formatter
    on the existing handler rather than stacking new handlers.

    Args:
        level: Logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        stream: Optional output stream; defaults to ``sys.stderr`` to
            match Python's stdlib :func:`logging.basicConfig` behaviour.

    """
    root = logging.getLogger()
    target_stream: TextIO = stream if stream is not None else sys.stderr
    formatter = JsonFormatter()
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Look for an existing handler we previously installed so this stays
    # idempotent across repeated calls (e.g. from CLI re-entry in tests).
    json_handler: logging.Handler | None = None
    for handler in root.handlers:
        if getattr(handler, _CONFIGURED_FLAG, False):
            json_handler = handler
            break

    if json_handler is None:
        json_handler = logging.StreamHandler(target_stream)
        setattr(json_handler, _CONFIGURED_FLAG, True)
        root.addHandler(json_handler)
    else:
        json_handler.setStream(target_stream)  # type: ignore[attr-defined]

    json_handler.setFormatter(formatter)
    json_handler.setLevel(numeric_level)
    root.setLevel(numeric_level)

    # Lazy import avoids a circular dependency between
    # ``scylla.utils.json_logging`` and ``scylla.e2e.log_context``.
    from scylla.e2e.log_context import ContextFilter

    if not any(isinstance(f, ContextFilter) for f in json_handler.filters):
        json_handler.addFilter(ContextFilter())


def is_json_logging_enabled() -> bool:
    """Return ``True`` if ``SCYLLA_JSON_LOGS`` is set to a truthy value."""
    raw = os.environ.get(_ENV_VAR, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}
