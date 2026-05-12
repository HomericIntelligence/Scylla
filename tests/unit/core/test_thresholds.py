"""Tests for ``scylla.core.thresholds``.

These guard the contract introduced when ``DEFAULT_PASS_THRESHOLD`` was
promoted from ``scylla.metrics.grading`` to ``scylla.core.thresholds`` to
break the ``config`` <-> ``metrics`` import cycle (issue #1937, edge 1).
"""

from __future__ import annotations


def test_default_pass_threshold_value() -> None:
    """The canonical threshold lives in ``scylla.core.thresholds``."""
    from scylla.core.thresholds import DEFAULT_PASS_THRESHOLD

    assert DEFAULT_PASS_THRESHOLD == 0.60


def test_metrics_grading_reexports_threshold() -> None:
    """``scylla.metrics.grading`` re-exports the constant for back-compat."""
    import scylla.core.thresholds as core_thresholds
    import scylla.metrics.grading as grading

    assert grading.DEFAULT_PASS_THRESHOLD is core_thresholds.DEFAULT_PASS_THRESHOLD


def test_config_models_does_not_import_metrics() -> None:
    """``scylla.config.models`` must not import from ``scylla.metrics``.

    Importing ``metrics`` from ``config`` is one direction of the cycle
    eliminated in #1937 (edge 1 of 3).
    """
    import pathlib

    import scylla.config.models as config_models

    source_path = pathlib.Path(config_models.__file__)
    source = source_path.read_text(encoding="utf-8")
    assert "from scylla.metrics" not in source
    assert "import scylla.metrics" not in source
