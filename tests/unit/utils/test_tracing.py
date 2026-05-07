"""Unit tests for :mod:`scylla.utils.tracing`."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from scylla.utils import tracing
from scylla.utils.tracing import _NoOpTracer, configure_tracing, get_tracer


def test_configure_tracing_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """configure_tracing() returns None when SCYLLA_OTEL_EXPORTER is unset."""
    monkeypatch.delenv("SCYLLA_OTEL_EXPORTER", raising=False)
    assert configure_tracing() is None


def test_configure_tracing_empty_value_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty / whitespace SCYLLA_OTEL_EXPORTER is treated as unset."""
    monkeypatch.setenv("SCYLLA_OTEL_EXPORTER", "")
    assert configure_tracing() is None
    monkeypatch.setenv("SCYLLA_OTEL_EXPORTER", "   ")
    assert configure_tracing() is None


def test_configure_tracing_unknown_value_warns_and_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown exporter names emit a warning and return None."""
    monkeypatch.setenv("SCYLLA_OTEL_EXPORTER", "jaeger")
    with pytest.warns(UserWarning, match="Unknown"):
        result = configure_tracing()
    assert result is None


def test_get_tracer_noop_context_manager_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_tracer() must return a tracer whose start_as_current_span is a CM.

    This is the load-bearing contract for call sites: ``with
    tracer.start_as_current_span(...)`` must work whether or not tracing is
    actually configured.
    """
    monkeypatch.delenv("SCYLLA_OTEL_EXPORTER", raising=False)
    tracer = get_tracer("scylla.test")
    with tracer.start_as_current_span("noop") as span:
        # set_attribute must be safe to call on the no-op span shim too.
        span.set_attribute("k", "v")


def test_get_tracer_returns_local_noop_when_otel_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When opentelemetry isn't importable, get_tracer falls back to _NoOpTracer."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("simulated missing opentelemetry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    tracer = get_tracer("scylla.test")
    assert isinstance(tracer, _NoOpTracer)
    with tracer.start_as_current_span("noop") as span:
        span.set_attribute("k", "v")


def test_configure_tracing_warns_when_otel_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SCYLLA_OTEL_EXPORTER set + opentelemetry uninstalled => UserWarning."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("simulated missing opentelemetry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setenv("SCYLLA_OTEL_EXPORTER", "console")
    with pytest.warns(UserWarning, match="not installed"):
        result = configure_tracing()
    assert result is None


def test_configure_tracing_console_exporter_real_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With opentelemetry-sdk installed, console exporter returns a real Tracer."""
    pytest.importorskip("opentelemetry.sdk.trace")
    monkeypatch.setenv("SCYLLA_OTEL_EXPORTER", "console")
    tracer = configure_tracing()
    assert tracer is not None
    # The returned tracer must support start_as_current_span as a CM.
    with tracer.start_as_current_span("scylla.test.span") as span:
        span.set_attribute("foo", "bar")


def test_get_tracer_is_name_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_tracer accepts an arbitrary name and returns a usable tracer."""
    monkeypatch.delenv("SCYLLA_OTEL_EXPORTER", raising=False)
    a = get_tracer("scylla.module.a")
    b = get_tracer("scylla.module.b")
    # Both must be usable as context managers regardless of identity.
    with a.start_as_current_span("a-span"):
        pass
    with b.start_as_current_span("b-span"):
        pass


def test_module_imports_cleanly_without_otel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tracing module itself must import even if opentelemetry is absent.

    Lazy-import contract: no opentelemetry.* import happens at module load.
    """
    # Reload to verify import succeeds without touching opentelemetry.
    importlib.reload(tracing)
    assert hasattr(tracing, "configure_tracing")
    assert hasattr(tracing, "get_tracer")
