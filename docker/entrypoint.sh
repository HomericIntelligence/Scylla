#!/bin/bash
# Entry point script for scylla-runner container
#
# This script handles test execution within the Docker container.
# It validates environment variables, sets up the workspace, and
# executes the appropriate test command based on the tier configuration.
#
# Environment Variables (injected by orchestrator):
#   TIER           - Test tier (T0, T1, T2, T3, T4, T5, T6)
#   MODEL          - Model identifier
#   RUN_NUMBER     - Run number (1-9)
#   ANTHROPIC_API_KEY - API key for Claude
#   OPENAI_API_KEY    - API key for OpenAI (optional)
#   TEST_ID        - Unique test identifier
#   TIMEOUT        - Execution timeout in seconds
#   REPO_URL       - Git repository URL to clone
#   REPO_HASH      - Git commit hash to checkout
#   TEST_COMMAND   - Command to execute for testing

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Display help message
show_help() {
    cat << EOF
scylla-runner - AI Agent Test Execution Container

Usage: docker run scylla-runner:latest [OPTIONS] [COMMAND]

Options:
    --help          Show this help message
    --version       Show version information
    --validate      Validate environment configuration
    --run           Execute test run (default)

Environment Variables:
    TIER            Test tier (T0-T6) [required for --run]
    MODEL           Model identifier [required for --run]
    RUN_NUMBER      Run number (1-9) [required for --run]
    ANTHROPIC_API_KEY  Claude API key [required]
    OPENAI_API_KEY     OpenAI API key [optional]
    TEST_ID         Unique test identifier [required for --run]
    TIMEOUT         Execution timeout in seconds [default: 300]
    REPO_URL        Git repository URL to clone [optional]
    REPO_HASH       Git commit hash to checkout [optional]
    TEST_COMMAND    Command to execute [optional]

Examples:
    # Show help
    docker run scylla-runner:latest --help

    # Validate environment
    docker run -e ANTHROPIC_API_KEY=\$KEY scylla-runner:latest --validate

    # Run a test
    docker run -e TIER=T0 -e MODEL=claude-sonnet-4-5-20250929 -e RUN_NUMBER=1 \\
               -e TEST_ID=test-001 -e ANTHROPIC_API_KEY=\$KEY \\
               -v /path/to/workspace:/workspace \\
               scylla-runner:latest --run

EOF
}

# Display version information
show_version() {
    echo "scylla-runner version: latest"
    echo "Python: $(python3 --version 2>&1)"
    echo "Node.js: $(node --version 2>&1)"
    echo "Git: $(git --version 2>&1)"

    # Check if Claude CLI is installed
    if command -v claude &> /dev/null; then
        echo "Claude CLI: $(claude --version 2>&1 || echo 'installed')"
    else
        echo "Claude CLI: not installed"
    fi
}

# Validate required environment variables
validate_env() {
    local errors=0

    log_info "Validating environment configuration..."

    # Check for authentication (either API key or credentials file)
    if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ ! -f "${HOME}/.claude/.credentials.json" ]]; then
        log_error "No authentication found (neither ANTHROPIC_API_KEY nor credentials file)"
        ((errors++))
    else
        if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
            log_info "ANTHROPIC_API_KEY is set"
        fi
        if [[ -f "${HOME}/.claude/.credentials.json" ]]; then
            log_info "Claude Code credentials file is mounted"
        fi
    fi

    # Validate tier if set
    if [[ -n "${TIER:-}" ]]; then
        if [[ ! "${TIER}" =~ ^T[0-6]$ ]]; then
            log_error "TIER must be T0, T1, T2, T3, T4, T5, or T6 (got: ${TIER})"
            ((errors++))
        else
            log_info "TIER: ${TIER}"
        fi
    fi

    # Validate run number if set
    if [[ -n "${RUN_NUMBER:-}" ]]; then
        if [[ ! "${RUN_NUMBER}" =~ ^[1-9]$ ]]; then
            log_error "RUN_NUMBER must be 1-9 (got: ${RUN_NUMBER})"
            ((errors++))
        else
            log_info "RUN_NUMBER: ${RUN_NUMBER}"
        fi
    fi

    # Validate model if set
    if [[ -n "${MODEL:-}" ]]; then
        log_info "MODEL: ${MODEL}"
    fi

    # Validate test ID if set
    if [[ -n "${TEST_ID:-}" ]]; then
        log_info "TEST_ID: ${TEST_ID}"
    fi

    # Check optional variables
    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
        log_info "OPENAI_API_KEY is set"
    fi

    if [[ -n "${TIMEOUT:-}" ]]; then
        log_info "TIMEOUT: ${TIMEOUT}s"
    else
        log_info "TIMEOUT: 300s (default)"
    fi

    # Check workspace
    if [[ -d "/workspace" ]]; then
        log_info "Workspace directory exists"
        log_info "Workspace contents: $(find /workspace -maxdepth 1 2>/dev/null | wc -l) items"
    else
        log_warn "Workspace directory not mounted"
    fi

    if [[ ${errors} -gt 0 ]]; then
        log_error "Validation failed with ${errors} error(s)"
        return 1
    fi

    log_info "Environment validation passed"
    return 0
}

