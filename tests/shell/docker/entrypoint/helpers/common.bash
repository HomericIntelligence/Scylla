# common.bash — shared BATS helpers for docker/entrypoint.sh tests

_HELPERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_MOCKS_DIR="${_HELPERS_DIR}/../mocks"

# Prepend the mocks/ directory so our stubs shadow real binaries.
setup_mocks() {
    export PATH="${_MOCKS_DIR}:${PATH}"
}

# Unset all mock control variables so each test starts clean.
# `unset` returns 0 for non-existent (and non-readonly) variables, so no
# error-suppression is needed here. If any variable becomes readonly in the
# future, unset will fail loudly — that's the desired behaviour.
clean_state() {
    unset CLAUDE_MOCK_EXIT
    unset TIMEOUT_MOCK_EXIT
    unset GIT_MOCK_CLONE_EXIT
    unset PYTHON_MOCK_EXIT
    unset ANTHROPIC_API_KEY
    unset OPENAI_API_KEY
    unset TIER
    unset RUN_NUMBER
    unset MODEL
    unset TEST_ID
    unset TIMEOUT
    unset REPO_URL
    unset REPO_HASH
    unset TEST_COMMAND
}
