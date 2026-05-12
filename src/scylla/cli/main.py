"""Command-line interface for ProjectScylla."""

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from scylla import __version__
from scylla.config import DEFAULT_JUDGE_MODEL, ConfigLoader
from scylla.e2e.orchestrator import EvalOrchestrator, OrchestratorConfig
from scylla.reporting import (
    HtmlReportGenerator,
    JsonReportGenerator,
    MarkdownReportGenerator,
    ReportData,
    ReportWriter,
    SensitivityAnalysis,
    TierMetrics,
    TransitionAssessment,
    create_tier_metrics,
)
from scylla.utils.json_logging import (
    configure_json_logging,
    is_json_logging_enabled,
)
from scylla.utils.tracing import configure_tracing, get_tracer

# Dict-dispatch mapping format names to generator classes.
# Adding a new format requires only a new entry here
# and a generator class that satisfies the ReportWriter protocol.
FORMAT_GENERATORS: dict[str, type[ReportWriter]] = {
    "html": HtmlReportGenerator,
    "json": JsonReportGenerator,
    "markdown": MarkdownReportGenerator,
}


@click.group()
@click.version_option(version=__version__, prog_name="scylla")
def cli() -> None:
    """ProjectScylla - AI Agent Testing Framework.

    Evaluate and benchmark AI agent architectures across multiple tiers.
    """
    # Opt-in structured JSON logging via SCYLLA_JSON_LOGS=1.
    # Default behaviour (text logs) is unchanged.
    if is_json_logging_enabled():
        configure_json_logging()
    # Opt-in OpenTelemetry tracing via SCYLLA_OTEL_EXPORTER=console|otlp.
    # When unset, this is a no-op and no SDK imports happen.
    configure_tracing()


@cli.command()
@click.argument("test_id")
@click.option(
    "--tier",
    "-t",
    multiple=True,
    help="Tier(s) to run (e.g., T0, T1). Can be specified multiple times.",
)
@click.option(
    "--model",
    "-m",
    help="Run specific model only.",
)
@click.option(
    "--runs",
    "-r",
    default=10,
    type=int,
    help="Number of runs per tier (default: 10).",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    help="Override output directory.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Minimal output (for CI).",
)
def run(
    test_id: str,
    tier: tuple[str, ...],
    model: str | None,
    runs: int,
    output_dir: Path | None,
    verbose: bool,
    quiet: bool,
) -> None:
    """Run evaluation for a test case.

    TEST_ID is the identifier of the test to run (e.g., 001-justfile-to-makefile).

    Examples:
        scylla run 001-justfile-to-makefile

        scylla run 001-justfile-to-makefile --tier T0 --tier T1

        scylla run 001-justfile-to-makefile --model claude-opus-4-6 --runs 1

    """
    if verbose and quiet:
        raise click.UsageError("Cannot use --verbose and --quiet together.")

    tiers = list(tier) if tier else None  # None means use test defaults
    model_id = model or ConfigLoader().load_defaults().default_model

    # Configure orchestrator
    base_path = output_dir.parent if output_dir else Path(".")
    config = OrchestratorConfig(
        base_path=base_path,
        runs_per_tier=runs,
        tiers=tiers,
        model=model_id,
        quiet=quiet,
        verbose=verbose,
    )

    orchestrator = EvalOrchestrator(config)

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("scylla.experiment.run") as span:
        span.set_attribute("experiment.test_id", test_id)
        span.set_attribute("experiment.model", model_id)
        span.set_attribute("experiment.runs_per_tier", runs)
        if tiers is not None:
            span.set_attribute("experiment.tiers", ",".join(tiers))
        try:
            if runs == 1 and tiers and len(tiers) == 1:
                # Single run mode
                result = orchestrator.run_single(
                    test_id=test_id,
                    model_id=model_id,
                    tier_id=tiers[0],
                )
                if not quiet:
                    click.echo(f"\nResult: {'PASS' if result.judgment.passed else 'FAIL'}")
                    click.echo(f"Grade: {result.judgment.letter_grade}")
                    click.echo(f"Cost: ${result.metrics.cost_usd:.4f}")
            else:
                # Multi-run mode
                results = orchestrator.run_test(
                    test_id=test_id,
                    models=[model_id],
                    tiers=tiers,
                    runs_per_tier=runs,
                )
                if not quiet:
                    passed = sum(1 for r in results if r.judgment.passed)
                    click.echo(f"\nCompleted {len(results)} runs")
                    click.echo(f"Pass rate: {passed}/{len(results)}")

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)


