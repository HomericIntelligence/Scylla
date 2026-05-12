"""Shared infrastructure for rerun.py and rerun_judges.py.

This module consolidates common patterns for re-running agents and judges,
including config loading, tiers directory detection, and dry-run output formatting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from scylla.e2e.models import ExperimentConfig
from scylla.e2e.tier_manager import TierManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class RerunContext(BaseModel):
    """Shared context for rerun operations."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    experiment_dir: Path
    config: ExperimentConfig
    tier_manager: TierManager
    tiers_dir: Path


def load_rerun_context(experiment_dir: Path) -> RerunContext:
    """Load experiment config and auto-detect tiers directory.

    Args:
        experiment_dir: Path to experiment directory

    Returns:
        RerunContext with loaded configuration

    Raises:
        FileNotFoundError: If config or tiers directory not found

    """
    logger.info(f"Scanning experiment directory: {experiment_dir}")

    # Load experiment config
    config_file = experiment_dir / "config" / "experiment.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Experiment config not found: {config_file}")

    config = ExperimentConfig.load(config_file)
    logger.info(f"Loaded config: {config.experiment_id}")

    # Auto-detect tiers_dir: look for tests/fixtures/tests/ in parent directories
    current = experiment_dir
    tiers_dir = None
    for _ in range(5):  # Search up to 5 levels up
        candidate = current / "tests" / "fixtures" / "tests"
        if candidate.exists() and candidate.is_dir():
            # Find test-NNN directory
            test_dirs = [
                d for d in candidate.iterdir() if d.is_dir() and d.name.startswith("test-")
            ]
            if test_dirs:
                tiers_dir = sorted(test_dirs)[0]  # Use first test dir
                break
        current = current.parent
        if current == current.parent:  # Reached root
            break

    if not tiers_dir:
        # Fallback: try ProjectScylla root
        project_root = Path(__file__).parent.parent.parent.parent
        candidate = project_root / "tests" / "fixtures" / "tests"
        if candidate.exists():
            test_dirs = [
                d for d in candidate.iterdir() if d.is_dir() and d.name.startswith("test-")
            ]
            if test_dirs:
                tiers_dir = sorted(test_dirs)[0]

    if not tiers_dir:
        raise FileNotFoundError(
            "Could not auto-detect tiers directory. Please ensure the experiment was created "
            "with a valid test fixture directory."
        )

    logger.info(f"Using tiers directory: {tiers_dir}")

    # Create tier manager
    tier_manager = TierManager(tiers_dir)

    return RerunContext(
        experiment_dir=experiment_dir,
        config=config,
        tier_manager=tier_manager,
        tiers_dir=tiers_dir,
    )


def print_dry_run_summary(
    items_by_status: dict[Any, Any],
    status_names: dict[Any, str],
    max_preview: int = 10,
) -> None:
    """Print dry-run summary for runs or judge slots.

    Args:
        items_by_status: Dictionary mapping status enum to list of items
        status_names: Dictionary mapping status enum to display name
        max_preview: Maximum number of items to preview per status (default: 10)

    """
    print("\n" + "=" * 70)  # noqa: T201
    print("DRY RUN MODE - No changes will be made")  # noqa: T201
    print("=" * 70)  # noqa: T201

    for status, items in items_by_status.items():
        if items:
            display_name = status_names.get(status, status.value.upper())
            print(f"\n{display_name} ({len(items)} items):")  # noqa: T201
            for item in items[:max_preview]:
                # Format item based on its attributes
                if hasattr(item, "judge_number"):
                    # Judge slot format
                    print(  # noqa: T201
                        f"  - {item.tier_id}/{item.subtest_id}/run_{item.run_number:02d} "
                        f"judge_{item.judge_number:02d} ({item.judge_model}): {item.reason}"
                    )
                else:
                    # Run format
                    run_id = f"{item.tier_id}/{item.subtest_id}/run_{item.run_number:02d}"
                    print(f"  - {run_id}: {item.reason}")  # noqa: T201
            if len(items) > max_preview:
                print(f"  ... and {len(items) - max_preview} more")  # noqa: T201
