"""Tests for scripts/check_package_version_consistency.py."""

import textwrap
from pathlib import Path

import pytest

from scripts.check_package_version_consistency import (
    check_init_version,
    check_package_version_consistency,
    check_skill_files,
    find_aspirational_versions,
    get_canonical_version,
)

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


def write_init(directory: Path, version: str = "0.1.0") -> Path:
    """Write a minimal src/scylla/__init__.py with __version__."""
    scylla_dir = directory / "src" / "scylla"
    scylla_dir.mkdir(parents=True, exist_ok=True)
    path = scylla_dir / "__init__.py"
    path.write_text(f'__version__ = "{version}"\n')
    return path


def write_skill_file(directory: Path, rel_path: str, content: str) -> Path:
    """Write a skill markdown file at the given relative path."""
    path = directory / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def setup_minimal_repo(
    root: Path,
    *,
    pyproject_version: str = "0.1.0",
    init_version: str = "0.1.0",
) -> None:
    """Set up a minimal repo with consistent version files."""
    write_pyproject(root, pyproject_version)
    write_init(root, init_version)


# ---------------------------------------------------------------------------
# TestGetCanonicalVersion
# ---------------------------------------------------------------------------


class TestGetCanonicalVersion:
    """Tests for get_canonical_version()."""

    def test_reads_version(self, tmp_path: Path) -> None:
        """Should return the version string from pyproject.toml."""
        write_pyproject(tmp_path, "0.1.0")
        assert get_canonical_version(tmp_path / "pyproject.toml") == "0.1.0"

    def test_reads_higher_version(self, tmp_path: Path) -> None:
        """Should return any valid semver version."""
        write_pyproject(tmp_path, "2.3.1")
        assert get_canonical_version(tmp_path / "pyproject.toml") == "2.3.1"

    def test_missing_file_exits(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if pyproject.toml does not exist."""
        with pytest.raises(SystemExit) as exc_info:
            get_canonical_version(tmp_path / "pyproject.toml")
        assert exc_info.value.code == 1

    def test_malformed_toml_exits(self, tmp_path: Path) -> None:
        """Should sys.exit(1) on malformed TOML."""
        path = tmp_path / "pyproject.toml"
        path.write_text("not [valid toml\n")
        with pytest.raises(SystemExit) as exc_info:
            get_canonical_version(path)
        assert exc_info.value.code == 1

    def test_missing_version_key_exits(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if [project].version is missing."""
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nname = "scylla"\n')
        with pytest.raises(SystemExit) as exc_info:
            get_canonical_version(path)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestCheckInitVersion
# ---------------------------------------------------------------------------


class TestCheckInitVersion:
    """Tests for check_init_version()."""

    def test_matching_version_passes(self, tmp_path: Path) -> None:
        """Should return empty list when __version__ matches."""
        write_init(tmp_path, "0.1.0")
        assert check_init_version(tmp_path, "0.1.0") == []

    def test_mismatched_version_fails(self, tmp_path: Path) -> None:
        """Should return error when __version__ differs."""
        write_init(tmp_path, "0.2.0")
        errors = check_init_version(tmp_path, "0.1.0")
        assert len(errors) == 1
        assert "0.2.0" in errors[0]

    def test_missing_init_file(self, tmp_path: Path) -> None:
        """Should return error when __init__.py is missing."""
        errors = check_init_version(tmp_path, "0.1.0")
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_importlib_metadata_passes(self, tmp_path: Path) -> None:
        """Should pass when __init__.py uses importlib.metadata (no hardcoded __version__)."""
        scylla_dir = tmp_path / "src" / "scylla"
        scylla_dir.mkdir(parents=True)
        init_path = scylla_dir / "__init__.py"
        init_path.write_text(
            "from importlib.metadata import version as _get_version\n"
            '__version__ = _get_version("scylla")\n'
        )
        # The regex won't match the dynamic assignment — no error
        assert check_init_version(tmp_path, "0.1.0") == []

    def test_single_quote_version(self, tmp_path: Path) -> None:
        """Should match __version__ with single quotes."""
        scylla_dir = tmp_path / "src" / "scylla"
        scylla_dir.mkdir(parents=True)
        init_path = scylla_dir / "__init__.py"
        init_path.write_text("__version__ = '0.1.0'\n")
        assert check_init_version(tmp_path, "0.1.0") == []


# ---------------------------------------------------------------------------
# TestFindAspirationalVersions
# ---------------------------------------------------------------------------


class TestFindAspirationalVersions:
    """Tests for find_aspirational_versions()."""

    def test_no_versions_passes(self, tmp_path: Path) -> None:
        """Should return empty list for files with no version references."""
        path = tmp_path / "test.md"
        path.write_text("# No version references here\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_matching_version_passes(self, tmp_path: Path) -> None:
        """Should not flag versions equal to canonical."""
        path = tmp_path / "test.md"
        path.write_text("Released in v0.1.0\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_lower_version_passes(self, tmp_path: Path) -> None:
        """Should not flag versions below canonical."""
        path = tmp_path / "test.md"
        path.write_text("Originally released in v0.0.1\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_higher_version_fails(self, tmp_path: Path) -> None:
        """Should flag versions above canonical."""
        path = tmp_path / "test.md"
        path.write_text("Will be removed in v2.0.0\n")
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 1
        assert "v2.0.0" in errors[0]
        assert ":1:" in errors[0]

    def test_multiple_versions_on_same_line(self, tmp_path: Path) -> None:
        """Should flag all aspirational versions even on the same line."""
        path = tmp_path / "test.md"
        path.write_text("| v1.5.0 | deprecated | v2.0.0 | removed |\n")
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 2

    def test_version_without_v_prefix(self, tmp_path: Path) -> None:
        """Should detect version numbers without a 'v' prefix."""
        path = tmp_path / "test.md"
        path.write_text("Deprecated as of 1.5.0\n")
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 1
        assert "v1.5.0" in errors[0]

    def test_reports_correct_line_number(self, tmp_path: Path) -> None:
        """Should report the correct line number for aspirational versions."""
        path = tmp_path / "test.md"
        path.write_text("line 1\nline 2\nRemoved in v3.0.0\nline 4\n")
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 1
        assert ":3:" in errors[0]

    def test_url_embedded_versions_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions embedded in URL paths."""
        path = tmp_path / "test.md"
        path.write_text(
            "Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).\n"
        )
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_fenced_code_block_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions inside fenced code blocks."""
        path = tmp_path / "test.md"
        path.write_text(
            "# Config example\n\n"
            "```yaml\n"
            "pixi-version: v0.62.2\n"
            "bats-core: '>=1.11.0'\n"
            "```\n\n"
            "Plain text v2.0.0 should still be flagged.\n"
        )
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 1
        assert "v2.0.0" in errors[0]

    def test_tilde_fenced_code_block_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions inside tilde-fenced code blocks."""
        path = tmp_path / "test.md"
        path.write_text("~~~\nversion = '5.0.0'\n~~~\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_inline_code_versions_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions inside inline code spans (backticks)."""
        path = tmp_path / "test.md"
        path.write_text("Known bug in `v2.0.67`. Use the `/config` command.\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_double_backtick_inline_code_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions inside double-backtick inline code spans."""
        path = tmp_path / "test.md"
        path.write_text("Do not use aspirational versions (e.g., ``v1.5.0``, ``v2.0.0``).\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_github_action_version_pin_ignored(self, tmp_path: Path) -> None:
        """Should not flag versions in GitHub Action pins like @v0.8.1."""
        path = tmp_path / "test.md"
        path.write_text("Use prefix-dev/setup-pixi@v0.8.1 for CI.\n")
        assert find_aspirational_versions(path, (0, 1, 0), "test.md") == []

    def test_plain_text_version_still_flagged(self, tmp_path: Path) -> None:
        """Should still flag plain-text aspirational versions outside code contexts."""
        path = tmp_path / "test.md"
        path.write_text("This will ship in v2.0.0 of our project.\n")
        errors = find_aspirational_versions(path, (0, 1, 0), "test.md")
        assert len(errors) == 1
        assert "v2.0.0" in errors[0]


# ---------------------------------------------------------------------------
# TestCheckChangelog
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestCheckSkillFiles
# ---------------------------------------------------------------------------


class TestCheckSkillFiles:
    """Tests for check_skill_files()."""

    def test_no_skill_dirs_passes(self, tmp_path: Path) -> None:
        """Should pass when neither .claude-plugin/skills/ nor .claude/ exist."""
        assert check_skill_files(tmp_path, "0.1.0") == []

    def test_clean_skill_file_passes(self, tmp_path: Path) -> None:
        """Should pass when skill files only reference the canonical version."""
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/example/SKILL.md",
            "# Example Skill\n\nAdded in v0.1.0\n",
        )
        assert check_skill_files(tmp_path, "0.1.0") == []

    def test_aspirational_in_skills_detected(self, tmp_path: Path) -> None:
        """Should detect aspirational versions in .claude-plugin/skills/ files."""
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/backward-compat-removal/SKILL.md",
            "# backward-compat-removal\n\nRemove as part of v2.0.0 cleanup\n",
        )
        errors = check_skill_files(tmp_path, "0.1.0")
        assert len(errors) == 1
        assert "v2.0.0" in errors[0]
        assert "backward-compat-removal" in errors[0]

    def test_aspirational_in_claude_dir_detected(self, tmp_path: Path) -> None:
        """Should detect aspirational versions in .claude/ markdown files."""
        write_skill_file(
            tmp_path,
            ".claude/agents/test-agent.md",
            "# Agent\n\nTarget version: v3.0.0\n",
        )
        errors = check_skill_files(tmp_path, "0.1.0")
        assert len(errors) == 1
        assert "v3.0.0" in errors[0]

    def test_non_md_files_ignored(self, tmp_path: Path) -> None:
        """Should only scan .md files, not other file types."""
        skills_dir = tmp_path / ".claude-plugin" / "skills" / "example"
        skills_dir.mkdir(parents=True)
        (skills_dir / "config.yaml").write_text("version: v5.0.0\n")
        assert check_skill_files(tmp_path, "0.1.0") == []

    def test_multiple_skill_files_scanned(self, tmp_path: Path) -> None:
        """Should scan all markdown files across both directories."""
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/skill-a/SKILL.md",
            "Removed in v2.0.0\n",
        )
        write_skill_file(
            tmp_path,
            ".claude/shared/guidance.md",
            "Planned for v3.0.0\n",
        )
        errors = check_skill_files(tmp_path, "0.1.0")
        assert len(errors) == 2

    def test_external_tool_versions_not_flagged(self, tmp_path: Path) -> None:
        """Should not flag versions that match or are below canonical."""
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/ci/SKILL.md",
            "# CI Skill\n\nUses action v0.0.1 and tool 0.1.0\n",
        )
        assert check_skill_files(tmp_path, "0.1.0") == []


# ---------------------------------------------------------------------------
# TestCheckPackageVersionConsistency (integration)
# ---------------------------------------------------------------------------


class TestCheckPackageVersionConsistency:
    """Integration tests for check_package_version_consistency()."""

    def test_all_consistent_returns_zero(self, tmp_path: Path) -> None:
        """Should return 0 when all versions match."""
        setup_minimal_repo(tmp_path)
        assert check_package_version_consistency(tmp_path) == 0

    def test_init_mismatch_returns_one(self, tmp_path: Path) -> None:
        """Should return 1 when __init__.py version differs."""
        setup_minimal_repo(tmp_path, init_version="0.2.0")
        assert check_package_version_consistency(tmp_path) == 1

    def test_skill_files_not_scanned_by_default(self, tmp_path: Path) -> None:
        """Should NOT scan skill files when --scan-skills is not set."""
        setup_minimal_repo(tmp_path)
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/test/SKILL.md",
            "Removed in v9.0.0\n",
        )
        assert check_package_version_consistency(tmp_path, scan_skills=False) == 0

    def test_skill_files_scanned_when_enabled(self, tmp_path: Path) -> None:
        """Should scan skill files when --scan-skills is True."""
        setup_minimal_repo(tmp_path)
        write_skill_file(
            tmp_path,
            ".claude-plugin/skills/test/SKILL.md",
            "Removed in v9.0.0\n",
        )
        assert check_package_version_consistency(tmp_path, scan_skills=True) == 1

    def test_verbose_prints_ok(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """With verbose=True, should print OK message on success."""
        setup_minimal_repo(tmp_path)
        result = check_package_version_consistency(tmp_path, verbose=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "0.1.0" in captured.out

    def test_verbose_prints_canonical_version(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """With verbose=True, should print the canonical version."""
        setup_minimal_repo(tmp_path)
        check_package_version_consistency(tmp_path, verbose=True)
        captured = capsys.readouterr()
        assert "Canonical version" in captured.out

    def test_error_count_reported(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should report total violation count on failure."""
        setup_minimal_repo(tmp_path, init_version="0.3.0")
        check_package_version_consistency(tmp_path)
        captured = capsys.readouterr()
        assert "1 package version consistency violation(s)" in captured.err

    def test_missing_pyproject_exits(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if pyproject.toml is missing."""
        with pytest.raises(SystemExit) as exc_info:
            check_package_version_consistency(tmp_path)
        assert exc_info.value.code == 1
