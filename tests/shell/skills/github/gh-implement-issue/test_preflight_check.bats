#!/usr/bin/env bats
# Tests for preflight_check.sh
# Covers the 5 behavioral scenarios from issue #800.

load helpers/common

SCRIPT="$(git -C "$(dirname "$BATS_TEST_FILENAME")" rev-parse --show-toplevel)/scripts/preflight_check.sh"

setup() {
    setup_mocks
    clean_state
}

# ---------------------------------------------------------------------------
# Test 1: Closed issue triggers exit 1
# ---------------------------------------------------------------------------
@test "closed issue triggers exit 1" {
    export GH_MOCK_ISSUE_STATE='{"state":"CLOSED","title":"Done Issue","closedAt":"2024-01-01T00:00:00Z"}'

    run bash "$SCRIPT" 800

    [ "$status" -eq 1 ]
    [[ "$output" == *"[STOP]"* ]]
    [[ "$output" == *"CLOSED"* ]]
}

# ---------------------------------------------------------------------------
# Test 2: Merged PR triggers exit 1
# ---------------------------------------------------------------------------
@test "merged PR triggers exit 1" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"My Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[{"number":99,"title":"Fix everything","state":"MERGED"}]'

    run bash "$SCRIPT" 800

    [ "$status" -eq 1 ]
    [[ "$output" == *"[STOP]"* ]]
    [[ "$output" == *"MERGED"* ]]
}

# ---------------------------------------------------------------------------
# Test 3: Open PR exits 0 with warning
# ---------------------------------------------------------------------------
@test "open PR exits 0 with warning" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"My Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[{"number":42,"title":"WIP: Fix","state":"OPEN"}]'

    run bash "$SCRIPT" 800

    [ "$status" -eq 0 ]
    [[ "$output" == *"[WARN]"* ]]
    [[ "$output" == *"OPEN PR"* ]]
}

# ---------------------------------------------------------------------------
# Test 4: Worktree conflict triggers exit 1
# ---------------------------------------------------------------------------
@test "worktree conflict triggers exit 1" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"My Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[]'
    export GIT_MOCK_WORKTREE="/home/user/Scylla/.worktrees/issue-800  abc1234 [800-auto-impl]"

    run bash "$SCRIPT" 800

    [ "$status" -eq 1 ]
    [[ "$output" == *"[STOP]"* ]]
    [[ "$output" == *"Worktree already exists"* ]]
}

# ---------------------------------------------------------------------------
# Test 5: Clean state passes all checks
# ---------------------------------------------------------------------------
@test "clean state passes all checks" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"Clean Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[]'
    # GIT_MOCK_WORKTREE, GIT_MOCK_LOG, GIT_MOCK_BRANCH all unset → empty output

    run bash "$SCRIPT" 800

    [ "$status" -eq 0 ]
    [[ "$output" == *"SAFE TO PROCEED"* ]]
}

# ---------------------------------------------------------------------------
# Test 6: Missing issue number argument exits 1 (#901)
# ---------------------------------------------------------------------------
@test "missing issue number argument exits 1" {
    run bash "$SCRIPT"

    [ "$status" -eq 1 ]
    [[ "$output" == *"issue number"* ]] || [[ "$output" == *"usage"* ]] || [[ "$output" == *"Usage"* ]]
}

# ---------------------------------------------------------------------------
# Test 7: gh CLI failure (unreachable/auth failure) exits 1 (#902)
# ---------------------------------------------------------------------------
@test "gh CLI failure exits 1 with STOP message" {
    # Create a temporary gh that always fails
    local tmpdir
    tmpdir="$(mktemp -d)"
    printf '#!/usr/bin/env bash\nexit 1\n' > "${tmpdir}/gh"
    chmod +x "${tmpdir}/gh"
    export PATH="${tmpdir}:${PATH}"

    run bash "$SCRIPT" 800

    [ "$status" -eq 1 ]
    [[ "$output" == *"[STOP]"* ]]

    rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Test 8: Empty worktree list does not abort the script (#905)
# ---------------------------------------------------------------------------
@test "empty worktree list passes check 4 without aborting" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"Clean Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[]'
    # GIT_MOCK_WORKTREE is unset → git worktree list returns empty → grep exits 1 → || true rescues
    unset GIT_MOCK_WORKTREE

    run bash "$SCRIPT" 800

    [ "$status" -eq 0 ]
    [[ "$output" == *"SAFE TO PROCEED"* ]]
}

# ---------------------------------------------------------------------------
# Test 9: Merged PR mentions issue in title but has no closingRef → PASS (#909)
# ---------------------------------------------------------------------------
@test "merged PR with title mention but no closingRef passes check 3" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"My Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[{"number":55,"title":"Fix issue 800 typo","state":"MERGED"}]'
    export GH_MOCK_PR_CLOSES=""   # explicit empty → closingIssuesReferences:[]

    run bash "$SCRIPT" 800

    [ "$status" -eq 0 ]
    [[ "$output" == *"[PASS]"* ]]
}

# ---------------------------------------------------------------------------
# Test 10: Merged PR with formal closingRef triggers STOP for check 3 (#909)
# ---------------------------------------------------------------------------
@test "merged PR with formal closingRef triggers STOP for check 3" {
    export GH_MOCK_ISSUE_STATE='{"state":"OPEN","title":"My Issue","closedAt":null}'
    export GH_MOCK_PR_JSON='[{"number":42,"title":"Fix it","state":"MERGED"}]'
    export GH_MOCK_PR_CLOSES=800  # formal close reference

    run bash "$SCRIPT" 800

    [ "$status" -eq 1 ]
    [[ "$output" == *"[STOP]"* ]]
}
