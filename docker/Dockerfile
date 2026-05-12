# Dockerfile for scylla-runner:latest
# Multi-stage build for reduced image size
#
# This image provides:
# - Python 3.10+ environment
# - Git and common build tools (runtime only)
# - Claude Code CLI for agent evaluation
# - Entry point for test execution

# ============================================================================
# Stage 1: Builder - Install Python packages with build dependencies
# ============================================================================
# Pinned to SHA256 digest for reproducibility - prevents drift from upstream updates
# Python 3.12 aligns with pyproject.toml classifiers (3.10-3.13); requires-python = ">=3.10"
# NOTE: ci/Containerfile pins a different SHA256 for the same python:3.12-slim tag.
# Both intentionally kept separate; if you update either digest, update both files together.
FROM python:3.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS builder

# Set build environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies (will NOT be in final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: Build backend (invalidated only when hatchling version changes)
# Pinned to match pyproject.toml [build-system].requires — see #1141
# Audit (#1209): all static pip installs are pinned; dynamic Layer 2 install
# (from pyproject.toml via tomllib) is intentionally version-spec controlled there.
RUN pip install --no-cache-dir "hatchling==1.29.0"

# Layer 2: Dependencies (invalidated only when pyproject.toml changes or EXTRAS changes)
# Copy only pyproject.toml first so dependency installs are cached separately
# from source changes.
# NOTE: Uses tomllib with a tomli fallback (see issues #1138, #1200). The builder stage
# supports Python 3.10+ — tomllib is stdlib since 3.11; tomli is pre-installed as a
# fallback for 3.10 environments (e.g. minimal/musl variants).
#
# Optional-dependency groups from [project.optional-dependencies] that are built
# into this layer when EXTRAS is set at build time:
#   analysis  — matplotlib, numpy, pandas, scipy, seaborn, altair, vl-convert-python, krippendorff
#   dev       — pytest, pytest-cov, pre-commit, ruff, defusedxml
#   nats      — nats-py (NATS JetStream event subscription)
#
# EXTRAS validation: unknown group names emit an error and exit non-zero (see #1204).
# Typos like EXTRAS=analyysis are caught immediately rather than silently omitted.
#
# Usage:
#   docker build .                               # runtime deps only (default)
#   docker build --build-arg EXTRAS=analysis .   # + analysis group in cache layer
#   docker build --build-arg EXTRAS=analysis,dev .  # + both groups
ARG EXTRAS=""
COPY pyproject.toml /opt/scylla/
RUN pip install --no-cache-dir "tomli==2.0.2" \
    && EXTRAS="$EXTRAS" python3 - <<'PYEOF' > /tmp/deps.txt
