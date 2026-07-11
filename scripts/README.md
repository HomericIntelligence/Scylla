# Scripts Directory

This directory contains utility scripts for running Scylla experiments.

## Git Hooks

### `install_hooks.sh`

Installs tracked git hooks from `scripts/hooks/` into `.git/hooks/`.

Run once after cloning or whenever hook files change:

```bash
bash scripts/install_hooks.sh
```

Hooks installed:

| Hook | Trigger | What it does |
|------|---------|--------------|
| `pre-push` | Every `git push` | Runs `pytest` with coverage; aborts push if tests fail or coverage drops below the threshold in `pyproject.toml` |

The coverage threshold is read directly from `pyproject.toml` (`[tool.coverage.report] fail_under`) so there is a single source of truth — update the threshold there and the hook message updates automatically.

---

## Main Scripts

### `manage_experiment.py`

Unified entry point for running and managing E2E experiments. Replaces all legacy scripts.

**Subcommands:**

- `run` — Run a single experiment, batch of experiments, or re-execute from a checkpoint state
- `repair` — Repair corrupt checkpoint by rebuilding from `run_result.json` files

**Usage:**

```bash
# Run single test
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1

# Batch run all tests in a parent dir (auto-discovers test-* subdirs)
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/ --threads 4

# Batch run specific tests
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/ --tests test-001 test-005

# Run with custom model settings
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 T1 T2 \
    --runs 5 \
    --model claude-sonnet-4-5-20250929 \
    --judge-model claude-opus-4-5-20251101
```

### `run_experiment_in_container.sh`

Wrapper script that runs `manage_experiment.py run` inside a Docker container for complete isolation.

**Usage:**

```bash
# Run T0 with 1 run, verbose
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v

# Run multiple tiers
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 T1 T2 --runs 5
```

**What it does:**

1. Checks if Docker is installed and running
2. Builds `scylla-runner:latest` image if not present
3. Mounts project directory to `/workspace` in container
4. Mounts Claude Code credentials (if available)
5. Passes API keys from environment
6. Runs `manage_experiment.py run` with your arguments

**Requirements:**

- Docker installed and running
- Either:
  - Claude Code credentials at `~/.claude/.credentials.json`, or
  - `ANTHROPIC_API_KEY` environment variable set

## When to Use Each Script

### Use `run_experiment_in_container.sh` (Docker) when

- You need complete isolation from host environment
- You want reproducible execution environment
- You're running on different machines and want consistency
- You want to ensure no config leakage between runs

### Use `manage_experiment.py run` (Direct) when

- You're developing and iterating quickly
- You want faster execution (no container overhead)
- You have the correct environment already set up
- You're debugging and need direct access to logs

Both methods produce identical results.

## Architecture

See [docs/container-architecture.md](../docs/container-architecture.md) for detailed architecture documentation.

## Common Tasks

### Quick T0 Validation

```bash
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 --max-subtests 1 -v
```

### Full Tier Run

```bash
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 T1 T2 T3 T4 T5 T6 \
    --runs 10
```

### Custom Model Configuration

```bash
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 \
    --model claude-sonnet-4-5-20250929 \
    --judge-model claude-opus-4-5-20251101
```

### Resume from Checkpoint

Experiments automatically save checkpoints after each run. To resume:

```bash
# Just run the same command - it will auto-resume
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 --runs 10

# Or force fresh start
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --tiers T0 --runs 10 \
    --fresh
```

## Recovery Commands

Use `manage_experiment.py run --from <STATE>` to re-execute from a specific point in an
existing experiment. The `--from` flag resets matching states in the checkpoint to pending
and resumes from there.

### Recovery Quick Reference

| Goal | Command |
|------|---------|
| Re-run failed agent executions | `run --from replay_generated --filter-status failed` |
| Re-run all judge evaluations | `run --from judge_pipeline_run` |
| Regenerate reports only | `run --from run_finalized` |
| Fix corrupted checkpoint | `repair <checkpoint.json>` |

### Re-run Failed Agents

```bash
# Re-run failed agents in tier T0
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --results-dir results/ \
    --from replay_generated \
    --filter-tier T0 \
    --filter-status failed
```

### Re-run All Judges

```bash
# Re-run all judge evaluations from the beginning of the judge pipeline
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --results-dir results/ \
    --from judge_pipeline_run \
    --filter-tier T0
```

### Regenerate Reports from Existing Data

```bash
# Rebuild reports without re-running agents or judges
python scripts/manage_experiment.py run \
    --config tests/fixtures/tests/test-001 \
    --results-dir results/ \
    --from run_finalized
```

### Repair Corrupt Checkpoint

```bash
python scripts/manage_experiment.py repair results/experiment-001/checkpoint.json
```

**When to use:**

- Checkpoint `completed_runs` is empty despite having completed runs
- Run state is out of sync with actual run_result.json files on disk

## Troubleshooting

### Docker Issues

```bash
# Check Docker status
docker info

# Rebuild image
docker build -t scylla-runner:latest -f docker/Dockerfile .

# Clean Docker cache
docker builder prune -a -f
```

### Permission Issues

```bash
# Fix results directory permissions
sudo chown -R $USER:$USER results/
```

### Credential Issues

```bash
# Check credentials
ls -la ~/.claude/.credentials.json

# Or set API key
export ANTHROPIC_API_KEY="your-key-here"
```

## Related Files

- `../docker/Dockerfile` - Docker image definition
- `../docker/entrypoint.sh` - Container entrypoint script
- `../docs/container-architecture.md` - Architecture documentation
