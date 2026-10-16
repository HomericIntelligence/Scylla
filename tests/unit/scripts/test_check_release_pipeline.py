"""Tests for scripts/check_release_pipeline.py."""

import textwrap
from pathlib import Path

import pytest
import yaml

from scripts.check_release_pipeline import (
    check_dist_matches_version,
    check_oidc_permissions,
    check_publish_gating,
    check_release_pipeline,
    check_tag_trigger,
    get_triggers,
    load_release_workflow,
    main,
)

VALID_RELEASE_SHA = "dc37677b2e1c63e2034f94d8a5b11f265b73ba33"

VALID_RELEASE_YML = f"""\
name: Release

on:
  workflow_dispatch:
    inputs:
      part:
        type: choice
        options:
          - patch
  push:
    tags:
      - "v*"

jobs:
  release:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - run: echo "create release"

  build:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - run: echo "build dist"

  publish-pypi:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/scylla
    permissions:
      id-token: write
    steps:
      - uses: pypa/gh-action-pypi-publish@{VALID_RELEASE_SHA}

  publish-testpypi:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    environment:
      name: testpypi
    permissions:
      id-token: write
    steps:
      - uses: pypa/gh-action-pypi-publish@{VALID_RELEASE_SHA}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_pyproject(directory: Path, version: str = "0.1.0") -> Path:
    """Write a minimal pyproject.toml with the given version."""
    content = textwrap.dedent(f"""\
        [project]
        name = "scylla"
        version = "{version}"
    """)
    path = directory / "pyproject.toml"
    path.write_text(content)
    return path


def write_workflow(root: Path, content: str = VALID_RELEASE_YML) -> Path:
    """Write a release.yml under the root's .github/workflows directory."""
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / "release.yml"
    path.write_text(content)
    return path


def setup_valid_repo(root: Path) -> None:
    """Set up a repo fixture with a valid release.yml and pyproject.toml."""
    write_pyproject(root)
    write_workflow(root)


def make_dist(root: Path, version: str = "0.1.0") -> Path:
    """Create a dist/ fixture with one wheel and one sdist for the version."""
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    (dist / f"scylla-{version}-py3-none-any.whl").write_bytes(b"w")
    (dist / f"scylla-{version}.tar.gz").write_bytes(b"s")
    return dist


# ---------------------------------------------------------------------------
# Structural checks against the live tree
# ---------------------------------------------------------------------------


class TestLiveTree:
    """The shipped repository must pass structural validation."""

    def test_live_tree_passes(self) -> None:
        """The real repo root passes structural mode (no --dist-dir)."""
        repo_root = Path(__file__).parent.parent.parent.parent
        assert check_release_pipeline(repo_root) == 0


# ---------------------------------------------------------------------------
# Valid fixtures
# ---------------------------------------------------------------------------


class TestValidFixture:
    """A well-formed release pipeline passes all checks."""

    def test_valid_fixture_passes(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Full fixture incl. dist returns 0 and prints PASS lines verbosely."""
        setup_valid_repo(tmp_path)
        make_dist(tmp_path)
        assert check_release_pipeline(tmp_path, dist_dir=tmp_path / "dist", verbose=True) == 0
        out = capsys.readouterr().out
        assert "PASS: tag trigger" in out
        assert "PASS: publish gating" in out
        assert "PASS: OIDC permissions" in out
        assert "PASS: action pins" in out
        assert "PASS: dist/version match" in out


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for main() argument handling."""

    def test_main_repo_root_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """main([]) uses the script-parent default repo-root and passes."""
        monkeypatch.setattr("sys.argv", ["check_release_pipeline.py", "--verbose"])
        assert main() == 0
        assert "OK: Release pipeline is well-formed" in capsys.readouterr().out


class TestTagTrigger:
    """Tests for check_tag_trigger()."""

    def test_missing_v_star_tag_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Removing the v* tag trigger is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace('    tags:\n      - "v*"\n', "    tags:\n      - nightly\n"),
        )
        workflow = load_release_workflow(tmp_path)
        errors = check_tag_trigger(workflow)
        assert len(errors) == 1
        assert "v*" in errors[0]
        assert check_release_pipeline(tmp_path) == 1
        assert "on.push.tags must include 'v*'" in capsys.readouterr().err

    def test_on_key_parsed_as_true(self, tmp_path: Path) -> None:
        """Triggers stored under PyYAML's coerced True key are still found."""
        setup_valid_repo(tmp_path)
        workflow = yaml.safe_load((tmp_path / ".github/workflows/release.yml").read_text())
        assert True in workflow  # PyYAML quirk: bare `on:` parses as True
        triggers = get_triggers(workflow)
        assert triggers["push"]["tags"] == ["v*"]


# ---------------------------------------------------------------------------
# Publish gating
# ---------------------------------------------------------------------------


