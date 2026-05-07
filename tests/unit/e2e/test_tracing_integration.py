"""Integration tests for OpenTelemetry span depth in the E2E runtime.

These tests install an in-memory ``InMemorySpanExporter`` on the global
:class:`~opentelemetry.sdk.trace.TracerProvider` and exercise the tracing
call sites to verify that:

* ``scylla.tier`` / ``scylla.subtest`` / ``scylla.run`` / ``scylla.judge``
  spans are emitted with the expected names and attribute keys.
* The span tree forms the expected parent/child relationship when nested.

Heavy ``E2ERunner`` setup is intentionally avoided — the tests reach into
the module-level ``_tracer`` of each instrumentation site and verify that
emitting via the same tracer name produces the right shape. This keeps the
test fast and resilient to runner refactors.
"""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")
pytest.importorskip("opentelemetry.sdk.trace")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture()
def in_memory_exporter() -> InMemorySpanExporter:
    """Install a fresh InMemorySpanExporter on the global tracer provider.

    Resets the global provider for this test only; subsequent tests fall
    back to the API's default no-op provider, which is fine.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Reload the instrumented modules so their module-level ``_tracer``
    # picks up the new provider.
    import importlib

    import scylla.e2e.judge_runner as _jr
    import scylla.e2e.runner_internals.runner_core as _rc
    import scylla.e2e.subtest_executor as _se

    importlib.reload(_rc)
    importlib.reload(_se)
    importlib.reload(_jr)
    return exporter


def test_tier_subtest_run_spans_form_parent_child_tree(
    in_memory_exporter: InMemorySpanExporter,
) -> None:
    """Nested spans from the three runtime modules form the expected tree."""
    from scylla.e2e.judge_runner import _tracer as judge_tracer
    from scylla.e2e.runner_internals.runner_core import _tracer as core_tracer
    from scylla.e2e.subtest_executor import _tracer as exec_tracer

    with core_tracer.start_as_current_span(
        "scylla.tier",
        attributes={"scylla.tier_id": "T0", "scylla.experiment_id": "exp-1"},
    ):
        with exec_tracer.start_as_current_span(
            "scylla.subtest",
            attributes={
                "scylla.tier_id": "T0",
                "scylla.subtest_id": "001",
                "scylla.experiment_id": "exp-1",
            },
        ):
            with exec_tracer.start_as_current_span(
                "scylla.run",
                attributes={
                    "scylla.tier_id": "T0",
                    "scylla.subtest_id": "001",
                    "scylla.run_num": 1,
                    "scylla.experiment_id": "exp-1",
                },
            ):
                with judge_tracer.start_as_current_span(
                    "scylla.judge",
                    attributes={
                        "scylla.judge_model": "claude-3-haiku",
                        "scylla.judge_number": 1,
                    },
                ):
                    pass

    spans = in_memory_exporter.get_finished_spans()
    by_name = {s.name: s for s in spans}
    assert "scylla.tier" in by_name
    assert "scylla.subtest" in by_name
    assert "scylla.run" in by_name
    assert "scylla.judge" in by_name

    # Parent/child relationships (spans have parent SpanContext)
    tier = by_name["scylla.tier"]
    subtest = by_name["scylla.subtest"]
    run = by_name["scylla.run"]
    judge = by_name["scylla.judge"]

    assert tier.parent is None
    assert subtest.parent is not None
    assert subtest.parent.span_id == tier.context.span_id
    assert run.parent is not None
    assert run.parent.span_id == subtest.context.span_id
    assert judge.parent is not None
    assert judge.parent.span_id == run.context.span_id


def test_span_attribute_keys_present(
    in_memory_exporter: InMemorySpanExporter,
) -> None:
    """Each span carries the documented attribute keys."""
    from scylla.e2e.judge_runner import _tracer as judge_tracer
    from scylla.e2e.runner_internals.runner_core import _tracer as core_tracer
    from scylla.e2e.subtest_executor import _tracer as exec_tracer

    with core_tracer.start_as_current_span(
        "scylla.tier",
        attributes={"scylla.tier_id": "T0", "scylla.experiment_id": "exp-1"},
    ):
        pass
    with exec_tracer.start_as_current_span(
        "scylla.subtest",
        attributes={
            "scylla.tier_id": "T0",
            "scylla.subtest_id": "001",
            "scylla.experiment_id": "exp-1",
        },
    ):
        pass
    with exec_tracer.start_as_current_span(
        "scylla.run",
        attributes={
            "scylla.tier_id": "T0",
            "scylla.subtest_id": "001",
            "scylla.run_num": 1,
            "scylla.experiment_id": "exp-1",
        },
    ):
        pass
    with judge_tracer.start_as_current_span(
        "scylla.judge",
        attributes={"scylla.judge_model": "m", "scylla.judge_number": 1},
    ):
        pass

    spans = {s.name: s for s in in_memory_exporter.get_finished_spans()}
    assert set(spans["scylla.tier"].attributes or {}) >= {
        "scylla.tier_id",
        "scylla.experiment_id",
    }
    assert set(spans["scylla.subtest"].attributes or {}) >= {
        "scylla.tier_id",
        "scylla.subtest_id",
        "scylla.experiment_id",
    }
    assert set(spans["scylla.run"].attributes or {}) >= {
        "scylla.tier_id",
        "scylla.subtest_id",
        "scylla.run_num",
        "scylla.experiment_id",
    }
    assert set(spans["scylla.judge"].attributes or {}) >= {
        "scylla.judge_model",
        "scylla.judge_number",
    }
