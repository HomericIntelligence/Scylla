# Observability Setup Runbook

This runbook explains how to enable structured JSON logs, OpenTelemetry
tracing, and Prometheus metrics for a Scylla experiment run.

All three signals are **opt-in**. The defaults produce plain text logs,
no spans, and no metric output. Default behaviour is unchanged if no
environment variables are set.

> **Conventions used below**
>
> - `EXP_DIR` — the experiment directory (parent of `checkpoint.json`).
> - Code references: `path:lines`, valid for the tree this runbook was
>   authored against; function names will not drift even if lines do.

---

## 1. Structured JSON logs (`SCYLLA_JSON_LOGS`)

Set `SCYLLA_JSON_LOGS=1` before invoking the CLI. Implemented at
`src/scylla/utils/json_logging.py:85` and wired into the CLI at
`src/scylla/cli/main.py:49-52`.

```bash
SCYLLA_JSON_LOGS=1 uv run scylla run-tier T0
SCYLLA_JSON_LOGS=1 uv run python scripts/manage_experiment.py run "$EXP_DIR"
```

Each log line is a JSON object. When an OTel span is active in the same
process, the formatter injects `trace_id` (32-char hex) and `span_id`
(16-char hex) into every record automatically
(`src/scylla/utils/json_logging.py:156`).

**Why plain text is still the default**: JSON log parsing adds latency
per log call and makes interactive terminal output unreadable for
developers. Enable it only in environments where a log-aggregation
pipeline (e.g. Loki, CloudWatch Logs) consumes the output.

---

## 2. OpenTelemetry tracing (`SCYLLA_OTEL_EXPORTER`)

Set `SCYLLA_OTEL_EXPORTER` to one of two recognised values. Implemented
at `src/scylla/utils/tracing.py:49-155` and activated at
`src/scylla/cli/main.py:53`.

| Value | Effect |
|-------|--------|
| `console` | Spans printed to stderr (development / smoke-test) |
| `otlp` | Spans sent via gRPC OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT` |
| unset | NoOp tracer; no SDK imports; zero overhead |

### Console (smoke-test)

```bash
SCYLLA_OTEL_EXPORTER=console uv run scylla run <test-id>
```

### OTLP collector (production)

```bash
# Start a local OTLP collector (e.g. Grafana Alloy, OpenTelemetry Collector)
# Default endpoint: http://localhost:4317

pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
SCYLLA_OTEL_EXPORTER=otlp \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
  uv run scylla run <test-id>
```

The OTel SDK is **not** a hard dependency of Scylla; install it
only on hosts where tracing is required. If the packages are absent when
`SCYLLA_OTEL_EXPORTER` is set, a `UserWarning` is emitted and the run
continues with NoOp tracing (`src/scylla/utils/tracing.py:116-123`).

**Span depth**: tier → subtest → run → judge spans are all emitted when
tracing is enabled (see issue #1933 for the depth documentation).

---

## 3. Prometheus textfile metrics (`SCYLLA_METRICS_PATH`)

Set `SCYLLA_METRICS_PATH` to a writable file path. The
`PrometheusTextfileEmitter` (`src/scylla/metrics/emitter.py:91`) writes
Prometheus exposition format to that file after each metric event using
an atomic rename, so the node-exporter textfile collector never reads a
partial file.

```bash
SCYLLA_METRICS_PATH=/var/lib/node_exporter/textfile_collector/scylla.prom \
  uv run python scripts/manage_experiment.py run "$EXP_DIR"
```

If `SCYLLA_METRICS_PATH` is unset, `get_default_emitter()` returns a
`NoOpEmitter` that drops every sample silently
(`src/scylla/metrics/emitter.py:156-165`).

**Integration note**: The MetricEmitter scaffold is wired into the
experiment runner (`src/scylla/e2e/runner_internals/runner_core.py:684`)
and judge runner (`src/scylla/e2e/judge_runner.py:352`). Full call-site
coverage is tracked in `docs/dev/metrics-emitter.md`.

---

## Combining all three signals

```bash
SCYLLA_JSON_LOGS=1 \
SCYLLA_OTEL_EXPORTER=otlp \
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317 \
SCYLLA_METRICS_PATH=/var/lib/node_exporter/textfile_collector/scylla.prom \
  uv run python scripts/manage_experiment.py run "$EXP_DIR"
```

---

## See also

- `src/scylla/utils/json_logging.py` — JSON log formatter
- `src/scylla/utils/tracing.py` — OTel tracing scaffold
- `src/scylla/metrics/emitter.py` — MetricEmitter / PrometheusTextfileEmitter
- `src/scylla/cli/main.py` — CLI entry point wiring all three signals
- Issue #1887 — follow-up for exhaustive span instrumentation
