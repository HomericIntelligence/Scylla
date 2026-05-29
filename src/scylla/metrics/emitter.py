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

See ``docs/dev/metrics-emitter.md`` for the full API reference and
``docs/dev/tracing.md`` for the Instrumentation Map listing every wired site.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

__all__ = [
    "MetricEmitter",
    "NoOpEmitter",
    "PrometheusTextfileEmitter",
    "get_default_emitter",
]

# Default histogram bucket boundaries (seconds). +Inf is always appended.
_BUCKETS: tuple[float, ...] = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

_LabelsKey = tuple[tuple[str, str], ...]


@dataclass
class _HistState:
    """Accumulated state for one histogram series (name + label combination)."""

    bucket_counts: list[int] = field(default_factory=lambda: [0] * (len(_BUCKETS) + 1))
    sum: float = 0.0
    count: int = 0


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

    def emit_histogram(  # noqa: B027 — intentionally non-abstract for backward compat
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Emit a histogram observation.

        The default implementation is a silent no-op so that existing
        operator-implemented subclasses continue to work without changes.
        Override in concrete emitters to record histogram data.
        """


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

    def emit_histogram(
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

    Histograms are stored separately in ``_histograms`` and rendered as
    canonical Prometheus histogram blocks on each write so that repeated
    observations never produce duplicate ``_bucket`` lines.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """Create an emitter that writes to ``path`` (parent dirs auto-created)."""
        self._path = Path(path)
        self._lines: list[str] = []
        self._histograms: dict[tuple[str, _LabelsKey], _HistState] = {}
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

    def emit_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a histogram observation and atomically rewrite the file.

        Buckets follow ``_BUCKETS`` boundaries plus the implicit ``+Inf``
        bucket. All mutations are guarded by ``self._lock``.
        """
        labels_key: _LabelsKey = tuple(sorted((labels or {}).items()))
        key = (name, labels_key)
        with self._lock:
            state = self._histograms.get(key)
            if state is None:
                state = _HistState()
                self._histograms[key] = state
            for i, boundary in enumerate(_BUCKETS):
                if value <= boundary:
                    state.bucket_counts[i] += 1
            # +Inf bucket always includes every observation
            state.bucket_counts[len(_BUCKETS)] += 1
            state.sum += value
            state.count += 1
            self._atomic_write()

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
        parts: list[str] = list(self._lines)
        # Render histogram blocks: one canonical set of _bucket/_sum/_count
        # lines per (name, labels) pair. Kept separate from self._lines so
        # repeated observations never produce duplicate _bucket lines.
        for (hist_name, labels_key), state in self._histograms.items():
            label_dict = dict(labels_key)
            for i, boundary in enumerate(_BUCKETS):
                le_labels = {**label_dict, "le": str(boundary)}
                parts.append(
                    f"{hist_name}_bucket{_format_labels(le_labels)} {state.bucket_counts[i]}"
                )
            inf_labels = {**label_dict, "le": "+Inf"}
            inf_count = state.bucket_counts[len(_BUCKETS)]
            parts.append(f"{hist_name}_bucket{_format_labels(inf_labels)} {inf_count}")
            parts.append(f"{hist_name}_sum{_format_labels(label_dict or None)} {state.sum}")
            parts.append(f"{hist_name}_count{_format_labels(label_dict or None)} {state.count}")
        body = "\n".join(parts) + "\n"
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
