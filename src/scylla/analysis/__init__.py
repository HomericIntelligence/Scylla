"""Statistical analysis package for Scylla experiment results.

This module provides data loading, statistical analysis, figure generation,
and table generation for evaluating agent performance across ablation study
tiers.
"""

from scylla.analysis.dataframes import (
    build_criteria_df,
    build_judges_df,
    build_runs_df,
    build_subtests_df,
)
from scylla.analysis.loader import load_all_experiments, load_experiment, load_rubric_weights

__all__ = [
    "build_criteria_df",
    "build_judges_df",
    "build_runs_df",
    "build_subtests_df",
    "load_all_experiments",
    "load_experiment",
    "load_rubric_weights",
]
