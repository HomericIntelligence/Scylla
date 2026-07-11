# Docker Image Specification: scylla-runner

This directory contains the Docker configuration for `scylla-runner:latest`, the base image used for isolated AI agent test execution in Scylla.

## Overview

The `scylla-runner` image provides a consistent, isolated environment for running AI agent evaluations. Each test run executes in its own container to ensure independent results for prompt sensitivity measurement.

## Quick Start

### Build the Image

```bash
cd docker/

# Using Docker directly
docker build -t scylla-runner:latest .

# Using Docker Compose
docker-compose build
```

### Run Validation

```bash
# Validate the image and environment
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY scylla-runner:latest --validate
```

### Run a Test

```bash
docker run \
    -e TIER=T0 \
    -e MODEL=claude-sonnet-4-5-20250929 \
    -e RUN_NUMBER=1 \
    -e TEST_ID=test-001 \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -v /path/to/workspace:/workspace \
    scylla-runner:latest --run
```

## Optional Dependency Groups

The Dockerfile supports pre-installing optional extras into the cached Layer 2 via the `EXTRAS` build argument.
When `EXTRAS` is not set (the default), the image is identical to the original runtime-only image.

### Available Groups

| Group | Packages | Use Case |
|-------|----------|----------|
| `analysis` | matplotlib, numpy, pandas, scipy, seaborn, altair, vl-convert-python, krippendorff | Statistical analysis and reporting |
| `dev` | pytest, pytest-cov, pre-commit, ruff, defusedxml | Development and testing |

### Caching Contract

- **Layer 2** (cached): `[project].dependencies` + any groups named in `EXTRAS`
- **Layer 3** (invalidated on source change): `pip install --no-deps /opt/scylla/`

Setting `EXTRAS` moves the optional packages into Layer 2.  A subsequent source-only rebuild will hit the
Layer 2 cache for both runtime deps and the named extras, and only re-run the fast `--no-deps` Layer 3 step.
If `pip install /opt/scylla/[analysis]` is run *without* `EXTRAS=analysis`, the analysis packages bypass the
cache layer and are reinstalled on every source change.

### Build Commands

```bash
# Runtime dependencies only (default — identical to previous behaviour)
docker build -t scylla-runner:latest -f docker/Dockerfile .

# Include analysis group in the cached layer
docker build --build-arg EXTRAS=analysis -t scylla-runner:analysis -f docker/Dockerfile .

# Include both analysis and dev groups
docker build --build-arg EXTRAS=analysis,dev -t scylla-runner:dev -f docker/Dockerfile .

# Using Docker Compose (reads EXTRAS from the environment)
EXTRAS=analysis docker-compose build
```

## Build Verification

After building the Docker image, verify the build completed successfully:

### Verify Image Exists

```bash
# Check that the image was created
docker images scylla-runner:latest

# Expected output should show:
# REPOSITORY      TAG       IMAGE ID       CREATED         SIZE
# scylla-runner   latest    <image-id>     <time>          <size>
```

### Test Container Start

```bash
# Verify container starts without errors
docker run --rm scylla-runner:latest --version

# Expected output should display versions of:
# - Python
# - Node.js
# - Claude CLI
# - Git
```

### Validate Core Components

```bash
# Run full environment validation
docker run --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY scylla-runner:latest --validate

# This checks:
# - All required binaries are present
# - Python imports work correctly
# - Claude CLI is accessible
# - Environment variables are set
```

### Verify Build Size

```bash
# Check image size is reasonable (should be < 2GB)
docker images scylla-runner:latest --format "{{.Size}}"

# If size is excessive, consider:
# - Clearing npm cache during build
# - Using multi-stage build
# - Removing unnecessary dependencies
```

## Component Verification

Verify all installed components are functioning correctly:

### Python Environment

```bash
# Check Python version (should be 3.10+)
docker run --rm scylla-runner:latest python --version

# Verify scylla package imports
docker run --rm scylla-runner:latest python -c "import scylla; print('scylla package OK')"

# Check Python package installations
docker run --rm scylla-runner:latest python -c "import pytest, yaml, json; print('Core packages OK')"
```

### Node.js and Claude CLI

```bash
# Check Node.js version (should be 20.x LTS)
docker run --rm scylla-runner:latest node --version

# Check npm version
docker run --rm scylla-runner:latest npm --version

# Verify Claude CLI installation
docker run --rm scylla-runner:latest claude --version

# Check Claude CLI path
docker run --rm scylla-runner:latest which claude
```

### System Tools

```bash
# Verify git installation
docker run --rm scylla-runner:latest git --version

# Verify make installation
docker run --rm scylla-runner:latest make --version

# Verify GCC/G++ for compilation
docker run --rm scylla-runner:latest gcc --version
docker run --rm scylla-runner:latest g++ --version
```

### User Permissions

```bash
# Verify non-root user
docker run --rm scylla-runner:latest whoami
# Expected output: scylla

# Verify user can write to workspace
docker run --rm -v /tmp/test-workspace:/workspace scylla-runner:latest \
    sh -c "touch /workspace/test.txt && rm /workspace/test.txt && echo 'Workspace writable'"
```

