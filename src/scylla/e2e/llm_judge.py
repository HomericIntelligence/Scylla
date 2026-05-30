"""LLM-based judge for evaluating E2E task completion.

This module provides LLM-based evaluation of agent task completion,
using structured prompts and rubrics for consistent scoring.

Build pipeline execution is in build_pipeline.py.
Script creation and log saving is in pipeline_scripts.py.
Data models are in llm_judge_models.py.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from hephaestus.resilience.circuit_breaker import get_circuit_breaker

from scylla.config.constants import DEFAULT_JUDGE_MODEL
from scylla.e2e.build_pipeline import _format_pipeline_result, _run_and_log_pipeline
from scylla.e2e.filters import is_test_config_file
from scylla.e2e.llm_judge_models import BuildPipelineResult, JudgeResult, _score_to_grade
from scylla.e2e.pipeline_scripts import _save_judge_logs
from scylla.judge import extract_json_from_llm_response
from scylla.judge.prompts import JUDGE_SYSTEM_PROMPT_FILE, build_task_prompt

logger = logging.getLogger(__name__)


# Note: _build_judge_prompt() has been moved to scylla.judge.prompts.build_task_prompt()
# This module now imports and uses that consolidated implementation.


_GIT_STATUS_LABELS: dict[str, str] = {
    "M": "modified",
    "A": "added",
    "??": "created",
    "D": "deleted",
}


def _parse_git_status_line(line: str) -> tuple[str, str]:
    """Parse a single git status --porcelain output line.

    Args:
        line: A single porcelain status line

    Returns:
        Tuple of (status_code, file_path)

    """
    status = line[:2].strip()
    # Git porcelain format: XY filename (2 status chars + space + path)
    if len(line) > 3 and line[2] == " ":
        file_path = line[3:].strip()
    elif " " in line:
        file_path = line.split(" ", 1)[1].strip() if " " in line[1:] else ""
    else:
        file_path = ""
    return status, file_path


def _expand_untracked_dir(workspace: Path, full_path: Path, lines: list[str]) -> None:
    """Expand an untracked directory into individual file entries.

    Args:
        workspace: Root workspace path for computing relative paths
        full_path: Absolute path to the untracked directory
        lines: List to append formatted entries to

    """
    for child in sorted(full_path.rglob("*")):
        if child.is_file():
            rel_path = child.relative_to(workspace)
            if not is_test_config_file(str(rel_path)):
                lines.append(f"- `{rel_path}` (created)")


def _get_workspace_state(workspace: Path) -> str:
    """Get a description of modified/created files in the workspace.

    Only lists files that were modified or created by the agent (using git status),
    not their full contents. The patchfile section already shows the actual changes.

    Excludes test configuration files (CLAUDE.md, .claude/) that are set up by
    the test framework, not by the agent being evaluated.

    For untracked directories, recursively lists all files inside to give judge
    visibility into directory contents.

    Args:
        workspace: Path to the workspace directory

    Returns:
        String listing modified/created file paths.

    """
    try:
        # Get modified, added, and untracked files using git status
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return "(unable to get workspace state)"

        lines = ["Files modified/created by agent:"]

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            status, file_path = _parse_git_status_line(line)

            if is_test_config_file(file_path):
                continue

            full_path = workspace / file_path

            if status == "??" and full_path.is_dir():
                _expand_untracked_dir(workspace, full_path, lines)
            else:
                label = _GIT_STATUS_LABELS.get(status, status)
                lines.append(f"- `{file_path}` ({label})")

        if len(lines) == 1:
            lines.append("(no changes detected)")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "(git status timed out)"
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Error getting workspace state: {e}")
        return f"(error getting workspace state: {e})"


def _get_committed_diff(workspace: Path) -> str | None:
    """Get diff of the most recent commit (fallback when no staged/unstaged changes).

    Used when the agent committed its changes via stage_commit_agent_changes.

    Args:
        workspace: Path to the workspace directory.

    Returns:
        Diff string if the last commit has changes, None otherwise.

    """
    result = subprocess.run(
        ["git", "diff", "HEAD~1..HEAD", "--", ".", ":(exclude)CLAUDE.md", ":(exclude).claude"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0 and result.stdout.strip():
        return "## Committed Changes\n" + result.stdout.strip()
    return None


def _collect_diff_sections(workspace: Path) -> list[str] | None:
    """Collect diff sections from staged, unstaged, and committed changes.

    Returns list of diff section strings, None if git diff failed entirely.

    Args:
        workspace: Path to the workspace directory.

    """
    exclude_args = [":(exclude)CLAUDE.md", ":(exclude).claude"]
    unstaged = subprocess.run(
        ["git", "diff", "--", ".", *exclude_args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--", ".", *exclude_args],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if unstaged.returncode != 0 and staged.returncode != 0:
        logger.warning("git diff failed")
        return None

    sections: list[str] = []
    if unstaged.stdout.strip():
        sections.append("## Unstaged Changes\n" + unstaged.stdout.strip())
    if staged.stdout.strip():
        sections.append("## Staged Changes\n" + staged.stdout.strip())
    if not sections:
        committed = _get_committed_diff(workspace)
        if committed:
            sections.append(committed)
    return sections


def _get_patchfile(workspace: Path) -> str:
    """Generate a patchfile from the agent's changes.

    Uses git diff to capture all changes made by the agent, including both
    staged and unstaged changes. Excludes test configuration files (CLAUDE.md,
    .claude/) that are managed by the test framework.

    Args:
        workspace: Path to the workspace directory

    Returns:
        String containing the git diff output.

    """
    if not workspace.exists():
        return "(workspace not found — worktree may have been cleaned)"

    try:
        sections = _collect_diff_sections(workspace)
        if sections is None:
            return "(unable to generate patchfile)"
        if not sections:
            return "(no changes detected)"

        diff = "\n\n".join(sections)

        # Truncate if too long (keep first and last portions)
        max_lines = 500
        lines = diff.split("\n")
        if len(lines) > max_lines:
            half = max_lines // 2
            truncated = [*lines[:half], "", "... (truncated)", "", *lines[-half:]]
            return "\n".join(truncated)

        return diff

    except subprocess.TimeoutExpired:
        return "(git diff timed out)"
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Error generating patchfile: {e}")
        return f"(error generating patchfile: {e})"


def _get_deleted_files(workspace: Path) -> list[str]:
    """Get list of files deleted by the agent.

    Args:
        workspace: Path to the workspace directory

    Returns:
        List of deleted file paths.

    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=D", "HEAD"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return []

        deleted = result.stdout.strip().split("\n")
        return [f for f in deleted if f]

    except (subprocess.SubprocessError, OSError):
        return []


