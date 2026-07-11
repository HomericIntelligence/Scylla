#!/bin/bash
# Run the Scylla CI suite locally inside a container.
#
# Mirrors what GitHub Actions runs, using the same CI container image.
# Supports both Podman (rootless, no SU — preferred) and Docker.
#
# Usage:
#   ./scripts/run_ci_local.sh              # Run all CI checks
#   ./scripts/run_ci_local.sh pre-commit   # Linting + type checking only
#   ./scripts/run_ci_local.sh test         # pytest unit + integration
#   ./scripts/run_ci_local.sh test-unit    # pytest unit tests only
#   ./scripts/run_ci_local.sh test-int     # pytest integration tests only
#   ./scripts/run_ci_local.sh security     # pip-audit dependency scan
#   ./scripts/run_ci_local.sh shell-test   # BATS shell tests
#
# Container engine: auto-detected (podman first, docker fallback).
# Override: CONTAINER_ENGINE=docker ./scripts/run_ci_local.sh
#
# Image: uses 'scylla-ci:local' if available, falls back to GHCR image.
# Build locally: pixi run ci-build  (or: podman build -f ci/Containerfile -t scylla-ci:local .)

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SUBSET="${1:-all}"

# CI image: prefer locally-built image; fall back to GHCR
LOCAL_IMAGE="scylla-ci:local"
GHCR_IMAGE="ghcr.io/homericintelligence/scylla-ci:latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[CI]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[CI]${NC} $*"; }
log_error() { echo -e "${RED}[CI]${NC} $*" >&2; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

# ============================================================================
# Container engine detection
# ============================================================================

detect_engine() {
    if [ -n "${CONTAINER_ENGINE:-}" ]; then
        if ! command -v "${CONTAINER_ENGINE}" &> /dev/null; then
            log_error "CONTAINER_ENGINE=${CONTAINER_ENGINE} not found in PATH"
            exit 1
        fi
        log_info "Container engine: ${CONTAINER_ENGINE} (from env)"
        return
    fi

    if command -v podman &> /dev/null; then
        CONTAINER_ENGINE="podman"
        log_info "Container engine: podman (rootless)"
    elif command -v docker &> /dev/null; then
        CONTAINER_ENGINE="docker"
        log_info "Container engine: docker"
    else
        log_error "No container engine found. Install podman (recommended) or docker."
        log_error "  Podman: https://podman.io/getting-started/installation"
        exit 1
    fi
    export CONTAINER_ENGINE
}

# ============================================================================
# Image resolution
# ============================================================================

resolve_image() {
    if "${CONTAINER_ENGINE}" image exists "${LOCAL_IMAGE}" 2>/dev/null || \
       "${CONTAINER_ENGINE}" images -q "${LOCAL_IMAGE}" 2>/dev/null | grep -q .; then
        CI_IMAGE="${LOCAL_IMAGE}"
        log_info "Using local CI image: ${CI_IMAGE}"
    else
        log_warn "Local image '${LOCAL_IMAGE}' not found."
        log_warn "Pulling from GHCR: ${GHCR_IMAGE}"
        log_warn "(To build locally: pixi run ci-build)"
        "${CONTAINER_ENGINE}" pull "${GHCR_IMAGE}"
        CI_IMAGE="${GHCR_IMAGE}"
    fi
    export CI_IMAGE
}

# ============================================================================
# Run a command inside the CI container
# ============================================================================
# Volume mounts:
#   /workspace  — the full repo (rw, :Z for SELinux/Podman)
#   /workspace/.git — repo git metadata (read-only, for pre-commit incremental)
# --userns=keep-id — Podman: map host UID into container (fixes mounted file ownership)
# No effect on Docker (flag ignored or equivalent to default behavior)

run_in_container() {
    local cmd=("$@")
    local engine_flags=()

    # Podman-specific flags for rootless execution
    if [ "${CONTAINER_ENGINE}" = "podman" ]; then
        engine_flags+=(--userns=keep-id)
    fi

    "${CONTAINER_ENGINE}" run --rm \
        "${engine_flags[@]}" \
        --volume "${PROJECT_ROOT}:/workspace:Z" \
        --workdir /workspace \
        "${CI_IMAGE}" \
        "${cmd[@]}"
}

# ============================================================================
# CI steps
# ============================================================================

run_pre_commit() {
    log_step "Pre-commit (linting, type checking, security hooks)"
    run_in_container \
        pixi run --environment lint \
        pre-commit run --all-files --show-diff-on-failure
}

run_test_unit() {
    log_step "Unit tests (pytest tests/unit, 75% coverage floor)"
    run_in_container \
        pixi run pytest tests/unit \
            --override-ini="addopts=" \
            -v --strict-markers \
            --cov=src/scylla --cov-report=term-missing \
            --cov-fail-under=75
}

run_test_integration() {
    log_step "Integration tests (pytest tests/integration)"
    run_in_container \
        pixi run pytest tests/integration \
            -v --cov=src/scylla --cov-report=term-missing
}

run_security() {
    log_step "Security scan (pip-audit, HIGH/CRITICAL only)"
    run_in_container \
        pixi run --environment lint pip-audit
}

run_shell_tests() {
    log_step "Shell tests (BATS)"
    run_in_container \
        sh -c "PREFLIGHT_INTEGRATION=0 pixi run test-shell"
}

# ============================================================================
# Main
# ============================================================================

FAILED=()

run_step() {
    local name="$1"
    local fn="$2"
    if ! "${fn}"; then
        FAILED+=("${name}")
        log_error "${name} FAILED"
    fi
}

detect_engine
resolve_image

log_info "CI subset: ${SUBSET}"
log_info "Project root: ${PROJECT_ROOT}"

case "${SUBSET}" in
    pre-commit)
        run_step "pre-commit" run_pre_commit
        ;;
    test|test-all)
        run_step "test-unit" run_test_unit
        run_step "test-integration" run_test_integration
        ;;
    test-unit)
        run_step "test-unit" run_test_unit
        ;;
    test-int|test-integration)
        run_step "test-integration" run_test_integration
        ;;
    security)
        run_step "security" run_security
        ;;
    shell-test|shell)
        run_step "shell-test" run_shell_tests
        ;;
    all)
        run_step "pre-commit" run_pre_commit
        run_step "test-unit" run_test_unit
        run_step "test-integration" run_test_integration
        run_step "security" run_security
        run_step "shell-test" run_shell_tests
        ;;
    *)
        log_error "Unknown subset: ${SUBSET}"
        log_error "Valid values: all, pre-commit, test, test-unit, test-int, security, shell-test"
        exit 1
        ;;
esac

echo ""
if [ "${#FAILED[@]}" -eq 0 ]; then
    log_info "All CI checks passed."
else
    log_error "Failed: ${FAILED[*]}"
    exit 1
fi
