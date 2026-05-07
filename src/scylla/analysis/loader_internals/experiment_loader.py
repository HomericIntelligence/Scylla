"""Experiment-level loaders: directory traversal and rubric weight aggregation."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import yaml

from .models import RubricConflict, RubricConflictError, RunData
from .run_loader import load_run, resolve_agent_model

logger = logging.getLogger(__name__)


def load_experiment(
    experiment_dir: Path,
    agent_model: str,
    experiment_name: str | None = None,
) -> list[RunData]:
    """Load all runs from an experiment.

    Args:
        experiment_dir: Path to experiment directory (contains tier dirs)
        agent_model: Agent model display name
        experiment_name: Override for experiment name. If None, uses directory name.

    Returns:
        List of all run data

    Note:
        Automatically skips non-tier directories (config, judges.txt, etc.)

    """
    runs = []
    experiment_name = experiment_name or experiment_dir.name

    # Iterate through tier directories (T0-T6) — results live under completed/
    from scylla.e2e.paths import COMPLETED_DIR

    completed_dir = experiment_dir / COMPLETED_DIR
    scan_base = completed_dir if completed_dir.exists() else experiment_dir
    for tier_dir in sorted(scan_base.iterdir()):
        if not tier_dir.is_dir() or not tier_dir.name.startswith("T"):
            continue

        tier_id = tier_dir.name

        # Iterate through subtest directories
        for subtest_dir in sorted(tier_dir.iterdir()):
            if not subtest_dir.is_dir() or not subtest_dir.name.isdigit():
                continue

            subtest_id = subtest_dir.name

            # Iterate through run directories
            for run_dir in sorted(subtest_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue

                try:
                    run = load_run(run_dir, experiment_name, tier_id, subtest_id, agent_model)
                    runs.append(run)
                except Exception as e:
                    logger.warning("Failed to load %s: %s", run_dir, e)
                    continue

    return runs


def load_all_experiments(
    data_dir: Path,
    exclude: list[str] | None = None,
) -> dict[str, list[RunData]]:
    """Load all experiments from a data directory.

    Args:
        data_dir: Path to fullruns directory
        exclude: List of experiment names to exclude (default: [])

    Returns:
        Dictionary mapping experiment name to list of runs

    Note:
        To load rubric weights with conflict resolution, call
        :func:`load_rubric_weights` separately with the desired
        ``rubric_conflict`` policy.

    """
    if exclude is None:
        exclude = []

    experiments = {}

    for exp_dir in sorted(data_dir.iterdir()):
        if not exp_dir.is_dir():
            continue

        # Find the timestamped subdirectory (use latest if multiple)
        timestamped_dirs = sorted([d for d in exp_dir.iterdir() if d.is_dir()])
        if not timestamped_dirs:
            continue

        # Use the latest timestamped directory (sorted alphabetically = chronologically)
        actual_exp_dir = timestamped_dirs[-1]
        exp_name = exp_dir.name

        if exp_name in exclude:
            logger.info("Skipping excluded experiment: %s", exp_name)
            continue

        logger.info("Loading experiment: %s", exp_name)

        # Resolve agent model from experiment configuration
        try:
            agent_model = resolve_agent_model(actual_exp_dir)
        except ValueError as e:
            logger.warning("%s, skipping experiment", e)
            continue

        runs = load_experiment(actual_exp_dir, agent_model, experiment_name=exp_name)
        experiments[exp_name] = runs
        logger.info("  Loaded %d runs (agent model: %s)", len(runs), agent_model)

    return experiments


def load_rubric_weights(  # noqa: C901  # config loading with many format/version branches
    data_dir: Path,
    exclude: list[str] | None = None,
    rubric_conflict: RubricConflict = "error",
) -> dict[str, float]:
    """Load and merge category weights from all experiments' rubric.yaml files.

    Scans every experiment directory for rubric.yaml and parses
    ``categories.*.weight``.  When the same category appears in more than one
    experiment the ``rubric_conflict`` policy controls resolution:

    * ``'error'`` (default) – raise :class:`RubricConflictError` immediately.
    * ``'warn'``  – emit a :class:`UserWarning` and keep the *first* value.
    * ``'first'`` – silently keep the first value encountered.
    * ``'last'``  – silently overwrite with the most-recently-seen value.

    Float comparison uses a tolerance of ``1e-6`` to avoid spurious conflicts
    from JSON serialisation round-trips.

    Args:
        data_dir: Root fullruns directory.
        exclude: List of experiment names to exclude.
        rubric_conflict: Policy for handling conflicting rubric weights.

    Returns:
        Dictionary mapping category names to weights, or ``{}`` if no
        rubric.yaml was found in any experiment.

    Raises:
        RubricConflictError: If ``rubric_conflict='error'`` and a conflict is
            detected.

    """
    exclude = exclude or []

    # accumulated_weights maps category → (weight, source_experiment_name)
    accumulated: dict[str, tuple[float, str]] = {}
    found_any = False

    for exp_dir in sorted(data_dir.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name in exclude:
            continue

        exp_name = exp_dir.name

        # Use the latest timestamp directory (sorted alphabetically = chronologically)
        ts_dirs = sorted(d for d in exp_dir.iterdir() if d.is_dir())
        if not ts_dirs:
            continue
        ts_dir = ts_dirs[-1]

        rubric_path = ts_dir / "rubric.yaml"
        if not rubric_path.exists():
            continue

        with rubric_path.open() as f:
            data = yaml.safe_load(f)

        categories = data.get("categories", {}) if data else {}
        found_any = True

        for cat_name, cat_data in categories.items():
            new_weight: float = cat_data.get("weight", 0.0) if cat_data else 0.0

            if cat_name not in accumulated:
                accumulated[cat_name] = (new_weight, exp_name)
                continue

            existing_weight, existing_exp = accumulated[cat_name]
            if abs(existing_weight - new_weight) <= 1e-6:
                # Identical within tolerance – no conflict.
                continue

            # Genuine conflict – apply policy.
            if rubric_conflict == "error":
                raise RubricConflictError(
                    category=cat_name,
                    exp_first=existing_exp,
                    weight_first=existing_weight,
                    exp_second=exp_name,
                    weight_second=new_weight,
                )
            elif rubric_conflict == "warn":
                warnings.warn(
                    f"Rubric conflict for category '{cat_name}': "
                    f"experiment '{existing_exp}' defines weight={existing_weight}, "
                    f"but experiment '{exp_name}' defines weight={new_weight}. "
                    "Keeping first value.",
                    UserWarning,
                    stacklevel=2,
                )
                # Keep first – no update to accumulated.
            elif rubric_conflict == "first":
                pass  # Keep first – no update to accumulated.
            elif rubric_conflict == "last":
                accumulated[cat_name] = (new_weight, exp_name)

    if not found_any:
        return {}

    return {cat: weight for cat, (weight, _) in accumulated.items()}