import os, sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]  # Python 3.10 fallback (#1200)
with open('/opt/scylla/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
project = data.get('project', {})
opt = project.get('optional-dependencies', {})
valid = set(opt.keys())
extras = {g.strip() for g in os.environ.get('EXTRAS', '').split(',') if g.strip()}
unknown = extras - valid
if unknown:
    print(f'ERROR: Unknown EXTRAS group(s): {sorted(unknown)}. Valid: {sorted(valid)}', file=sys.stderr)
    sys.exit(1)
deps = list(project.get('dependencies', []))
for g in extras:
    deps.extend(opt.get(g, []))
print(' '.join(deps))
PYEOF
RUN pip install --user --no-cache-dir $(cat /tmp/deps.txt) \
    && rm -f /tmp/deps.txt

# Layer 3: Package install (invalidated when src/scylla/ source changes)
# Source-only changes hit cached layer 2 and only re-run this install step.
COPY README.md /opt/scylla/
COPY src/ /opt/scylla/src/
RUN pip install --user --no-cache-dir --no-deps /opt/scylla/

# ============================================================================
# Node.js source stage — copy binaries without curl | bash installer
# ============================================================================
# Pinned to node:20-slim SHA256 for reproducibility.
# Using multi-stage copy avoids the NodeSource curl|bash pattern which
# introduces an external dependency and pipe-to-shell security risk.
# Digest pinned 2026-03-26: node:20-slim (see #1591; may rotate — re-pin if CI breaks)
FROM node:20-slim@sha256:1e85773c98c31d4fe5b545e4cb17379e617b348832fb3738b22a08f68dec30f3 AS node-source

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
# Pinned to SHA256 digest for reproducibility - prevents drift from upstream updates
# Python 3.12 aligns with pyproject.toml classifiers (3.10-3.13); requires-python = ">=3.10"
FROM python:3.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

# Set labels for image metadata
LABEL org.opencontainers.image.title="scylla-runner"
LABEL org.opencontainers.image.description="AI agent testing and evaluation runner"
LABEL org.opencontainers.image.vendor="ProjectScylla"
LABEL org.opencontainers.image.version="latest"

# Copy Python packages from builder stage to global location
COPY --from=builder /root/.local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /root/.local/bin /usr/local/bin

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/scylla \
    XDG_CONFIG_HOME=/home/scylla/.config \
    CLAUDE_CONFIG_DIR=/home/scylla/.claude

# Install ONLY runtime dependencies (no build tools, no curl — Node.js copied from source stage)
# apt-get upgrade resolves OS-level CVEs (e.g. CVE-2026-0861 glibc heap corruption)
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code CLI)
# Copy from pinned node:20-slim stage — avoids curl|bash external dependency risk.
# node:20-slim ships /usr/local/bin/node and /usr/local/lib/node_modules/npm
COPY --from=node-source /usr/local/bin/node /usr/local/bin/node
COPY --from=node-source /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Install Claude Code CLI and patch transitive CVEs in a single layer.
# Merging into one RUN ensures npm's cache (which may contain auth tokens from
# the registry handshake) is purged in the same layer — Trivy's secret scanner
# inspects every layer, so a separate cleanup RUN would not help.
#
# CVE patches (npm audit fix --force is unreliable for global installs):
#   CVE-2024-21538 (cross-spawn ReDoS)
#   CVE-2025-64756 (glob command injection)
#   CVE-2026-26996/27903/27904 (minimatch DoS)
#   CVE-2026-23745/23950/24842/26960/29786/31802 (tar path traversal/overwrite)
#
# MAINTENANCE: These npm patch versions are pinned manually because Dependabot
# does not scan Dockerfile RUN lines. Update cadence and verification steps are
# documented in docs/dev/dockerfile-npm-cve-patches.md. Run
# `scripts/check_dockerfile_npm_patches.sh` to print currently-pinned versions
# and check them against the npm registry for newer fix releases.
RUN npm install -g @anthropic-ai/claude-code@2.1.91 \
    # Patch claude-code's transitive deps
    && cd /usr/local/lib/node_modules/@anthropic-ai/claude-code \
    && npm install cross-spawn@7.0.6 glob@11.1.0 minimatch@10.2.5 tar@7.5.13 --save \
    # Patch npm's own bundled copies — npm install inside npm's tree is unreliable,
    # so we install fixed versions globally then copy them over the vulnerable copies
    && npm install -g tar@7.5.13 cross-spawn@7.0.6 glob@11.1.0 minimatch@10.2.5 \
    && for pkg in tar cross-spawn glob minimatch; do \
         rm -rf /usr/local/lib/node_modules/npm/node_modules/$pkg \
         && cp -r /usr/local/lib/node_modules/$pkg /usr/local/lib/node_modules/npm/node_modules/$pkg; \
       done \
    && npm uninstall -g tar cross-spawn glob minimatch \
    # Purge npm cache — contains auth tokens from registry handshake
    && npm cache clean --force \
    && rm -rf /root/.npm /home/scylla/.npm /tmp/npm-*

# Create non-root user for security
RUN groupadd -r scylla && useradd -r -g scylla -m -s /bin/bash scylla

# Set up workspace directory (will be mounted at runtime with full project)
WORKDIR /workspace
RUN chown -R scylla:scylla /workspace

# Ensure clean Claude Code environment (no pre-existing config)
RUN rm -rf /home/scylla/.claude /home/scylla/.claude-plugin 2>/dev/null || true && \
    mkdir -p /home/scylla/.claude && \
    chown -R scylla:scylla /home/scylla/.claude

# Copy entry point script from docker/ subdirectory
COPY --chown=scylla:scylla docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables that containers receive at runtime
# These are documented but not set here - they're injected by the orchestrator
#
# TIER           - Test tier (T0, T1, T2, T3, T4, T5, T6)
# MODEL          - Model identifier (e.g., claude-sonnet-4-5-20250929)
# RUN_NUMBER     - Run number (1-9 for prompt sensitivity)
# ANTHROPIC_API_KEY - API key for Claude (passed from host)
# OPENAI_API_KEY    - API key for OpenAI models (if needed)
# TEST_ID        - Unique identifier for this test run
# TIMEOUT        - Maximum execution time in seconds

# Switch to non-root user
USER scylla

# Health check for container orchestration platforms
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c 'import scylla; print("OK")' || exit 1

# Default entry point
ENTRYPOINT ["/entrypoint.sh"]

# Default command (can be overridden)
CMD ["--help"]
