"""Judge runner CLI module.

This module provides a command-line interface for running judge evaluations
in containerized environments. It's designed to be invoked as:

    python -m scylla.judge.runner --workspace <path> --output <path> --model <id> --prompt <path>

The runner reads the task prompt, evaluates the workspace, and writes the
judgment output to the specified output directory.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from scylla.config.constants import DEFAULT_JUDGE_MODEL
from scylla.judge.evaluator import (
    Judgment,
)

logger = logging.getLogger(__name__)


class RunnerError(Exception):
    """Base exception for runner errors."""

    pass


class RunnerValidationError(RunnerError):
    """Raised when validation of arguments fails."""

    pass


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.

    """
    parser = argparse.ArgumentParser(
        description="Judge runner for containerized evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Path to workspace directory to evaluate (read-only)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output directory for results",
    )

    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help=f"Model ID to use for evaluation (default: {DEFAULT_JUDGE_MODEL})",
    )

    parser.add_argument(
        "--prompt",
        type=Path,
        required=True,
        help="Path to task prompt file",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout for evaluation in seconds (default: 300)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """Validate command-line arguments.

    Args:
        args: Parsed arguments.

    Raises:
        RunnerValidationError: If validation fails.

    """
    # Validate workspace exists
    if not args.workspace.exists():
        raise RunnerValidationError(f"Workspace does not exist: {args.workspace}")

    if not args.workspace.is_dir():
        raise RunnerValidationError(f"Workspace is not a directory: {args.workspace}")

    # Validate prompt file exists
    if not args.prompt.exists():
        raise RunnerValidationError(f"Prompt file does not exist: {args.prompt}")

    if not args.prompt.is_file():
        raise RunnerValidationError(f"Prompt is not a file: {args.prompt}")

    # Validate output directory or create it
    if not args.output.exists():
        try:
            args.output.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RunnerValidationError(f"Failed to create output directory: {e}") from e

    if not args.output.is_dir():
        raise RunnerValidationError(f"Output is not a directory: {args.output}")

    # Validate timeout
    if args.timeout <= 0:
        raise RunnerValidationError(f"Timeout must be positive: {args.timeout}")


def load_task_prompt(prompt_file: Path) -> str:
    """Load task prompt from file.

    Args:
        prompt_file: Path to prompt file.

    Returns:
        Task prompt content.

    Raises:
        RunnerError: If loading fails.

    """
    try:
        return prompt_file.read_text()
    except OSError as e:
        raise RunnerError(f"Failed to load prompt file: {e}") from e


def collect_workspace_state(workspace: Path) -> str:
    """Collect workspace state for evaluation context.

    Args:
        workspace: Path to workspace directory.

    Returns:
        Human-readable summary of workspace contents.

    """
    # List files in workspace (non-recursive for now)
    files = []
    try:
        for item in sorted(workspace.iterdir()):
            if item.is_file():
                files.append(f"- {item.name}")
            elif item.is_dir():
                files.append(f"- {item.name}/ (directory)")
    except OSError as e:
        logger.warning(f"Failed to list workspace contents: {e}")
        return f"Error listing workspace: {e}"

    if not files:
        return "Workspace is empty"

    return "Workspace contents:\n" + "\n".join(files)


def run_evaluation(
    workspace: Path,
    prompt: str,
    model: str,
    timeout: int,
) -> Judgment:
    """Run judge evaluation.

    Args:
        workspace: Path to workspace to evaluate.
        prompt: Task prompt.
        model: Model ID to use.
        timeout: Timeout in seconds.

    Returns:
        Judgment from evaluation.

    Raises:
        RunnerError: If evaluation fails.

    """
    # Note: Current implementation uses placeholder judgments suitable for containerized
    # environments. Full adapter integration deferred until requirements are clarified.
    # Model and timeout parameters reserved for future adapter integration.

    # Collect workspace state
    workspace_state = collect_workspace_state(workspace)

    # Create a basic judgment for now
    # This is a placeholder implementation
    logger.warning("Using placeholder judgment - full adapter integration not yet implemented")

    judgment = Judgment()
    judgment.qualitative_feedback = (
        f"Workspace evaluated with model {model}. "
        f"Task: {prompt[:100]}... "
        f"State: {workspace_state[:100]}..."
    )

    return judgment


def write_output(judgment: Judgment, output_dir: Path) -> None:
    """Write judgment to output directory.

    Args:
        judgment: Judgment to write.
        output_dir: Output directory.

    Raises:
        RunnerError: If writing fails.

    """
    try:
        # Write judgment as JSON
        output_file = output_dir / "judgment.json"

        # Convert judgment to dict
        judgment_dict: dict[str, Any] = {
            "requirements": {
                req_id: {
                    "score": score.score,
                    "confidence": score.confidence,
                    "notes": score.notes,
                }
                for req_id, score in judgment.requirements.items()
            },
            "categories": {
                cat_name: {
                    "score": score.score,
                    "confidence": score.confidence,
                    "notes": score.notes,
                }
                for cat_name, score in judgment.categories.items()
            },
            "summary": (
                {
                    "weighted_score": judgment.summary.weighted_score,
                    "passed": judgment.summary.passed,
                    "letter_grade": judgment.summary.letter_grade,
                    "overall_confidence": judgment.summary.overall_confidence,
                    "strengths": judgment.summary.strengths,
                    "weaknesses": judgment.summary.weaknesses,
                }
                if judgment.summary
                else None
            ),
            "exploratory_testing": (
                {
                    "commands_run": judgment.exploratory_testing.commands_run,
                    "observations": judgment.exploratory_testing.observations,
                    "failures": judgment.exploratory_testing.failures,
                }
                if judgment.exploratory_testing
                else None
            ),
            "qualitative_feedback": judgment.qualitative_feedback,
        }

        output_file.write_text(json.dumps(judgment_dict, indent=2))
        logger.info(f"Judgment written to {output_file}")

    except (OSError, TypeError, ValueError) as e:
        raise RunnerError(f"Failed to write output: {e}") from e


def main() -> int:
    """Execute judge runner.

    Returns:
        Exit code (0 for success, 1 for error).

    """
    # Parse arguments
    try:
        args = parse_args()
    except SystemExit:
        return 1

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Judge runner starting")
    logger.info(f"Workspace: {args.workspace}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Prompt: {args.prompt}")

    try:
        # Validate arguments
        validate_arguments(args)

        # Load task prompt
        prompt = load_task_prompt(args.prompt)
        logger.info(f"Loaded prompt ({len(prompt)} chars)")

        # Run evaluation
        judgment = run_evaluation(
            workspace=args.workspace,
            prompt=prompt,
            model=args.model,
            timeout=args.timeout,
        )

        # Write output
        write_output(judgment, args.output)

        logger.info("Judge evaluation completed successfully")
        return 0

    except RunnerError as e:
        logger.error(f"Runner error: {e}")
        return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
