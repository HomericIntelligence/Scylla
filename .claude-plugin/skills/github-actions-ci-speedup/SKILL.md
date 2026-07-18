# Skill: github-actions-ci-speedup

## Overview

| Field     | Value |
|-----------|-------|
| Date      | 2026-02-20 |
| Issue     | #787 |
| PR        | #835 |
| Objective | Reduce GitHub Actions CI from 7+ minutes to ~2 minutes by enabling dependency caching, caching pre-commit environments, and running pre-commit on changed files only for PRs |
| Outcome   | Success — all changes committed and pushed; expected 5–6 min savings per job on cache hits |

## When to Use

- CI/CD pipeline is taking 5+ minutes on dependency installation
- Dependency caching is disabled or misconfigured, so every run re-resolves and re-downloads
- Every CI run shows "Cache miss" with no successful restore or save
- Pre-commit runs `--all-files` even on PRs that touch only a few files
- Codecov step failing with 429 rate-limit errors

## Root Cause: Uncached Dependency Install

Without a warm dependency cache, every CI run does a full `uv sync` (download + resolve),
which dominates wall-clock time. The fix is to let `astral-sh/setup-uv` cache the uv
download/build cache via its built-in `enable-cache: true`, keyed off `uv.lock`.

## Verified Workflow

### 1. Identify the problem

Look for these patterns in CI logs:

- `uv sync` step taking 5–7 minutes on every run
- `Cache miss` with no successful restore or save
- Total CI time dominated by dependency install (>80% of runtime)

### 2. Enable uv caching (both jobs)

Use `astral-sh/setup-uv` with `enable-cache: true`; it caches the uv cache directory and
keys it off `uv.lock` automatically:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@<sha>  # v7
  with:
    enable-cache: true

- name: Install dependencies
  run: uv sync --all-groups --all-extras --locked
```

**Key points:**

- `enable-cache: true` keys the uv cache off `uv.lock` — invalidated only when dependencies change
- The uv cache is restored across runs, so `uv sync` on a warm cache completes in seconds
- The pre-commit and test jobs can share the same cache since they use the same `uv.lock`
- `--locked` fails fast if `uv.lock` is out of date rather than silently re-resolving

### 3. Cache pre-commit hook environments

Pre-commit downloads and installs hooks (Node.js for markdownlint, yamllint, shellcheck) on every run. Add a second cache step:

```yaml
- name: Cache pre-commit environments
  uses: actions/cache@v4
  with:
    path: ~/.cache/pre-commit
    key: pre-commit-${{ runner.os }}-${{ hashFiles('.pre-commit-config.yaml') }}
    restore-keys: |
      pre-commit-${{ runner.os }}-
```

### 4. Run pre-commit on changed files only for PRs

```yaml
- name: Run pre-commit
  env:
    EVENT_NAME: ${{ github.event_name }}
    BASE_REF: ${{ github.base_ref }}
  run: |
    uv sync --all-groups --all-extras --locked
    if [ "$EVENT_NAME" = "push" ]; then
      uv run pre-commit run --all-files --show-diff-on-failure
    else
      uv run pre-commit run --from-ref "origin/$BASE_REF" --to-ref HEAD --show-diff-on-failure
    fi
```

**Security note**: `github.base_ref` must go through an `env:` variable (not inline `${{ }}` in `run:`). This is the safe pattern per GitHub's injection guidance.

### 5. Fix Codecov rate limiting

```yaml
- name: Upload coverage
  if: matrix.test-group.name == 'unit'
  uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
    flags: ${{ matrix.test-group.name }}
    token: ${{ secrets.CODECOV_TOKEN }}
    fail_ci_if_error: false
```

### 6. Verify

After pushing:

1. **First run**: cache miss, but `Cache saved successfully` appears (not `Failed to save`)
2. **Second run (same PR)**: cache hit, `uv sync` completes in <30s
3. All tests pass, coverage ≥ 72%
4. All pre-commit hooks pass

## Failed Attempts

### 1. (Historical) Working around broken `setup-pixi` built-in cache

**Note**: This project has migrated from pixi to uv. The original speedup work fought an
unreliable `prefix-dev/setup-pixi` `cache: true` (HTTP 400 / `Saved cache with ID -1`) by
replacing it with an explicit `actions/cache@v4` over `.pixi` and `~/.cache/rattler/cache`.
That workaround no longer applies: `astral-sh/setup-uv`'s built-in `enable-cache: true` is
reliable, so prefer it over a hand-rolled cache step.

### 2. Using `github.base_ref` directly inline in `run:` step

**What happened**: The security pre-tool-use hook blocked the edit with a warning about using `${{ github.base_ref }}` directly inside a `run:` block (potential injection risk if the ref were attacker-controlled in a fork PR).

**Fix**: Move it to an `env:` block and reference via `$BASE_REF`. This is the safe and correct pattern regardless of actual injection risk.

### 3. (Historical) Caching only `.pixi` without the package cache

**Note**: Superseded by the uv migration. Under pixi, caching only `.pixi` without
`~/.cache/rattler/cache` (the downloaded conda packages) meant packages were re-downloaded
on every run. With `astral-sh/setup-uv` `enable-cache: true`, the uv cache directory is
handled for you, so there is no separate package cache to manage.

## Results & Parameters

| Metric | Before | After (cache hit) |
|--------|--------|-------------------|
| `uv sync` (test job) | ~6m21s | ~10-20s |
| `uv sync` (pre-commit job) | ~6m16s | ~10-20s |
| pre-commit hook setup | ~32s | ~3-5s |
| Total CI wall-clock | ~7m30s | ~2 min |
| Percentage wasted on install | 85% | ~10% |

**Configuration used:**

```yaml
# uv dependency cache: handled by setup-uv, keyed off uv.lock
- uses: astral-sh/setup-uv@<sha>  # v7
  with:
    enable-cache: true

# Pre-commit cache key pattern
key: pre-commit-${{ runner.os }}-${{ hashFiles('.pre-commit-config.yaml') }}
restore-keys: |
  pre-commit-${{ runner.os }}-
```

## Diagnosis Checklist

When CI is slow due to dependency installation:

- [ ] Check the `uv sync` step duration — if >2 min on a warm cache, caching is broken
- [ ] Look for repeated `Cache miss` with no successful save
- [ ] Confirm `enable-cache: true` is set on `astral-sh/setup-uv`
- [ ] Confirm the pre-commit cache uses `actions/cache@v4` (not v3 or v2)
- [ ] Confirm `uv sync` uses `--locked` so a stale `uv.lock` fails fast