def _load_reference_patch(reference_path: Path) -> str | None:
    """Load a reference patch file for comparison.

    Args:
        reference_path: Path to the reference patch file

    Returns:
        Contents of the reference patch, or None if not found.

    """
    if not reference_path.exists():
        return None

    try:
        return reference_path.read_text()
    except OSError as e:
        logger.warning(f"Error loading reference patch: {e}")
        return None


def _gather_judge_context(
    workspace: Path,
    task_prompt: str,
    agent_output: str,
    include_patchfile: bool,
    reference_patch_path: Path | None,
    rubric_path: Path | None,
    run_build_pipeline: bool,
    language: str,
    pipeline_baseline: BuildPipelineResult | None,
    judge_dir: Path | None,
) -> tuple[str, BuildPipelineResult | None]:
    """Gather all context needed for the judge prompt.

    Collects workspace state, patchfile, reference patch, rubric, and pipeline
    results, then builds the judge prompt string.

    Args:
        workspace: Path to the workspace with agent's output
        task_prompt: The original task prompt
        agent_output: The agent's stdout output
        include_patchfile: Whether to include git diff in evaluation context
        reference_patch_path: Optional path to reference solution patch
        rubric_path: Optional path to rubric YAML file
        run_build_pipeline: Whether to run build/lint/test pipeline
        language: Programming language for pipeline selection
        pipeline_baseline: Optional baseline pipeline result
        judge_dir: Directory for pipeline output saving

    Returns:
        Tuple of (judge_prompt, pipeline_result)

    """
    workspace_state = _get_workspace_state(workspace)

    patchfile = None
    deleted_files = None
    if include_patchfile:
        patchfile = _get_patchfile(workspace)
        deleted_files = _get_deleted_files(workspace)

    reference_patch = None
    if reference_patch_path:
        reference_patch = _load_reference_patch(reference_patch_path)

    rubric_content = None
    if rubric_path and rubric_path.exists():
        try:
            rubric_content = rubric_path.read_text()
            logger.debug(f"Loaded rubric from {rubric_path}")
        except OSError as e:
            logger.warning(f"Failed to load rubric from {rubric_path}: {e}")

    pipeline_result = None
    if run_build_pipeline:
        pipeline_result = _run_and_log_pipeline(workspace, language, judge_dir)

    pipeline_result_str = _format_pipeline_result(pipeline_result)
    baseline_pipeline_str = _format_pipeline_result(pipeline_baseline)

    judge_prompt = build_task_prompt(
        task_prompt=task_prompt,
        agent_output=agent_output,
        workspace_state=workspace_state,
        patchfile=patchfile,
        deleted_files=deleted_files,
        reference_patch=reference_patch,
        pipeline_result_str=pipeline_result_str,
        rubric_content=rubric_content,
        baseline_pipeline_str=baseline_pipeline_str,
    )

    return judge_prompt, pipeline_result


