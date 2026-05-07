"""Metric emitter abstraction for time-series database integration.

Provides a pluggable :class:`MetricEmitter` interface so operators can wire
ProjectScylla metrics (pass rates, CoP, latency) to a TSDB without touching
the metric-computation call sites.

The default :func:`get_default_emitter` returns a :class:`NoOpEmitter` unless
``SCYLLA_METRICS_PATH`` is set, in which case a
:class:`PrometheusTextfileEmitter` is returned. This module deliberately
introduces no new runtime dependencies — the textfile output is plain text
that the Prometheus node-exporter ``textfile`` collector (or VictoriaMetrics
``vmagent``) ingests natively.

This is opt-in scaffolding only; no existing metrics call site is wired to an
emitter yet. See ``docs/dev/metrics-emitter.md`` for the integration plan.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock

__all__ = [
    "MetricEmitter",
    "NoOpEmitter",
    "PrometheusTextfileEmitter",
    "get_default_emitter",
]


def _format_labels(labels: dict[str, str] | None) -> str:
    """Render labels as Prometheus-style ``{k="v",k2="v2"}`` (empty if none)."""
    if not labels:
        return ""
    # Escape backslash, double-quote, and newline per Prometheus exposition format.
    parts = []
    for key in sorted(labels):
        value = labels[key].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append(f'{key}="{value}"')
    return "{" + ",".join(parts) + "}"


class MetricEmitter(ABC):
    """Abstract base class for metric emitters."""

    @abstractmethod
    def emit_counter(
        self,
        name: str,
        value: int,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Emit a monotonic counter sample."""

    @abstractmethod
    def emit_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Emit a gauge sample."""


class NoOpEmitter(MetricEmitter):
    """Default emitter that drops every sample."""

    def emit_counter(
        self,
        name: str,
        value: int,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Drop the sample (no-op)."""
        return

    def emit_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Drop the sample (no-op)."""
        return


class PrometheusTextfileEmitter(MetricEmitter):
    """Emit samples in Prometheus textfile-collector format.

    Each call appends one line to an in-memory buffer and atomically rewrites
    the target file (``write tmp + os.replace``) so a concurrent reader (the
    node-exporter textfile collector) never observes a partial line.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """Create an emitter that writes to ``path`` (parent dirs auto-created)."""
        self._path = Path(path)
        self._lines: list[str] = []
        self._lock = Lock()
        # Ensure parent dir exists so the first emit doesn't crash.
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit_counter(
        self,
        name: str,
        value: int,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Append a counter sample line and atomically rewrite the file."""
        self._append(name, float(value), labels)

    def emit_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Append a gauge sample line and atomically rewrite the file."""
        self._append(name, float(value), labels)

    def _append(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None,
    ) -> None:
        line = f"{name}{_format_labels(labels)} {value}"
        with self._lock:
            self._lines.append(line)
            self._atomic_write()

    def _atomic_write(self) -> None:
        # Write to a sibling tmp file then os.replace — guaranteed atomic on
        # POSIX and Windows for files on the same filesystem.
        body = "\n".join(self._lines) + "\n"
        fd, tmp_path = tempfile.mkstemp(
            prefix=self._path.name + ".",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            os.replace(tmp_path, self._path)
        except Exception:
            # Best-effort cleanup of the tmp file on failure.
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise


def get_default_emitter() -> MetricEmitter:
    """Build the default emitter from environment.

    Returns a :class:`PrometheusTextfileEmitter` if ``SCYLLA_METRICS_PATH``
    is set, otherwise a :class:`NoOpEmitter`.
    """
    path = os.environ.get("SCYLLA_METRICS_PATH")
    if path:
        return PrometheusTextfileEmitter(path)
    return NoOpEmitter()
