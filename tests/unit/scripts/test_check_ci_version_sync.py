"""Tests for scripts/check_ci_version_sync.py."""

from pathlib import Path

import pytest

from scripts.check_ci_version_sync import (
    check_ci_version_sync,
    get_gitleaks_versions,
    get_pixi_version_from_canonical,
    get_setup_pixi_shas,
    validate_gitleaks_consistency,
    validate_pixi_consistency,
    validate_setup_pixi_sha_consistency,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def setup_pixi_version_file(repo_root: Path, version: str) -> Path:
    """Write .github/pixi-version canonical file."""
    github_dir = repo_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    path = github_dir / "pixi-version"
    path.write_text(version)
    return path


def setup_workflow(
    repo_root: Path,
    name: str,
    pixi_version: str | None = None,
    setup_pixi_sha: str | None = None,
) -> Path:
    """Write a minimal GitHub workflow file."""
    github_workflows = repo_root / ".github" / "workflows"
    github_workflows.mkdir(parents=True, exist_ok=True)
    path = github_workflows / f"{name}.yml"

    lines = ["name: Test Workflow", "on: push", "jobs:", "  test:", "    runs-on: ubuntu-latest"]
    lines.append("    steps:")

    if pixi_version:
        lines.append("      - name: Setup pixi")
        lines.append("        with:")
        lines.append(f"          pixi-version: {pixi_version}")

    if setup_pixi_sha:
        lines.append("      - name: Another step")
        lines.append(f"        uses: prefix-dev/setup-pixi@{setup_pixi_sha}")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


def setup_composite_action(
    repo_root: Path,
    setup_pixi_sha: str | None = None,
) -> Path:
    """Write .github/actions/setup-pixi/action.yml composite action."""
    actions_dir = repo_root / ".github" / "actions" / "setup-pixi"
    actions_dir.mkdir(parents=True, exist_ok=True)
    path = actions_dir / "action.yml"

    lines = [
        "name: Setup pixi",
        "inputs:",
        "  environment:",
        "    description: Environment to activate",
        "    default: default",
        "runs:",
        "  using: composite",
        "  steps:",
    ]

    if setup_pixi_sha:
        lines.append(f"    - uses: prefix-dev/setup-pixi@{setup_pixi_sha}")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


def setup_containerfile(repo_root: Path, pixi_version: str | None = None) -> Path:
    """Write ci/Containerfile with ARG PIXI_VERSION."""
    ci_dir = repo_root / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    path = ci_dir / "Containerfile"

    lines = ["FROM python:3.12-slim"]
    if pixi_version:
        lines.append(f"ARG PIXI_VERSION={pixi_version}")
    lines.append("RUN echo 'test'")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


def setup_pre_commit_config(repo_root: Path, gitleaks_version: str | None = None) -> Path:
    """Write .pre-commit-config.yaml with gitleaks version."""
    path = repo_root / ".pre-commit-config.yaml"

    lines = ["repos:", "  - repo: https://github.com/gitleaks/gitleaks"]
    if gitleaks_version:
        lines.append(f"    rev: {gitleaks_version}")
    else:
        lines.append("    rev: v8.30.1")
    lines.append("    hooks:")
    lines.append("      - id: gitleaks")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


def setup_security_workflow(
    repo_root: Path,
    gitleaks_version: str | None = None,
) -> Path:
    """Write .github/workflows/security.yml with GITLEAKS_VERSION."""
    github_workflows = repo_root / ".github" / "workflows"
    github_workflows.mkdir(parents=True, exist_ok=True)
    path = github_workflows / "security.yml"

    lines = ["name: Security Checks", "on: push", "env:"]
    if gitleaks_version:
        lines.append(f'  GITLEAKS_VERSION: "{gitleaks_version}"')
    else:
        lines.append('  GITLEAKS_VERSION: "8.30.1"')
    lines.append("jobs:")
    lines.append("  scan:")
    lines.append("    runs-on: ubuntu-latest")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Tests for get_pixi_version_from_canonical
# ---------------------------------------------------------------------------


class TestGetPixiVersionFromCanonical:
    """Tests for get_pixi_version_from_canonical()."""

    def test_reads_canonical_file(self, tmp_path: Path) -> None:
        """Should read pixi version from .github/pixi-version."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        assert get_pixi_version_from_canonical(tmp_path) == "v0.67.2"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        """Should strip leading/trailing whitespace."""
        setup_pixi_version_file(tmp_path, "  v0.67.2  \n")
        assert get_pixi_version_from_canonical(tmp_path) == "v0.67.2"

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if canonical file doesn't exist."""
        with pytest.raises(SystemExit) as exc_info:
            get_pixi_version_from_canonical(tmp_path)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Tests for validate_pixi_consistency
# ---------------------------------------------------------------------------


class TestValidatePixiConsistency:
    """Tests for validate_pixi_consistency()."""

    def test_pixi_consistent_passes(self, tmp_path: Path) -> None:
        """Should return 0 when all pixi versions match."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        assert validate_pixi_consistency(tmp_path) == 0

    def test_pixi_drift_in_workflow_fails(self, tmp_path: Path) -> None:
        """Should return 1 when workflow has mismatched pixi-version."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.63.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        result = validate_pixi_consistency(tmp_path)
        assert result == 1

    def test_pixi_drift_in_containerfile_fails(self, tmp_path: Path) -> None:
        """Should return 1 when Containerfile has mismatched ARG."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_containerfile(tmp_path, pixi_version="v0.63.2")

        result = validate_pixi_consistency(tmp_path)
        assert result == 1

    def test_multiple_workflows_all_checked(self, tmp_path: Path) -> None:
        """Should check all workflows in .github/workflows/."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_workflow(tmp_path, "test.yml", pixi_version="v0.63.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        result = validate_pixi_consistency(tmp_path)
        assert result == 1


# ---------------------------------------------------------------------------
# Tests for get_setup_pixi_shas
# ---------------------------------------------------------------------------


class TestGetSetupPixiShas:
    """Tests for get_setup_pixi_shas()."""

    def test_extracts_sha_from_workflows(self, tmp_path: Path) -> None:
        """Should extract prefix-dev/setup-pixi@SHA from workflows."""
        sha = "abc1234def567"
        setup_workflow(tmp_path, "build.yml", setup_pixi_sha=sha)
        shas = get_setup_pixi_shas(tmp_path)
        assert sha in shas

    def test_extracts_sha_from_composite_action(self, tmp_path: Path) -> None:
        """Should extract SHA from composite action."""
        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_pixi_sha=sha)
        shas = get_setup_pixi_shas(tmp_path)
        assert sha in shas

    def test_multiple_workflows_all_checked(self, tmp_path: Path) -> None:
        """Should extract SHAs from all workflows."""
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_workflow(tmp_path, "build.yml", setup_pixi_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_pixi_sha=sha2)
        shas = get_setup_pixi_shas(tmp_path)
        assert sha1 in shas
        assert sha2 in shas