def _execute_judge_with_retry(
    judge_prompt: str,
    model: str,
    workspace: Path,
    actual_judge_dir: Path | None,
    judge_start: float,
    language: str,
) -> JudgeResult:
    """Execute the judge with retry logic and save logs.

    Retries up to 3 times on JSON parse failure, appending a JSON reminder
    on each retry. Saves logs and timing if actual_judge_dir is provided.

    Args:
        judge_prompt: The fully constructed judge prompt
        model: Model to use for judging
        workspace: Path to the workspace
        actual_judge_dir: Directory to save judge logs (or None)
        judge_start: Start time for timing measurement
        language: Programming language (for log saving)

    Returns:
        JudgeResult from the judge

    Raises:
        ValueError: If judge response cannot be parsed after all retries
        RuntimeError: If retry loop exhausted without recording an error

    """
    _max_judge_attempts = 3
    _json_reminder = (
        "\n\n**IMPORTANT**: Your response MUST be a valid JSON object only. "
        "Do not include any text, explanation, or markdown before or after the JSON. "
        "Start your response with `{` and end with `}`."
    )
    last_parse_error: Exception | None = None
    stdout = stderr = result = ""
    for _attempt in range(_max_judge_attempts):
        _prompt = judge_prompt if _attempt == 0 else judge_prompt + _json_reminder
        if _attempt > 0:
            logger.warning(
                f"Judge parse failure on attempt {_attempt}/{_max_judge_attempts - 1}, retrying "
                f"with JSON reminder (model={model})"
            )
        stdout, stderr, result = _call_claude_judge(_prompt, model, workspace)
        try:
            judge_result = _parse_judge_response(result)
            break
        except ValueError as e:
            last_parse_error = e
    else:
        if last_parse_error is None:
            raise RuntimeError("Judge retry loop exhausted but last_parse_error is None")
        raise last_parse_error

    if actual_judge_dir:
        _save_judge_logs(
            actual_judge_dir,
            judge_prompt,
            result,
            judge_result,
            model,
            workspace,
            raw_stdout=stdout,
            raw_stderr=stderr,
            language=language,
        )

        judge_duration = time.time() - judge_start
        timing_file = actual_judge_dir / "timing.json"
        with open(timing_file, "w") as f:
            json.dump(
                {
                    "judge_duration_seconds": judge_duration,
                    "measured_at": _get_utc_now().isoformat(),
                },
                f,
                indent=2,
            )

    return judge_result


