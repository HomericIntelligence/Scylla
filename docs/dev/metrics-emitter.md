# Metric Emitter Scaffold

This document describes the `scylla.metrics.emitter` module, a thin
abstraction that lets an operator forward ProjectScylla experiment metrics
(pass rates, Cost-of-Pass, latency, etc.) into a queryable time-series
database (TSDB) such as Prometheus or VictoriaMetrics.

> **Status: opt-in scaffolding.** No existing metric-computation site is
> wired to an emitter yet. Wiring is tracked as a follow-up under issue
> [#1888](https://github.com/HomericIntelligence/ProjectScylla/issues/1888).

## API

```python
from scylla.metrics.emitter import get_default_emitter

emitter = get_default_emitter()
emitter.emit_counter("scylla_runs_total", 1, labels={"tier": "T2"})
emitter.emit_gauge("scylla_pass_rate", 0.67, labels={"tier": "T2"})
```

- `MetricEmitter` — abstract base class with `emit_counter` and
  `emit_gauge`. (Histograms are intentionally out of scope for v1.)
- `NoOpEmitter` — drops every sample. **Default**.
- `PrometheusTextfileEmitter(path)` — writes Prometheus textfile-collector
  format to `path` using an atomic `write tmp + os.replace` cycle.
- `get_default_emitter()` — returns a `PrometheusTextfileEmitter` if the
  environment variable `SCYLLA_METRICS_PATH` is set, otherwise a
  `NoOpEmitter`.

## Output format

Each emit appends one line to the destination file:

```text
scylla_runs_total{tier="T2"} 1.0
scylla_pass_rate{model="haiku",tier="T2"} 0.67
```

Labels are sorted by key for deterministic diffs. Values are escaped per
the [Prometheus exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/)
(`\\`, `\"`, `\n`).

## Why textfile, not push-gateway or in-process `/metrics`?

ProjectScylla experiments are short-lived batch jobs, not long-running
servers, so the typical "expose `/metrics` and let Prometheus scrape it"
pattern does not fit:

| Backend | Why not |
|---|---|
| In-process HTTP `/metrics` | Process exits before scrape interval; samples lost. |
| Push-gateway | Requires deploying and operating an extra service; samples accumulate forever unless explicitly deleted; not recommended by Prometheus for batch jobs of unknown duration. |
| **Textfile collector** | Process writes a flat file; node-exporter (already deployed on most hosts) reads it on every scrape. Survives process exit. No new service to run. |

VictoriaMetrics' `vmagent` and Grafana Alloy both natively ingest the
same textfile format, so this choice is not Prometheus-specific.

## Operator wiring

1. Deploy `node_exporter` with `--collector.textfile.directory=/var/lib/node_exporter/textfiles`
   (most distros already do this).
2. Set `SCYLLA_METRICS_PATH` for the experiment process:

   ```bash
   export SCYLLA_METRICS_PATH=/var/lib/node_exporter/textfiles/scylla.prom
   pixi run scylla run ...
   ```

3. Confirm samples appear in Prometheus / VictoriaMetrics under metric
   names prefixed with `scylla_`.

## Atomicity guarantee

`PrometheusTextfileEmitter` writes to a sibling `*.tmp` file in the same
directory and then calls `os.replace`, which is a kernel-atomic rename on
both POSIX and Windows when source and destination share a filesystem.
The textfile collector therefore sees either the previous full snapshot
or the new full snapshot — never a partially written line.

## What this PR does **not** do

- Does **not** add any new runtime dependency (no `prometheus_client`,
  no `statsd`).
- Does **not** modify any existing metric-computation site. Wiring
  `emit_counter` / `emit_gauge` calls into the experiment runner,
  judge, or aggregator is out of scope; see the #1888 follow-up.
- Does **not** prescribe a TSDB topology. Choosing Prometheus vs.
  VictoriaMetrics vs. another backend is an operator decision.