# ---------------------------------------------------------------------------
# Tests for validate_setup_pixi_sha_consistency
# ---------------------------------------------------------------------------


class TestValidateSetupPixiShaConsistency:
    """Tests for validate_setup_pixi_sha_consistency()."""

    def test_setup_pixi_sha_consistent_passes(self, tmp_path: Path) -> None:
        """Should return 0 when all setup-pixi SHAs match."""
        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_pixi_sha=sha)
        setup_workflow(tmp_path, "build.yml", setup_pixi_sha=sha)

        assert validate_setup_pixi_sha_consistency(tmp_path) == 0

    def test_setup_pixi_sha_drift_fails(self, tmp_path: Path) -> None:
        """Should return 1 when setup-pixi SHAs differ."""
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_pixi_sha=sha1)
        setup_workflow(tmp_path, "build.yml", setup_pixi_sha=sha2)

        result = validate_setup_pixi_sha_consistency(tmp_path)
        assert result == 1

    def test_no_setup_pixi_usage_passes(self, tmp_path: Path) -> None:
        """Should pass (return 0) if no setup-pixi usage found."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        result = validate_setup_pixi_sha_consistency(tmp_path)
        assert result == 0


# ---------------------------------------------------------------------------
# Tests for get_gitleaks_versions
# ---------------------------------------------------------------------------


class TestGetGitleaksVersions:
    """Tests for get_gitleaks_versions()."""

    def test_extracts_from_pre_commit_config(self, tmp_path: Path) -> None:
        """Should extract gitleaks version from .pre-commit-config.yaml."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        versions = get_gitleaks_versions(tmp_path)
        assert "8.30.1" in [v.lstrip("v") for v in versions]

    def test_extracts_from_security_workflow(self, tmp_path: Path) -> None:
        """Should extract GITLEAKS_VERSION from security.yml."""
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")
        versions = get_gitleaks_versions(tmp_path)
        assert "8.30.1" in [v.lstrip("v") for v in versions]

    def test_collects_from_multiple_sources(self, tmp_path: Path) -> None:
        """Should collect versions from both sources."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")
        versions = get_gitleaks_versions(tmp_path)
        normalized = [v.lstrip("v") for v in versions]
        assert "8.30.1" in normalized


# ---------------------------------------------------------------------------
# Tests for validate_gitleaks_consistency
# ---------------------------------------------------------------------------


class TestValidateGitleaksConsistency:
    """Tests for validate_gitleaks_consistency()."""

    def test_gitleaks_consistent_passes(self, tmp_path: Path) -> None:
        """Should return 0 when gitleaks versions match."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")

        assert validate_gitleaks_consistency(tmp_path) == 0

    def test_gitleaks_drift_fails(self, tmp_path: Path) -> None:
        """Should return 1 when gitleaks versions differ."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.21.2")

        result = validate_gitleaks_consistency(tmp_path)
        assert result == 1

    def test_gitleaks_drift_with_v_prefix_normalization(self, tmp_path: Path) -> None:
        """Should normalize v prefix before comparing."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")

        assert validate_gitleaks_consistency(tmp_path) == 0


