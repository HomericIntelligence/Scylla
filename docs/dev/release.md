# Release Process

This document describes how to cut a Scylla release and the one-time
setup required to enable PyPI publishing via Trusted Publishing (OIDC).

## Release workflow overview

The `release.yml` workflow handles the full release pipeline:

| Trigger | Jobs that run |
|---------|--------------|
| `workflow_dispatch` (part=patch/minor/major) | `bump-version` — bumps `pyproject.toml`, commits, tags, opens PR |
| `push` tag `v*` | `release` (GitHub Release) → `build` (sdist + wheel) → `publish-pypi` (PyPI OIDC) |
| `workflow_dispatch` (testpypi=true) | `publish-testpypi` — publishes to TestPyPI for smoke-testing |

## Normal release procedure

1. Trigger the **Release** workflow via GitHub Actions → *Run workflow* with the
   desired version part (`patch`, `minor`, or `major`).
2. The workflow bumps the version in `pyproject.toml`, commits,
   creates a tag (`vX.Y.Z`), and opens a PR.
3. Once the version-bump PR merges the tag is already pushed, which triggers the
   `release` → `build` → `publish-pypi` chain automatically.

## One-time PyPI Trusted Publishing setup

PyPI Trusted Publishing uses OIDC tokens so **no `PYPI_API_TOKEN` secret is
needed** in the repository or organisation settings.

### Prerequisites

- A PyPI account with maintainer rights (or the ability to create the project).
- A TestPyPI account for dry-run testing (recommended).

### Steps

#### 1. Create the PyPI project

If the project does not yet exist on PyPI:

```bash
# Build locally and upload once with a traditional API token to claim the name.
# After this first upload you can switch to Trusted Publishing.
python -m build
python -m twine upload dist/*
```

Alternatively, create the project through the PyPI web UI at
<https://pypi.org/manage/projects/> without uploading anything, then configure
Trusted Publishing before the first upload.

#### 2. Configure Trusted Publishing on PyPI

1. Go to <https://pypi.org/manage/project/scylla/settings/publishing/>.
2. Under **Add a new publisher**, select **GitHub Actions**.
3. Fill in the form exactly as shown:

   | Field | Value |
   |-------|-------|
   | PyPI project name | `scylla` |
   | Owner | `HomericIntelligence` |
   | Repository name | `Scylla` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

4. Click **Add**.

#### 3. Configure Trusted Publishing on TestPyPI (optional but recommended)

Repeat step 2 on <https://test.pypi.org/manage/project/scylla/settings/publishing/>
with the same values except **Environment name** = `testpypi`.

#### 4. Create the GitHub environment

1. Go to **Settings → Environments** in the GitHub repository.
2. Create an environment named `pypi`.
3. Optionally add a protection rule (e.g. required reviewers, tag-only
   deployment) to prevent accidental publishes.
4. Repeat for `testpypi`.

No secrets need to be added to the environment — the OIDC token is exchanged
automatically by `pypa/gh-action-pypi-publish`.

## TestPyPI dry-run

To smoke-test the publish pipeline without cutting a real tag:

1. Go to **Actions → Release → Run workflow**.
2. Set **Version part** to any value (it will not be used).
3. Set **Dry-run: publish to TestPyPI** to `true`.
4. Click **Run workflow**.

The `publish-testpypi` job will build and publish to TestPyPI.  Verify the
package installs correctly:

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ scylla
```

## Verifying a release

After a successful publish:

```bash
pip install scylla
scylla --help
```

The `scylla` entry-point is defined in `pyproject.toml`:

```toml
[project.scripts]
scylla = "scylla.cli.main:cli"
```

## Artifact inspection

The `build` job uploads `dist/` as a GitHub Actions artifact named `dist` with
a 7-day retention window.  Download it from the workflow run summary to inspect
the sdist and wheel before they land on PyPI.

## Security notes

- The workflow uses OIDC (`id-token: write`) only in the publish jobs; the
  `bump-version` and `release` jobs do not have this permission.
- No `PYPI_API_TOKEN` or other credentials are stored in GitHub Secrets.
- The `pypa/gh-action-pypi-publish` action is pinned to a specific commit SHA
  for supply-chain safety.
