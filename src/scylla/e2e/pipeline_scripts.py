"""Pipeline script creation and output saving for E2E evaluation.

This module handles creating reproducible bash scripts for build/lint/test
pipelines and saving their outputs and judge logs to disk.

Extracted from llm_judge.py to isolate I/O and script generation concerns.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scylla.e2e.llm_judge_models import BuildPipelineResult, JudgeResult
from scylla.e2e.template_loader import write_script

logger = logging.getLogger(__name__)


def _create_python_scripts(commands_dir: Path, workspace: Path) -> None:
    """Create Python build/lint/test scripts using templates.

    Args:
        commands_dir: Directory to create scripts in
        workspace: Path to the workspace directory

    """
    write_script(
        commands_dir / "python_check.sh",
        "python_check.sh.template",
        workspace=str(workspace),
    )
    write_script(
        commands_dir / "python_format.sh",
        "python_format.sh.template",
        workspace=str(workspace),
    )
    write_script(
        commands_dir / "python_test.sh",
        "python_test.sh.template",
        workspace=str(workspace),
    )


def _create_mojo_build_script(build_script: Path, workspace: Path, is_modular: bool) -> None:
    """Create Mojo build script using templates.

    Args:
        build_script: Path to the build script to create
        workspace: Path to the workspace directory
        is_modular: Whether this is a modular repo

    """
    template_name = "mojo_build_modular.sh.template" if is_modular else "mojo_build.sh.template"
    write_script(build_script, template_name, workspace=str(workspace))


def _create_mojo_format_script(format_script: Path, workspace: Path, is_modular: bool) -> None:
    """Create Mojo format check script using templates.

    Args:
        format_script: Path to the format script to create
        workspace: Path to the workspace directory
        is_modular: Whether this is a modular repo

    """
    if is_modular:
        template_name = "mojo_format_modular.sh.template"
    elif (workspace / "mojo").is_dir():
        template_name = "mojo_format_standalone_subdir.sh.template"
    else:
        template_name = "mojo_format.sh.template"

    write_script(format_script, template_name, workspace=str(workspace))


def _create_mojo_test_script(test_script: Path, workspace: Path, is_modular: bool) -> None:
    """Create Mojo test script using templates.

    Args:
        test_script: Path to the test script to create
        workspace: Path to the workspace directory
        is_modular: Whether this is a modular repo

    """
    template_name = "mojo_test_modular.sh.template" if is_modular else "mojo_test.sh.template"
    write_script(test_script, template_name, workspace=str(workspace))


def _create_mojo_scripts(commands_dir: Path, workspace: Path) -> None:
    """Create Mojo build/lint/test scripts.

    Args:
        commands_dir: Directory to create scripts in
        workspace: Path to the workspace directory

    """
    from scylla.e2e.build_pipeline import _is_modular_repo

    is_modular = _is_modular_repo(workspace)

    build_script = commands_dir / "mojo_build.sh"
    _create_mojo_build_script(build_script, workspace, is_modular)

    format_script = commands_dir / "mojo_format.sh"
    _create_mojo_format_script(format_script, workspace, is_modular)

    test_script = commands_dir / "mojo_test.sh"
    _create_mojo_test_script(test_script, workspace, is_modular)


def _create_precommit_script(commands_dir: Path, workspace: Path) -> None:
    """Create pre-commit hooks script using template.

    Args:
        commands_dir: Directory to create script in
        workspace: Path to the workspace directory

    """
    write_script(
        commands_dir / "precommit.sh",
        "precommit.sh.template",
        workspace=str(workspace),
    )


def _create_run_all_script(commands_dir: Path, language: str) -> None:
    """Create run_all.sh script that executes all tools using template.

    Args:
        commands_dir: Directory to create script in
        language: Programming language ("python" or "mojo")

    """
    template_name = f"run_all_{language}.sh.template"
    write_script(commands_dir / "run_all.sh", template_name)


def _save_pipeline_commands(run_dir: Path, workspace: Path, language: str = "python") -> None:
    """Save all build/lint/test commands as reproducible bash scripts.

    Creates individual scripts for each tool in run_dir/commands/ directory,
    plus a run_all.sh script that executes all tools in sequence.
    Called once per run (not per judge) since results are identical.

    Detects if workspace is modular/mojo monorepo and generates appropriate commands.

    Args:
        run_dir: Run directory (e.g., run_01/)
        workspace: Path to the workspace directory
        language: Programming language ("python" or "mojo")

    """
    commands_dir = run_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    # Create language-specific scripts
    if language == "python":
        _create_python_scripts(commands_dir, workspace)
    else:
        _create_mojo_scripts(commands_dir, workspace)

    # Create shared scripts
    _create_precommit_script(commands_dir, workspace)
    _create_run_all_script(commands_dir, language)


def _save_pipeline_outputs(
    run_dir: Path, result: BuildPipelineResult, language: str = "python"
) -> None:
    """Save outputs from each pipeline step for debugging.

    Args:
        run_dir: Run directory containing commands/ subdirectory
        result: BuildPipelineResult with outputs from each step
        language: Programming language ("python" or "mojo")

    """
    commands_dir = run_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    prefix = "mojo" if language != "python" else "python"

    # Save each step's output (combined stdout/stderr as stored in BuildPipelineResult)
    if result.build_output:
        (commands_dir / f"{prefix}_build_output.log").write_text(result.build_output)
    if result.format_output:
        (commands_dir / f"{prefix}_format_output.log").write_text(result.format_output)
    if result.test_output:
        (commands_dir / f"{prefix}_test_output.log").write_text(result.test_output)
    if result.precommit_output:
        (commands_dir / "precommit_output.log").write_text(result.precommit_output)


def _save_judge_logs(
    judge_dir: Path,
    prompt: str,
    response: str,
    result: JudgeResult,
    model: str,
    workspace: Path | None = None,
    raw_stdout: str = "",
    raw_stderr: str = "",
    language: str = "python",
) -> None:
    """Save judge evaluation logs and generate replay script.

    Args:
        judge_dir: Directory for judge outputs
        prompt: The judge prompt
        response: Raw LLM response
        result: Parsed judge result
        model: Model used for judging
        workspace: Path to the workspace directory (for saving pipeline commands)
        raw_stdout: Raw stdout from subprocess (optional)
        raw_stderr: Raw stderr from subprocess (optional)
        language: Programming language ("python" or "mojo")

    """
    judge_dir.mkdir(parents=True, exist_ok=True)

    # Save the prompt to run level (shared by all judges) - write once
    # The prompt is at run_dir/judge_prompt.md, not inside judge/ subdir
    # judge_dir is e.g. run_01/judge/judge_01/, so go up 2 levels to get run_dir
    run_dir = judge_dir.parent.parent
    judge_prompt_path = run_dir / "judge_prompt.md"
    if not judge_prompt_path.exists():
        judge_prompt_path.write_text(prompt)

    # Save raw response
    (judge_dir / "response.txt").write_text(response)

    # Save raw subprocess output (NEW)
    if raw_stdout:
        (judge_dir / "stdout.log").write_text(raw_stdout)
    if raw_stderr:
        (judge_dir / "stderr.log").write_text(raw_stderr)

    # Save structured result (keep as judgment.json for compatibility)
    with open(judge_dir / "judgment.json", "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    # Create MODEL.md with judge model information
    try:
        # Try to get claude-code version
        claude_version_result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        claude_code_version = (
            claude_version_result.stdout.strip()
            if claude_version_result.returncode == 0
            else "unknown"
        )

        model_info = f"""# Judge Model Information

**Model**: {model}
**Claude Code Version**: {claude_code_version}
**Timestamp**: {datetime.now(timezone.utc).isoformat()}
"""
        (judge_dir / "MODEL.md").write_text(model_info)
    except OSError as e:
        logger.warning(f"Failed to create MODEL.md: {e}")

    # Generate replay script for re-running judge
    replay_script = judge_dir / "replay.sh"
    replay_content = f"""#!/usr/bin/env bash
# Replay judge evaluation
# Generated by Scylla E2E test framework

set -euo pipefail

JUDGE_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# Re-run Claude CLI with the same prompt and model (shared judge_prompt.md at run level)
claude \\
  --model {model} \\
  --prompt "$JUDGE_DIR/../../judge_prompt.md" \\
  > "$JUDGE_DIR/response.txt"

echo "Judge response saved to $JUDGE_DIR/response.txt"
"""
    replay_script.write_text(replay_content)
    replay_script.chmod(0o755)

    # NOTE: Pipeline commands (run_all.sh) are now saved once per run by the caller,
    # not per judge, to avoid duplication