def _load_results(test_id: str, base_path: Path = Path(".")) -> list[dict[str, Any]]:
    """Load all result.json files for a test.

    Args:
        test_id: Test identifier
        base_path: Base path for runs directory

    Returns:
        List of result dictionaries

    """
    runs_dir = base_path / "runs" / test_id
    results: list[dict[str, Any]] = []

    if not runs_dir.exists():
        return results

    for result_file in runs_dir.rglob("result.json"):
        with open(result_file) as f:
            results.append(json.load(f))

    return results


def _calculate_tier_metrics(
    tier_id: str, results: list[dict[str, Any]], t0_pass_rate: float | None = None
) -> TierMetrics:
    """Calculate metrics for a tier from results.

    Args:
        tier_id: Tier identifier
        results: List of result dictionaries for this tier
        t0_pass_rate: T0 pass rate for uplift calculation

    Returns:
        TierMetrics for the tier

    """
    tier_names = {
        "T0": "Prompts",
        "T1": "Skills",
        "T2": "Tooling",
        "T3": "Delegation",
        "T4": "Hierarchy",
        "T5": "Hybrid",
        "T6": "Super",
    }

    pass_rates = [r["grading"]["pass_rate"] for r in results]
    impl_rates = [r["judgment"]["impl_rate"] for r in results]
    composites = [r["grading"]["composite_score"] for r in results]
    costs = [r["grading"]["cost_of_pass"] for r in results]
    # Filter out infinity for cost median
    valid_costs = [c for c in costs if c != float("inf")]

    pass_rate_median = statistics.median(pass_rates)
    impl_rate_median = statistics.median(impl_rates)
    composite_median = statistics.median(composites)
    cost_median = statistics.median(valid_costs) if valid_costs else float("inf")
    consistency_std = statistics.stdev(pass_rates) if len(pass_rates) > 1 else 0.0

    # Calculate uplift vs T0
    uplift = 0.0
    if t0_pass_rate is not None and t0_pass_rate > 0:
        uplift = ((pass_rate_median - t0_pass_rate) / t0_pass_rate) * 100

    return create_tier_metrics(
        tier_id=tier_id,
        tier_name=tier_names.get(tier_id, tier_id),
        pass_rate_median=pass_rate_median,
        impl_rate_median=impl_rate_median,
        composite_median=composite_median,
        cost_of_pass_median=cost_median,
        consistency_std_dev=consistency_std,
        uplift=uplift,
    )


def _resolve_output_path(output: str | None, base_path: Path) -> tuple[Path, Path | None]:
    """Resolve the --output flag into a report directory and optional file path.

    Paths with a recognized extension (.md, .json) are treated as explicit file
    paths; paths without extensions are treated as directories.

    Args:
        output: Raw --output value (``None`` when not provided, ``"-"`` for
            stdout is handled by the caller).
        base_path: Fallback base directory (used when *output* is ``None``).

    Returns:
        Tuple of ``(report_dir, resolved_output_path)``.

    """
    output_path = Path(output) if output else None
    resolved: Path | None = None

    if output_path is not None and output_path.suffix in (".md", ".json", ".html"):
        resolved = output_path
        report_dir = output_path.parent
    elif output_path is not None:
        report_dir = output_path
    else:
        report_dir = base_path / "reports"

    return report_dir, resolved


def _warn_format_extension_mismatch(output: str | None, output_format: str) -> None:
    """Emit a stderr warning when the output file extension implies a different format.

    Args:
        output: Raw --output value (``None`` or ``"-"`` are silently ignored).
        output_format: Requested format name (e.g. ``"markdown"`` or ``"json"``).

    """
    if output is None or output == "-":
        return
    ext_format: dict[str, str] = {".html": "html", ".md": "markdown", ".json": "json"}
    output_ext = Path(output).suffix.lower()
    implied_format = ext_format.get(output_ext)
    if implied_format is not None and implied_format != output_format:
        click.echo(
            f"Warning: --output extension '{output_ext}' implies format '{implied_format}' "
            f"but --format is '{output_format}'. "
            "The file will be written in the requested format.",
            err=True,
        )


