#!/usr/bin/env bash
# Run a multi-phase batch experiment using manage_experiment.py.
#
# Executes three sequential phases:
#   Phase 1: Agent execution   (--until agent_complete)
#   Phase 2: Diff capture      (--until diff_captured, single thread)
#   Phase 3: Judging + finalize (full pipeline to completion)
#
# Usage:
#   ./scripts/run_batch_experiment.sh --results-dir <dir> --tests <t1> [<t2>...] [OPTIONS]
#
# Required:
#   --results-dir <dir>    Output directory for experiment results
#   --tests <id>...        One or more test IDs (e.g. test-001 test-002)
#
# Common options (passed through to manage_experiment.py in all phases):
#   --model <id>           Agent model ID (default: claude-haiku-4-5)
#   --judge-model <id>     Primary judge model (default: claude-opus-4-6)
#   --add-judge <id>       Add extra judge model (repeatable)
#   --tiers <T>...         Tiers to run (default: T0 T1 T2 T3 T4 T5 T6)
#   --runs <n>             Runs per subtest (default: 3)
#   --max-subtests <n>     Max subtests per tier (default: 50)
#   --config <dir>         Test config directory (default: tests/fixtures/tests/)
#   --threads <n>          Phase 1/3 thread count (default: 5)
#   --max-concurrent-agents <n>  Concurrent agent limit (default: 3)
#   --off-peak             Wait for off-peak API hours before each subtest
#
# Examples:
#   # Minimal: single test, default model
#   ./scripts/run_batch_experiment.sh \
#       --results-dir ~/results/my-run \
#       --tests test-001
#
#   # Full haiku batch: multiple tests, custom threads
#   ./scripts/run_batch_experiment.sh \
#       --results-dir ~/results/haiku-run \
#       --model claude-haiku-4-5 \
#       --tests test-001 test-002 test-003 \
#       --threads 5 \
#       --runs 5

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
RESULTS_DIR=""
TESTS=()
MODEL="claude-haiku-4-5"
JUDGE_MODEL="claude-opus-4-6"
EXTRA_JUDGES=("claude-sonnet-4-6" "claude-haiku-4-5")
TIERS=(T0 T1 T2 T3 T4 T5 T6)
RUNS=3
MAX_SUBTESTS=50
CONFIG_DIR="tests/fixtures/tests/"
THREADS=5
MAX_CONCURRENT_AGENTS=3
OFF_PEAK=0

# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
    case "$1" in
        --results-dir)   RESULTS_DIR="$2";        shift 2 ;;
        --tests)
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                TESTS+=("$1"); shift
            done
            ;;
        --model)         MODEL="$2";              shift 2 ;;
        --judge-model)   JUDGE_MODEL="$2";        shift 2 ;;
        --add-judge)
            EXTRA_JUDGES=()
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                EXTRA_JUDGES+=("$1"); shift
            done
            ;;
        --tiers)
            TIERS=()
            shift
            while [[ $# -gt 0 && "$1" != --* ]]; do
                TIERS+=("$1"); shift
            done
            ;;
        --runs)                   RUNS="$2";                   shift 2 ;;
        --max-subtests)           MAX_SUBTESTS="$2";           shift 2 ;;
        --config)                 CONFIG_DIR="$2";             shift 2 ;;
        --threads)                THREADS="$2";                shift 2 ;;
        --max-concurrent-agents)  MAX_CONCURRENT_AGENTS="$2";  shift 2 ;;
        --off-peak)               OFF_PEAK=1;                  shift ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
if [[ -z "$RESULTS_DIR" ]]; then
    echo "Error: --results-dir is required" >&2
    exit 1
fi

if [[ ${#TESTS[@]} -eq 0 ]]; then
    echo "Error: --tests requires at least one test ID" >&2
    exit 1
fi

# --------------------------------------------------------------------------- #
# Build common args
# --------------------------------------------------------------------------- #
COMMON_ARGS=(
    --judge-model "$JUDGE_MODEL"
)
for j in "${EXTRA_JUDGES[@]}"; do
    COMMON_ARGS+=(--add-judge "$j")
done
COMMON_ARGS+=(
    --results-dir "$RESULTS_DIR"
    --tiers "${TIERS[@]}"
    --runs "$RUNS"
    --max-subtests "$MAX_SUBTESTS"
    --config "$CONFIG_DIR"
    --model "$MODEL"
    --tests "${TESTS[@]}"
)
if [[ "$OFF_PEAK" -eq 1 ]]; then
    COMMON_ARGS+=(--off-peak)
fi

LOG_FILE="$RESULTS_DIR/run.log"
mkdir -p "$RESULTS_DIR"

cd "$REPO_DIR"

echo "=== Batch experiment: ${TESTS[*]} ===" | tee "$LOG_FILE"
echo "  results-dir : $RESULTS_DIR"         | tee -a "$LOG_FILE"
echo "  model       : $MODEL"               | tee -a "$LOG_FILE"
echo "  tiers       : ${TIERS[*]}"          | tee -a "$LOG_FILE"
echo "  runs        : $RUNS"                | tee -a "$LOG_FILE"
echo ""

echo "=== Phase 1: agent execution (${THREADS} threads, --until agent_complete) ===" \
    | tee -a "$LOG_FILE"
uv run python scripts/manage_experiment.py run \
    --threads "$THREADS" \
    --until agent_complete \
    --max-concurrent-agents "$MAX_CONCURRENT_AGENTS" \
    "${COMMON_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"

echo "=== Phase 2: diff capture (1 thread, --until diff_captured) ===" \
    | tee -a "$LOG_FILE"
uv run python scripts/manage_experiment.py run \
    --threads 1 \
    --until diff_captured \
    "${COMMON_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"

echo "=== Phase 3: judging + finalization (${THREADS} threads) ===" \
    | tee -a "$LOG_FILE"
uv run python scripts/manage_experiment.py run \
    --threads "$THREADS" \
    --max-concurrent-agents "$MAX_CONCURRENT_AGENTS" \
    "${COMMON_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"

echo "=== Batch complete. Results: $RESULTS_DIR ===" | tee -a "$LOG_FILE"