class TestPublishGating:
    """Tests for check_publish_gating()."""

    def test_publish_pypi_without_tag_gate_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A publish job not gated on tag push is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace(
                """  publish-pypi:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
""",
                """  publish-pypi:
    if: github.event_name == 'push'
""",
            ),
        )
        workflow = load_release_workflow(tmp_path)
        errors = check_publish_gating(workflow)
        assert len(errors) == 1
        assert "publish-pypi" in errors[0]
        assert "startsWith(github.ref, 'refs/tags/v')" in errors[0]
        assert check_release_pipeline(tmp_path) == 1
        assert "job 'publish-pypi' must gate" in capsys.readouterr().err

    def test_testpypi_not_dispatch_gated_fails(self, tmp_path: Path) -> None:
        """A TestPyPI job not gated on workflow_dispatch is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace(
                "    if: github.event_name == 'workflow_dispatch'\n",
                "    if: always()\n",
            ),
        )
        workflow = load_release_workflow(tmp_path)
        errors = check_publish_gating(workflow)
        assert len(errors) == 1
        assert "publish-testpypi" in errors[0]

    def test_missing_required_job_fails(self, tmp_path: Path) -> None:
        """Removing a required publishing job is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.split("  build:")[0] + "\n",
        )
        errors = check_publish_gating(load_release_workflow(tmp_path))
        assert any("build" in e for e in errors)
        assert any("publish-pypi" in e for e in errors)
        assert any("publish-testpypi" in e for e in errors)


# ---------------------------------------------------------------------------
# OIDC permissions
# ---------------------------------------------------------------------------


class TestOidcPermissions:
    """Tests for check_oidc_permissions()."""

    def test_missing_id_token_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dropping id-token: write from publish-pypi is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace(
                """    environment:
      name: pypi
      url: https://pypi.org/p/scylla
    permissions:
      id-token: write
""",
                """    permissions:
      contents: read
""",
            ),
        )
        workflow = load_release_workflow(tmp_path)
        errors = check_oidc_permissions(workflow)
        assert len(errors) == 2
        assert any("id-token" in e for e in errors)
        assert any("environment" in e for e in errors)
        assert check_release_pipeline(tmp_path) == 1
        assert "'publish-pypi' must declare" in capsys.readouterr().err

    def test_wrong_environment_name_fails(self, tmp_path: Path) -> None:
        """Renaming the pypi environment is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace("      name: pypi\n", "      name: production\n"),
        )
        workflow = load_release_workflow(tmp_path)
        errors = check_oidc_permissions(workflow)
        assert len(errors) == 1
        assert "environment 'pypi'" in errors[0]

    def test_string_environment_accepted(self, tmp_path: Path) -> None:
        """An environment declared as a plain string still validates."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace(
                """    environment:
      name: pypi
      url: https://pypi.org/p/scylla
""",
                """    environment: pypi
""",
            ),
        )
        assert check_oidc_permissions(load_release_workflow(tmp_path)) == []


# ---------------------------------------------------------------------------
# Action pins
# ---------------------------------------------------------------------------


class TestActionPins:
    """Tests for check_action_pins()."""

    def test_branch_ref_pin_fails(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Pinning the publish action to a branch ref is a violation."""
        setup_valid_repo(tmp_path)
        write_workflow(
            tmp_path,
            VALID_RELEASE_YML.replace(f"@{VALID_RELEASE_SHA}", "@release/v1", 1),
        )
        assert check_release_pipeline(tmp_path) == 1
        err = capsys.readouterr().err
        assert "full 40-hex commit SHA" in err
        assert "@release/v1" in err


# ---------------------------------------------------------------------------
# Dist/version matching
# ---------------------------------------------------------------------------


class TestDistMatchesVersion:
    """Tests for check_dist_matches_version()."""

    def test_empty_dist_fails(self, tmp_path: Path) -> None:
        """An empty dist/ fails loudly instead of passing vacuously."""
        setup_valid_repo(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        errors = check_dist_matches_version(tmp_path, dist)
        assert len(errors) == 1
        assert "empty" in errors[0]

    def test_missing_dist_dir_fails(self, tmp_path: Path) -> None:
        """A missing dist/ directory is a violation."""
        setup_valid_repo(tmp_path)
        errors = check_dist_matches_version(tmp_path, tmp_path / "dist")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_missing_sdist_fails(self, tmp_path: Path) -> None:
        """A wheel-only dist/ is a violation."""
        setup_valid_repo(tmp_path)
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "scylla-0.1.0-py3-none-any.whl").write_bytes(b"w")
        errors = check_dist_matches_version(tmp_path, dist)
        assert any("no sdist" in e for e in errors)

    def test_wheel_version_mismatch_fails(self, tmp_path: Path) -> None:
        """Artifacts carrying a different version than pyproject are violations."""
        setup_valid_repo(tmp_path)
        make_dist(tmp_path, version="9.9.9")
        errors = check_dist_matches_version(tmp_path, tmp_path / "dist")
        assert len(errors) == 2
        assert any("wheel" in e and "scylla-0.1.0-" in e for e in errors)
        assert any("sdist" in e and "scylla-0.1.0.tar.gz" in e for e in errors)

    def test_matching_artifacts_pass(self, tmp_path: Path) -> None:
        """Wheel + sdist matching pyproject version pass."""
        setup_valid_repo(tmp_path)
        make_dist(tmp_path)
        assert check_dist_matches_version(tmp_path, tmp_path / "dist") == []
