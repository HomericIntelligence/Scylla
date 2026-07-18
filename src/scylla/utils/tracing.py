"""Opt-in OpenTelemetry tracing scaffold for Scylla.

This module mirrors the shape of :mod:`scylla.utils.json_logging` (PR #1921):
a small, dependency-free shim that turns into a working tracer only when the
operator explicitly opts in via the ``SCYLLA_OTEL_EXPORTER`` environment
variable. Default behaviour of the application is unchanged.

The OpenTelemetry SDK is **not** a hard dependency of Scylla. Operators
who want real spans must install the packages themselves::

    pip install opentelemetry-api opentelemetry-sdk

When the env var is unset (the default), :func:`configure_tracing` returns
``None`` and :func:`get_tracer` returns a NoOp tracer whose
``start_as_current_span`` is a real context manager — so call sites can use
the same ``with tracer.start_as_current_span(...)`` shape regardless of
whether tracing is actually configured.

Activation::

    SCYLLA_OTEL_EXPORTER=console uv run scylla run <test-id>
    SCYLLA_OTEL_EXPORTER=otlp    uv run scylla run <test-id>

Recognised values:

* ``"console"`` — install a ``ConsoleSpanExporter`` (spans printed to stderr)
* ``"otlp"``    — install an OTLP exporter pointed at the standard
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` env var (defaults to ``http://localhost:4317``)
* unset / empty — NoOp tracing; no SDK imports happen

See ``docs/dev/tracing.md`` for the complete Instrumentation Map and
troubleshooting guide.
"""

from __future__ import annotations

import contextlib
import logging
import os
import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from opentelemetry.trace import Tracer

__all__ = ["configure_tracing", "get_tracer"]

_ENV_VAR = "SCYLLA_OTEL_EXPORTER"
_logger = logging.getLogger(__name__)


class _NoOpSpan:
    """Minimal span shim with the attributes call sites use."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op set_attribute."""

    def set_status(self, status: Any) -> None:
        """No-op set_status."""

    def record_exception(self, exception: BaseException) -> None:
        """No-op record_exception."""


class _NoOpTracer:
    """NoOp tracer used when tracing is disabled.

    Matches the subset of the OpenTelemetry ``Tracer`` interface we depend on
    so call sites can use ``with tracer.start_as_current_span(...)`` without
    branching on whether tracing was configured.
    """

    @contextlib.contextmanager
    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> Iterator[_NoOpSpan]:
        """Yield a no-op span as a context manager."""
        del name, args, kwargs
        yield _NoOpSpan()


def configure_tracing() -> Tracer | None:
    """Configure tracing based on ``SCYLLA_OTEL_EXPORTER``.

    Returns the configured global :class:`~opentelemetry.trace.Tracer` when
    the env var is set to a recognised value, or ``None`` when tracing is
    disabled. When the env var is set but the OpenTelemetry packages are not
    installed, a :class:`UserWarning` is emitted and ``None`` is returned.

    The function is safe to call multiple times: re-configuration installs
    the new exporter on the existing global ``TracerProvider`` rather than
    stacking providers.
    """
    exporter = os.environ.get(_ENV_VAR, "").strip().lower()
    if not exporter:
        return None

    if exporter not in {"console", "otlp"}:
        warnings.warn(
            f"Unknown {_ENV_VAR} value {exporter!r}; expected 'console' or 'otlp'. "
            "Tracing disabled.",
            UserWarning,
            stacklevel=2,
        )
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
            SpanExporter,
        )
    except ImportError:
        warnings.warn(
            f"{_ENV_VAR}={exporter!r} but opentelemetry-api / opentelemetry-sdk "
            "are not installed; tracing disabled. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk",
            UserWarning,
            stacklevel=2,
        )
        return None

    span_exporter: SpanExporter
    if exporter == "console":
        span_exporter = ConsoleSpanExporter()
    elif exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
        except ImportError:
            warnings.warn(
                f"{_ENV_VAR}=otlp but opentelemetry-exporter-otlp is not installed; "
                "falling back to ConsoleSpanExporter. "
                "Install with: pip install opentelemetry-exporter-otlp",
                UserWarning,
                stacklevel=2,
            )
            span_exporter = ConsoleSpanExporter()
        else:
            span_exporter = OTLPSpanExporter()
    else:  # pragma: no cover - guarded above
        return None

    provider = trace.get_tracer_provider()
    # If a real (non-proxy) provider is already installed, attach to it.
    # Otherwise, install a fresh SDK provider.
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider(resource=Resource.create({"service.name": "scylla"}))
        trace.set_tracer_provider(provider)

    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    return provider.get_tracer("scylla")


def get_tracer(name: str) -> Tracer | _NoOpTracer:
    """Return a tracer scoped to *name*.

    When the OpenTelemetry API is importable, the global ``TracerProvider``
    is used (this works whether or not :func:`configure_tracing` has been
    called — uncalled, the provider is the API's default no-op provider, so
    span creation is cheap). When the API is not importable at all, a local
    :class:`_NoOpTracer` is returned so call sites still work.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return _NoOpTracer()
    return trace.get_tracer(name)