def _load_report_data(
    test_id: str,
    results: list[dict[str, Any]],
) -> ReportData:
    """Build a fully-populated ReportData from raw run results.

    Groups results by tier, calculates per-tier metrics (pass rate,
    implementation rate, cost-of-pass, etc.), sensitivity analysis,
    transition assessments, and recommendations.

    Args:
        test_id: Test identifier.
        results: List of result dictionaries (each from a result.json file).

    Returns:
        ReportData with tiers, sensitivity, transitions, and recommendations.

    Raises:
        ValueError: If *results* is empty.

    """
    if not results:
        raise ValueError(f"No results provided for test: {test_id}")

    # Group results by tier
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        tier_id = r["tier_id"]
        if tier_id not in by_tier:
            by_tier[tier_id] = []
        by_tier[tier_id].append(r)

    # Sort tiers
    sorted_tiers = sorted(by_tier.keys())

    # Calculate T0 pass rate for uplift calculations
    t0_pass_rate = None
    if "T0" in by_tier:
        t0_results = by_tier["T0"]
        t0_pass_rates = [r["grading"]["pass_rate"] for r in t0_results]
        t0_pass_rate = statistics.median(t0_pass_rates)

    # Calculate metrics for each tier
    tier_metrics = []
    for tid in sorted_tiers:
        metrics = _calculate_tier_metrics(tid, by_tier[tid], t0_pass_rate)
        tier_metrics.append(metrics)

    # Calculate sensitivity analysis if multiple tiers
    sensitivity = None
    if len(tier_metrics) > 1:
        pass_rates = [m.pass_rate_median for m in tier_metrics]
        impl_rates = [m.impl_rate_median for m in tier_metrics]
        costs = [
            m.cost_of_pass_median for m in tier_metrics if m.cost_of_pass_median != float("inf")
        ]

        sensitivity = SensitivityAnalysis(
            pass_rate_variance=statistics.variance(pass_rates) if len(pass_rates) > 1 else 0.0,
            impl_rate_variance=statistics.variance(impl_rates) if len(impl_rates) > 1 else 0.0,
            cost_variance=statistics.variance(costs) if len(costs) > 1 else 0.0,
        )

    # Calculate transitions
    transitions = []
    for i in range(len(tier_metrics) - 1):
        from_tier = tier_metrics[i]
        to_tier = tier_metrics[i + 1]

        pass_delta = to_tier.pass_rate_median - from_tier.pass_rate_median
        impl_delta = to_tier.impl_rate_median - from_tier.impl_rate_median
        cost_delta = to_tier.cost_of_pass_median - from_tier.cost_of_pass_median

        # Worth it if pass rate improves more than cost increases (relative)
        worth_it = pass_delta > 0 and (cost_delta < 0 or pass_delta > cost_delta)

        transitions.append(
            TransitionAssessment(
                from_tier=from_tier.tier_id,
                to_tier=to_tier.tier_id,
                pass_rate_delta=pass_delta,
                impl_rate_delta=impl_delta,
                cost_delta=cost_delta,
                worth_it=worth_it,
            )
        )

    # Determine runs per tier (from first tier's count)
    runs_per_tier = len(by_tier[sorted_tiers[0]]) if sorted_tiers else 0

    # Create report data
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return ReportData(
        test_id=test_id,
        test_name=test_id.replace("-", " ").title(),
        timestamp=timestamp,
        runs_per_tier=runs_per_tier,
        judge_model=DEFAULT_JUDGE_MODEL,
        tiers=tier_metrics,
        sensitivity=sensitivity,
        transitions=transitions,
        key_finding=f"Evaluated {len(results)} runs across {len(sorted_tiers)} tier(s).",
        recommendations=[
            "Review per-tier metrics to identify optimal configuration.",
            "Consider cost-of-pass when selecting production tier.",
        ],
    )


