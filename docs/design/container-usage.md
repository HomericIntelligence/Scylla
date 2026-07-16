# Container Usage Guide

This guide explains how to run Scylla experiments using Docker containers.

## Overview

Scylla provides two scripts for running experiments in containers:

1. **`run_experiment_in_container.sh`** - Run a single experiment (container auto-exits)
2. **`launch_container_shell.sh`** - Start an interactive shell (run multiple experiments)

## Prerequisites

- Docker installed and running
- Claude Code credentials at `~/.claude/.credentials.json` (or `ANTHROPIC_API_KEY` set)

## Quick Start

### Option 1: Single Experiment (Auto-Exit)

Run one experiment and exit automatically:

```bash
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v
```

**Use this when:**

- Running a single experiment
- Running in CI/CD pipelines
- You want the container to clean up after completion

### Option 2: Interactive Shell (Multiple Experiments)

Start an interactive container where you can run multiple experiments:

```bash
# Launch the container
./scripts/launch_container_shell.sh

# Inside the container, run experiments:
python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v

# Run another experiment
python scripts/manage_experiment.py run \
    --tiers-dir tests/fixtures/tests/test-002 \
    --tiers T1 T2 --runs 5

# Exit when done
exit
```

**Use this when:**

- Running multiple experiments back-to-back
- Debugging experiment issues
- Iterating on experiment configurations
- You want to avoid container startup overhead

## Container Specifications

### Image Details

- **Name**: `scylla-runner:latest`
- **Base**: `python:3.14.2-slim`
- **Includes**:
  - Python 3.14.2
  - Node.js 20.x LTS
  - Claude Code CLI
  - Git, make, build tools
  - Scylla package (installed from source)

### Mounts

Both scripts mount:

1. **Project Directory**: `/home/mvillmow/Scylla` → `/workspace` (read-write)
2. **Credentials**: `~/.claude/.credentials.json` → `/tmp/host-creds/.credentials.json` (read-only)

Results are written to the mounted `results/` directory and persist on the host.

### User

- **Container User**: `scylla` (UID 999)
- **Home**: `/home/scylla`
- **Working Directory**: `/workspace`

## Script Reference

### run_experiment_in_container.sh

```bash
./scripts/run_experiment_in_container.sh [experiment-args]
```

**Features:**

- Auto-builds image if missing
- Mounts credentials and project directory
- Runs `python scripts/manage_experiment.py run` with your arguments
- Container auto-removes after completion (`--rm`)
- Passes through all experiment arguments

**Examples:**

```bash
# Basic usage
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 -v

# Multiple tiers
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 T1 T2 --runs 5

# Fresh start (ignore checkpoints)
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 --fresh -v

# Limited subtests for testing
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 --max-subtests 3 -v
```

### launch_container_shell.sh

```bash
./scripts/launch_container_shell.sh [container-name]
```

**Features:**

- Auto-builds image if missing
- Launches interactive bash shell
- Container auto-removes on exit (`--rm`)
- Mounts credentials and project directory
- Optional custom container name

**Examples:**

```bash
# Launch with auto-generated name
./scripts/launch_container_shell.sh

# Launch with custom name
./scripts/launch_container_shell.sh my-experiment-session

# Re-attach to running container (if using --name without --rm)
docker exec -it my-experiment-session bash
```

## Common Workflows

### Workflow 1: Quick Test

```bash
# Run single experiment, auto-exit
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 --runs 1 --max-subtests 1 -v
```

### Workflow 2: Iterative Development

```bash
# Start interactive shell
./scripts/launch_container_shell.sh dev-session

# Inside container: run experiments iteratively
python scripts/manage_experiment.py run --tiers-dir tests/fixtures/tests/test-001 --tiers T0 --runs 1 -v
# ... review results ...

python scripts/manage_experiment.py run --tiers-dir tests/fixtures/tests/test-001 --tiers T0 --runs 1 --fresh -v
# ... review results ...

# Exit when done
exit
```