# ---------------------------------------------------------------------------
# Tests for check_ci_version_sync
# ---------------------------------------------------------------------------


class TestCheckCiVersionSync:
    """Tests for check_ci_version_sync()."""

    def test_passes_when_all_consistent(self, tmp_path: Path) -> None:
        """Should return 0 when all three checks pass."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_pixi_sha=sha)
        setup_workflow(tmp_path, "test.yml", setup_pixi_sha=sha)

        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")

        assert check_ci_version_sync(tmp_path) == 0

    def test_fails_on_pixi_drift(self, tmp_path: Path) -> None:
        """Should return 1 on pixi version drift."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.63.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        assert check_ci_version_sync(tmp_path) == 1

    def test_fails_on_setup_pixi_sha_drift(self, tmp_path: Path) -> None:
        """Should return 1 on setup-pixi SHA drift."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_pixi_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_pixi_sha=sha2)

        assert check_ci_version_sync(tmp_path) == 1

    def test_fails_on_gitleaks_drift(self, tmp_path: Path) -> None:
        """Should return 1 on gitleaks version drift."""
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.67.2")
        setup_containerfile(tmp_path, pixi_version="v0.67.2")

        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.21.2")

        assert check_ci_version_sync(tmp_path) == 1

    def test_all_three_checks_reported_together(self, tmp_path: Path) -> None:
        """Should report all three checks together."""
        # Pixi drift
        setup_pixi_version_file(tmp_path, "v0.67.2")
        setup_workflow(tmp_path, "build.yml", pixi_version="v0.63.2")

        # Setup-pixi SHA drift
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_pixi_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_pixi_sha=sha2)

        # Gitleaks drift
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.21.2")

        result = check_ci_version_sync(tmp_path)
        assert result == 1