@cli.command()
@click.argument("test_id")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(sorted(FORMAT_GENERATORS.keys())),
    default="markdown",
    help="Report format (default: markdown).",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help=(
        "Output destination. Use '-' for stdout. "
        "Paths ending in '.md' or '.json' are written as exact files; "
        "any other path is treated as a directory and the filename is auto-generated."
    ),
)
def report(
    test_id: str,
    output_format: str,
    output: str | None,
) -> None:
    """Generate report for a completed test.

    TEST_ID is the identifier of the test (e.g., 001-justfile-to-makefile).

    Examples:
        scylla report 001-justfile-to-makefile

        scylla report 001-justfile-to-makefile --format json

        scylla report 001-justfile-to-makefile --format json --output -

    """
    stdout_mode = output == "-"
    _warn_format_extension_mismatch(output, output_format)
    click.echo(f"Generating {output_format} report for: {test_id}", err=stdout_mode)

    base_path = Path(".")
    results = _load_results(test_id, base_path)

    if not results:
        click.echo(f"\nNo results found for test: {test_id}", err=True)
        click.echo(f"Run 'scylla run {test_id}' first to generate results.", err=True)
        sys.exit(1)

    click.echo(f"  Found {len(results)} run results", err=stdout_mode)

    report_data = _load_report_data(test_id, results)

    # Log per-tier summary
    for tier in report_data.tiers:
        by_tier_count = sum(1 for r in results if r["tier_id"] == tier.tier_id)
        click.echo(
            f"  {tier.tier_id}: {by_tier_count} runs, pass rate: {tier.pass_rate_median:.1%}",
            err=stdout_mode,
        )

    # Generate report using dict-dispatch — single code path for all formats
    generator_cls = FORMAT_GENERATORS[output_format]
    if stdout_mode:
        generator = generator_cls(Path("."))
        content = generator.generate_report(report_data)
        click.echo(content)
    else:
        report_dir, resolved_output_path = _resolve_output_path(output, base_path)
        generator = generator_cls(report_dir)
        report_path = generator.write_report(report_data, output_path=resolved_output_path)
        click.echo(f"\nReport generated: {report_path}")


@cli.command("list")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed test information.",
)
def list_tests(verbose: bool) -> None:
    """List available test cases.

    Examples:
        scylla list

        scylla list --verbose

    """
    # Load from tests/fixtures/tests directory
    tests_dir = Path("tests/fixtures/tests")
    tests: list[tuple[str, str]] = []

    if tests_dir.exists():
        for test_path in sorted(tests_dir.iterdir()):
            if test_path.is_dir():
                test_yaml = test_path / "test.yaml"
                if test_yaml.exists():
                    import yaml

                    try:
                        with open(test_yaml) as f:
                            test_data = yaml.safe_load(f)
                        test_id = test_data.get("id", test_path.name)
                        description = test_data.get("name", "No description")
                        tests.append((test_id, description))
                    except Exception:
                        # Skip invalid test files
                        continue

    # Fallback to default list if no tests found (for backward compatibility)
    if not tests:
        tests = [
            ("001-justfile-to-makefile", "Convert Justfile to Makefile"),
        ]

    click.echo("Available tests:\n")

    for test_id, description in tests:
        if verbose:
            click.echo(f"  {test_id}")
            click.echo(f"    Description: {description}")
            click.echo()
        else:
            click.echo(f"  {test_id}: {description}")


@cli.command("list-tiers")
def list_tiers() -> None:
    """List available evaluation tiers.

    Examples:
        scylla list-tiers

    """
    tiers = [
        ("T0", "Prompts", "System prompt ablation (empty → full CLAUDE.md)"),
        ("T1", "Skills", "Domain expertise via installed skills by category"),
        ("T2", "Tooling", "External tools and MCP servers"),
        ("T3", "Delegation", "Flat multi-agent with specialist agents"),
        ("T4", "Hierarchy", "Nested orchestration with orchestrator agents"),
        ("T5", "Hybrid", "Best combinations and permutations"),
        ("T6", "Super", "Everything enabled at maximum capability"),
    ]

    click.echo("Evaluation tiers:\n")

    for tier_id, name, description in tiers:
        click.echo(f"  {tier_id} ({name})")
        click.echo(f"    {description}")
        click.echo()