### Workflow 3: Full Evaluation

```bash
# Run all tiers in a single command
./scripts/run_experiment_in_container.sh \
    --tiers-dir tests/fixtures/tests/test-001 \
    --tiers T0 T1 T2 T3 T4 T5 T6 \
    --runs 10 \
    -v
```

## Troubleshooting

### Docker Image Not Found

**Symptom:** `Docker image scylla-runner:latest not found`

**Solution:** Both scripts auto-build the image. If build fails, manually build:

```bash
docker build -t scylla-runner:latest -f docker/Dockerfile .
```

### Credentials Not Found

**Symptom:** `No Claude Code credentials or ANTHROPIC_API_KEY found`

**Solutions:**

1. Ensure `~/.claude/.credentials.json` exists:

   ```bash
   ls -la ~/.claude/.credentials.json
   ```

2. Or set API key in environment:

   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   ./scripts/run_experiment_in_container.sh ...
   ```

### Permission Denied on Results

**Symptom:** `Permission denied: 'results/...'`

**Solution:** Ensure results directory is writable:

```bash
chmod 777 results/
```

The scripts automatically do this, but if you manually created the directory it might have wrong permissions.

### Container Already Exists

**Symptom:** `Container 'xyz' already exists`

**Solution:**

```bash
# Check if it's running
docker ps -a | grep xyz

# Remove if not needed
docker rm xyz

# Or attach to it if it's running
docker exec -it xyz bash
```

### TTY Not Available

**Symptom:** `the input device is not a TTY`

**Solution:** This is expected when running scripts in non-interactive environments (like CI/CD). The scripts automatically detect TTY availability and adjust.

## Advanced Usage

### Custom API Keys

Pass API keys to container:

```bash
export ANTHROPIC_API_KEY=your-anthropic-key
export OPENAI_API_KEY=your-openai-key

./scripts/run_experiment_in_container.sh ...
```

### Persistent Container

For long-running experiments, use a named container without `--rm`:

```bash
# Modify launch_container_shell.sh to remove --rm flag
# Then launch with custom name
./scripts/launch_container_shell.sh long-running-session

# Container persists after exit
# Re-attach later
docker start long-running-session
docker exec -it long-running-session bash
```

### Custom Mounts

Edit the scripts to add custom volume mounts:

```bash
# In either script, add to VOLUMES array:
VOLUMES+=(
    "-v" "/path/on/host:/path/in/container:ro"
)
```

## Architecture

### How It Works

1. **Wrapper Script** (`launch_container_shell.sh` or `run_experiment_in_container.sh`):
   - Checks Docker installation
   - Builds image if needed
   - Prepares credentials with proper permissions
   - Mounts project directory and credentials
   - Launches container with appropriate command

2. **Container** (`scylla-runner:latest`):
   - Runs entrypoint script (`/entrypoint.sh`)
   - Copies credentials to container user's home
   - Sets up Claude Code environment
   - Executes experiment script or opens shell

3. **Experiment** (`manage_experiment.py`):
   - Runs entirely inside single container
   - Agents execute directly (no nested containers)
   - Judges evaluate directly (no nested containers)
   - Results written to mounted `/workspace/results/`

### No Nested Containers

Unlike the previous architecture, the current design runs the **entire experiment inside a single container**:

- **OLD**: Host → Container per agent → Container per judge (complex)
- **NEW**: Host → Single container → All agents + judges (simple)

This provides:

- ✅ Better performance (no container startup overhead per execution)
- ✅ Simpler debugging (everything in one place)
- ✅ Easier credential management (mount once)
- ✅ Better resource control (one container to manage)

## See Also

- [Container Architecture](./container-architecture.md) - Detailed architecture documentation
- [scripts/README.md](../scripts/README.md) - Script reference documentation
- [docker/README.md](../docker/README.md) - Docker image specification
