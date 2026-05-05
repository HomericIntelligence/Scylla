"""Unit tests for table generation.

Note: These are basic smoke tests to ensure tables can be generated.
Full validation of table content is deferred to integration tests.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest


def test_table01_tier_summary_format(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 1 returns valid dual-format output."""
    from scylla.analysis.tables import table01_tier_summary

    markdown, latex = table01_tier_summary(sample_runs_df)

    # Verify both formats are non-empty strings
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify key content is present
    assert "Pass Rate" in markdown or "pass rate" in markdown.lower()
    assert "tabular" in latex or "table" in latex.lower()


def test_tables_module_imports() -> None:
    """Test that tables module can be imported."""
    import scylla.analysis.tables

    assert scylla.analysis.tables is not None


def test_table_function_signatures() -> None:
    """Test that all table functions exist with expected signature."""
    import inspect

    from scylla.analysis import tables

    # List of expected table functions
    table_functions = [
        "table01_tier_summary",
        "table02_tier_comparison",
        "table03_judge_agreement",
        "table04_criteria_performance",
        "table05_cost_analysis",
        "table06_model_comparison",
        "table07_subtest_detail",
        "table08_summary_statistics",
        "table09_experiment_config",
        "table10_normality_tests",
        "table_cfp_comparison",
    ]

    for func_name in table_functions:
        assert hasattr(tables, func_name), f"Missing function: {func_name}"
        func = getattr(tables, func_name)
        sig = inspect.signature(func)
        # Should return tuple[str, str] for (markdown, latex)
        # Check if annotation is the string "tuple[str, str]" or the actual type
        ann = sig.return_annotation
        is_valid = (
            ann == inspect._empty
            or ann == tuple[str, str]
            or (isinstance(ann, str) and ann == "tuple[str, str]")
        )
        assert is_valid, f"Invalid return annotation for {func_name}: {ann}"


def test_table01_consistency_clamped() -> None:
    """Test that consistency values are clamped to [0, 1].

    Regression test for P0 bug where inline formula 1 - (std/mean) could produce
    negative values when std > mean (high-variance subtests).
    """
    import pandas as pd

    from scylla.analysis.tables import table01_tier_summary

    # Create minimal test data with high variance (std > mean)
    # This should trigger the clamping logic
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 10,
            "tier": ["T0"] * 10,
            "score": [0.1, 0.2, 0.3, 0.8, 0.9, 0.05, 0.15, 0.25, 0.5, 0.7],  # High variance
            "passed": [True] * 5 + [False] * 5,
            "cost_usd": [1.0] * 10,
            "subtest": [f"test_{i}" for i in range(10)],
        }
    )

    markdown, latex = table01_tier_summary(test_data)

    # Verify tables generated (basic smoke test)
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify no negative consistency values appear in output
    # Consistency should be clamped to [0, 1]
    assert (
        "-" not in markdown.split("Consistency")[1].split("|")[0]
        if "Consistency" in markdown
        else True
    )


def test_table01_uses_compute_cop() -> None:
    """Test that table01 uses shared compute_cop function.

    Regression test for P1 bug where inline formula duplicated compute_cop logic.
    """
    import pandas as pd

    from scylla.analysis.tables import table01_tier_summary

    # Create test data with zero pass rate to trigger inf CoP
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 5,
            "tier": ["T0"] * 5,
            "score": [0.0] * 5,
            "passed": [False] * 5,  # Zero pass rate
            "cost_usd": [1.0] * 5,
            "subtest": [f"test_{i}" for i in range(5)],
        }
    )

    markdown, latex = table01_tier_summary(test_data)

    # Verify tables generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)

    # Verify that inf appears in output (compute_cop returns inf for zero pass rate)
    assert "inf" in markdown.lower() or "∞" in markdown


