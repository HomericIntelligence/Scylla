"""Guard: the repo uses uv, not pixi, as its Python toolchain (Odysseus ADR-017).

Scylla migrated from pixi + pip to uv (mirroring HomericIntelligence/Hephaestus#2236).
These regression tests lock in the migration so a stray pixi.toml/pixi.lock cannot
creep back in and so the uv single-source-of-truth files remain present and coherent.
"""

from __future__ import annotations

import sys
from pathlib import Path

# tomllib is stdlib on 3.11+; fall back to tomli on 3.10.
if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib

_REPO_ROOT = Path(__file__).resolve().parents[3]


class TestUvRuntimeContract:
    """The uv toolchain is the single source of truth for Python deps."""

    def test_pixi_toml_absent(self) -> None:
        """pixi.toml must not exist — it was removed in the uv migration."""
        assert not (_REPO_ROOT / "pixi.toml").exists(), (
            "pixi.toml reappeared — Scylla uses uv (ADR-017), not pixi. "
            "Declare dependencies in pyproject.toml instead."
        )

    def test_pixi_lock_absent(self) -> None:
        """pixi.lock must not exist — it was removed in the uv migration."""
        assert not (_REPO_ROOT / "pixi.lock").exists(), (
            "pixi.lock reappeared — Scylla uses uv (ADR-017). Commit uv.lock instead."
        )

    def test_pixi_version_file_absent(self) -> None:
        """The canonical .github/pixi-version file must not exist."""
        assert not (_REPO_ROOT / ".github" / "pixi-version").exists(), (
            ".github/pixi-version reappeared — the pixi pin is obsolete under uv."
        )

    def test_setup_pixi_action_absent(self) -> None:
        """The composite setup-pixi action must not exist."""
        assert not (_REPO_ROOT / ".github" / "actions" / "setup-pixi").exists(), (
            ".github/actions/setup-pixi reappeared — CI uses astral-sh/setup-uv."
        )

    def test_uv_lock_present(self) -> None:
        """uv.lock must be committed as the resolved dependency lockfile."""
        assert (_REPO_ROOT / "uv.lock").is_file(), (
            "uv.lock missing — run 'uv lock' and commit the result."
        )

    def test_pyproject_declares_dependency_groups(self) -> None:
        """pyproject.toml must expose a uv-native [dependency-groups].dev group."""
        with (_REPO_ROOT / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
        groups = data.get("dependency-groups", {})
        assert "dev" in groups, "pyproject.toml must define [dependency-groups].dev"
        assert groups["dev"], "[dependency-groups].dev must not be empty"

    def test_no_pixi_run_in_justfile(self) -> None:
        """The justfile must invoke tools via 'uv run', never 'pixi run'."""
        justfile_text = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
        assert "pixi run" not in justfile_text, (
            "justfile still references 'pixi run' — convert recipes to 'uv run'."
        )