## Image Contents

The `scylla-runner:latest` image includes:

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.10 | Runtime environment |
| Node.js | 20.x LTS | Claude Code CLI dependency |
| Git | Latest | Repository operations |
| Make | Latest | Build tool |
| GCC/G++ | Latest | Compilation support |
| Claude Code CLI | Latest | Agent evaluation tool |

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-...` |

### Test Configuration Variables

| Variable | Description | Values | Example |
|----------|-------------|--------|---------|
| `TIER` | Test tier | T0-T6 | `T0` |
| `MODEL` | Model identifier | Any valid model ID | `claude-sonnet-4-5-20250929` |
| `RUN_NUMBER` | Run number for prompt sensitivity | 1-9 | `1` |
| `TEST_ID` | Unique test identifier | Any string | `test-abc-001` |

### Optional Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key (if needed) | - | `sk-...` |
| `TIMEOUT` | Execution timeout (seconds) | 300 | `600` |
| `REPO_URL` | Repository to clone | - | `https://github.com/...` |
| `REPO_HASH` | Commit hash to checkout | - | `abc123` |
| `TEST_COMMAND` | Command to execute | - | `pytest tests/` |

## Entry Point Commands

The entry point script supports several commands:

| Command | Description |
|---------|-------------|
| `--help` | Display help message |
| `--version` | Show installed tool versions |
| `--validate` | Validate environment configuration |
| `--run` | Execute test run |

## Container Lifecycle

