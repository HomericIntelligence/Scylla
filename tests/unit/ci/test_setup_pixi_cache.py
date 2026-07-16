"""Regression tests for the shared Pixi setup action."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SETUP_PIXI_ACTION = _PROJECT_ROOT / ".github" / "actions" / "setup-pixi" / "action.yml"


class TestSetupPixiCache(unittest.TestCase):
    """The shared setup action must own its environment cache safely."""

    def test_delegates_environment_cache_to_setup_pixi(self) -> None:
        """Use setup-pixi's cache instead of restoring a second `.pixi` archive."""
        action = yaml.safe_load(_SETUP_PIXI_ACTION.read_text())
        setup_steps = [
            step
            for step in action["runs"]["steps"]
            if step.get("uses", "").startswith("prefix-dev/setup-pixi@")
        ]
        cache_steps = [
            step
            for step in action["runs"]["steps"]
            if step.get("uses", "").startswith("actions/cache@")
        ]

        self.assertEqual(len(setup_steps), 1)
        self.assertIs(setup_steps[0]["with"]["cache"], True)
        self.assertEqual(cache_steps, [])