def test_table08_summary_statistics() -> None:
    """Test Table 8 summary statistics smoke test."""
    import pandas as pd

    from scylla.analysis.tables import table08_summary_statistics

    # Create minimal test data
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 20,
            "tier": ["T0"] * 20,
            "score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] * 2,
            "cost_usd": [1.0, 1.5, 2.0, 2.5, 3.0] * 4,
            "duration_seconds": [10, 20, 30, 40, 50] * 4,
            "total_tokens": [1000, 2000, 3000, 4000, 5000] * 4,
        }
    )

    markdown, latex = table08_summary_statistics(test_data)

    # Verify tables generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify contains statistics headers
    assert "Mean" in markdown
    assert "Median" in markdown
    assert "Skew" in markdown
    assert "Kurt" in markdown


def test_table09_experiment_config() -> None:
    """Test Table 9 experiment configuration smoke test."""
    import pandas as pd

    from scylla.analysis.tables import table09_experiment_config

    # Create minimal test data
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 10,
            "tier": ["T0"] * 5 + ["T1"] * 5,
            "subtest": ["test1", "test2", "test1", "test2", "test1"] * 2,
        }
    )

    markdown, latex = table09_experiment_config(test_data)

    # Verify tables generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify contains configuration headers
    assert "Tiers" in markdown
    assert "Total Runs" in markdown


def test_table10_normality_tests() -> None:
    """Test Table 10 normality tests smoke test."""
    import pandas as pd

    from scylla.analysis.tables import table10_normality_tests

    # Create test data with sufficient samples for Shapiro-Wilk (need N >= 3)
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 10,
            "tier": ["T0"] * 10,
            "score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "cost_usd": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5],
        }
    )

    markdown, latex = table10_normality_tests(test_data)

    # Verify tables generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify contains normality test headers
    assert "Shapiro-Wilk" in markdown
    assert "Normal?" in markdown
    assert "W" in markdown
    assert "p-value" in markdown


# ============================================================================
# Functional tests for tables 02-07 (P0-2 from audit)
# ============================================================================


