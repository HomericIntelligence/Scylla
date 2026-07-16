"""Regression guard for the empty-wheel bug class (PR #2046).

A global ``[tool.hatch.build] sources = ["src"]`` remaps the *sdist* contents
to drop the ``src/`` prefix; ``python -m build`` then builds the wheel FROM the
sdist, where ``packages = ["src/scylla"]`` matches nothing and hatchling ships
an empty wheel (dist-info only). The static pyproject string check in
``test_py_typed.py`` passes in both the broken and fixed states, so this test
builds real artifacts through the vulnerable sdist -> wheel path and inspects
the wheel zip directly.
"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

import pytest

hatchling_ourselves = pytest.importorskip(
    "hatchling",
    reason="hatchling (the build backend) must be an env dependency so this "
    "guard cannot silently stop running — see pixi.toml [pypi-dependencies]",
)

from hatchling.builders.sdist import SdistBuilder  # noqa: E402
from hatchling.builders.wheel import WheelBuilder  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]


def _build_sdist(dest: Path) -> Path:
    builder = SdistBuilder(str(REPO_ROOT))
    return Path(next(builder.build(directory=str(dest), versions=["standard"])))


def _build_wheel(source_root: Path, dest: Path) -> Path:
    builder = WheelBuilder(str(source_root))
    return Path(next(builder.build(directory=str(dest), versions=["standard"])))


def _wheel_names(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as zf:
        return zf.namelist()


def test_direct_wheel_ships_package(tmp_path: Path) -> None:
    """Tree -> wheel path ships scylla/ at the wheel top level."""
    names = _wheel_names(_build_wheel(REPO_ROOT, tmp_path))
    assert any(n == "scylla/__init__.py" for n in names), names[:20]
    assert any(n == "scylla/py.typed" for n in names), names[:20]
    assert not any(n.startswith("src/") for n in names), (
        "src/ prefix leaked into the wheel"
    )


def test_sdist_roundtrip_wheel_ships_package(tmp_path: Path) -> None:
    """sdist -> extract -> wheel path (what `python -m build` does).

    This is the exact path that shipped an empty wheel when a global
    ``sources = ["src"]`` remapped the sdist layout (PR #2046 / #2030).
    """
    sdist = _build_sdist(tmp_path)
    extract_dir = tmp_path / "extracted"
    with tarfile.open(sdist) as tf:
        tf.extractall(extract_dir, filter="data")
    (sdist_root,) = extract_dir.iterdir()

    # The sdist must preserve the src/ layout the wheel config expects.
    assert (sdist_root / "src" / "scylla" / "__init__.py").is_file(), (
        "sdist no longer contains src/scylla/ — a global sources remap "
        "has likely been reintroduced"
    )

    names = _wheel_names(_build_wheel(sdist_root, tmp_path / "wheel_out"))
    assert any(n == "scylla/__init__.py" for n in names), (
        "wheel built from the sdist is missing scylla/__init__.py — "
        f"empty-wheel regression; first entries: {names[:20]}"
    )
    assert any(n == "scylla/py.typed" for n in names)
    assert not any(n.startswith("src/") for n in names)