When used with the Docker orchestration system (issue #35):

```
1. Container created with unique name: scylla-{test_id}-{tier}-{model}-r{run_number}
2. Workspace volume mounted at /workspace
3. Environment variables injected
4. Repository cloned (if REPO_URL provided)
5. Specific commit checked out (if REPO_HASH provided)
6. Test command executed with timeout
7. Container stopped (preserved for analysis)
8. Results captured from stdout/stderr
```

## Security Considerations

1. **Non-root user**: Container runs as `scylla` user, not root
2. **API keys**: Passed at runtime, never baked into image
3. **Network isolation**: Containers can be run with network restrictions
4. **Resource limits**: Apply Docker resource limits for cost control

## Local Development

### Using Docker Compose

```bash
# Build and run validation
docker-compose build
docker-compose run test

# Interactive shell for debugging
docker-compose run shell

# Check versions
docker-compose run version
```

### Environment File

Create a `.env` file in the docker directory for local development:

```bash
ANTHROPIC_API_KEY=your-key-here
OPENAI_API_KEY=optional-key
WORKSPACE_PATH=/path/to/your/workspace
```

## Pre-Deployment Checklist

Before deploying the Docker image to production or CI/CD pipelines, verify all components:

### Build Verification

- [ ] Docker build completes without errors
- [ ] Image size is reasonable (< 2GB)
- [ ] Image appears in `docker images` output
- [ ] No security vulnerabilities reported by `docker scan` (if available)

### Component Verification

- [ ] Python version is 3.10 or higher
- [ ] Node.js version is 20.x LTS
- [ ] Claude CLI is installed and accessible
- [ ] Git, make, gcc, g++ are available
- [ ] `scylla` package imports successfully

### Functional Verification

- [ ] `--version` command displays all component versions
- [ ] `--validate` command passes with valid API key
- [ ] Container starts and stops cleanly
- [ ] Non-root user (`scylla`) is configured correctly
- [ ] Workspace volume is writable

### Security Verification

- [ ] Container runs as non-root user
- [ ] No API keys are baked into the image
- [ ] No sensitive data in image layers
- [ ] Image uses official base images only

### Integration Verification

- [ ] Test execution completes successfully with `--run`
- [ ] Environment variables are respected
- [ ] Timeout mechanism works correctly
- [ ] Results are captured from stdout/stderr

### Documentation Verification

- [ ] README.md is up to date
- [ ] All entry point commands are documented
- [ ] Environment variables are documented
- [ ] Troubleshooting section covers common issues

## CI/CD Integration

### GitHub Actions Example

The `EXTRAS` build argument selects which optional dependency groups are baked into
the cached Layer 2 during the Docker build.  In CI you pass it as a plain
`--build-arg`; it is **not** a secret (it contains no credentials).

**When to use `EXTRAS` in CI:**

- `EXTRAS=analysis` — include matplotlib, numpy, pandas, scipy, seaborn, altair,
  vl-convert-python, and krippendorff for statistical analysis and reporting jobs.
- `EXTRAS=dev` — include pytest, pytest-cov, pre-commit, ruff, and defusedxml for
  development and testing jobs.
- `EXTRAS=analysis,dev` — include both groups.
- Omit `--build-arg EXTRAS` (or set it to an empty string) for a minimal runtime-only
  image identical to the previous default behaviour.

**Storage recommendation:** Store the `EXTRAS` value as a **build matrix variable**
(e.g., via a `matrix` strategy or a workflow-level `env` block), not as a repository
secret.  Secrets are for credentials; `EXTRAS` is a plain string that selects packages
and carries no sensitive information.

```yaml
jobs:
  build-docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image (runtime only)
        run: docker build -t scylla-runner:latest -f docker/Dockerfile .

      - name: Test Docker image
        run: |
          docker run scylla-runner:latest --version
          docker run -e ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }} \
            scylla-runner:latest --validate

      - name: Push to registry (optional)
        if: github.ref == 'refs/heads/main'
        run: |
          docker tag scylla-runner:latest ghcr.io/${{ github.repository }}/scylla-runner:latest
          docker push ghcr.io/${{ github.repository }}/scylla-runner:latest
```

To build an analysis-capable image in CI, pass `--build-arg EXTRAS=analysis`:

```yaml
jobs:
  build-docker-analysis:
    runs-on: ubuntu-latest
    env:
      EXTRAS: analysis   # build matrix variable — not a secret
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image with analysis extras
        run: |
          docker build \
            --build-arg EXTRAS=${{ env.EXTRAS }} \
            -t scylla-runner:${{ env.EXTRAS }} \
            -f docker/Dockerfile .

      - name: Verify analysis packages are present
        run: |
          docker run --rm scylla-runner:${{ env.EXTRAS }} \
            python -c "import numpy, pandas, matplotlib; print('analysis extras OK')"
```

To build multiple variants in a single workflow using a matrix:

```yaml
jobs:
  build-variants:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        extras: ["", "analysis", "analysis,dev"]
    steps:
      - uses: actions/checkout@v4

      - name: Compute image tag
        id: tag
        run: |
          TAG="${{ matrix.extras }}"
          echo "name=scylla-runner:${TAG:-latest}" >> "$GITHUB_OUTPUT"

      - name: Build Docker image
        run: |
          docker build \
            --build-arg EXTRAS="${{ matrix.extras }}" \
            -t ${{ steps.tag.outputs.name }} \
            -f docker/Dockerfile .
```

## Troubleshooting

### Image Build Fails

**Issue**: NodeSource repository not accessible
**Solution**: Check internet connectivity and try rebuilding

```bash
docker build --no-cache -t scylla-runner:latest .
```

### Claude CLI Not Found

**Issue**: `claude: command not found`
**Solution**: Verify npm install succeeded

```bash
docker run scylla-runner:latest which claude
docker run scylla-runner:latest claude --version
```

### Permission Denied in Workspace

**Issue**: Cannot write to /workspace
**Solution**: Ensure the mounted volume has correct permissions

```bash
# On host
chmod -R 777 /path/to/workspace

# Or use correct ownership
docker run -u $(id -u):$(id -g) ...
```

### Timeout Issues

**Issue**: Test execution times out
**Solution**: Increase TIMEOUT environment variable

```bash
docker run -e TIMEOUT=600 ... scylla-runner:latest --run
```

### Missing Entry Point Commands

**Issue**: `--run-agent` or `--run-judge` commands not recognized
**Context**: These commands are planned for future implementation to support specialized execution modes.

**Current Workaround**: Use the `--run` command with appropriate environment variables:

```bash
# For agent execution (current approach)
docker run \
    -e TIER=T3 \
    -e MODEL=claude-sonnet-4-5-20250929 \
    -e TEST_ID=agent-test-001 \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    scylla-runner:latest --run

# For judge execution (future enhancement)
# Currently not implemented - use external judge scripts
```

**Planned Enhancement**: Add dedicated entry point commands for:

- `--run-agent`: Execute agent-specific tests with delegation support
- `--run-judge`: Run LLM judge evaluation on agent outputs
- `--run-benchmark`: Execute full benchmark suite

### Python Import Errors

**Issue**: `ImportError: No module named 'scylla'`
**Solution**: Verify the scylla package is installed in the container

```bash
# Check if scylla is installed
docker run --rm scylla-runner:latest pip list | grep scylla

# If missing, rebuild with --no-cache
docker build --no-cache -t scylla-runner:latest .
```

### Container Exit Without Output

**Issue**: Container exits immediately without producing output
**Solution**: Check entry point script and logs

```bash
# Run with verbose logging
docker run --rm scylla-runner:latest --help

# Check container logs for errors
docker logs <container-id>

# Run interactive shell to debug
docker run --rm -it scylla-runner:latest /bin/bash
```

### API Key Not Recognized

**Issue**: `ANTHROPIC_API_KEY` environment variable not found
**Solution**: Ensure the key is passed correctly at runtime

```bash
# Verify environment variable is set on host
echo $ANTHROPIC_API_KEY

# Pass explicitly to container
docker run -e ANTHROPIC_API_KEY=sk-ant-... scylla-runner:latest --validate

# For docker-compose, use .env file in docker/ directory
```

## File Structure

```
docker/
├── Dockerfile          # Main image definition
├── docker-compose.yml  # Local development compose file
├── entrypoint.sh       # Container entry point script
├── .dockerignore       # Build context exclusions
└── README.md           # This documentation
```

## Related Issues

- #35 - Docker container orchestration
- #2 - Parent epic for infrastructure
