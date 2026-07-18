# Tracing (OpenTelemetry scaffold)

Scylla ships an **opt-in** OpenTelemetry tracing scaffold alongside the
opt-in JSON logging foundation (PR #1921). This document describes the
scaffold, what is — and is not — wired up, and how operators activate it.

## Status

- **Span depth in place.** The tracing module emits a root
  `scylla.experiment.run` span at the CLI entry point and child spans at
  every meaningful runtime boundary — tier, subtest, run, and judge. See
  [Span hierarchy](#span-hierarchy) below.
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
SCYLLA_OTEL_EXPORTER=console uv run scylla run 001-justfile-to-makefile --tier T0 --runs 1
```

## Required packages (operators install these)

OpenTelemetry is **not** a hard dependency of Scylla. Operators who
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

Child spans below this root cover the rest of the runtime — see
[Span hierarchy](#span-hierarchy).

## Span hierarchy

Beyond the single root `scylla.experiment.run` span, the runtime emits
child spans at every meaningful execution boundary. The full hierarchy is:

| Span name                        | Emitted by                                        | Attributes                                                                                       |
|----------------------------------|---------------------------------------------------|--------------------------------------------------------------------------------------------------|
| `scylla.experiment.run`          | `src/scylla/cli/main.py`                          | `experiment.test_id`, `experiment.model`, `experiment.runs_per_tier`, `experiment.tiers`         |
| `scylla.tier`                    | `src/scylla/e2e/runner_internals/runner_core.py`  | `scylla.tier_id`, `scylla.experiment_id`                                                         |
| `scylla.subtest`                 | `src/scylla/e2e/subtest_executor.py`              | `scylla.tier_id`, `scylla.subtest_id`, `scylla.experiment_id`                                    |
| `scylla.run`                     | `src/scylla/e2e/subtest_executor.py`              | `scylla.tier_id`, `scylla.subtest_id`, `scylla.run_num`, `scylla.experiment_id`                  |
| `scylla.judge`                   | `src/scylla/e2e/judge_runner.py`                  | `scylla.judge_model`, `scylla.judge_number`                                                      |
| `scylla.container.run`           | `src/scylla/executor/docker.py`                   | `scylla.image`, `scylla.container_id`, `scylla.exit_code`                                        |
| `scylla.container.run_detached`  | `src/scylla/executor/docker.py`                   | `scylla.image`, `scylla.container_id`                                                            |
| `scylla.container.stop`          | `src/scylla/executor/docker.py`                   | `scylla.container_id`                                                                            |
| `scylla.rate_limit.pause`        | `src/scylla/e2e/rate_limit.py`                    | `scylla.reason`, `scylla.retry_after_seconds`                                                    |

Failures at any level call `span.record_exception(exc)` before re-raising,
so spans carry exception events even when the run itself fails.

## Instrumentation Map

Every actively-wired call site, with its span, counter, histogram, labels, and source file.

| Instrumentation Point | Span | Counter | Histogram | Labels | Source File |
|-----------------------|------|---------|-----------|--------|-------------|
| Experiment run (root) | `scylla.experiment.run` | — | — | `experiment.test_id`, `experiment.model` | `src/scylla/cli/main.py` |
| Tier start/end | `scylla.tier` | `scylla_tier_runs_total` | — | `tier`, `outcome`, `experiment` | `src/scylla/e2e/runner_internals/runner_finalization.py` |
| Subtest start/end | `scylla.subtest` | `scylla_subtest_runs_total` | — | `tier`, `outcome` | `src/scylla/e2e/subtest_executor.py` |
| Run start/end | `scylla.run` | `scylla_experiment_pass_rate` (gauge) | — | `tier`, `outcome` | `src/scylla/e2e/subtest_executor.py` |
| Judge call | `scylla.judge` | `scylla_judge_evaluations_total` | `scylla_judge_call_seconds` | `model` | `src/scylla/e2e/judge_runner.py` |
| Adapter call | — | — | `scylla_adapter_call_seconds` | `tier`, `subtest`, `model` | `src/scylla/e2e/stages.py` |
| Checkpoint save | — | `scylla_checkpoint_save_total` | `scylla_checkpoint_save_seconds` | `experiment`, `outcome` | `src/scylla/persistence/checkpoint.py` |
| Rate-limit pause | `scylla.rate_limit.pause` | `scylla_rate_limit_pauses_total` | `scylla_rate_limit_pause_seconds` | `reason` | `src/scylla/e2e/rate_limit.py` |
| Container run | `scylla.container.run` | `scylla_container_lifecycle_total` | `scylla_container_run_seconds` | `event`, `image` | `src/scylla/executor/docker.py` |
| Container stop | `scylla.container.stop` | `scylla_container_lifecycle_total` | `scylla_container_stop_seconds` | `event` | `src/scylla/executor/docker.py` |
| Error dispatch | — | `scylla_errors_total` | — | `error_class`, `tier` | `src/scylla/e2e/parallel_executor.py`, `src/scylla/e2e/subtest_executor.py` |
| Config startup | — | — (gauge) | — | — | `src/scylla/cli/main.py` |

## Troubleshooting

**Empty textfile (`$SCYLLA_METRICS_PATH`):**

- Check that `SCYLLA_METRICS_PATH` is set and the parent directory is writable.
- Check that the process has write permission: `touch $SCYLLA_METRICS_PATH`.

**Missing `trace_id` / `span_id` in JSON logs:**

- Verify `opentelemetry-api` is installed: `pip show opentelemetry-api`.
- Confirm `SCYLLA_OTEL_EXPORTER` is set (even to `console`) — the trace fields are injected only when an active span exists.

**Traces and logs not correlated:**

- Set both `SCYLLA_OTEL_EXPORTER` and `SCYLLA_JSON_LOGS=1` together. The JSON formatter injects `trace_id`/`span_id` from the currently active OTel span; if tracing is not configured there is no active span to read.
- Verify the same process sets both env vars (not split across a shell wrapper and the subprocess).

> **Cardinality note.** `scylla.subtest_id` is recorded as a span attribute
> only — never as a metric label. The OTLP collector budgets cardinality
> at the trace-storage tier; metric exporters keep low-cardinality labels.

## Sample trace tree

For an experiment with 2 tiers, 3 subtests per tier and 2 runs per
subtest, the span tree looks like this (one judge per run shown for
brevity — multi-judge runs add sibling `scylla.judge` spans):

```text
scylla.experiment.run
├── scylla.tier (T0)
│   ├── scylla.subtest (001)
│   │   ├── scylla.run (run_num=1)
│   │   │   └── scylla.judge (claude-3-haiku, #1)
│   │   └── scylla.run (run_num=2)
│   │       └── scylla.judge (claude-3-haiku, #1)
│   ├── scylla.subtest (002)
│   │   ├── scylla.run (run_num=1) → scylla.judge
│   │   └── scylla.run (run_num=2) → scylla.judge
│   └── scylla.subtest (003)
│       ├── scylla.run (run_num=1) → scylla.judge
│       └── scylla.run (run_num=2) → scylla.judge
└── scylla.tier (T1)
    └── ... (same shape)
```

## Production OTLP collector setup

The repo ships **no** collector configuration — operators stand one up
themselves. The minimal deployment below uses Jaeger as both trace store
and UI; it is sufficient for inspecting Scylla traces locally and in
single-host shared environments.

### `docker-compose.observability.yml`

Save this on the host running Scylla (do **not** check it into the
repo — it is operator-side configuration):

```yaml
version: "3.9"
services:
  jaeger:
    image: jaegertracing/all-in-one:1.60
    container_name: jaeger
    ports:
      - "16686:16686"   # Jaeger UI
      - "14250:14250"   # gRPC ingestion (used by the collector)
    environment:
      - COLLECTOR_OTLP_ENABLED=true

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.108.0
    container_name: otel-collector
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP (optional)
    depends_on:
      - jaeger
```

### `otel-collector-config.yaml`

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp/jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger]
```

### Operator quick-start

1. Install the OTel client packages once:

   ```bash
   pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
   ```

2. Bring the observability stack up:

   ```bash
   docker compose -f docker-compose.observability.yml up -d
   ```

3. Run an experiment with the OTLP exporter pointed at the local
   collector:

   ```bash
   SCYLLA_OTEL_EXPORTER=otlp \
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
   uv run scylla run 001-justfile-to-makefile --tier T0 --runs 1
   ```

4. Open the Jaeger UI at <http://localhost:16686>, select the
   `scylla` service, and query for the `scylla.experiment.run` span.
   Drill into the trace to see the full tier → subtest → run → judge
   tree described above.

For multi-host deployments, point `OTEL_EXPORTER_OTLP_ENDPOINT` at the
collector's externally reachable address and add TLS/auth as appropriate
in `otel-collector-config.yaml`.

## Out of scope for this scaffold

- `opentelemetry-instrumentation-*` auto-instrumentation packages.

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
