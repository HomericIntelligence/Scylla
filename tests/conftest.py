"""Top-level pytest configuration shared by all test suites.

This module is the project-wide ``conftest.py`` for ``tests/``. Directory-
level conftests (e.g. ``tests/unit/adapters/conftest.py``) remain authoritative
for fixtures that are tightly scoped to one domain (NATS publishers, e2e
checkpoint helpers, sample analysis DataFrames, etc.). Anything declared here
is available to every test in the suite.

Conventions
-----------
- Custom pytest markers are declared in ``pyproject.toml`` under
  ``[tool.pytest.ini_options].markers`` (see ``--strict-markers``). Add new
  markers there, not here.
- Fixtures placed in this file should be genuinely project-wide. Domain-
  specific fixtures belong in the nearest directory-level ``conftest.py``.
- The repo-root path constant is exposed both as a fixture (``repo_root``)
  for runtime use and as a module-level ``REPO_ROOT`` import target so
  module-level ``parametrize`` callers can avoid recomputing it.

Audit reference: GitHub issue #1871. A review of the five existing
directory-level conftests found no genuine fixture-level duplication —
each holds tightly-scoped helpers (e2e checkpoints, NATS server, adapter
mocks, analysis DataFrames, scripts/agents sys.path injection). The most
duplicated pattern across tests was ``Path(__file__).parents[N]`` to locate
the repo root; this file centralizes that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: Absolute path to the repository root (the directory containing
#: ``pyproject.toml`` and ``tests/``). Prefer importing this constant in
#: modules that need the path at collection time (e.g. inside a
#: ``@pytest.mark.parametrize`` argument), and use the ``repo_root``
#: fixture inside test functions.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the absolute path to the repository root.

    Centralizes the ``Path(__file__).parents[N]`` pattern that appears at
    module scope in many test files. Prefer this fixture inside test
    bodies; for collection-time uses (e.g. ``parametrize``), import the
    ``REPO_ROOT`` constant from ``tests.conftest`` instead.
    """
    return REPO_ROOT