@cli.command("list-models")
def list_models() -> None:
    """List configured models.

    Examples:
        scylla list-models

    """
    from scylla.config import ConfigurationError

    loader = ConfigLoader()

    try:
        models = loader.load_all_models()
    except ConfigurationError as e:
        click.echo(f"Error loading model configurations: {e}", err=True)
        sys.exit(1)

    if not models:
        click.echo("No model configurations found in config/models/")
        click.echo("\nCreate YAML files in config/models/ to add models.")
        return

    click.echo("Configured models:\n")

    for _model_key, model in models.items():
        # Calculate pricing display
        input_per_1m = model.cost_per_1k_input * 1000
        output_per_1m = model.cost_per_1k_output * 1000
        pricing = f"${input_per_1m:.2f}/${output_per_1m:.2f} per 1M tokens"

        click.echo(f"  {model.model_id}")
        if model.name:
            click.echo(f"    Name: {model.name}")
        if model.provider:
            click.echo(f"    Provider: {model.provider}")
        click.echo(f"    Pricing: {pricing}")
        click.echo()


@cli.group()
def audit() -> None:
    """Audit configuration files for consistency issues."""


@audit.command("models")
@click.option(
    "--config-dir",
    default=".",
    show_default=True,
    help="Project root directory (must contain config/models/).",
)
def audit_models(config_dir: str) -> None:
    """Audit model config files for filename/model_id mismatches.

    Exits non-zero if any mismatches are detected, making it suitable for
    use in pre-commit hooks or CI pipelines.

    Examples:
        scylla audit models

        scylla audit models --config-dir /path/to/project

    """
    from scylla.config.validation import validate_filename_model_id_consistency

    loader = ConfigLoader(Path(config_dir))
    models_dir = loader.base_path / "config" / "models"

    if not models_dir.exists():
        click.echo(f"ERROR: models directory not found: {models_dir}", err=True)
        sys.exit(1)

    mismatches: list[str] = []
    for config_path in sorted(models_dir.glob("*.yaml")):
        if config_path.stem.startswith("_"):
            continue
        try:
            model_config = loader.load_model(config_path.stem)
        except Exception:
            continue
        if model_config is None:
            continue
        warnings = validate_filename_model_id_consistency(config_path, model_config.model_id)
        for warning in warnings:
            mismatch_line = f"MISMATCH: {config_path.name} → {warning}"
            mismatches.append(mismatch_line)
            click.echo(mismatch_line)

    if mismatches:
        click.echo(f"\n{len(mismatches)} mismatch(es) detected.", err=True)
        sys.exit(1)
    else:
        click.echo("OK: all model config filenames match their model_id.")


@cli.command()
@click.argument("test_id")
def status(test_id: str) -> None:
    """Show status of a test evaluation.

    TEST_ID is the identifier of the test (e.g., 001-justfile-to-makefile).

    Examples:
        scylla status 001-justfile-to-makefile

    """
    click.echo(f"Status for: {test_id}\n")

    # Load from runs directory
    runs_dir = Path("runs")
    results: list[dict[str, Any]] = []

    if runs_dir.exists():
        # Find all result.json files for this test_id
        for result_file in runs_dir.glob(f"**/{test_id}/**/result.json"):
            try:
                with open(result_file) as f:
                    result_data = json.load(f)
                results.append(result_data)
            except Exception:
                # Skip invalid result files
                continue

    if not results:
        click.echo("  No results found.")
        click.echo(f"\n  Run 'scylla run {test_id}' to start evaluation.")
        return

    # Display summary by tier
    tiers: dict[str, dict[str, Any]] = {}
    for result in results:
        tier_id = result.get("tier_id", "unknown")
        if tier_id not in tiers:
            tiers[tier_id] = {"total": 0, "passed": 0, "costs": []}

        tiers[tier_id]["total"] += 1
        if result.get("judgment", {}).get("passed", False):
            tiers[tier_id]["passed"] += 1
        cost = result.get("metrics", {}).get("cost_usd", 0.0)
        tiers[tier_id]["costs"].append(cost)

    click.echo(f"  Total runs: {len(results)}\n")

    for tier_id in sorted(tiers.keys()):
        tier_data = tiers[tier_id]
        pass_rate = tier_data["passed"] / tier_data["total"] if tier_data["total"] > 0 else 0.0
        avg_cost = statistics.mean(tier_data["costs"]) if tier_data["costs"] else 0.0

        click.echo(f"  {tier_id}:")
        click.echo(f"    Runs: {tier_data['total']}")
        click.echo(f"    Pass Rate: {pass_rate:.1%}")
        click.echo(f"    Avg Cost: ${avg_cost:.3f}")
        click.echo()


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
