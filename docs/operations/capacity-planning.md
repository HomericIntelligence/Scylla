# Capacity Planning Methodology

Closes [#1892](https://github.com/HomericIntelligence/Scylla/issues/1892).
Refs [#1867](https://github.com/HomericIntelligence/Scylla/issues/1867) (audit
epic), [#1880](https://github.com/HomericIntelligence/Scylla/issues/1880)
(`--fail-on-resource-check`), [#1891](https://github.com/HomericIntelligence/Scylla/issues/1891)
(failure recovery runbook).

## 1. Scope

This document defines the **methodology** an operator should follow to size a host
(or fleet of hosts) for a Scylla experiment, and provides the **measurement
templates** that future runs must populate. It deliberately does *not* contain
empirical numbers for per-run RAM, disk, wall-clock, or token consumption: those
quantities are workload- and model-dependent and have not yet been measured under
controlled conditions.

In scope:

- The dimensions (resource axes) that govern total resource consumption.
- The aggregate sizing formulas that combine per-run measurements into a total
  experiment budget.
- The pre-flight safety mechanism (`log_resource_preflight`) and the operator
  flags that gate it.
- A reproducible measurement procedure so that any operator can fill in the
  `TBD` cells with values from their own host class.

Out of scope:

- Concrete numbers for `peak_RAM_MB`, `wall_clock_min`, `agent_tokens`, etc. Every
  cell that lacks a citation is marked `TBD` and explained in the footnotes.
- Cost estimates (covered separately by the Cost-of-Pass metric in
  [`docs/research.md`](../research.md)).
- Container-level sizing for AchaeanFleet images (covered by that repository).

## 2. Resource axes

The total cost of an experiment is a product of a small set of operator-controlled
dimensions. All of these are explicit fields on
[`ExperimentConfig`](../../src/scylla/e2e/models.py) (`src/scylla/e2e/models.py`)
and can therefore be read directly out of `experiment.json` after a run.

| Axis | Field | Default | Citation |
|------|-------|---------|----------|
| Models under test | `models` | `[DEFAULT_AGENT_MODEL]` | `src/scylla/e2e/models.py:765` |
| Runs per sub-test | `runs_per_subtest` | `10` | `src/scylla/e2e/models.py:766` |
| Tiers to run | `tiers_to_run` | all of `TierID` (T0–T6) | `src/scylla/e2e/models.py:767` |
| Judge models (consensus) | `judge_models` | `[DEFAULT_JUDGE_MODEL]` | `src/scylla/e2e/models.py:768` |
| Per-run timeout (s) | `timeout_seconds` | `3600` | `src/scylla/e2e/models.py:769` |
| Max conversation turns | `max_turns` | unlimited (`None`) | `src/scylla/e2e/models.py:770` |
| Max sub-tests per tier | `max_subtests` | all (`None`) | `src/scylla/e2e/models.py:771` |
| Skip agent teams | `skip_agent_teams` | `False` | `src/scylla/e2e/models.py:772` |
| Thinking mode | `thinking_mode` | `"None"` | `src/scylla/e2e/models.py:773` |
| Max concurrent workspaces | `max_concurrent_workspaces` | `cpu_count * 2` | `src/scylla/e2e/models.py:795`, `src/scylla/e2e/resource_manager.py:64` |
| Max concurrent agents | `max_concurrent_agents` | `min(threads, cpu_count)` | `src/scylla/e2e/models.py:796`, `src/scylla/e2e/resource_manager.py:65` |
| Off-peak gating | `off_peak` | `False` | `src/scylla/e2e/models.py:797` |
| Pre-flight strict mode | `fail_on_resource_check` | `False` | `src/scylla/e2e/models.py:801` |

The corresponding CLI flags (wired by
[`scripts/manage_experiment.py`](../../scripts/manage_experiment.py)):

| CLI flag | argparse line |
|----------|----------------|
| `--off-peak` | `scripts/manage_experiment.py:259` |
| `--keep-failed-workspaces` | `scripts/manage_experiment.py:266` |
| `--max-concurrent-workspaces N` | `scripts/manage_experiment.py:272` |
| `--max-concurrent-agents N` | `scripts/manage_experiment.py:279` |
| `--fail-on-resource-check` | `scripts/manage_experiment.py:286` |

### 2.1 Sub-test counts per tier

The 120-sub-test total is the canonical workload; counts come from
[`tests/claude-code/shared/tiers.yaml`](../../tests/claude-code/shared/tiers.yaml)
and are mirrored in [`/AGENTS.md`](../../AGENTS.md):

| Tier | Name | Sub-tests |
|------|------|-----------|
| T0 | Prompts | 24 |
| T1 | Skills | 10 |
| T2 | Tooling | 15 |
| T3 | Delegation | 41 |
| T4 | Hierarchy | 14 |
| T5 | Hybrid | 15 |
| T6 | Super | 1 |
| **Total** | — | **120** |

## 3. Per-run resource estimate templates

A "run" is one execution of one sub-test, for one (model, tier, sub-test) tuple.
The tables below define the **schema** that a measurement campaign must populate.
Every quantitative cell is `TBD` until measured per the procedure in
[§7](#7-measurement-procedure).

### 3.1 Per-run agent execution

| Tier | Agent model | Workspace disk (GB)<sup>a</sup> | Peak RAM (MB)<sup>a</sup> | Subprocesses<sup>b</sup> | Wall-clock (min)<sup>a</sup> | Agent tokens (in / out)<sup>a</sup> |
|------|-------------|--------------------------------:|--------------------------:|-------------------------:|-----------------------------:|------------------------------------:|
| T0 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T0 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T0 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T1 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T1 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T1 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T2 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T2 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T2 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T3 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T3 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T3 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T4 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T4 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T4 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T5 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T5 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T5 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T6 | claude-haiku-4-5 | TBD | TBD | TBD | TBD | TBD / TBD |
| T6 | claude-sonnet-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |
| T6 | claude-opus-4-6 | TBD | TBD | TBD | TBD | TBD / TBD |

<sup>a</sup> Measured from a real run — see [§7](#7-measurement-procedure) and the
measurement campaign tracked under [#1892](https://github.com/HomericIntelligence/Scylla/issues/1892).

<sup>b</sup> "Subprocesses" includes the `claude` CLI plus any tool subprocesses
spawned during the run. Counted via `ps --ppid <runner-pid>` snapshots.

### 3.2 Per-run judge execution

Judges run after agents and consume separate API quota. Multiple judges per run
are common when `judge_models` lists more than one model (consensus voting,
[`src/scylla/e2e/models.py:744`](../../src/scylla/e2e/models.py)).

| Tier | Judge model | Wall-clock (s)<sup>a</sup> | Judge tokens (in / out)<sup>a</sup> |
|------|-------------|---------------------------:|------------------------------------:|
| T0 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T1 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T2 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T3 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T4 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T5 | claude-sonnet-4-6 | TBD | TBD / TBD |
| T6 | claude-sonnet-4-6 | TBD | TBD / TBD |

<sup>a</sup> Judge cost is largely tier-invariant in the limit (judges read a fixed
rubric + the agent's transcript), but transcript length grows with tier complexity.
Measure per tier; do not assume invariance.

## 4. Aggregate sizing formulas

The total experiment budget is a sum over (tier, sub-test, run, model) tuples,
divided by parallelism. The formulas below are exact; only the per-run inputs
are `TBD`.

### 4.1 Wall-clock

Let:

- `S_t` = sub-tests in tier *t* (see §2.1; `S_T3 = 41`, etc.)
- `R` = `runs_per_subtest` (default `10`,
  [`src/scylla/e2e/models.py:766`](../../src/scylla/e2e/models.py))
- `M` = `len(models)` (default 1)
- `J` = `len(judge_models)` (default 1)
- `T_t,m` = mean per-run agent wall-clock for (tier, model) — from
  [§3.1](#31-per-run-agent-execution); **TBD**
- `T_judge_t,j` = mean per-run judge wall-clock for (tier, judge) — from
  [§3.2](#32-per-run-judge-execution); **TBD**
- `P_a` = effective agent parallelism = `min(max_concurrent_agents,
  cpu_count)` ([`src/scylla/e2e/resource_manager.py:65`](../../src/scylla/e2e/resource_manager.py))
- `P_w` = effective workspace parallelism = `max_concurrent_workspaces` (default
  `cpu_count * 2`, [`src/scylla/e2e/resource_manager.py:64`](../../src/scylla/e2e/resource_manager.py))

Then total agent wall-clock (assuming saturated parallelism):

```text
W_agent = (1 / P_a) * sum_{t in tiers} sum_{m in models} ( S_t * R * T_t,m )
```

Total judge wall-clock (judges typically share `P_a` because they are also
`claude` CLI processes; consult `parallel_executor.py` for the exact contention
model):

```text
W_judge = (1 / P_a) * sum_{t in tiers} sum_{j in judges} ( S_t * R * M * T_judge_t,j )
```

Total wall-clock lower bound:

```text
W_total >= W_agent + W_judge
```

The *upper* bound includes off-peak idle time (see
[§5.2](#52-off-peak-gating)) and is unbounded in the worst case.

### 4.2 Disk

Workspaces are per-run, ephemeral, and capped at `P_w` live at once. Failed
workspaces are kept on disk when `--keep-failed-workspaces` is set
([`scripts/manage_experiment.py:266`](../../scripts/manage_experiment.py)).

Let:

- `D_ws` = peak per-run workspace disk (GB) — from §3.1; **TBD**
- `F` = expected failure rate (0.0–1.0); **TBD per tier**
- `N_total` = total runs = `sum_t S_t * R * M = 120 * R * M` (default `120 * 10 * 1 = 1200`)
- `D_ckpt` = checkpoint + reports footprint (GB); **TBD**, typically O(100 MB)
  on a finished experiment

Live disk (steady-state):

```text
D_live = P_w * D_ws
```

If `--keep-failed-workspaces` is set, accumulated disk grows with completed
runs:

```text
D_kept = F * N_total * D_ws
```

Total disk envelope:

```text
D_total = D_live + D_kept + D_ckpt
```

For the default `keep_failed_workspaces = False`
([`src/scylla/e2e/models.py:794`](../../src/scylla/e2e/models.py)), `D_kept = 0`
and the envelope reduces to `D_live + D_ckpt`.

### 4.3 RAM

RAM is dominated by concurrent agent processes. Each run holds one `claude` CLI
plus its tool subprocesses; the runner enforces `P_a` concurrency via the
resource manager.

```text
RAM_peak ~= P_a * R_run + RAM_runner
```

where `R_run` is per-run peak RAM (§3.1, **TBD**) and `RAM_runner` is the
orchestrator's own footprint (**TBD**, expected O(500 MB)).

### 4.4 Tokens

Tokens flow to two distinct rate-limit pools (agent vs. judge); plan budgets
separately.

```text
Tokens_agent_in  = sum_{t,m} S_t * R * tok_in_t,m
Tokens_agent_out = sum_{t,m} S_t * R * tok_out_t,m
Tokens_judge_in  = sum_{t,j} S_t * R * M * tok_judge_in_t,j
Tokens_judge_out = sum_{t,j} S_t * R * M * tok_judge_out_t,j
```

All `tok_*` factors are **TBD** — populate from §3.1 / §3.2 after the
measurement campaign.

## 5. Rate-limit pre-flight

### 5.1 `log_resource_preflight()`

Before the runner enters the per-tier loop, it calls
[`log_resource_preflight()`](../../src/scylla/e2e/health.py)
(`src/scylla/e2e/health.py:312`) from
[`src/scylla/e2e/runner.py:616`](../../src/scylla/e2e/runner.py). This function
inspects free RAM and free disk on `/` and classifies the host into three
states.

Thresholds (constants in [`health.py`](../../src/scylla/e2e/health.py)):

| Class | RAM constant | Disk constant | Behaviour |
|-------|--------------|---------------|-----------|
| Critical | `CRITICAL_RAM_MB = 512` (`src/scylla/e2e/health.py:294`) | `CRITICAL_DISK_GB = 5` (`src/scylla/e2e/health.py:295`) | **Always** raises `ResourcePreflightError` (`src/scylla/e2e/health.py:298`), regardless of any flag. |
| Warning | `WARN_RAM_MB = 4096` (`src/scylla/e2e/health.py:288`) | `WARN_DISK_GB = 50` (`src/scylla/e2e/health.py:289`) | Logs a warning. With `fail_on_warn=True` (wired from `--fail-on-resource-check`), also raises. |
| OK | above warning | above warning | Logs informational lines and proceeds. |

The hard-abort behaviour for the critical class was added in PR #1917 in
response to issue [#1880](https://github.com/HomericIntelligence/Scylla/issues/1880);
the previous behaviour was warn-only and would let an under-provisioned host
proceed into a workload that would inevitably crash.

Operator-facing flag:

```bash
python scripts/manage_experiment.py run ... --fail-on-resource-check
```

(argparse definition: [`scripts/manage_experiment.py:286`](../../scripts/manage_experiment.py)).

### 5.2 Off-peak gating

When `--off-peak` is set
([`scripts/manage_experiment.py:259`](../../scripts/manage_experiment.py)),
[`parallel_executor.py:215`](../../src/scylla/e2e/parallel_executor.py)
calls `wait_for_off_peak()` from
[`src/scylla/e2e/scheduling.py:48`](../../src/scylla/e2e/scheduling.py).
Peak hours are defined as 12:00–19:00 UTC weekdays
(`PEAK_START_UTC = 12`, `PEAK_END_UTC = 19` —
[`scheduling.py:27-28`](../../src/scylla/e2e/scheduling.py)). Weekends are
always off-peak.

Off-peak gating extends wall-clock unboundedly during peak hours but reduces
rate-limit pressure on the API. Plan accordingly: if an experiment must finish
inside a fixed window, do not enable `--off-peak`.

## 6. Worst-case envelope

Given a host with `RAM_host` (MB) and `DISK_host` (GB), the maximum
sustainable parallelism is:

```text
P_a_max = floor( (RAM_host - RAM_runner_TBD) / R_run_TBD )
P_w_max = floor( (DISK_host - D_ckpt_TBD) / D_ws_TBD )
P_safe  = min(P_a_max, P_w_max, cpu_count)
```

The operator should pass `--max-concurrent-agents P_safe` and
`--max-concurrent-workspaces P_safe` (or a tighter bound) to keep the host
inside both the RAM and disk envelopes. The defaults
(`cpu_count * 2` workspaces, `min(threads, cpu_count)` agents —
[`resource_manager.py:64-65`](../../src/scylla/e2e/resource_manager.py)) are
*CPU-aware but RAM/disk-blind*; on RAM-constrained hosts they will exceed
`P_a_max` and trigger OOM.

Until the per-run constants in §3.1 are measured, operators should:

1. Run a single sub-test (`--max-subtests 1 --runs-per-subtest 1`) under
   `time` + `/usr/bin/time -v` to collect `R_run` and `D_ws` empirically.
2. Apply the formulas above to derive a safe `P_safe` for the target host.
3. Run a 2-tier dry pass before a full T0–T6 sweep.

## 7. Measurement procedure

Use this procedure to populate the `TBD` cells in §3 for a given (tier, model)
pair. All commands assume a checked-out Scylla worktree and a configured
`uv` environment.

### 7.1 Single-run instrumentation

```bash
# 1. Snapshot disk before the run.
DISK_BEFORE=$(du -sb "$EXPERIMENT_DIR" 2>/dev/null | cut -f1)

# 2. Launch one sub-test with --max-subtests 1 --runs-per-subtest 1, wrapped
#    in /usr/bin/time -v to capture peak RSS and elapsed wall-clock.
/usr/bin/time -v -o /tmp/scylla-time.txt \
  uv run python scripts/manage_experiment.py run \
    --experiment-id capacity-probe-T${TIER}-${MODEL_SHORT} \
    --tiers T${TIER} \
    --models ${MODEL} \
    --max-subtests 1 \
    --runs-per-subtest 1 \
    --max-concurrent-agents 1 \
    --max-concurrent-workspaces 1 \
    --fail-on-resource-check

# 3. Snapshot disk after.
DISK_AFTER=$(du -sb "$EXPERIMENT_DIR" 2>/dev/null | cut -f1)
echo "Workspace delta (bytes): $((DISK_AFTER - DISK_BEFORE))"

# 4. Extract peak RSS (MB) and elapsed wall-clock from /tmp/scylla-time.txt.
grep -E 'Maximum resident set size|Elapsed \(wall clock\) time' /tmp/scylla-time.txt
```

### 7.2 Subprocess fan-out

While the run is in flight (in another shell):

```bash
# Sample the process tree every 5s for the duration of the run.
RUNNER_PID=$(pgrep -f "scripts/manage_experiment.py run")
while kill -0 "$RUNNER_PID" 2>/dev/null; do
  ps --ppid "$RUNNER_PID" -o pid,rss,cmd \
    | tee -a /tmp/scylla-procs.log
  sleep 5
done
# Peak subprocess count:
awk 'NR>1 {print NR}' /tmp/scylla-procs.log | sort -u | wc -l
```

### 7.3 Token accounting

Tokens are recorded per-run in the experiment checkpoint. After the probe
completes:

```bash
# checkpoint.json sits under the timestamped experiment dir.
CHECKPOINT=$(find "$EXPERIMENT_DIR" -name checkpoint.json | head -1)
wc -l "$CHECKPOINT"

# Extract input/output tokens for the agent and judge for the single run:
uv run python -c "
import json, sys
ck = json.load(open('$CHECKPOINT'))
# Walk into ck['tier_states'][...] to extract token counts; exact path
# depends on the checkpoint schema version.
print(json.dumps(ck.get('tier_states', {}), indent=2)[:2000])
"
```

(The exact JSON path depends on the checkpoint schema; see
[`src/scylla/e2e/checkpoint.py`](../../src/scylla/e2e/checkpoint.py).)

### 7.4 Aggregating into §3 tables

Run the procedure above 3–5 times per (tier, model) pair to estimate variance.
Record the **mean** and **p95** in the §3 tables; the formulas in §4 use the
mean for capacity planning and the p95 for safety-margin sizing.

## 8. Known constraints

### 8.1 Peak-hour API rate limits

The Anthropic API enforces tighter per-organisation rate limits during the
window 12:00–19:00 UTC on weekdays
([`scheduling.py:27-28`](../../src/scylla/e2e/scheduling.py)). Without
`--off-peak`, a long-running experiment will see judge or agent calls fail
with HTTP 429 and the framework will rely on its retry/back-off path. With
`--off-peak`, peak hours add idle time but reduce 429 pressure to ~zero.

### 8.1a Docker resource limits (issue #1948)

Every agent container launched by `DockerExecutor` now carries hard resource
caps via three flags added in `src/scylla/executor/docker.py:_build_run_command`:

| Docker flag | Default | Config key |
|-------------|---------|-----------|
| `--memory` | `8g` | `docker.resource_limits.memory_limit` |
| `--cpus` | `2.0` | `docker.resource_limits.cpu_limit` |
| `--pids-limit` | `512` | `docker.resource_limits.pids_limit` |

Defaults live in `config/defaults.yaml` under the `docker.resource_limits`
block and are modelled by `ResourceLimitsConfig`
(`src/scylla/config/models.py`). They can be overridden per-tier by
constructing a `ContainerConfig` with a custom `ResourceLimitsConfig`.

**Sizing guidance:**

- Set `memory_limit` to at most `RAM_host / P_a` so that `P_a` concurrent
  containers cannot collectively exceed host RAM (see §6).
- Set `cpu_limit` to at most `cpu_count / P_a` so CPU contention stays
  bounded.
- `pids_limit` of 512 is generous for most workloads; lower it to 256 on
  hosts where the process table is under pressure.

These limits are a *floor* safety net, not a substitute for correct
`max_concurrent_agents` sizing as described in §6.

### 8.2 Disk-full failure mode

If free disk drops below `CRITICAL_DISK_GB = 5`
([`src/scylla/e2e/health.py:295`](../../src/scylla/e2e/health.py)) at the
start of an experiment, `log_resource_preflight()` aborts immediately. If it
drops *during* an experiment (e.g. a runaway tool produces a multi-GB log),
the framework currently does *not* re-check, and individual runs may fail
with `OSError: No space left on device`. Recovery is documented in the
operational-readiness runbook tracked under
[#1891](https://github.com/HomericIntelligence/Scylla/issues/1891).

Mitigations:

- Reserve at least `WARN_DISK_GB = 50`
  ([`src/scylla/e2e/health.py:289`](../../src/scylla/e2e/health.py)) of free
  disk before launch.
- Avoid `--keep-failed-workspaces` on long sweeps unless you have measured
  `D_kept` from §4.2 and confirmed it fits.
- Place `$EXPERIMENT_DIR` on a partition with at least
  `D_live + D_kept + D_ckpt` of free space.

### 8.3 Critical resource thresholds

The critical thresholds are deliberately set lower than typical CI runners
(16 GB RAM, 50 GB disk) so that a healthy CI host never trips them
([`src/scylla/e2e/health.py:291-293`](../../src/scylla/e2e/health.py)). They
exist as a *floor*, not a recommendation. Operators should size for the
warning thresholds (`WARN_RAM_MB = 4096`, `WARN_DISK_GB = 50`) and pass
`--fail-on-resource-check` to convert the warnings into hard aborts before
work begins.

### 8.4 Partial-tier failure semantics

A failure in one tier does **not** abort the experiment
([`/AGENTS.md`](../../AGENTS.md), §"Partial-Failure Semantics"). When sizing,
budget for the *full* envelope: a tier that fails early will free its share
of disk and RAM, but a tier that fails late may still have consumed its
upper-bound resources before failing. Operators must check `tier_states` in
the checkpoint, not just `experiment_state`, to determine whether all tiers
succeeded.

## 9. Future work

This document is methodology only. The empirical follow-up — running the
measurement procedure of §7 against each (tier, model) pair on a reference
host class and populating the `TBD` cells in §3 — is tracked under
[#1892](https://github.com/HomericIntelligence/Scylla/issues/1892) as
the *capacity-planning measurement campaign*. Until that campaign lands,
operators should treat §6 as advisory and fall back to the conservative path
in §6 step 1 (single-sub-test probe before a full sweep).
