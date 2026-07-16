# ADR: Docker Integration Testing Deferred

**Date**: 2026-02-27
**Status**: Accepted
**Issue**: [#1114](https://github.com/HomericIntelligence/Scylla/issues/1114)

## Context

The `.github/workflows/docker-test.yml` CI workflow contained a step that ran
`pixi run pytest tests/docker/ -v --no-cov`, but `tests/docker/` never existed.
This created a false sense of Docker test coverage while wasting CI resources on
a step that would fail immediately if it ever ran against an empty directory.

## Decision

Remove the dead `pytest tests/docker/` step from the CI workflow. Retain the two
genuine validation steps:

1. **Dockerfile syntax check** — `docker build --check docker/` validates syntax
   without building the image.
2. **docker-compose config check** — `docker compose config --quiet` validates the
   compose file structure.

Rename the workflow from "Docker Build Test" to "Docker Validation" to accurately
reflect what it does.

## Reasons

- The Docker image requires `ANTHROPIC_API_KEY` and Claude Code credentials.
  Meaningful integration tests cannot run in standard CI without injecting secrets.
- `docker/entrypoint.sh` contains 457 lines of shell logic. Shell script testing
  belongs in `tests/shell/` using BATS, not in `tests/docker/` using pytest.
- Issue #1113 already tracks the shell script test gap and is the correct scope
  for entrypoint coverage.
- The two retained validation steps provide genuine value (catch Dockerfile syntax
  errors and compose file misconfigurations) with zero maintenance overhead.

## Consequences

- `tests/docker/` is not created; it remains absent.
- The CI workflow no longer references non-existent test files.
- Docker integration testing remains a known gap, tracked in issue #1113.
- If Docker integration tests are later implemented, they should be added as a
  separate workflow with appropriate secrets configuration.

## Future Implementation Guide (Option A: Full Integration Tests)

### Required GitHub Actions Secrets

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `ANTHROPIC_API_KEY` | API key for Claude model access during container tests | Anthropic Console → API Keys |

The `docker-test.yml` workflow currently performs syntax validation only (no secrets required).
If Docker integration tests are added, `ANTHROPIC_API_KEY` is the only secret needed for the
image to run agent workloads.

### Configuring Secrets in GitHub Repository Settings

1. Navigate to **Settings → Secrets and variables → Actions** in the GitHub repository.
2. Click **New repository secret**.
3. Set **Name** to `ANTHROPIC_API_KEY`.
4. Set **Value** to a valid Anthropic API key scoped to the project.
5. Click **Add secret**.

Do not mount `~/.claude/.credentials.json` into CI containers — environment variables are the
correct injection method for GitHub Actions runners. The credential file pattern applies only
to local development environments.

### Skeleton Workflow Step

```yaml
- name: Run Docker integration tests
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    docker run --rm \
      -e ANTHROPIC_API_KEY \
      scylla:test \
      pytest tests/docker/ -v
```

Notes:

- `--rm` removes the container after the test run.
- Pass `-e ANTHROPIC_API_KEY` (no value) to forward the env var set in the `env:` block;
  this avoids echoing the secret in the shell command.
- If tests write artifacts, add `-v ${{ github.workspace }}/test-results:/results`.
- Credential files written inside the container are cleaned up automatically by `--rm`;
  no explicit cleanup step is needed.
- Gate the step on non-fork PRs to avoid leaking secrets:
  `if: github.event.pull_request.head.repo.full_name == github.repository`
- WSL2 local dev note: `/tmp` is not exposed to Docker by default on WSL2; use a home
  directory path or an explicitly bound path for any temporary credential directories.

### Acceptance Criteria for Option A

- [ ] `ANTHROPIC_API_KEY` secret is configured in repository settings.
- [ ] `docker-test.yml` includes a step with `-e ANTHROPIC_API_KEY` (env var injection,
      not file mount).
- [ ] At least one test in `tests/docker/` makes a real API call and passes in CI.
- [ ] Workflow step is gated to not run on forks.
