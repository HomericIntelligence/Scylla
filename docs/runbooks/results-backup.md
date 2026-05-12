# Results Backup and Disaster Recovery Runbook

This runbook covers what to back up, how to back it up, and how to
recover when the `results/` artifacts are partially or fully lost.

> **Conventions used below**
>
> - `EXP_DIR` — experiment directory (parent of `checkpoint.json`).
> - `RESULTS_DIR` — the top-level `results/` directory at repo root.
> - "Source of truth" files — files that cannot be regenerated without
>   re-running the experiment or the judge; back these up first.

---

## 1. What to back up (and why)

### Irreplaceable (back up every run)

| Path | What it contains |
|------|-----------------|
| `$EXP_DIR/checkpoint.json` | Experiment state, tier/run bookkeeping |
| `$EXP_DIR/config/experiment.json` | Config snapshot (hash-locked on resume) |
| `$EXP_DIR/runs/<tier>/<sub>/run_N/run_result.json` | Per-run outcome and token counts |
| `$EXP_DIR/runs/<tier>/<sub>/run_N/judgment*.json` | LLM-judge verdicts |
| `$EXP_DIR/runs/<tier>/<sub>/run_N/logs/` | Agent logs for audit / post-hoc analysis |

### Reconstructible (back up opportunistically)

| Path | How to reconstruct |
|------|--------------------|
| `$EXP_DIR/runs/<tier>/<sub>/run_N/workspace/` | Re-cloned on next resume |
| `$EXP_DIR/checkpoint.tmp.*.json` | Leftover from a clean run; safe to drop |
| HTML coverage reports (`htmlcov/`) | `pixi run test` regenerates |

---

## 2. Backup procedure

There is currently **no automated backup** wired into the runner (see
TODO in `experiment-failure-recovery.md`, issue #1891). Operators must
run backups manually or via cron.

### Minimal rsync snapshot (recommended)

```bash
# Exclude reconstructible workspace dirs to save space
rsync -av --exclude='*/workspace/' \
  "$EXP_DIR/" \
  "backup-host:/backups/scylla/$(basename $EXP_DIR)/$(date +%Y%m%dT%H%M%S)/"
```

### Full tar archive

```bash
tar --exclude='*/workspace' \
  -czf "/backups/scylla-$(basename $EXP_DIR)-$(date +%Y%m%dT%H%M%S).tar.gz" \
  "$EXP_DIR"
```

### S3 / object store

```bash
aws s3 sync "$EXP_DIR/" \
  "s3://your-bucket/scylla/$(basename $EXP_DIR)/" \
  --exclude "*/workspace/*"
```

**Backup frequency**: at minimum once per tier completion (~every few
hours for a T0-T6 run). The checkpoint is updated after every run
(`save_checkpoint()` at `src/scylla/e2e/checkpoint.py:510-545`), so
fine-grained snapshots of just `checkpoint.json` are cheap and valuable.

---

## 3. Disaster recovery

### Case A — `checkpoint.json` is lost but run artefacts exist

Use `manage_experiment.py repair` to reconstruct the checkpoint from the
on-disk `run_result.json` files:

```bash
pixi run python scripts/manage_experiment.py repair "$EXP_DIR"
```

This reconciles `completed_runs` and `run_states` with whatever
`run_result.json` files exist under `$EXP_DIR/runs/`. See
`experiment-failure-recovery.md §1` for full detail.

### Case B — Partial `run_result.json` loss

1. Identify the missing run dirs:

   ```bash
   find "$EXP_DIR/runs" -type d -name "run_*" \
     ! -name "workspace" | sort
   ```

2. Reset those runs to `pending` and re-execute:

   ```bash
   pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
     --from workspace_setup \
     --filter-tier <TIER> --filter-subtest <SUBTEST>
   ```

3. Re-run the judge on any run that has `run_result.json` but no
   `judgment*.json`.

### Case C — Total loss

Restore from the latest backup, then resume:

```bash
rsync -av "backup-host:/backups/scylla/$(basename $EXP_DIR)/latest/" "$EXP_DIR/"
pixi run python scripts/manage_experiment.py run --resume "$EXP_DIR"
```

Runs completed before the backup are preserved; runs in-progress at
backup time restart from their last known `RunState`.

---

## 4. Data governance

Issue #1958 tracks compliance and governance gaps including data-retention
policy. Until a formal policy is published, retain experiment results for
the duration of the associated research project plus 12 months.

---

## See also

- `experiment-failure-recovery.md` — checkpoint repair procedures
- `src/scylla/e2e/checkpoint.py` — save/load/repair entry points
- `scripts/manage_experiment.py` — `repair` and `run --resume` commands
- Issue #1891 — rolling checkpoint backup (`.bak`) tracking issue
- Issue #1958 — compliance and governance (data-policy tracking)
