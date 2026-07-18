"""Tests for scripts/bump_version.py."""

import subprocess
import textwrap
from pathlib import Path

import pytest

from scripts.bump_version import (
    bump_version,
    compute_new_version,
    create_git_tag,
    get_current_version,
    update_pyproject_version,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_pyproject(directory: Path, version: str) -> Path:
    """Write a minimal pyproject.toml with the given version."""
    content = textwrap.dedent(f"""\
        [project]
        name = "test-project"
        version = "{version}"
    """)
    path = directory / "pyproject.toml"
    path.write_text(content)
    return path


def setup_repo(root: Path, version: str) -> None:
    """Create pyproject.toml with the given version (single source of truth)."""
    write_pyproject(root, version)


def init_git_repo(root: Path) -> None:
    """Initialize a minimal git repo so git tag commands succeed."""
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# TestGetCurrentVersion
# ---------------------------------------------------------------------------


class TestGetCurrentVersion:
    """Tests for get_current_version()."""

    def test_valid_version(self, tmp_path: Path) -> None:
        """Should return parsed (major, minor, patch) tuple."""
        write_pyproject(tmp_path, "1.2.3")
        assert get_current_version(tmp_path) == (1, 2, 3)

    def test_zero_version(self, tmp_path: Path) -> None:
        """Should handle 0.0.0 version."""
        write_pyproject(tmp_path, "0.0.0")
        assert get_current_version(tmp_path) == (0, 0, 0)

    def test_large_numbers(self, tmp_path: Path) -> None:
        """Should handle large version numbers."""
        write_pyproject(tmp_path, "100.200.300")
        assert get_current_version(tmp_path) == (100, 200, 300)

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if pyproject.toml does not exist."""
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1

    def test_malformed_toml_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) on malformed TOML."""
        path = tmp_path / "pyproject.toml"
        path.write_text("this is not [valid toml\n")
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1

    def test_no_project_section_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if [project] section is missing."""
        path = tmp_path / "pyproject.toml"
        path.write_text("[build-system]\nrequires = ['setuptools']\n")
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1

    def test_no_version_field_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if version is missing from [project]."""
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nname = "test"\n')
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1

    def test_non_semver_version_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if version is not X.Y.Z format."""
        write_pyproject(tmp_path, "1.2")
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1

    def test_non_numeric_version_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if version parts are not integers."""
        write_pyproject(tmp_path, "1.2.beta")
        with pytest.raises(SystemExit) as exc_info:
            get_current_version(tmp_path)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestComputeNewVersion
# ---------------------------------------------------------------------------


class TestComputeNewVersion:
    """Tests for compute_new_version()."""

    def test_patch_bump(self) -> None:
        """Should increment patch and preserve major/minor."""
        assert compute_new_version((0, 1, 0), "patch") == (0, 1, 1)

    def test_minor_bump_resets_patch(self) -> None:
        """Should increment minor and reset patch to 0."""
        assert compute_new_version((0, 1, 2), "minor") == (0, 2, 0)

    def test_major_bump_resets_minor_and_patch(self) -> None:
        """Should increment major and reset minor+patch to 0."""
        assert compute_new_version((0, 1, 2), "major") == (1, 0, 0)

    def test_zero_version_patch(self) -> None:
        """Should bump 0.0.0 to 0.0.1."""
        assert compute_new_version((0, 0, 0), "patch") == (0, 0, 1)

    def test_large_numbers(self) -> None:
        """Should handle large version numbers correctly."""
        assert compute_new_version((99, 99, 99), "patch") == (99, 99, 100)

    def test_invalid_part_raises(self) -> None:
        """Should raise ValueError for invalid part name."""
        with pytest.raises(ValueError, match="Invalid part"):
            compute_new_version((0, 1, 0), "invalid")


# ---------------------------------------------------------------------------
# TestUpdatePyprojectVersion
# ---------------------------------------------------------------------------


class TestUpdatePyprojectVersion:
    """Tests for update_pyproject_version()."""

    def test_updates_version(self, tmp_path: Path) -> None:
        """Should write the new version to pyproject.toml."""
        write_pyproject(tmp_path, "0.1.0")
        update_pyproject_version(tmp_path, "0.1.0", "0.2.0")
        content = (tmp_path / "pyproject.toml").read_text()
        assert 'version = "0.2.0"' in content

    def test_preserves_other_content(self, tmp_path: Path) -> None:
        """Should not alter other lines in pyproject.toml."""
        write_pyproject(tmp_path, "0.1.0")
        update_pyproject_version(tmp_path, "0.1.0", "0.2.0")
        content = (tmp_path / "pyproject.toml").read_text()
        assert 'name = "test-project"' in content

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if pyproject.toml is missing."""
        with pytest.raises(SystemExit) as exc_info:
            update_pyproject_version(tmp_path, "0.1.0", "0.2.0")
        assert exc_info.value.code == 1

    def test_no_version_line_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if no version line found."""
        path = tmp_path / "pyproject.toml"
        path.write_text('[project]\nname = "test"\n')
        with pytest.raises(SystemExit) as exc_info:
            update_pyproject_version(tmp_path, "0.1.0", "0.2.0")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# TestCreateGitTag
# ---------------------------------------------------------------------------


class TestCreateGitTag:
    """Tests for create_git_tag()."""

    def test_creates_tag_in_git_repo(self, tmp_path: Path) -> None:
        """Should create a git tag when called inside a valid git repo."""
        init_git_repo(tmp_path)
        result = create_git_tag("1.2.3", tmp_path)
        assert result == 0
        tags = (
            subprocess.run(
                ["git", "tag"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert "v1.2.3" in tags

    def test_returns_one_on_duplicate_tag(self, tmp_path: Path) -> None:
        """Should return 1 if the tag already exists."""
        init_git_repo(tmp_path)
        create_git_tag("1.0.0", tmp_path)
        result = create_git_tag("1.0.0", tmp_path)
        assert result == 1

    def test_verbose_prints_tag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Verbose mode should print the created tag name."""
        init_git_repo(tmp_path)
        create_git_tag("2.0.0", tmp_path, verbose=True)
        captured = capsys.readouterr()
        assert "v2.0.0" in captured.out


# ---------------------------------------------------------------------------
# TestBumpVersion (integration)
# ---------------------------------------------------------------------------


class TestBumpVersion:
    """Tests for bump_version() orchestrator."""

    def test_patch_bump(self, tmp_path: Path) -> None:
        """Should bump patch version in pyproject.toml."""
        setup_repo(tmp_path, "0.1.0")
        init_git_repo(tmp_path)
        result = bump_version(tmp_path, "patch")
        assert result == 0
        assert 'version = "0.1.1"' in (tmp_path / "pyproject.toml").read_text()

    def test_minor_bump(self, tmp_path: Path) -> None:
        """Should bump minor version in pyproject.toml."""
        setup_repo(tmp_path, "1.2.3")
        init_git_repo(tmp_path)
        result = bump_version(tmp_path, "minor")
        assert result == 0
        assert 'version = "1.3.0"' in (tmp_path / "pyproject.toml").read_text()

    def test_major_bump(self, tmp_path: Path) -> None:
        """Should bump major version in pyproject.toml."""
        setup_repo(tmp_path, "1.2.3")
        init_git_repo(tmp_path)
        result = bump_version(tmp_path, "major")
        assert result == 0
        assert 'version = "2.0.0"' in (tmp_path / "pyproject.toml").read_text()

    def test_no_git_tag_by_default(self, tmp_path: Path) -> None:
        """Should not create a git tag when --tag is not passed."""
        setup_repo(tmp_path, "0.1.0")
        init_git_repo(tmp_path)
        result = bump_version(tmp_path, "patch")
        assert result == 0
        tags = (
            subprocess.run(
                ["git", "tag"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert "v0.1.1" not in tags

    def test_creates_git_tag_when_flag_passed(self, tmp_path: Path) -> None:
        """Should create a git tag v{new_version} when tag=True is passed."""
        setup_repo(tmp_path, "0.1.0")
        init_git_repo(tmp_path)
        result = bump_version(tmp_path, "patch", tag=True)
        assert result == 0
        tags = (
            subprocess.run(
                ["git", "tag"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert "v0.1.1" in tags

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """Dry run should not modify any files."""
        setup_repo(tmp_path, "0.1.0")
        result = bump_version(tmp_path, "patch", dry_run=True)
        assert result == 0
        assert 'version = "0.1.0"' in (tmp_path / "pyproject.toml").read_text()

    def test_dry_run_prints_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry run should print the old -> new version."""
        setup_repo(tmp_path, "0.1.0")
        bump_version(tmp_path, "patch", dry_run=True)
        captured = capsys.readouterr()
        assert "0.1.0" in captured.out
        assert "0.1.1" in captured.out

    def test_verbose_prints_details(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Verbose mode should print bumping details."""
        setup_repo(tmp_path, "0.1.0")
        init_git_repo(tmp_path)
        bump_version(tmp_path, "patch", verbose=True)
        captured = capsys.readouterr()
        assert "Bumping version" in captured.out

    def test_prints_next_steps(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print next steps after successful bump."""
        setup_repo(tmp_path, "0.1.0")
        init_git_repo(tmp_path)
        bump_version(tmp_path, "patch")
        captured = capsys.readouterr()
        assert "uv lock" in captured.out
        assert "git commit" in captured.out

    def test_missing_pyproject_exits_one(self, tmp_path: Path) -> None:
        """Should sys.exit(1) if pyproject.toml is missing."""
        with pytest.raises(SystemExit) as exc_info:
            bump_version(tmp_path, "patch")
        assert exc_info.value.code == 1