# Set up the workspace (clone repo if needed)
setup_workspace() {
    log_info "Setting up workspace..."

    # Clone repository if URL is provided
    if [[ -n "${REPO_URL:-}" ]]; then
        log_info "Cloning repository: ${REPO_URL}"

        # Check if workspace is empty
        if [[ -z "$(ls -A /workspace 2>/dev/null)" ]]; then
            git clone "${REPO_URL}" /workspace
        else
            log_warn "Workspace not empty, skipping clone"
        fi

        # Checkout specific commit if hash is provided
        if [[ -n "${REPO_HASH:-}" ]]; then
            log_info "Checking out commit: ${REPO_HASH}"
            cd /workspace && git checkout "${REPO_HASH}"
        fi
    fi

    log_info "Workspace setup complete"
}

# Ensure clean Claude Code environment
ensure_clean_claude_environment() {
    log_info "Ensuring clean Claude Code environment..."

    # Ensure .claude directory exists with proper permissions
    mkdir -p "${HOME}/.claude"
    chmod 700 "${HOME}/.claude"  # Owner can read/write/execute

    # Check for credentials in various locations (in order of preference)
    if [[ -f "/tmp/host-creds/.credentials.json" ]]; then
        # Current method: mounted from host
        log_info "Found mounted credentials at /tmp/host-creds/.credentials.json"
        cp "/tmp/host-creds/.credentials.json" "${HOME}/.claude/.credentials.json"
        chmod 600 "${HOME}/.claude/.credentials.json"  # Owner can read/write (for token refresh)
        log_info "Copied credentials to ${HOME}/.claude/.credentials.json"
    elif [[ -f "${HOME}/.claude/.credentials.json" ]]; then
        # Already exists (e.g., from previous setup)
        log_info "Using existing Claude Code credentials at ${HOME}/.claude/.credentials.json"
        chmod 600 "${HOME}/.claude/.credentials.json"  # Ensure proper permissions
    elif [[ -f "/mnt/claude-creds/.credentials.json" ]]; then
        # Legacy path support
        log_info "Found mounted credentials at /mnt/claude-creds/.credentials.json"
        cp "/mnt/claude-creds/.credentials.json" "${HOME}/.claude/.credentials.json"
        chmod 600 "${HOME}/.claude/.credentials.json"
        log_info "Copied credentials to ${HOME}/.claude/.credentials.json"
    elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        log_info "Using ANTHROPIC_API_KEY from environment"
    else
        log_warn "No Claude Code credentials or ANTHROPIC_API_KEY found"
        log_warn "Run 'claude auth' inside container to authenticate"
    fi

    log_info "Claude Code environment ready"
}

# Execute agent in container
run_agent() {
    log_info "Starting agent execution in container..."

    # Ensure clean Claude Code environment
    ensure_clean_claude_environment

    # Read task prompt
    if [[ ! -f "/prompt/task.md" ]]; then
        log_error "Task prompt not found at /prompt/task.md"
        exit 1
    fi

    # Validate authentication
    if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ ! -f "${HOME}/.claude/.credentials.json" ]]; then
        log_error "No authentication found (neither ANTHROPIC_API_KEY nor credentials file)"
        exit 1
    fi

    if [[ -z "${MODEL:-}" ]]; then
        log_error "MODEL is not set"
        exit 1
    fi

    # Change to workspace
    cd /workspace

    # Set timeout (default 600 seconds)
    local timeout_seconds="${TIMEOUT:-600}"

    log_info "Executing Claude CLI with model: ${MODEL}"
    log_info "Timeout: ${timeout_seconds}s"

    # Execute Claude Code CLI
    timeout "${timeout_seconds}" claude \
        --model "${MODEL}" \
        --print \
        --output-format stream-json \
        --verbose \
        "$(cat /prompt/task.md)" \
        > /output/stdout.log 2> /output/stderr.log

    local exit_code=$?

    # Save result
    if [[ ${exit_code} -eq 124 ]]; then
        echo "{\"exit_code\": ${exit_code}, \"timeout\": true}" > /output/result.json
        log_error "Agent execution timed out after ${timeout_seconds}s"
    else
        echo "{\"exit_code\": ${exit_code}, \"timeout\": false}" > /output/result.json
        log_info "Agent execution completed with exit code: ${exit_code}"
    fi

    # Make output files world-writable so host can overwrite them.
    # Best-effort: some files may not exist depending on execution path; log unexpected
    # failures (other than missing files) to stderr rather than aborting the agent.
    if ! chmod 666 /output/result.json /output/stdout.log /output/stderr.log 2>/dev/null; then
        echo "warn: chmod on /output/{result.json,stdout.log,stderr.log} encountered errors (idempotent)" >&2
    fi

    exit ${exit_code}
}