def run_llm_judge(
    workspace: Path,
    task_prompt: str,
    agent_output: str,
    model: str = DEFAULT_JUDGE_MODEL,  # REQUIRED: Must use Opus for accurate judging
    judge_dir: Path | None = None,
    reference_patch_path: Path | None = None,
    rubric_path: Path | None = None,
    include_patchfile: bool = True,
    run_build_pipeline: bool = True,
    judge_run_number: int = 1,
    language: str = "python",
    pipeline_baseline: BuildPipelineResult | None = None,
) -> JudgeResult:
    """Run LLM judge evaluation on agent's work.

    IMPORTANT: The judge model MUST be claude-opus-4-6.
    Opus provides the most accurate and consistent evaluations.
    Do NOT use Sonnet or Haiku - quality matters more than speed for judging.

    Uses the Claude CLI to evaluate task completion with an LLM judge.

    Raises ValueError if the judge response cannot be parsed.

    Args:
        workspace: Path to the workspace with agent's output
        task_prompt: The original task prompt
        agent_output: The agent's stdout output
        model: Model to use for judging (must be Opus for accurate judging)
        judge_dir: Directory for judge outputs (prompt.md, response.txt, judgment.json, replay.sh)
        reference_patch_path: Optional path to reference solution patch for comparison
        rubric_path: Optional path to rubric YAML file with checklist items
        include_patchfile: Whether to include git diff in evaluation context
        run_build_pipeline: Whether to run build/lint/test pipeline (default True)
        judge_run_number: Judge run number for creating judge_{N}/ subdirectory (default 1)
        language: Programming language ("python" or "mojo") for pipeline selection (default "mojo")
        pipeline_baseline: Optional baseline pipeline result from before agent execution

    Returns:
        JudgeResult with evaluation details.

    """
    judge_start = time.time()

    judge_prompt, _pipeline_result = _gather_judge_context(
        workspace=workspace,
        task_prompt=task_prompt,
        agent_output=agent_output,
        include_patchfile=include_patchfile,
        reference_patch_path=reference_patch_path,
        rubric_path=rubric_path,
        run_build_pipeline=run_build_pipeline,
        language=language,
        pipeline_baseline=pipeline_baseline,
        judge_dir=judge_dir,
    )

    actual_judge_dir = None
    if judge_dir:
        actual_judge_dir = judge_dir / f"judge_{judge_run_number:02d}"
        actual_judge_dir.mkdir(parents=True, exist_ok=True)

    # Save judge_prompt.md early so it's available for reruns
    # even if _call_claude_judge() fails with an exception
    if actual_judge_dir:
        run_dir = actual_judge_dir.parent.parent
        judge_prompt_path = run_dir / "judge_prompt.md"
        if not judge_prompt_path.exists():
            judge_prompt_path.write_text(judge_prompt)

    return _execute_judge_with_retry(
        judge_prompt=judge_prompt,
        model=model,
        workspace=workspace,
        actual_judge_dir=actual_judge_dir,
        judge_start=judge_start,
        language=language,
    )


def _extract_response_from_stream(stream_output: str) -> str:
    """Extract assistant response text from stream-json output.

    Parses newline-delimited JSON events and concatenates text blocks
    from type:assistant message events. Falls back to the result field
    if populated (for forward compatibility when CLI bug is fixed).

    Args:
        stream_output: Raw stream-json output from Claude CLI

    Returns:
        Extracted response text

    """
    text_parts: list[str] = []
    result_text = ""

    for line in stream_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") == "assistant":
            message = event.get("message", {})
            for block in message.get("content", []):
                if block.get("type") == "text":
                    text_parts.append(block["text"])
        elif event.get("type") == "result":
            result_text = event.get("result", "")

    # Prefer result field if populated (CLI bug is fixed)
    if result_text.strip():
        return result_text

    return "".join(text_parts)


def _raise_if_rate_limit(stdout: str, stderr: str) -> None:
    """Raise RateLimitError if stdout/stderr contain rate limit indicators.

    Handles both single-object JSON (``--output-format json``) and
    stream-json (``--output-format stream-json``) stdout formats.
    """
    from scylla.e2e.rate_limit import RateLimitError, detect_rate_limit

    rate_limit_info = detect_rate_limit(stdout, stderr, source="judge")
    if rate_limit_info:
        raise RateLimitError(rate_limit_info)


def _raise_if_rate_limit_in_error(error_msg: str) -> None:
    """Raise RateLimitError if the extracted error message matches rate limit patterns.

    Handles the case where detect_rate_limit misses stream-json format but the
    error message was successfully extracted from individual JSON lines.
    """
    if error_msg == "No error message":
        return
    from datetime import datetime
    from datetime import timezone as tz

    from scylla.e2e.rate_limit import (
        RateLimitError,
        RateLimitInfo,
        _detect_rate_limit_from_stderr,
    )

    rl_msg, rl_retry = _detect_rate_limit_from_stderr(error_msg)
    if rl_msg:
        raise RateLimitError(
            RateLimitInfo(
                source="judge",
                retry_after_seconds=rl_retry,
                error_message=error_msg,
                detected_at=datetime.now(tz.utc).isoformat(),
            )
        )


def _extract_cli_error(stdout: str, stderr: str) -> str:
    """Extract error message from Claude CLI output (JSON stdout or stderr)."""
    error_msg = "No error message"
    if stdout:
        for line in stdout.strip().splitlines():
            try:
                data = json.loads(line.strip())
                if data.get("is_error"):
                    error_msg = data.get("result", data.get("error", "Unknown JSON error"))
                    break
            except json.JSONDecodeError:
                continue
    if error_msg == "No error message" and stderr:
        error_msg = stderr.strip()
    return error_msg


