"""Tests for scripts/check_ci_version_sync.py."""

from pathlib import Path

from scripts.check_ci_version_sync import (
    check_ci_version_sync,
    get_gitleaks_versions,
    get_setup_uv_shas,
    validate_gitleaks_consistency,
    validate_setup_uv_sha_consistency,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def setup_workflow(
    repo_root: Path,
    name: str,
    setup_uv_sha: str | None = None,
) -> Path:
    """Write a minimal GitHub workflow file."""
    github_workflows = repo_root / ".github" / "workflows"
    github_workflows.mkdir(parents=True, exist_ok=True)
    path = github_workflows / f"{name}.yml"

    lines = ["name: Test Workflow", "on: push", "jobs:", "  test:", "    runs-on: ubuntu-latest"]
    lines.append("    steps:")

    if setup_uv_sha:
        lines.append("      - name: Setup uv")
        lines.append(f"        uses: astral-sh/setup-uv@{setup_uv_sha}")

    content = "\n".join(lines) + "\n"
    path.write_text(content)
    return path


def setup_composite_action(
    repo_root: Path,
    setup_uv_sha: str | None = None,
) -> Path:
    """Write .github/actions/setup-env/action.yml composite action."""
    actions_dir = repo_root / ".github" / "actions" / "setup-env"
    actions_dir.mkdir(parents=True, exist_ok=True)
    path = actions_dir / "action.yml"

    lines = [
        "name: Setup uv",
        "runs:",
        "  using: composite",
        "  steps:",
    ]

    if setup_uv_sha:
        lines.append(f"    - uses: astral-sh/setup-uv@{setup_uv_sha}")

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
# Tests for get_setup_uv_shas
# ---------------------------------------------------------------------------


class TestGetSetupUvShas:
    """Tests for get_setup_uv_shas()."""

    def test_extracts_sha_from_workflows(self, tmp_path: Path) -> None:
        """Should extract astral-sh/setup-uv@SHA from workflows."""
        sha = "abc1234def567"
        setup_workflow(tmp_path, "build.yml", setup_uv_sha=sha)
        shas = get_setup_uv_shas(tmp_path)
        assert sha in shas

    def test_extracts_sha_from_composite_action(self, tmp_path: Path) -> None:
        """Should extract SHA from composite action."""
        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_uv_sha=sha)
        shas = get_setup_uv_shas(tmp_path)
        assert sha in shas

    def test_multiple_workflows_all_checked(self, tmp_path: Path) -> None:
        """Should extract SHAs from all workflows."""
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_workflow(tmp_path, "build.yml", setup_uv_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_uv_sha=sha2)
        shas = get_setup_uv_shas(tmp_path)
        assert sha1 in shas
        assert sha2 in shas


# ---------------------------------------------------------------------------
# Tests for validate_setup_uv_sha_consistency
# ---------------------------------------------------------------------------


class TestValidateSetupUvShaConsistency:
    """Tests for validate_setup_uv_sha_consistency()."""

    def test_setup_uv_sha_consistent_passes(self, tmp_path: Path) -> None:
        """Should return 0 when all setup-uv SHAs match."""
        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_uv_sha=sha)
        setup_workflow(tmp_path, "build.yml", setup_uv_sha=sha)

        assert validate_setup_uv_sha_consistency(tmp_path) == 0

    def test_setup_uv_sha_drift_fails(self, tmp_path: Path) -> None:
        """Should return 1 when setup-uv SHAs differ."""
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_uv_sha=sha1)
        setup_workflow(tmp_path, "build.yml", setup_uv_sha=sha2)

        result = validate_setup_uv_sha_consistency(tmp_path)
        assert result == 1

    def test_no_setup_uv_usage_passes(self, tmp_path: Path) -> None:
        """Should pass (return 0) if no setup-uv usage found."""
        result = validate_setup_uv_sha_consistency(tmp_path)
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
        """Should return 0 when all checks pass."""
        sha = "abc1234def567"
        setup_composite_action(tmp_path, setup_uv_sha=sha)
        setup_workflow(tmp_path, "test.yml", setup_uv_sha=sha)

        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.30.1")

        assert check_ci_version_sync(tmp_path) == 0

    def test_fails_on_setup_uv_sha_drift(self, tmp_path: Path) -> None:
        """Should return 1 on setup-uv SHA drift."""
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_uv_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_uv_sha=sha2)

        assert check_ci_version_sync(tmp_path) == 1

    def test_fails_on_gitleaks_drift(self, tmp_path: Path) -> None:
        """Should return 1 on gitleaks version drift."""
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.21.2")

        assert check_ci_version_sync(tmp_path) == 1

    def test_all_checks_reported_together(self, tmp_path: Path) -> None:
        """Should report all checks together."""
        # Setup-uv SHA drift
        sha1 = "abc1234def567"
        sha2 = "xyz9876abc543"
        setup_composite_action(tmp_path, setup_uv_sha=sha1)
        setup_workflow(tmp_path, "test.yml", setup_uv_sha=sha2)

        # Gitleaks drift
        setup_pre_commit_config(tmp_path, gitleaks_version="v8.30.1")
        setup_security_workflow(tmp_path, gitleaks_version="8.21.2")

        result = check_ci_version_sync(tmp_path)
        assert result == 1
