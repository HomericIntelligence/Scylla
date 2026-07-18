"""Tests that the .importlinter config is present and well-formed.

This test validates the import-linter infrastructure added in issue #1940
(decompose e2e/ god-package). The contracts tighten PR-by-PR as files move
out of e2e/; this file just guards the config itself.
"""

from __future__ import annotations

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]  # tests/unit/e2e/test_... → repo root


class TestImportLinterConfig:
    """Guards the .importlinter configuration file."""

    def test_importlinter_file_exists(self) -> None:
        """Repo root must contain .importlinter."""
        assert (REPO_ROOT / ".importlinter").exists(), (
            ".importlinter not found — run PR-A of issue #1940"
        )

    def test_importlinter_has_importlinter_section(self) -> None:
        """[importlinter] section with root_packages must be present."""
        cfg = configparser.ConfigParser()
        cfg.read(REPO_ROOT / ".importlinter")
        assert "importlinter" in cfg.sections(), ".importlinter must have an [importlinter] section"
        assert cfg.has_option("importlinter", "root_packages"), (
            "[importlinter] section must declare root_packages"
        )

    def test_importlinter_root_packages_contains_scylla(self) -> None:
        """root_packages must include 'scylla'."""
        cfg = configparser.ConfigParser()
        cfg.read(REPO_ROOT / ".importlinter")
        root_pkgs = cfg.get("importlinter", "root_packages")
        assert "scylla" in root_pkgs.split(), "root_packages must list 'scylla'"

    def test_lint_imports_recipe_in_justfile(self) -> None:
        """Justfile must expose a lint-imports recipe (run under uv)."""
        justfile_text = (REPO_ROOT / "justfile").read_text()
        assert "lint-imports" in justfile_text, (
            "justfile must define a lint-imports recipe for import-linter"
        )

    def test_import_linter_in_dev_dependencies(self) -> None:
        """import-linter must appear in pyproject.toml [dependency-groups].dev."""
        pyproject_text = (REPO_ROOT / "pyproject.toml").read_text()
        assert "import-linter" in pyproject_text, (
            "import-linter must be listed in pyproject.toml [dependency-groups].dev"
        )
