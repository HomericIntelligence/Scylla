# Incident Response Runbook

This runbook covers what to do when an experiment produces garbage data
or data whose validity is in doubt, and how to invalidate specific runs
or whole experiments so they do not pollute analysis.

> **Conventions used below**
>
> - `EXP_DIR` — the experiment directory (parent of `checkpoint.json`).
> - `CKPT` — `$EXP_DIR/checkpoint.json`.
> - "Garbage data" — results that are structurally valid (parseable JSON)
>   but scientifically invalid (wrong model, wrong prompt, wrong judge,
>   API error masked as a pass, etc.).

---

## 1. Detecting garbage data

### Symptoms

- Pass-rate is implausibly high (>0.95) or zero for a tier that
  previously averaged 0.3-0.7.
- `run_result.json` shows `total_tokens == 0` with a non-zero cost, or
  cost `$0.00` with a multi-minute runtime (see the Pydantic
  None-coercion pattern in MEMORY.md).
- The `agent_model` field in `run_result.json` does not match the model
  specified in the experiment config.
- Judge verdicts are all identical (e.g. all `pass`) across subtests
  that have known variance.
- The experiment resumed from a checkpoint with a different config
  (logged as `ConfigHashMismatch` at `src/scylla/e2e/checkpoint.py:618`).

### Diagnosis commands

```bash
# Sample a few run_result.json files
find "$EXP_DIR/runs" -name run_result.json | head -5 \
  | xargs -I{} python -m json.tool {}

# Check experiment config hash consistency
uv run python -c "
from pathlib import Path
from scylla.e2e.checkpoint import load_checkpoint
c = load_checkpoint(Path('$CKPT'))
print('config_hash:', c.config_hash)
print('tier_states:', c.tier_states)
"

# Spot-check token counts across runs
find "$EXP_DIR/runs" -name run_result.json \
  | xargs python -c "
import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))
    print(f, d.get('total_tokens'), d.get('total_cost_usd'))
" 2>/dev/null | sort -k2 -n | head -20
```

---

## 2. Invalidating individual runs

If only specific runs are corrupt, reset them to `pending` and re-execute.
The runner will recreate the workspace and re-run the agent from scratch.

```bash
# Snapshot first (always)
cp -a "$CKPT" "$CKPT.pre-invalidate.$(date +%s)"

# Reset one subtest in tier T3 to pending
uv run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
  --from workspace_setup \
  --filter-tier T3 \
  --filter-subtest S0042

# Reset all failed runs across the experiment
uv run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
  --from workspace_setup \
  --filter-status failed
```

See `experiment-failure-recovery.md §2` for the full reset flag
reference and the state-machine ordering.

---

## 3. Invalidating a whole tier

If an entire tier's results are suspect (e.g. wrong model config was
used for the whole tier):

```bash
cp -a "$CKPT" "$CKPT.pre-invalidate.$(date +%s)"

uv run python scripts/manage_experiment.py run --resume "$EXP_DIR" \
  --from workspace_setup \
  --filter-tier T2
```

This resets all runs in T2 to `pending` and cascades the tier state back
to `pending` (`src/scylla/e2e/checkpoint.py:770-810`).

---

## 4. Marking an experiment as invalid (do not analyse)

There is currently **no first-class "invalidated" experiment state** in
the checkpoint schema. The supported approach is:

1. Stop the experiment process if it is running.
2. Rename the experiment directory with an `INVALID-` prefix:

   ```bash
   mv "$EXP_DIR" "$(dirname $EXP_DIR)/INVALID-$(basename $EXP_DIR)"
   ```

3. Create a `INVALID.md` inside the renamed directory explaining why:

   ```bash
   cat > "$(dirname $EXP_DIR)/INVALID-$(basename $EXP_DIR)/INVALID.md" <<'EOF'
   ## Reason for invalidation

   <date> — <your name>: <one-sentence reason>

   ## Affected tiers / runs

   All tiers — wrong judge model (gpt-4o-mini used instead of claude-3-5-sonnet).

   ## Action

   Re-run required from scratch.
   EOF
   ```

4. File a GitHub issue linking the invalidated experiment directory and
   the root cause. Reference it from the `INVALID.md`.

This keeps the raw data on disk for audit purposes while preventing
automated analysis scripts (which look for `checkpoint.json` in named
directories) from picking it up.

---

## 5. Post-incident checklist

- [ ] Snapshot taken before any changes.
- [ ] Root cause identified and documented (GitHub issue + `INVALID.md`).
- [ ] Affected runs or experiment marked invalid.
- [ ] Re-run scheduled or completed.
- [ ] Analysis pipeline re-run against clean results only.
- [ ] Post-mortem note added to the GitHub issue.

---

## See also

- `experiment-failure-recovery.md` — checkpoint repair and run resets
- `src/scylla/e2e/checkpoint.py` — `reset_runs_for_from_state`,
  `reset_tiers_for_from_state`
- `scripts/manage_experiment.py` — `run --resume`, `--from`, `--filter-*`
- MEMORY.md: `Pydantic None Coercion Pattern` — $0 cost symptom
- MEMORY.md: `Batch Result Analysis` — how to find true first-run results
