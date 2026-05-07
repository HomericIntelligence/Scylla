# Tracing (OpenTelemetry scaffold)

ProjectScylla ships an **opt-in** OpenTelemetry tracing scaffold alongside the
opt-in JSON logging foundation (PR #1921). This document describes the
scaffold, what is — and is not — wired up, and how operators activate it.

## Status

- **Scaffold only.** The tracing module and a single root span at the CLI
  entrypoint are in place. Exhaustive instrumentation across every logging
  site is intentionally out of scope and tracked as a follow-up under
  issue #1887.
- **Opt-in.** Default behaviour of the application is unchanged. With no
  configuration, no OpenTelemetry SDK imports happen.

## Activation

Set the `SCYLLA_OTEL_EXPORTER` environment variable before invoking the CLI:

| Value     | Behaviour                                                     |
|-----------|---------------------------------------------------------------|
| unset / empty | NoOp tracing (default). No SDK imports, no spans emitted. |
| `console` | Install `ConsoleSpanExporter` — spans printed to stderr.       |
| `otlp`    | Install OTLP/gRPC exporter (uses `OTEL_EXPORTER_OTLP_ENDPOINT`, default `http://localhost:4317`). |
| anything else | NoOp tracing + a `UserWarning`.                            |

Example:

```bash
SCYLLA_OTEL_EXPORTER=console pixi run scylla run 001-justfile-to-makefile --tier T0 --runs 1
```

## Required packages (operators install these)

OpenTelemetry is **not** a hard dependency of ProjectScylla. Operators who
opt in must install the packages themselves:

```bash
pip install opentelemetry-api opentelemetry-sdk
# For SCYLLA_OTEL_EXPORTER=otlp:
pip install opentelemetry-exporter-otlp
```

If `SCYLLA_OTEL_EXPORTER` is set but the packages are missing, a
`UserWarning` is emitted and tracing is silently disabled — the application
otherwise runs normally.

## Programmatic API

```python
from scylla.utils.tracing import configure_tracing, get_tracer

configure_tracing()  # honours SCYLLA_OTEL_EXPORTER; returns Tracer | None

tracer = get_tracer(__name__)
with tracer.start_as_current_span("my.span") as span:
    span.set_attribute("key", "value")
    ...
```

`get_tracer(name)` returns a name-scoped tracer. When tracing isn't
configured (or OpenTelemetry isn't installed), it returns a NoOp tracer
whose `start_as_current_span` is still a real context manager — call sites
do **not** need to branch on whether tracing is enabled.

## Where the root span lives

The CLI entrypoint (`src/scylla/cli/main.py`) wraps the `run` command body
in a single root span named `scylla.experiment.run` with attributes:

- `experiment.test_id`
- `experiment.model`
- `experiment.runs_per_tier`
- `experiment.tiers` (when explicit tiers are passed)

This is deliberately the *only* span emitted by this scaffold. Adding spans
to deeper layers (orchestrator, executor, judge, metrics) is follow-up work
under issue #1887.

## Out of scope for this scaffold

- Spans at every logging site.
- `opentelemetry-instrumentation-*` auto-instrumentation packages.
- Real OTLP collector deployment / endpoint configuration.

These remain open under issue #1887.

## Log/span correlation

When both `SCYLLA_JSON_LOGS=1` and `SCYLLA_OTEL_EXPORTER=...` are set,
the JSON formatter automatically enriches each log line with:

- `tier_id`, `subtest_id`, `run_num` — thread-local execution context
  injected by `scylla.e2e.log_context.ContextFilter`. Empty fields are
  omitted from output.
- `trace_id` (32-char lowercase hex) and `span_id` (16-char lowercase
  hex) — the currently active OpenTelemetry span, matching the
  [OpenTelemetry log-correlation convention][otel-log-corr]. Omitted
  when no recording span is active or when `opentelemetry-api` is not
  installed.

Sample JSON line emitted from inside an active span:

```json
{"timestamp": "2026-05-07T12:00:00.000000+00:00", "level": "INFO",
 "name": "scylla.executor", "message": "subtest start",
 "tier_id": "T0", "subtest_id": "05", "run_num": "1",
 "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
 "span_id": "00f067aa0ba902b7"}
```

OpenTelemetry remains an optional dependency: when not installed, the
trace fields are silently omitted and JSON logging continues to work.

[otel-log-corr]: https://opentelemetry.io/docs/specs/otel/logs/data-model/#trace-context-fields