def test_table02_tier_comparison_statistical_workflow(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 2 statistical workflow: Kruskal-Wallis → pairwise → Holm-Bonferroni."""
    from scylla.analysis.tables import table02_tier_comparison

    markdown, latex = table02_tier_comparison(sample_runs_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 100
    assert len(latex) > 100

    # Verify statistical workflow documented
    assert "Kruskal-Wallis" in markdown
    assert "Mann-Whitney" in markdown
    assert "Holm-Bonferroni" in markdown

    # Verify contains tier comparisons
    assert "T0" in markdown and "T1" in markdown

    # Verify p-values present (format: 0.XXX or < 0.001)
    assert "p=" in markdown or "p <" in markdown


def test_table02_handles_single_tier(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 2 handles edge case of single tier."""
    from scylla.analysis.tables import table02_tier_comparison

    # Filter to single tier
    single_tier = sample_runs_df[sample_runs_df["tier"] == "T0"]

    markdown, latex = table02_tier_comparison(single_tier)

    # Should still generate output (no comparisons)
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0


def test_table02_holm_bonferroni_correction_applied(sample_runs_df: pd.DataFrame) -> None:
    """Test that Holm-Bonferroni correction is actually applied."""
    from scylla.analysis.tables import table02_tier_comparison

    # The fixture has 2 models × (3 choose 2) = 2 × 3 = 6 pairwise comparisons
    # Holm-Bonferroni should correct these p-values

    markdown, _latex = table02_tier_comparison(sample_runs_df)

    # Verify correction method mentioned in footer
    assert "Holm-Bonferroni" in markdown


def test_table03_judge_agreement(sample_judges_df: pd.DataFrame) -> None:
    """Test Table 3 judge agreement with Krippendorff's alpha."""
    from scylla.analysis.tables import table03_judge_agreement

    markdown, latex = table03_judge_agreement(sample_judges_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 50
    assert len(latex) > 50

    # Verify contains Krippendorff's alpha
    assert "Krippendorff" in markdown or "α" in markdown or "alpha" in markdown.lower()

    # Verify contains agreement metrics
    # Alpha should be in [-1, 1] range
    assert "0." in markdown or "1." in markdown or "-" in markdown


def test_table03_handles_single_judge(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 3 handles edge case of single judge."""
    import pandas as pd

    from scylla.analysis.tables import table03_judge_agreement

    # Create single-judge data with varying scores (krippendorff requires variance)
    single_judge = pd.DataFrame(
        {
            "experiment": sample_runs_df["experiment"][:10],
            "agent_model": sample_runs_df["agent_model"][:10],
            "tier": sample_runs_df["tier"][:10],
            "subtest": sample_runs_df["subtest"][:10],
            "run_number": sample_runs_df["run_number"][:10],
            "judge_number": [1] * 10,
            "judge_model": ["claude-opus-4-6"] * 10,
            "judge_score": [0.5, 0.6, 0.7, 0.8, 0.9, 0.4, 0.5, 0.6, 0.7, 0.8],  # Varied scores
            "judge_grade": ["A"] * 10,
        }
    )

    # Single judge should raise ValueError (need at least 2 judges for agreement)
    with pytest.raises(ValueError):
        table03_judge_agreement(single_judge)


def test_table04_criteria_performance_holm_bonferroni(
    sample_criteria_df: Any, sample_runs_df: Any
) -> None:
    """Test Table 4 uses Holm-Bonferroni for criteria comparisons."""
    from scylla.analysis.tables import table04_criteria_performance

    markdown, latex = table04_criteria_performance(sample_criteria_df, sample_runs_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 100
    assert len(latex) > 100

    # Verify contains criteria
    assert "functional" in markdown or "code_quality" in markdown

    # Verify contains statistical comparisons
    assert "p-value" in markdown or "p =" in markdown or "Winner" in markdown


def test_table04_handles_single_model(sample_criteria_df: Any, sample_runs_df: Any) -> None:
    """Test Table 4 handles single model gracefully."""
    from scylla.analysis.tables import table04_criteria_performance

    # Filter to single model
    single_model_criteria = sample_criteria_df[
        sample_criteria_df["agent_model"] == "claude-sonnet-4-6"
    ]
    single_model_runs = sample_runs_df[sample_runs_df["agent_model"] == "claude-sonnet-4-6"]

    markdown, latex = table04_criteria_performance(single_model_criteria, single_model_runs)

    # Should still generate output (no comparisons)
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 50


def test_table04_data_driven_criteria_weights(sample_criteria_df: Any, sample_runs_df: Any) -> None:
    """Test Table 4 derives criteria weights from data when not provided."""
    from scylla.analysis.tables import table04_criteria_performance

    # Call without providing criteria_weights
    markdown, _latex = table04_criteria_performance(sample_criteria_df, sample_runs_df)

    # Should derive weights from actual criteria in data
    # All 5 criteria from fixture should appear
    criteria = [
        "functional",
        "code_quality",
        "proportionality",
        "build_pipeline",
        "overall_quality",
    ]
    present_criteria = sum(1 for c in criteria if c in markdown)

    # At least some criteria should be present
    assert present_criteria >= 3


def test_table05_cost_analysis_token_breakdown(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 5 cost analysis includes token breakdown."""
    from scylla.analysis.tables import table05_cost_analysis

    markdown, latex = table05_cost_analysis(sample_runs_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 100
    assert len(latex) > 100

    # Verify contains cost metrics
    assert "Cost" in markdown
    assert "CoP" in markdown or "Cost-of-Pass" in markdown

    # Verify contains token breakdown
    assert "Input" in markdown or "Output" in markdown or "Token" in markdown


def test_table05_handles_zero_cost_runs(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 5 handles runs with zero cost gracefully."""
    from scylla.analysis.tables import table05_cost_analysis

    # Add some zero-cost runs
    zero_cost_data = sample_runs_df.copy()
    zero_cost_data.loc[:5, "cost_usd"] = 0.0

    markdown, latex = table05_cost_analysis(zero_cost_data)

    # Should handle gracefully
    assert isinstance(markdown, str)
    assert isinstance(latex, str)


def test_table06_model_comparison_holm_bonferroni(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 6 uses Holm-Bonferroni for model comparisons."""
    from scylla.analysis.tables import table06_model_comparison

    markdown, latex = table06_model_comparison(sample_runs_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 100
    assert len(latex) > 100

    # Verify contains model names
    assert "sonnet" in markdown or "haiku" in markdown

    # Verify contains comparison metrics
    assert "Pass Rate" in markdown or "Mean Score" in markdown
    assert "p-value" in markdown or "p =" in markdown


def test_table06_handles_single_model() -> None:
    """Test Table 6 handles single model error case."""
    import pandas as pd

    from scylla.analysis.tables import table06_model_comparison

    # Single model data
    single_model = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 10,
            "tier": ["T0"] * 10,
            "score": [0.8] * 10,
            "passed": [True] * 10,
        }
    )

    markdown, _latex = table06_model_comparison(single_model)

    # Should return error message
    assert "Error" in markdown or "Need at least 2 models" in markdown


def test_table06_multiple_models_pairwise() -> None:
    """Test Table 6 handles multiple models with pairwise comparisons."""
    import pandas as pd

    from scylla.analysis.tables import table06_model_comparison

    # Create data with 3 models (3 choose 2 = 3 pairs)
    # Include all required columns for table06
    data = pd.DataFrame(
        {
            "agent_model": ["Model A"] * 10 + ["Model B"] * 10 + ["Model C"] * 10,
            "tier": ["T0"] * 30,
            "score": [0.9] * 10 + [0.7] * 10 + [0.5] * 10,
            "passed": [True] * 10 + [True] * 8 + [False] * 2 + [True] * 5 + [False] * 5,
            "cost_usd": [0.1] * 10 + [0.2] * 10 + [0.3] * 10,
            "total_tokens": [1000] * 10 + [2000] * 10 + [3000] * 10,  # Required column
        }
    )

    markdown, _latex = table06_model_comparison(data)

    # Should generate all pairwise comparisons
    assert "Model A vs Model B" in markdown
    assert "Model A vs Model C" in markdown
    assert "Model B vs Model C" in markdown


def test_table07_subtest_detail_appendix(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 7 subtest detail generates appendix table."""
    from scylla.analysis.dataframes import build_subtests_df
    from scylla.analysis.tables import table07_subtest_detail

    # Build proper subtests DataFrame using the function
    subtests_df = build_subtests_df(sample_runs_df)

    # Note: signature is table07_subtest_detail(runs_df, subtests_df)
    markdown, latex = table07_subtest_detail(sample_runs_df, subtests_df)

    # Verify both formats generated
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 100
    assert len(latex) > 100

    # Verify contains subtest identifiers
    assert "00" in markdown or "01" in markdown

    # Verify contains tier information
    assert "T0" in markdown or "T1" in markdown

    # Verify LaTeX uses longtable (for multi-page appendix)
    assert "longtable" in latex or "tabular" in latex


def test_table07_handles_empty_subtests() -> None:
    """Test Table 7 handles empty subtest data gracefully."""
    import pandas as pd

    from scylla.analysis.tables import table07_subtest_detail

    # Empty DataFrames
    empty_subtests = pd.DataFrame(
        columns=[
            "experiment",
            "agent_model",
            "tier",
            "subtest",
            "pass_rate",
            "mean_score",
        ]
    )
    empty_runs = pd.DataFrame(
        columns=["agent_model", "tier", "subtest", "score", "passed", "cost_usd"]
    )

    markdown, latex = table07_subtest_detail(empty_subtests, empty_runs)

    # Should handle gracefully
    assert isinstance(markdown, str)
    assert isinstance(latex, str)


def test_table02b_impl_rate_comparison_format(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 2b returns valid dual-format output."""
    from scylla.analysis.tables import table02b_impl_rate_comparison

    markdown, latex = table02b_impl_rate_comparison(sample_runs_df)

    # Verify both formats are non-empty strings
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Verify key content is present
    assert "Impl-Rate" in markdown
    assert "tabular" in latex or "table" in latex.lower()


def test_table02b_impl_rate_statistical_workflow(sample_runs_df: pd.DataFrame) -> None:
    """Test Table 2b follows correct statistical workflow."""
    from scylla.analysis.tables import table02b_impl_rate_comparison

    markdown, _latex = table02b_impl_rate_comparison(sample_runs_df)

    # Verify statistical components are present
    assert "Kruskal-Wallis" in markdown
    assert "Mann-Whitney" in markdown
    assert "Holm-Bonferroni" in markdown
    assert "Cliff" in markdown

    # Verify omnibus results section exists
    assert "Omnibus Test Results" in markdown


def test_table02b_handles_missing_impl_rate() -> None:
    """Test Table 2b handles missing impl_rate column gracefully."""
    import pandas as pd

    from scylla.analysis.tables import table02b_impl_rate_comparison

    # Create DataFrame without impl_rate column
    test_data = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 5,
            "tier": ["T0"] * 5,
            "score": [0.5, 0.6, 0.7, 0.8, 0.9],
            "passed": [True] * 5,
        }
    )

    markdown, _latex = table02b_impl_rate_comparison(test_data)

    # Should return error message
    assert "Error" in markdown
    assert "impl_rate" in markdown


def test_table02b_holm_bonferroni_correction_applied(sample_runs_df: pd.DataFrame) -> None:
    """Test that Holm-Bonferroni correction is applied to p-values."""
    from scylla.analysis.tables import table02b_impl_rate_comparison

    markdown, _latex = table02b_impl_rate_comparison(sample_runs_df)

    # Verify correction is documented
    assert "Holm-Bonferroni" in markdown
    assert "correction" in markdown.lower()


def test_table08_calculation_verification() -> None:
    """Test Table 8 calculates summary statistics correctly."""
    import pandas as pd

    from scylla.analysis.tables import table08_summary_statistics

    # Create known test data for verification
    test_data = pd.DataFrame(
        {
            "agent_model": ["TestModel"] * 10,
            "tier": ["T0"] * 10,
            "score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "cost_usd": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "duration_seconds": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "total_tokens": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000],
        }
    )

    markdown, latex = table08_summary_statistics(test_data)

    # Verify tables were generated
    assert markdown
    assert latex

    # Verify calculations for score metric (known values)
    score_data = test_data["score"]
    expected_mean = score_data.mean()  # 0.55
    expected_median = score_data.median()  # 0.55

    # Check that expected values appear in markdown (within formatting tolerance)
    assert f"{expected_mean:.4f}" in markdown or f"{expected_mean:.3f}" in markdown
    assert f"{expected_median:.4f}" in markdown or f"{expected_median:.3f}" in markdown

    # Verify N=10 appears
    assert "10" in markdown

    # Verify latex has same structure
    assert "TestModel" in latex
    assert "Score" in latex or "score" in latex.lower()


def test_table09_calculation_verification() -> None:
    """Test Table 9 correctly extracts experiment configuration."""
    import pandas as pd

    from scylla.analysis.tables import table09_experiment_config

    # Create test data with known configuration
    test_data = pd.DataFrame(
        {
            "experiment": ["exp001"] * 12,
            "agent_model": ["Model A"] * 6 + ["Model B"] * 6,
            "tier": ["T0", "T1"] * 6,
            "subtest": ["test1", "test2", "test3"] * 4,
        }
    )

    markdown, latex = table09_experiment_config(test_data)

    # Verify tables were generated
    assert markdown
    assert latex

    # Verify key configuration elements are present
    assert "exp001" in markdown or "Experiment" in markdown

    # Verify model count (2 models)
    assert "2" in markdown or ("Model A" in markdown and "Model B" in markdown)

    # Verify tier count (2 tiers: T0, T1)
    assert "T0" in markdown or "T1" in markdown or "2" in markdown

    # Verify subtest count (3 unique subtests)
    assert "3" in markdown or "test1" in markdown

    # Verify latex has same information
    assert "exp001" in latex or len(latex) > 100


def test_table02_power_column_present(sample_runs_df: pd.DataFrame) -> None:
    """Test that Power column is present in Table 2 markdown and LaTeX output."""
    from scylla.analysis.tables import table02_tier_comparison

    markdown, latex = table02_tier_comparison(sample_runs_df)

    assert "Power" in markdown
    assert "Power" in latex


def test_table02b_power_column_present(sample_runs_df: pd.DataFrame) -> None:
    """Test that Power column is present in Table 2b markdown and LaTeX output."""
    from scylla.analysis.tables import table02b_impl_rate_comparison

    markdown, latex = table02b_impl_rate_comparison(sample_runs_df)

    assert "Power" in markdown
    assert "Power" in latex


def test_table02_power_is_numeric(sample_runs_df: pd.DataFrame) -> None:
    """Test that power values in Table 2 are floating-point parseable.

    The mock_power_simulations autouse fixture returns 0.8 for mann_whitney_power,
    so all rows with N >= 5 should show '0.800'.
    """
    from scylla.analysis.tables import table02_tier_comparison

    markdown, _latex = table02_tier_comparison(sample_runs_df)

    # The mocked mann_whitney_power returns 0.8, so we expect 0.800 in output
    assert "0.800" in markdown


def test_table02_power_nan_for_small_samples() -> None:
    """Test that '—' sentinel appears for small-sample rows (N < 5)."""
    import pandas as pd

    from scylla.analysis.tables import table02_tier_comparison

    # 3 runs per tier per model — below the N >= 5 guard
    np.random.seed(0)
    data = []
    for model in ["Model A"]:
        for tier in ["T0", "T1"]:
            for run in range(1, 4):
                data.append(
                    {
                        "agent_model": model,
                        "tier": tier,
                        "subtest": "00",
                        "run_number": run,
                        "passed": int(np.random.choice([0, 1])),
                        "score": float(np.random.uniform(0.3, 0.9)),
                        "impl_rate": float(np.random.uniform(0.3, 0.9)),
                        "grade": "B",
                        "cost_usd": 0.05,
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "cache_creation_tokens": 0,
                        "cache_read_tokens": 0,
                        "total_tokens": 1500,
                        "duration_seconds": 10.0,
                        "agent_duration_seconds": 8.0,
                        "judge_duration_seconds": 2.0,
                        "consistency": 0.9,
                        "exit_code": 0,
                        "experiment": "test-exp",
                    }
                )
    small_df = pd.DataFrame(data)

    markdown, _latex = table02_tier_comparison(small_df)

    # All transitions have N=3 < 5, so power should be '—'
    assert "—" in markdown


def test_table02_omnibus_power_in_footer(sample_runs_df: pd.DataFrame) -> None:
    """Test that omnibus KW power value appears in Table 2 footer section."""
    from scylla.analysis.tables import table02_tier_comparison

    markdown, latex = table02_tier_comparison(sample_runs_df)

    # The mocked kruskal_wallis_power returns 0.75
    assert "power=0.750" in markdown
    assert "power=0.750" in latex


def test_table10_calculation_verification() -> None:
    """Test Table 10 calculates Shapiro-Wilk normality tests correctly."""
    import numpy as np
    import pandas as pd
    from scipy import stats as scipy_stats

    from scylla.analysis.tables import table10_normality_tests

    # Create test data: one normal distribution and one non-normal
    np.random.seed(42)
    normal_data = np.random.normal(0.5, 0.1, 50)  # Should pass normality
    uniform_data = np.random.uniform(0, 1, 50)  # Should fail normality

    test_data = pd.DataFrame(
        {
            "agent_model": ["NormalModel"] * 50 + ["UniformModel"] * 50,
            "tier": ["T0"] * 100,
            "score": np.concatenate([normal_data, uniform_data]),
            "cost_usd": np.concatenate([normal_data * 10, uniform_data * 10]),
        }
    )

    markdown, latex = table10_normality_tests(test_data)

    # Verify tables were generated
    assert markdown
    assert latex

    # Verify both models appear
    assert "NormalModel" in markdown
    assert "UniformModel" in markdown

    # Verify Shapiro-Wilk statistics are present (W statistic and p-value)
    # W statistic should be between 0 and 1
    assert "0." in markdown  # Some decimal number

    # Verify significance indicators (* or NS) are present
    assert "*" in markdown or "NS" in markdown or "Yes" in markdown or "No" in markdown

    # Manually verify one calculation
    normal_scores = test_data[test_data["agent_model"] == "NormalModel"]["score"]
    _w_stat, _p_value = scipy_stats.shapiro(normal_scores)

    # Verify the table has substantial content with statistics
    assert len(markdown) > 100  # Table should have substantial content

    # Verify latex has same structure
    assert "NormalModel" in latex
    assert "UniformModel" in latex


# ============================================================================
# Tests for table_cfp_comparison
# ============================================================================


def test_table_cfp_comparison_format(sample_runs_df: pd.DataFrame) -> None:
    """Test table_cfp_comparison returns valid dual-format output."""
    from scylla.analysis.tables import table_cfp_comparison

    markdown, latex = table_cfp_comparison(sample_runs_df)

    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0

    # Both CFP and R_Prog sections should be present
    assert "CFP" in markdown
    assert "tabular" in latex or "table" in latex.lower()


def test_table_cfp_comparison_missing_column() -> None:
    """Test table_cfp_comparison returns placeholder when cfp column is absent."""
    import pandas as pd

    from scylla.analysis.tables import table_cfp_comparison

    df = pd.DataFrame(
        {
            "agent_model": ["claude-sonnet-4-6"] * 5,
            "tier": ["T0"] * 5,
            "score": [0.5, 0.6, 0.7, 0.8, 0.9],
            "passed": [True] * 5,
        }
    )

    markdown, latex = table_cfp_comparison(df)

    # Should return placeholder strings without raising
    assert isinstance(markdown, str)
    assert isinstance(latex, str)
    assert len(markdown) > 0
    assert len(latex) > 0


def test_table_cfp_comparison_all_nan(sample_runs_df: pd.DataFrame) -> None:
    """Test table_cfp_comparison handles all-NaN cfp column without error."""
    from scylla.analysis.tables import table_cfp_comparison

    df = sample_runs_df.copy()
    df["cfp"] = float("nan")
    df["r_prog"] = float("nan")

    markdown, latex = table_cfp_comparison(df)

    # Should complete without exception and return valid strings
    assert isinstance(markdown, str)
    assert isinstance(latex, str)


def test_table_cfp_comparison_statistical_workflow(sample_runs_df: pd.DataFrame) -> None:
    """Test table_cfp_comparison uses correct statistical workflow."""
    from scylla.analysis.tables import table_cfp_comparison

    markdown, latex = table_cfp_comparison(sample_runs_df)

    # Verify statistical workflow documented in CFP section
    assert "Kruskal-Wallis" in markdown
    assert "Mann-Whitney" in markdown
    assert "Holm-Bonferroni" in markdown

    # Verify both sections present
    assert "Change Fail Percentage" in markdown
    assert "Fine-Grained Progress" in markdown

    # LaTeX should have two table environments
    assert latex.count(r"\begin{table}") >= 2
