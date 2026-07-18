#!/usr/bin/env python3
"""Master script to generate all analysis outputs.

Runs data export, figure generation, and table generation in sequence.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scylla.utils.terminal import terminal_guard


def run_script(script_name: str, args: list[str], description: str) -> bool:
    """Run a script and return success status.

    Args:
        script_name: Name of the script to run
        args: Command-line arguments for the script
        description: Human-readable description

    Returns:
        True if successful, False otherwise

    """
    print(f"\n{'=' * 70}")
    print(f"{description}")
    print(f"{'=' * 70}\n")

    cmd = ["uv", "run", "python", script_name, *args]

    try:
        result = subprocess.run(cmd, check=False, stdin=subprocess.DEVNULL)  # Don't raise on error
        if result.returncode != 0:
            print(f"\nERROR: {script_name} failed with return code {result.returncode}")
        return result.returncode == 0
    except Exception as e:
        print(f"\nERROR: {script_name} failed with exception: {e}")
        return False


def main() -> None:
    """Run the complete analysis pipeline."""
    parser = argparse.ArgumentParser(
        description="Generate all analysis outputs (data + figures + tables)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path.home() / "fullruns",
        help="Root of fullruns/ (default: ~/fullruns)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs"),
        help="Base output directory (default: docs/)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip rendering figures to PNG/PDF",
    )
    parser.add_argument(
        "--skip-data",
        action="store_true",
        help="Skip data export (assume CSVs already exist)",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip figure generation",
    )
    parser.add_argument(
        "--skip-tables",
        action="store_true",
        help="Skip table generation",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="*",
        default=[],
        help="Experiment names to exclude (e.g., --exclude test001-dryrun)",
    )

    args = parser.parse_args()

    with terminal_guard():
        success = True

        # Build common exclude args
        exclude_args = []
        if args.exclude:
            exclude_args.extend(["--exclude", *args.exclude])

        # Step 1: Export data
        if not args.skip_data:
            export_args = [
                "--data-dir",
                str(args.data_dir),
                "--output-dir",
                str(args.output_dir / "data"),
                *exclude_args,
            ]
            if not run_script(
                "scripts/export_data.py",
                export_args,
                "Step 1/3: Exporting experiment data to CSV",
            ):
                success = False

        # Step 2: Generate figures
        if not args.skip_figures and success:
            figure_args = [
                "--data-dir",
                str(args.data_dir),
                "--output-dir",
                str(args.output_dir / "figures"),
                *exclude_args,
            ]
            if args.no_render:
                figure_args.append("--no-render")

            if not run_script(
                "scripts/generate_figures.py",
                figure_args,
                "Step 2/3: Generating figures (Vega-Lite specs + CSV)",
            ):
                success = False

        # Step 3: Generate tables
        if not args.skip_tables and success:
            table_args = [
                "--data-dir",
                str(args.data_dir),
                "--output-dir",
                str(args.output_dir / "tables"),
                *exclude_args,
            ]
            if not run_script(
                "scripts/generate_tables.py",
                table_args,
                "Step 3/3: Generating statistical tables (Markdown + LaTeX)",
            ):
                success = False

        # Summary
        print(f"\n{'=' * 70}")
        if success:
            print("✓ All analysis outputs generated successfully!")
            print("\nOutputs:")
            print(f"  Data:    {args.output_dir / 'data'}/*.csv")
            print(f"           {args.output_dir / 'data'}/summary.json")
            print(f"           {args.output_dir / 'data'}/statistical_results.json")
            print(f"  Figures: {args.output_dir / 'figures'}/*.{{png,pdf,vl.json,csv}}")
            print(f"           {args.output_dir / 'figures'}/*_include.tex (LaTeX snippets)")
            print(f"  Tables:  {args.output_dir / 'tables'}/*.{{md,tex}}")
            print("\nNext steps:")
            print(f"  - View figures: open {args.output_dir / 'figures'}/*.png")
            print(f"  - Include in LaTeX: \\input{{{args.output_dir / 'figures'}/*_include.tex}}")
            print(f"  - View tables: {args.output_dir / 'tables'}/*.md")
            print(f"  - Use data: {args.output_dir / 'data'}/*.csv")
            print(f"  - Statistical analysis: {args.output_dir / 'data'}/statistical_results.json")
        else:
            print("✗ Some steps failed. Check output above for errors.")
            sys.exit(1)


if __name__ == "__main__":
    main()
