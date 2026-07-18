# Dockerfile SHA256 Digest Update Procedure

**Scope**: `docker/Dockerfile` base image re-pinning
**Audience**: Scylla maintainers and contributors

---

## Why SHA256 Digest Pinning Is Used

`docker/Dockerfile` pins the `python:3.12-slim` base image to a specific SHA256 digest on both
the builder stage and the runtime stage:

```dockerfile
FROM python:3.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c AS builder
```

Tag-only references (e.g., `FROM python:3.12-slim`) are mutable. The Docker registry can replace
the bytes behind a tag at any time — even a minor-version tag like `python:3.12.9-slim` can be
republished with security patches during a multi-day benchmark run. Because Scylla uses
`ANTHROPIC_API_KEY` and accumulates results over runs that may span days, bit-for-bit
reproducibility is required for evaluation integrity. A floating tag could silently change the
runtime environment between the first and last run of an experiment.

SHA256 digest pinning guarantees that every container uses exactly the same image layer tree,
regardless of when or where it is pulled.

---

## When to Re-Pin

Re-pin the digest when any of the following occur:

| Trigger | Action |
|---------|--------|
| Python security advisory published for the pinned image | Re-pin immediately |
| Monthly scheduled review | Re-pin if a newer patch image is available |
| Dependabot or Trivy scan flags a CVE in the base image | Re-pin immediately |
| Upgrading to a new Python minor version (e.g., 3.12 -> 3.13) | Re-pin to new version |

---

## How to Find the New SHA256 Digest

### Method 1: docker pull + docker inspect (recommended for single-arch)

```bash
# Pull the latest image for the tag (updates local cache)
docker pull python:3.12-slim

# Extract the digest from the local image metadata
docker inspect --format='{{index .RepoDigests 0}}' python:3.12-slim
# Output: python@sha256:<new-digest>
```

Copy the hex string after `sha256:` — that is the value to use in the Dockerfile.

### Method 2: docker buildx imagetools (multi-architecture digest)

```bash
# Inspect the manifest list without pulling the image
docker buildx imagetools inspect python:3.12-slim
```

The output lists per-architecture digests and the overall manifest list digest. Use the
manifest list digest (the first entry labelled `Name:`) when the image must be reproducible
across multiple architectures (e.g., AMD64 and ARM64). For Scylla's current single-arch
CI use Method 1 is sufficient.

### Method 3: Docker Hub registry API

```bash
# Query the registry directly (no local pull required)
curl -s "https://hub.docker.com/v2/repositories/library/python/tags/3.12-slim" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['digest'])"
```

This returns the manifest digest from Docker Hub without downloading the image layers.

---

## How to Verify the Digest

Before updating the Dockerfile, confirm the digest is correct:

```bash
# Pull the image by digest to verify it resolves
docker pull python@sha256:<new-digest>

# Confirm the Python version matches expectations
docker run --rm python@sha256:<new-digest> python --version
# Expected: Python 3.12.x
```

The Python minor/patch version printed here should match what you expect from the tag you
are pinning (e.g., `python:3.12-slim` should resolve to `Python 3.12.x`).

---

## How to Update the Dockerfile

The digest appears on **two lines** in `docker/Dockerfile` — once for the builder stage
(line 15) and once for the runtime stage (line 69). Both must be updated together.

1. Open `docker/Dockerfile`.
2. Replace the SHA256 hex string on both `FROM` lines with the new digest.
3. Update the inline comment to reference the issue or PR where this re-pin was verified.

Example — replacing the builder stage line:

```dockerfile
# Pinned to SHA256 digest for reproducibility - prevents drift from upstream updates
# Python 3.12 aligns with pyproject.toml classifiers (3.10-3.12); requires-python = ">=3.10"
FROM python:3.12-slim@sha256:<new-digest> AS builder
```

Apply the same change to the runtime stage `FROM` line. Both lines must carry the same digest
because Docker multi-stage builds pull the base image independently for each stage that names it.

---

## How to Test the Updated Dockerfile Locally

Run these steps in order before pushing the branch:

```bash
# Step 1: Dockerfile syntax check (fast, no build required)
docker build --check docker/

# Step 2: Full image build with the new digest
docker build -t scylla-test:local -f docker/Dockerfile .

# Step 3: Functional smoke tests
docker run --rm scylla-test:local python --version
docker run --rm scylla-test:local python -c "import scylla; print('OK')"

# Step 4: Validate the compose file
docker compose -f docker/docker-compose.yml config --quiet
```

Step 1 (`docker build --check`) is also the check run by `.github/workflows/docker-test.yml` in
CI (see `docs/dev/adr/docker-testing-deferred.md` for context on Docker CI scope). Steps 2-4 are
local-only verification and are not automated in CI.

---

## PR Workflow

Follow the standard project workflow from `CLAUDE.md`:

```bash
# 1. Create a feature branch
git checkout -b <issue-number>-update-dockerfile-digest origin/main

# 2. Edit docker/Dockerfile (update both FROM lines)
# 3. Stage and commit
git add docker/Dockerfile
git commit -m "chore(docker): pin python:3.12-slim to <short-digest-prefix>"

# 4. Push
git push -u origin <issue-number>-update-dockerfile-digest

# 5. Open PR
gh pr create \
  --title "[Chore] Update Dockerfile SHA256 digest" \
  --body "Closes #<issue-number>

Updates python:3.12-slim digest to <new-digest>.
Verified locally with smoke tests per docs/dev/dockerfile-sha256-update.md."

# 6. Enable auto-merge
gh pr merge --auto --squash
```

Never push the digest change directly to `main`. A PR is required even for one-line changes.

---

## Reference

| Item | Location |
|------|----------|
| Dockerfile | `docker/Dockerfile` |
| Docker CI workflow | `.github/workflows/docker-test.yml` |
| Docker testing ADR | `docs/dev/adr/docker-testing-deferred.md` |
| PR workflow | `.claude/shared/pr-workflow.md` |
