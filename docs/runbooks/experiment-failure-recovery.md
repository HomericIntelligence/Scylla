# Experiment Failure Recovery Runbook

This runbook covers recovery procedures for the four most common ways a
Scylla E2E experiment can fail or get stuck mid-run:

1. [Checkpoint corruption](#1-checkpoint-corruption)
2. [Tier / run state needs reset](#2-tier--run-state-reset)
3. [Zombie false positive (live process flagged as dead)](#3-zombie-false-positive)
4. [Disk space exhaustion mid-experiment](#4-disk-space-exhaustion)

All procedures are derived from the actual recovery code paths in
`src/scylla/e2e/` and `scripts/manage_experiment.py`. Where the codebase has
**no automated recovery path**, this is called out explicitly and the manual
steps are spelled out.

> **Conventions used below**
>
> - `EXP_DIR` — the experiment directory (the parent of `checkpoint.json`).
>   This is `checkpoint.experiment_dir` in the JSON.
> - `CKPT` — `$EXP_DIR/checkpoint.json`.
> - All `pixi run` commands assume you are at the repo root.
> - Code references use the form `path:line` and point at the version of the
>   tree that this runbook was authored against; line numbers may drift but
>   the function names will not.

---

## 1. Checkpoint corruption

### Symptoms

- `pixi run python scripts/manage_experiment.py run --resume ...` aborts
  immediately with a `CheckpointError: Failed to load checkpoint from
  <path>: ...` traceback.
- `cat $CKPT | python -m json.tool` fails with a JSON parse error.
- `get_experiment_status()` (used by monitoring tools) silently reports
  `status=unknown` because the loader exception is swallowed at
  `src/scylla/e2e/checkpoint.py:666-667`.

### What the loader actually does

`load_checkpoint()` at `src/scylla/e2e/checkpoint.py:548-569` performs a
plain `json.load()` followed by `E2ECheckpoint.from_dict()`. There is **no
fallback to a backup file** — any `OSError` or `json.JSONDecodeError` is
re-raised as `CheckpointError`.

The writer (`save_checkpoint()` at `src/scylla/e2e/checkpoint.py:510-545`)
*does* use an atomic rename via a temp file
(`<stem>.tmp.<pid>.<tid><suffix>`, line 535) under a process-wide write lock
(`_checkpoint_write_lock`, line 507). So the most common corruption mode is
not a half-written file — it is one of:

- a stray `.tmp.<pid>.<tid>.json` left over from a crashed writer (can be
  used as a near-current snapshot);
- a `checkpoint.json` truncated by the OOM killer mid-`json.dump`
  (extremely rare given the temp-file pattern);
- a manual edit gone wrong.

> **Rolling backup (added in #1947):** `save_checkpoint()` now renames the
> current `checkpoint.json` to `checkpoint.json.bak` before writing a new
> primary.  `load_checkpoint()` automatically falls back to the `.bak` file
> when the primary fails to parse or validate, logging a structured `WARNING`
> with `fallback=True`.  In most corruption scenarios (e.g. a half-written
> file, manual edit gone wrong) the `.bak` produced by the last successful
> write can be used for recovery without manual intervention.

### Diagnosis commands

```bash
# Is the JSON parseable at all?
python -m json.tool "$CKPT" >/dev/null

# Are there any leftover atomic-write temp files?
ls -la "$EXP_DIR"/checkpoint.tmp.*.json 2>/dev/null

# What does the experiment status helper report?
pixi run python -c "
from pathlib import Path
from scylla.e2e.checkpoint import get_experiment_status
print(get_experiment_status(Path('$EXP_DIR')))
"
```

### Recovery steps

1. **Snapshot first.** Always copy the corrupt file aside before editing:

   ```bash
   cp -a "$CKPT" "$CKPT.corrupt.$(date +%s)"
   ```

2. **Try the automatic `.bak` fallback first.** As of #1947, `load_checkpoint`
   falls back to `checkpoint.json.bak` automatically when the primary file
   fails to parse or validate. If `--resume` succeeds after the corruption
   occurs, no manual intervention is needed. If `--resume` still fails,
   inspect the backup manually:

   ```bash
   # Validate the backup
   python -m json.tool "$CKPT.bak" >/dev/null

   # If the backup is valid but the automatic fallback did not trigger,
   # promote it manually:
   cp -a "$CKPT" "$CKPT.corrupt.$(date +%s)"
   cp "$CKPT.bak" "$CKPT"
   ```

3. **If a recent atomic-write temp file exists** and the backup is also
   corrupt, validate and promote the temp file:

   ```bash
   TMP=$(ls -t "$EXP_DIR"/checkpoint.tmp.*.json 2>/dev/null | head -1)
   python -m json.tool "$TMP" >/dev/null && mv "$TMP" "$CKPT"
   ```

4. **If you have no usable backup**, the safest minimal fix is to edit the
   JSON to fix the parse error (e.g. trailing comma, truncated object) and
   re-validate. The schema is enforced by `E2ECheckpoint.from_dict()` at
   `src/scylla/e2e/checkpoint.py:438-499`, which also handles version
   migration (currently `2.x → 3.x → 3.1`). If your edit breaks a required
   field, the loader will raise a Pydantic `ValidationError` —
   read the message and fix the offending field.

5. **As a last resort**, run `scripts/manage_experiment.py repair` on the
   checkpoint. This loader-level repair (`cmd_repair` at
   `scripts/manage_experiment.py:1263-...`) reconciles `completed_runs` and
   `run_states` with the on-disk `run_result.json` files in
   `<exp_dir>/runs/<tier>/<subtest>/run_NN/` (resolved via
   `scylla.e2e.paths.get_run_dir`). It cannot rebuild a totally corrupt
   checkpoint — only mismatched bookkeeping inside an otherwise valid one.

   ```bash
   pixi run python scripts/manage_experiment.py repair "$CKPT"
   ```

6. **Resume.** Once `python -m json.tool "$CKPT"` parses, run:

   ```bash
   pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR"
   ```

   The runner's `_load_checkpoint_and_config` path
   (`src/scylla/e2e/runner.py:219-259`) will validate `experiment_dir` and
   the saved config under `<exp_dir>/config/experiment.json`.

### Verification

- `python -m json.tool "$CKPT"` exits 0.
- `get_experiment_status($EXP_DIR)` reports a non-`unknown` status.
- `--resume` no longer raises `CheckpointError`. It either runs or stops
  with a *different* error (e.g. config-hash mismatch, which is a separate
  problem documented in `validate_checkpoint_config` at
  `src/scylla/e2e/checkpoint.py:618-632`).

---

## 2. Tier / run state reset

### When you need this

- You changed a tier's prompt/config and need to re-run only that tier.
- A specific subtest passed but you want to re-execute it from a particular
  `RunState` (e.g. re-run agents but keep cloned repos).
- A whole tier needs to start over because of a methodology fix.

This is a normal operational path, not really "failure recovery", but it is
the supported surgical knob for redoing work without nuking the experiment.

### What the reset functions actually do

Three reset entry points live in `src/scylla/e2e/checkpoint.py`:

| Function | Lines | Granularity |
|----------|-------|-------------|
| `reset_runs_for_from_state` | 685-767 | Per-run, with tier/subtest/run/status filters |
| `reset_tiers_for_from_state` | 770-810 | Per-tier |
| `reset_experiment_for_from_state` | 813-840 | Top-level experiment state |

Key behaviours (from the source):

- Runs are always reset to `RunState.PENDING` — there is no partial reset
  (line 699 comment: *"always resets to PENDING (full workspace
  recreation)"*).
- The reset cascades upward: subtest states for affected runs are reset
  (line 757), then containing tier states (line 761), then
  `experiment_state` is forced back to `tiers_running` (line 765).
- The "is this run past `from_state`?" check uses `_RUN_STATE_SEQUENCE`
  ordering from `src/scylla/e2e/state_machine.py`. Terminal states
  (`failed`, `rate_limited`) have `index == -1` and are **only** reset if a
  `status_filter` was supplied (line 748).
- All three functions ignore unknown state names with a warning and a
  `0`-count return — typos do nothing destructive.

### CLI surface

The CLI wrapper is `scripts/manage_experiment.py`, lines 182-245 for the
flags and lines 749-810 / 1172-1218 for the dispatch:

```bash
pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
    --from <RUN_STATE>                  # e.g. replay_generated
    [--from-tier <TIER_STATE>]
    [--from-experiment <EXPERIMENT_STATE>]
    [--filter-tier T2 --filter-tier T3]
    [--filter-subtest S0042]
    [--filter-run 1 --filter-run 2]
    [--filter-status failed]
```

> `--filter-judge-slot` is currently a no-op
> (`scripts/manage_experiment.py:242-245`). Do not rely on it.

### Diagnosis commands

```bash
# What states are runs currently in? (top-of-experiment summary)
pixi run python -c "
from pathlib import Path
from scylla.e2e.checkpoint import load_checkpoint
c = load_checkpoint(Path('$CKPT'))
print('experiment_state:', c.experiment_state)
print('tier_states:', c.tier_states)
"

# Per-run states for a given tier/subtest
pixi run python -c "
from pathlib import Path
from scylla.e2e.checkpoint import load_checkpoint
c = load_checkpoint(Path('$CKPT'))
print(c.run_states.get('T3', {}).get('S0042'))
"
```

### Recovery steps

1. Snapshot the checkpoint (see step 1 of section 1).
2. Pick the smallest filter that captures the work you want to redo. Each
   filter narrows the reset; combine `--filter-tier`, `--filter-subtest`,
   `--filter-run`, and `--filter-status` as needed.
3. Invoke `run --resume` with `--from <state>`. The reset is performed
   *before* execution (see `manage_experiment.py:1172-1218`), then the
   experiment continues normally.
4. Watch the log line `"Reset N runs to PENDING"` (emitted by the dispatch
   block).

### Verification

- The post-reset `tier_states` for affected tiers reads `pending`.
- Affected runs in `run_states` read `pending`.
- `experiment_state` reads `tiers_running` if anything was reset.
- A subsequent `--resume` (without `--from`) picks them up.

---

## 3. Zombie false positive

### What "zombie" means here

A *zombie* experiment, per `src/scylla/e2e/health.py:88-135`, is one where
**all three** of these are true:

1. `checkpoint.status == "running"`
   (`health.py:109-110`)
2. The PID — taken from `checkpoint.pid` first, then from
   `<exp_dir>/experiment.pid` — does not pass `os.kill(pid, 0)`
   (`health.py:113-124`, helper `_pid_is_alive` at `health.py:44-60`).
3. `checkpoint.last_heartbeat` is older than
   `heartbeat_timeout_seconds` (default `DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
   = 120`, set at `health.py:41`). Empty / unparseable timestamps are
   treated as stale (`_heartbeat_is_stale`, `health.py:63-85`).

When a resume detects a zombie, `reset_zombie_checkpoint`
(`health.py:138-160`) flips `status` from `running` to `interrupted` and
saves atomically. This is wired into the runner via
`ResumeManager.handle_zombie` (`src/scylla/e2e/resume_manager.py:82-113`)
called from `src/scylla/e2e/runner.py:325-326`.

### Symptoms of a *false positive*

The detection misclassifies a *live* process as dead in three real
situations:

- The original process holds the PID but `os.kill(pid, 0)` raises
  `PermissionError` because the resuming user is different (the helper
  treats `PermissionError` as "dead", `health.py:59`). Subtle but real on
  shared boxes.
- PID reuse: the original process died, a different unrelated process now
  owns the same PID, and that other process happens to be alive. In that
  case condition 2 is false and the experiment is *not* flagged — but the
  experiment is genuinely dead, so this is the inverse problem.
- The heartbeat thread (`HeartbeatThread`,
  `src/scylla/e2e/health.py:163-235`) failed silently on a `CheckpointError`
  (logged at WARNING, line 233) so heartbeats stopped while the worker
  threads kept running. `is_zombie()` then trips on the stale heartbeat
  *plus* a dead/unauthorised PID check.

The detection has been intentionally conservative — all three conditions
must hold — but a false positive can still happen and the auto-reset will
flip `status` to `interrupted` on you.

### Diagnosis commands

```bash
# What does the checkpoint claim?
pixi run python -c "
from pathlib import Path
from scylla.e2e.checkpoint import load_checkpoint
c = load_checkpoint(Path('$CKPT'))
print('status:', c.status)
print('pid:', c.pid)
print('last_heartbeat:', c.last_heartbeat)
"

# Is the PID actually alive?
PID=$(jq -r '.pid // empty' "$CKPT")
[ -n "$PID" ] && ps -p "$PID" -o pid,etime,cmd

# Cross-check the experiment.pid file the runner writes
cat "$EXP_DIR/experiment.pid" 2>/dev/null
```

### Escape hatch — what the code actually supports

There is **no first-class CLI flag to override zombie detection.** The
documented levers, derived from the code, are:

1. **Refresh the heartbeat without restarting.** Run a one-shot heartbeat
   write so the next resume sees a fresh timestamp:

   ```bash
   pixi run python -c "
   from pathlib import Path
   from scylla.e2e.checkpoint import load_checkpoint, save_checkpoint
   c = load_checkpoint(Path('$CKPT'))
   c.update_heartbeat()
   save_checkpoint(c, Path('$CKPT'))
   "
   ```

   `update_heartbeat()` is the supported mutator used by
   `HeartbeatThread._write_heartbeat` (`health.py:217-235`).

2. **Raise the staleness window.** `is_zombie()` accepts
   `heartbeat_timeout_seconds`, and `ResumeManager.handle_zombie` plumbs
   that argument through (`resume_manager.py:86-99`). There is no CLI
   passthrough today, so this requires either bumping
   `DEFAULT_HEARTBEAT_TIMEOUT_SECONDS` (`health.py:41`) for a one-off run,
   or calling `handle_zombie` from a small Python helper. Document the
   override in your operator notes if you do this.

3. **Accept the reset and re-resume.** If detection fired but the worker
   process is genuinely dead now (the more common case), let
   `reset_zombie_checkpoint` flip status to `interrupted` and re-run with
   `--resume`. `interrupted` is a benign state — the runner picks it up
   exactly like a clean resume.

4. **The truly stuck case** — process is genuinely alive and you cannot
   stop it but resume keeps tripping the zombie path — kill the live
   process first, then resume:

   ```bash
   PID=$(cat "$EXP_DIR/experiment.pid")
   kill "$PID" && sleep 2 && kill -9 "$PID" 2>/dev/null || true
   rm -f "$EXP_DIR/experiment.pid"
   pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR"
   ```

> **Note:** there is no CLI flag like `--no-zombie-check` or
> `--heartbeat-timeout`. If operators hit this regularly, file a follow-up
> to expose `heartbeat_timeout_seconds` on the `run` subcommand.

### Verification

- After step 1 (heartbeat refresh), `is_zombie()` returns `False`:

   ```bash
   pixi run python -c "
   from pathlib import Path
   from scylla.e2e.checkpoint import load_checkpoint
   from scylla.e2e.health import is_zombie
   c = load_checkpoint(Path('$CKPT'))
   print(is_zombie(c, Path('$EXP_DIR')))
   "
   ```

- After step 3 (accepted reset), `checkpoint.status == "interrupted"` and
  `--resume` proceeds normally.

---

## 4. Disk space exhaustion mid-experiment

### Symptoms

- Worker logs show `OSError: [Errno 28] No space left on device` from
  `cleanup_workspace` or from `save_checkpoint` (the latter raises
  `CheckpointError`, `src/scylla/executor/workspace.py:336-339` and
  `src/scylla/e2e/checkpoint.py:544-545`).
- Resource preflight already warned about it on startup: `log_resource_preflight()`
  (`src/scylla/e2e/health.py:287-314`) emits `Low disk warning: only
  X.YGB free.` when `<` 50 GB free at experiment start, and the periodic
  `_log_resource_usage()` (`health.py:259-284`) re-warns every 5 heartbeats
  (~2.5 min at 30 s interval) when free disk drops below 20 GB.
- New worktrees fail to materialise; runs sit in `pending` indefinitely
  because `workspace_slot()` (`src/scylla/e2e/resource_manager.py:78`) is
  capped by `max_concurrent_workspaces` and slot acquisition succeeds but
  the underlying `WorkspaceManager.cleanup_worktree()`
  (`src/scylla/e2e/workspace_manager.py:302`) cannot reclaim space.

### What the cleanup paths actually free

- `cleanup_workspace()` at `src/scylla/executor/workspace.py:303-339` removes
  the workspace directory. With `keep_logs=True` (default, used at
  `src/scylla/e2e/orchestrator.py:174`), it removes only the workspace dir
  and preserves `logs/`. With `keep_logs=False`, it removes the parent
  `run_dir` entirely.
- `stage_cleanup_worktree()` at `src/scylla/e2e/stage_finalization.py:537-582`
  is the per-run cleanup hook. It honours `config.keep_failed_workspaces`
  (`src/scylla/e2e/models.py:794`): when `False` (default) it cleans
  *every* run; when `True` (the `--keep-failed-workspaces` CLI flag) it
  preserves workspaces for failed runs for debugging.
- `max_concurrent_workspaces` (`models.py:795`, default `None` meaning
  auto) caps the number of *live* worktrees at any moment. This is the
  knob that bounds disk pressure during a run.

Both `keep_failed_workspaces` and `max_concurrent_workspaces` are
explicitly excluded from the config hash (`checkpoint.py:609-610`), so you
can change them between resumes without invalidating the checkpoint.

### Diagnosis commands

```bash
# Where is the experiment writing?
df -h "$EXP_DIR"

# Biggest consumers under the experiment dir
du -sh "$EXP_DIR"/* | sort -h | tail -10

# Are there many preserved failed workspaces?
find "$EXP_DIR/runs" -type d -name "workspace" | wc -l

# Are temp checkpoint files piling up after a crash?
ls -la "$EXP_DIR"/checkpoint.tmp.*.json 2>/dev/null
```

### Recovery steps — what is safe to delete

> **Rule of thumb:** anything under a *completed* run's workspace dir is
> reclaimable. Anything that is the source of truth for results
> (`run_result.json`, `judgment*.json`, the checkpoint itself, the saved
> `config/experiment.json`) is **not**.

1. **Stop new worktrees from being created** (optional but reduces churn):

   ```bash
   # When you next resume, lower the cap:
   pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
       --max-concurrent-workspaces 1
   ```

   `max_concurrent_workspaces` is on `ExperimentConfig`
   (`src/scylla/e2e/models.py:795`) and gets re-read on each resume.

2. **Reclaim space from completed runs.** Safe to delete (these are
   throwaway clones; results are preserved elsewhere):

   - `$EXP_DIR/runs/<tier>/<subtest>/run_NN/workspace/` — the git checkout
     (recreated on demand by `WorkspaceManager`).
   - Stray `$EXP_DIR/checkpoint.tmp.*.json` after you have verified
     `$CKPT` parses.

   Do **not** delete:

   - `$EXP_DIR/checkpoint.json`
   - `$EXP_DIR/config/experiment.json`
   - `$EXP_DIR/runs/<...>/run_NN/run_result.json` and any
     `judgment*.json` next to it
   - `$EXP_DIR/runs/<...>/run_NN/logs/`

3. **Remove preserved failed workspaces** if you used
   `--keep-failed-workspaces`. The semantics in
   `stage_finalization.py:553-561` show that a workspace is preserved only
   when `keep_failed and not run_passed`. Once you have read the failure
   data you need, delete just the workspace subdirectory:

   ```bash
   find "$EXP_DIR/runs" -type d -path "*/workspace" \
       | while read -r ws; do
           rm -rf "$ws"
         done
   ```

4. **Resume.** With more disk and a tighter cap, the experiment will
   recreate workspaces lazily as it works through pending runs.

### Critical: what NOT to do

- Do not run `rm -rf "$EXP_DIR/runs"` — that destroys judgements and run
  results, which are the recorded outputs of the experiment.
- Do not delete `$EXP_DIR/config/` — `runner._load_checkpoint_and_config`
  (`runner.py:238`) reads the saved `experiment.json` on every resume and
  will refuse to start if it is missing.
- Do not edit `$CKPT` to mark in-progress runs as completed; use the reset
  flow (section 2) instead.

### Verification

- `df -h "$EXP_DIR"` shows enough free space (preflight warns under
  50 GB; aim for at least 20 GB headroom to stay out of the
  `_log_resource_usage` WARNING band, `health.py:278`).
- `--resume` proceeds; checkpoint writes succeed (no
  `CheckpointError: Failed to save checkpoint`).
- `tier_states` and `run_states` continue advancing on subsequent
  heartbeats.

---

## See also

- `src/scylla/e2e/checkpoint.py` — checkpoint serialization, validation,
  state reset entry points
- `src/scylla/e2e/health.py` — zombie detection, heartbeat thread, resource
  preflight
- `src/scylla/e2e/resume_manager.py` — resume orchestration including
  zombie handling
- `src/scylla/e2e/runner.py` — top-level runner; PID / heartbeat lifecycle
- `src/scylla/e2e/stage_finalization.py` — per-run workspace cleanup
- `src/scylla/executor/workspace.py` — workspace create / cleanup
  primitives
- `scripts/manage_experiment.py` — CLI: `run --resume`, `repair`, `--from`
  / `--filter-*` flags
