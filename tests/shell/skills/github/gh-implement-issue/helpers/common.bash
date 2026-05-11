# common.bash — shared BATS helpers for preflight_check.sh tests

_HELPERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_MOCKS_DIR="${_HELPERS_DIR}/../mocks"

# Prepend the mocks/ directory so our stub gh/git shadow the real ones.
setup_mocks() {
    export PATH="${_MOCKS_DIR}:${PATH}"
}

# Unset all mock control variables so each test starts clean.
# `unset` returns 0 for non-existent (and non-readonly) variables, so no
# error-suppression is needed here. If any variable becomes readonly in the
# future, unset will fail loudly — that's the desired behaviour.
clean_state() {
    unset GH_MOCK_ISSUE_STATE
    unset GH_MOCK_PR_JSON
    unset GH_MOCK_ISSUE_COMMENTS
    unset GH_MOCK_PR_CLOSES
    unset GIT_MOCK_LOG
    unset GIT_MOCK_WORKTREE
    unset GIT_MOCK_BRANCH
}