# Execute judge in container
run_judge() {
    log_info "Starting judge execution in container..."

    # Ensure clean Claude Code environment
    ensure_clean_claude_environment

    # Validate authentication
    if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ ! -f "${HOME}/.claude/.credentials.json" ]]; then
        log_error "No authentication found (neither ANTHROPIC_API_KEY nor credentials file)"
        exit 1
    fi

    if [[ -z "${MODEL:-}" ]]; then
        log_error "MODEL is not set"
        exit 1
    fi

    # Workspace is READ-ONLY at /workspace
    # Output goes to /output
    cd /workspace

    log_info "Executing judge with model: ${MODEL}"

    # Run judge evaluation
    # Note: This assumes the scylla package is available in the container
    python -m scylla.judge.runner \
        --workspace /workspace \
        --output /output \
        --model "${MODEL}" \
        --prompt /prompt/task.md

    local exit_code=$?
    log_info "Judge execution completed with exit code: ${exit_code}"
    exit ${exit_code}
}

# Execute the test run (legacy mode)
run_test() {
    log_info "Starting test execution..."
    log_info "Tier: ${TIER}"
    log_info "Model: ${MODEL}"
    log_info "Run Number: ${RUN_NUMBER}"
    log_info "Test ID: ${TEST_ID}"

    # Validate required variables for test run
    local required_vars=("TIER" "MODEL" "RUN_NUMBER" "TEST_ID")
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required variable ${var} is not set"
            exit 1
        fi
    done

    # Check authentication separately (allow either API key or credentials file)
    if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ ! -f "${HOME}/.claude/.credentials.json" ]]; then
        log_error "No authentication found (neither ANTHROPIC_API_KEY nor credentials file)"
        exit 1
    fi

    # Set up workspace
    setup_workspace

    # Set timeout (default 300 seconds)
    local timeout_seconds="${TIMEOUT:-300}"

    # Execute test command if provided
    if [[ -n "${TEST_COMMAND:-}" ]]; then
        log_info "Executing test command: ${TEST_COMMAND}"

        # Run with timeout
        timeout "${timeout_seconds}" bash -c "${TEST_COMMAND}"
        local exit_code=$?

        if [[ ${exit_code} -eq 124 ]]; then
            log_error "Test execution timed out after ${timeout_seconds}s"
            exit 124
        fi

        log_info "Test execution completed with exit code: ${exit_code}"
        exit ${exit_code}
    else
        log_info "No TEST_COMMAND specified, entering interactive mode"
        log_info "You can run commands manually in /workspace"
        exec /bin/bash
    fi
}

# Main entry point
main() {
    local command="${1:---help}"

    case "${command}" in
        --help|-h)
            show_help
            ;;
        --version|-v)
            show_version
            ;;
        --validate)
            validate_env
            ;;
        --run-agent)
            run_agent
            ;;
        --run-judge)
            run_judge
            ;;
        --run)
            validate_env || exit 1
            run_test
            ;;
        python|python3)
            # Running Python scripts directly
            # Ensure clean environment and execute
            ensure_clean_claude_environment
            exec "$@"
            ;;
        bash|sh)
            # Running interactive shell
            # Set up credentials first, then launch shell
            ensure_clean_claude_environment

            # Show welcome message for interactive sessions
            if [[ -t 0 ]]; then
                echo ""
                echo "=========================================="
                echo "ProjectScylla Container Shell"
                echo "=========================================="
                echo "Working Directory: $(pwd)"
                echo "Python Version: $(python --version 2>&1)"
                echo ""
                echo "Credentials: ${HOME}/.claude/.credentials.json"
                if [[ -f "${HOME}/.claude/.credentials.json" ]]; then
                    echo "  ✓ Credentials found"
                else
                    echo "  ✗ Credentials not found - run 'claude auth' to login"
                fi
                echo ""
                echo "Run experiments:"
                echo "  python scripts/manage_experiment.py run \\"
                echo "    --tiers-dir tests/fixtures/tests/test-001 \\"
                echo "    --tiers T0 --runs 1 -v"
                echo ""
                echo "Authenticate Claude (if needed):"
                echo "  claude auth"
                echo ""
                echo "=========================================="
                echo ""
            fi

            exec "$@"
            ;;
        *)
            # If unknown command, treat as a shell command
            # This allows running arbitrary commands like:
            # docker run scylla-runner:latest python scripts/manage_experiment.py run --args
            ensure_clean_claude_environment
            exec "$@"
            ;;
    esac
}

main "$@"