def _call_claude_judge(
    evaluation_context: str,
    model: str,
    workspace: Path | None = None,
    timeout: int = 1200,
) -> tuple[str, str, str]:
    """Call Claude CLI to get judgment.

    The evaluation context (task, agent output, workspace state, pipeline results)
    is passed directly as the CLI prompt. No tool access is needed.

    Args:
        evaluation_context: The task, agent output, and workspace state to evaluate
        model: Model to use for judging
        workspace: Path to workspace (unused, kept for API compatibility)

    Returns:
        Tuple of (stdout, stderr, raw_response) where raw_response is the same as stdout.

    """
    # Judge evaluates from provided context only (workspace state, git diff,
    # pipeline results are all included in the prompt). No tool access needed,
    # which reduces memory overhead and avoids dependency on workspace existence.
    #
    # NOTE: --allowedTools takes variadic <tools...>, so any positional arg
    # placed after it gets consumed as a tool name instead of the prompt.
    # We pipe the evaluation context via stdin to avoid this and ARG_MAX limits.
    # Use stream-json to work around Claude CLI v2.1.83 bug where --print
    # mode returns empty result field despite the model generating tokens.
    # Stream-json events contain the actual response in type:assistant messages.
    cmd = [
        "claude",
        "--model",
        model,
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
        "--allowedTools",
        "",  # No tools — all context is in the prompt
        "--system-prompt-file",
        str(JUDGE_SYSTEM_PROMPT_FILE),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={k: v for k, v in os.environ.items() if k != "CLAUDECODE"},
        input=evaluation_context,
    )

    # Use circuit breaker for judge API calls
    cb = get_circuit_breaker("claude_api_judge", failure_threshold=5, recovery_timeout=60.0)

    from scylla.e2e.rate_limit import RateLimitError, _detect_rate_limit_from_stdout

    if result.returncode != 0:
        _raise_if_rate_limit(result.stdout, result.stderr)
        error_msg = _extract_cli_error(result.stdout, result.stderr)
        _raise_if_rate_limit_in_error(error_msg)
        cb._record_failure()
        exc = RuntimeError(f"Claude CLI failed (exit {result.returncode}): {error_msg}")
        # Attach raw streams so judge_runner can save them for post-hoc debugging
        exc._judge_stdout = result.stdout  # type: ignore[attr-defined]
        exc._judge_stderr = result.stderr  # type: ignore[attr-defined]
        raise exc

    # On success (exit 0), only check stdout for structured JSON rate-limit signals.
    # Stderr on a successful call is warnings/progress — scanning it risks false
    # positives when the model mentions "resets" or "rate limit" in valid output.
    rate_limit_info = _detect_rate_limit_from_stdout(result.stdout, source="judge")
    if rate_limit_info:
        raise RateLimitError(rate_limit_info)

    # Record success with circuit breaker
    cb._record_success()

    # Extract response text from stream-json events
    response_text = _extract_response_from_stream(result.stdout)
    return result.stdout, result.stderr, response_text


def _parse_judge_response(response: str) -> JudgeResult:
    """Parse the judge's JSON response.

    Args:
        response: Raw response from the LLM

    Returns:
        JudgeResult parsed from response.

    """
    # Extract JSON from response using shared utility
    response = response.strip()

    if not response:
        raise ValueError(
            "Judge returned empty response. "
            "This may indicate the prompt was not delivered to the model. "
            "Check stderr logs for details."
        )

    data = extract_json_from_llm_response(response)

    if data is None:
        raise ValueError(f"Judge response does not contain valid JSON.\nResponse: {response[:500]}")

    if "score" not in data:
        raise ValueError(
            f"Judge response missing required 'score' field. "
            f"Keys found: {list(data.keys())}\nResponse: {response[:500]}"
        )

    score = float(data.get("score") or 0.0)
    passed = bool(data.get("passed") or False)
    reasoning = str(data.get("reasoning") or "No reasoning provided")

    # Support both old and new format
    # New format: "categories" with structured breakdown
    # Old format: "criteria_scores" with flat structure
    criteria_scores = data.get("categories") or data.get("criteria_scores")

    # Validate score range
    score = max(0.0, min(1.0, score))

    return JudgeResult(
        score=score,
        passed=passed,
        grade=_score_to_grade(score),
        reasoning=reasoning,
        criteria_scores=criteria_scores,
        raw_response=response,
    )


def _get_utc_now() -> Any:
    """Get current UTC datetime (extracted for testability)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
