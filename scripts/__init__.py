r"""Scripts package for Scylla automation and tooling.

This directory contains standalone automation scripts and pre-commit hook helpers.
It is intentionally added to pytest's ``pythonpath`` in ``pyproject.toml`` so that
tests can import script modules directly (e.g. ``from export_data import ...`` or
``from manage_experiment import ...``) without requiring a package install step.

Pythonpath requirements summary
--------------------------------
``pyproject.toml`` sets ``pythonpath = [".", "scripts"]`` under
``[tool.pytest.ini_options]``.  This makes two things importable during test
collection:

* ``"."``      - the repo root, so ``scylla.*`` packages resolve correctly.
* ``"scripts"`` - this directory, so top-level script modules such as
  ``export_data``, ``manage_experiment``, ``common``, etc. are importable by
  their bare module names without a ``scripts.`` prefix.

Scripts that are run *directly* (e.g. ``pixi run python scripts/foo.py``)
rely on Python's standard behaviour of inserting the script's own directory
at ``sys.path[0]``, so they can also import sibling modules (``common``,
``validation``) without an explicit ``sys.path`` manipulation.

Scripts in ``scripts/agents/`` use explicit ``sys.path.insert`` calls to add
both the repo root *and* ``scripts/`` to the path, since they are one level
deeper and must reach ``scylla.*`` as well as ``common`` / ``agent_utils``.

Audit results (2026-02-28, issue #1193)
-----------------------------------------
``pixi run pytest --collect-only 2>&1 | grep 'ERROR|ModuleNotFoundError'``
produced **no collection errors**.  All 3480 tests were collected successfully.
No additional pythonpath entries are required beyond the existing configuration.
"""
