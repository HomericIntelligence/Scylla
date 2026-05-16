"""Rate limit detection and handling for E2E testing.

This module provides rate limit detection from both agent (Claude Code subprocess)
and judge (Opus API) responses, along with wait/retry logic.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

from scylla.e2e.paths import get_agent_dir

if TYPE_CHECKING:
    from scylla.persistence.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)


class RateLimitInfo(BaseModel):
    """Information about a detected rate limit.

    Attributes:
        source: Where rate limit occurred (agent or judge)
        retry_after_seconds: Seconds to wait before retry (with buffer)
        error_message: Human-readable error message
        detected_at: ISO timestamp when detected

    """

    source: str  # "agent" or "judge"
    retry_after_seconds: float | None
    error_message: str
    detected_at: str

    @model_validator(mode="after")
    def validate_source(self) -> RateLimitInfo:
        """Validate source field."""
        if self.source not in ("agent", "judge"):
            raise ValueError(f"Invalid source: {self.source}. Must be 'agent' or 'judge'.")
        return self


class InfrastructureFailureError(Exception):
    """Raised when an agent crashes before making any API calls (exit_code=-1, zero tokens).

    Caught at the subtest level in run_tier_subtests_parallel() so the failed
    run is skipped and the experiment continues with remaining subtests/tiers.
    """


class RateLimitError(Exception):
    """Raised when rate limit is detected from agent or judge.

    This exception carries rate limit details for handling by the
    pause/resume system.

    Attributes:
        info: RateLimitInfo with detection details

    """

    def __init__(self, info: RateLimitInfo):
        """Initialize with rate limit info.

        Args:
            info: Rate limit detection information

        """
        self.info = info
        super().__init__(f"Rate limit from {info.source}: {info.error_message}")


class WeeklyLimitError(RateLimitError):
    """Raised when a weekly/hard usage limit is hit (not a transient 429).

    Weekly limits reset on a specific date/time, not after seconds.
    Retrying after 60s will not help — the experiment must be paused
    until the reset time.

    Use this instead of ``RateLimitError`` when ``retry_after_seconds``
    represents hours or days (i.e. a date-based reset, not a server backoff).
    """


def parse_retry_after(stderr: str) -> float | None:
    """Extract Retry-After value from stderr/headers with 10% buffer.

    Handles:
    - Retry-After: 30 (seconds)
    - resets 4pm (America/Los_Angeles) format
    - Retry-After header in various formats

    Args:
        stderr: Standard error output containing headers

    Returns:
        Seconds to wait (with 10% buffer added), or None if not found

    """
    # Pattern 1: "Retry-After: <seconds>"
    match = re.search(r"Retry-After:\s*(\d+)", stderr, re.IGNORECASE)
    if match:
        seconds = float(match.group(1))
        # Add 10% buffer to be conservative
        return seconds * 1.1

    # Pattern 2: "resets 4pm (America/Los_Angeles)" or similar time format
    # Match patterns like "resets 4pm", "resets 12am", "resets 11:30pm"
    match = re.search(r"resets\s+(\d{1,2}):?(\d{2})?\s*(am|pm)", stderr, re.IGNORECASE)
    if match:
        import zoneinfo
        from datetime import datetime

        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        am_pm = match.group(3).lower()

        # Convert to 24-hour format
        if am_pm == "pm" and hour != 12:
            hour += 12
        elif am_pm == "am" and hour == 12:
            hour = 0

        # Try to extract timezone, default to America/Los_Angeles if not found
        tz_match = re.search(r"\(([^)]+)\)", stderr)
        tz_str = tz_match.group(1) if tz_match else "America/Los_Angeles"

        try:
            tz = zoneinfo.ZoneInfo(tz_str)
        except Exception as e:
            logger.debug("Timezone parsing failed, falling back to UTC: %s", e)
            tz = zoneinfo.ZoneInfo("UTC")

        # Get current time and target reset time
        now = datetime.now(tz)
        reset_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If reset time is in the past today, it means tomorrow
        if reset_time <= now:
            from datetime import timedelta

            reset_time += timedelta(days=1)

        # Calculate seconds until reset
        seconds = (reset_time - now).total_seconds()

        # Add 10% buffer to be conservative
        return seconds * 1.1

    return None


_STDERR_RATE_LIMIT_PATTERNS: list[tuple[str, bool, str]] = [
    # (substring_to_check, check_lower, error_message)
    # Ordered to match original elif priority: service-specific first, then 429,
    # then generic "rate limit" text, then the remaining patterns.
    ("weekly usage limit", True, "Weekly usage limit reached"),
    ("upgrade to continue", True, "Usage limit - upgrade required"),
    ("failed to configure provider", True, "Provider configuration failed"),
    # "429" is matched against raw stderr (not lowercased) to avoid false positives
    ("429", False, "HTTP 429: Rate limit exceeded"),
    ("rate limit", True, "Rate limit detected in stderr"),
    ("ratelimit", True, "Rate limit detected in stderr"),
    ("hit your limit", True, "API limit hit"),
    ("overloaded", True, "API overloaded"),
    # "resets <date>" appears in weekly usage limit messages, e.g.
    # "You've hit your limit · resets Apr 3, 6am (America/Los_Angeles)"
    ("resets ", True, "Usage limit with scheduled reset"),
]

# Rate-limit keywords for JSON is_error result fields (used in JSON + stream-json detection)
_JSON_RATE_LIMIT_KEYWORDS: tuple[str, ...] = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "overloaded",
    "429",
    "hit your limit",
    "resets",
    "weekly usage limit",
    "upgrade to continue",
    "failed to configure provider",
)


def _detect_rate_limit_from_stderr(stderr: str) -> tuple[str, float | None]:
    """Scan stderr for rate-limit indicator patterns.

    Args:
        stderr: Standard error text from subprocess.

    Returns:
        (error_message, retry_after) where error_message is empty string if no
        rate limit detected.

    """
    stderr_lower = stderr.lower()

    for pattern, use_lower, message in _STDERR_RATE_LIMIT_PATTERNS:
        haystack = stderr_lower if use_lower else stderr
        if pattern in haystack:
            return message, parse_retry_after(stderr)

    return "", None


def _make_rate_limit_info(
    source: str,
    error_msg: str,
    retry_after: float | None,
    text_for_retry_parse: str = "",
) -> RateLimitInfo:
    """Build the appropriate RateLimitInfo (or WeeklyLimitError info) instance.

    If ``retry_after`` is more than 3600 seconds (1 hour) the limit is
    considered a weekly/hard cap that cannot be resolved by a short wait.
    We still return a ``RateLimitInfo``; the *caller* is responsible for
    raising ``WeeklyLimitError`` when that distinction matters.

    Args:
        source: "agent" or "judge"
        error_msg: Human-readable error message
        retry_after: Seconds to wait, or None if unknown
        text_for_retry_parse: Additional text to try parsing retry-after from

    Returns:
        RateLimitInfo populated with the supplied values

    """
    if retry_after is None and text_for_retry_parse:
        retry_after = parse_retry_after(text_for_retry_parse)
    return RateLimitInfo(
        source=source,
        retry_after_seconds=retry_after,
        error_message=error_msg or "Rate limit detected",
        detected_at=datetime.now(timezone.utc).isoformat(),
    )


def _detect_rate_limit_from_json_line(data: dict[str, object], source: str) -> RateLimitInfo | None:
    """Check a single parsed JSON object for rate-limit indicators.

    Handles both ``--output-format json`` (single object) and individual
    lines from ``--output-format stream-json``.

    Args:
        data: Parsed JSON object
        source: "agent" or "judge"

    Returns:
        RateLimitInfo if rate limit detected, None otherwise

    """
    if not data.get("is_error"):
        return None

    result = data.get("result", data.get("error", ""))
    error_str = str(result).lower()

    if any(keyword in error_str for keyword in _JSON_RATE_LIMIT_KEYWORDS):
        retry_after = parse_retry_after(str(result))
        return _make_rate_limit_info(source, str(result), retry_after)

    return None


def _detect_rate_limit_from_stdout(stdout: str, source: str) -> RateLimitInfo | None:
    """Detect rate limit from stdout in JSON or stream-json format.

    Only checks structured JSON fields (``is_error: true``) — never scans
    raw response text, which risks false positives when the judge evaluates
    tasks that mention rate limits in their content.

    Args:
        stdout: Standard output from subprocess
        source: "agent" or "judge"

    Returns:
        RateLimitInfo if rate limit detected, None otherwise

    """
    if not stdout.strip():
        return None

    # 1. Try single-object JSON (--output-format json)
    try:
        data = json.loads(stdout.strip())
        info = _detect_rate_limit_from_json_line(data, source)
        if info:
            return info
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 2. Try stream-json: one JSON object per line (--output-format stream-json)
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            info = _detect_rate_limit_from_json_line(data, source)
            if info:
                return info
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return None


def detect_rate_limit(stdout: str, stderr: str, source: str = "agent") -> RateLimitInfo | None:
    """Detect rate limit from JSON or stream-json output, or stderr patterns.

    Detection order:
    1. Parse stdout as single JSON object (``--output-format json``)
    2. Parse stdout line-by-line as stream-json (``--output-format stream-json``)
    3. Scan stdout as plain text for rate-limit patterns
    4. Scan stderr for rate-limit patterns

    Args:
        stdout: Standard output from subprocess
        stderr: Standard error from subprocess
        source: Source of output ("agent" or "judge")

    Returns:
        RateLimitInfo if rate limit detected, None otherwise

    """
    info = _detect_rate_limit_from_stdout(stdout, source)
    if info:
        return info

    if stderr.strip():
        error_msg, retry_after = _detect_rate_limit_from_stderr(stderr)
        if error_msg:
            return _make_rate_limit_info(source, error_msg, retry_after)

    return None


def is_weekly_limit(info: RateLimitInfo) -> bool:
    """Return True if this rate limit is a weekly/hard cap, not a transient 429.

    Weekly limits reset on a specific date, typically hours or days away.
    A retry-after value greater than 3600 seconds (1 hour) is considered
    a weekly limit — short retries will not help.

    Args:
        info: RateLimitInfo to classify

    Returns:
        True if this is a weekly limit (long wait required)

    """
    if info.retry_after_seconds is not None and info.retry_after_seconds > 3600:
        return True
    # Also detect from error message keywords even if retry_after is unknown
    msg_lower = info.error_message.lower()
    return any(
        kw in msg_lower
        for kw in ("weekly usage limit", "hit your limit", "upgrade to continue", "resets ")
    )


def wait_for_rate_limit(
    retry_after: float | None,
    checkpoint: E2ECheckpoint,
    checkpoint_path: Path,
    log_func: Callable[[str], None] | None = None,
) -> None:
    """Wait for rate limit to expire with status updates.

    Updates checkpoint with pause status, waits, then updates to running.
    Provides periodic status updates during wait.

    Args:
        retry_after: Seconds to wait (already includes 10% buffer)
        checkpoint: Checkpoint to update with pause status
        checkpoint_path: Path to save updated checkpoint
        log_func: Function for status logging (default: logger.info)

    """
    if log_func is None:
        log_func = logger.info

    # Default wait if no Retry-After header
    if retry_after is None:
        retry_after = 60.0  # Default 60 seconds
        log_func("No Retry-After header found, using default 60s wait")

    # Ensure 10% buffer (should already be added by parse_retry_after)
    wait_time = retry_after

    # Update checkpoint with pause status
    from scylla.persistence.checkpoint import save_checkpoint

    checkpoint.status = "paused_rate_limit"
    checkpoint.rate_limit_until = (
        datetime.now(timezone.utc) + timedelta(seconds=wait_time)
    ).isoformat()
    checkpoint.pause_count += 1
    save_checkpoint(checkpoint, checkpoint_path)

    # Log to console (requirement: visible status)
    log_func(
        f"⏸️  Rate limit hit. Pausing for {wait_time:.0f}s (until {checkpoint.rate_limit_until})"
    )

    # Wait with Fibonacci backoff for status updates (1s, 1s, 2s, 3s, 5s, 8s... up to 5 min)
    remaining = wait_time
    fib_prev, fib_curr = 1, 1  # Start Fibonacci sequence at 1 second
    max_interval = 300  # Cap at 5 minutes (300 seconds)

    while remaining > 0:
        # Calculate next interval with Fibonacci backoff, capped at 5 minutes
        interval = min(fib_curr, max_interval)
        sleep_chunk = min(interval, remaining)
        time.sleep(sleep_chunk)
        remaining -= sleep_chunk

        # Check for shutdown between sleep iterations
        from scylla.e2e.shutdown import ShutdownInterruptedError, is_shutdown_requested

        if is_shutdown_requested():
            # Restore checkpoint to running state before raising
            checkpoint.status = "running"
            checkpoint.rate_limit_until = None
            checkpoint.rate_limit_source = None
            save_checkpoint(checkpoint, checkpoint_path)
            raise ShutdownInterruptedError("Shutdown requested during rate limit wait")

        if remaining > 0:
            # Calculate when next update will occur
            next_fib = fib_prev + fib_curr
            next_update_sec = min(next_fib, max_interval, remaining)

            minutes = remaining / 60
            next_update_min = next_update_sec / 60

            if minutes >= 1:
                log_func(
                    f"   Rate limit wait: {minutes:.1f} minutes remaining "
                    f"(next update in {next_update_min:.1f} min)"
                )
            else:
                log_func(
                    f"   Rate limit wait: {remaining:.0f} seconds remaining "
                    f"(next update in {next_update_sec:.0f} sec)"
                )

            # Update Fibonacci sequence for next iteration
            fib_prev, fib_curr = fib_curr, next_fib

    # Update checkpoint - resuming
    checkpoint.status = "running"
    checkpoint.rate_limit_until = None
    checkpoint.rate_limit_source = None
    save_checkpoint(checkpoint, checkpoint_path)

    log_func("▶️  Rate limit wait complete. Resuming...")


def validate_run_result(run_dir: Path) -> tuple[bool, str | None]:
    """Validate a run result to check if it's a valid completion.

    Checks:
    1. run_result.json exists and has valid judge_reasoning
    2. agent/stderr.log doesn't contain rate limit patterns
    3. agent/stdout.log doesn't contain rate limit patterns in JSON is_error
    4. exit_code is not -1 (unless other indicators show success)

    Args:
        run_dir: Path to the run directory (e.g., results/T0/01/run_01/)

    Returns:
        Tuple of (is_valid, failure_reason)
        - is_valid: True if run completed successfully, False if rate-limited
        - failure_reason: Description of why validation failed, or None

    """
    run_result_file = run_dir / "run_result.json"
    agent_dir = get_agent_dir(run_dir)
    stderr_file = agent_dir / "stderr.log"
    stdout_file = agent_dir / "stdout.log"

    # Check agent/stderr.log for rate limit patterns first
    if stderr_file.exists():
        stderr_content = stderr_file.read_text()
        rate_info = detect_rate_limit("", stderr_content, source="agent")
        if rate_info:
            return False, f"Rate limit in stderr: {rate_info.error_message}"

    # Check agent/stdout.log for rate limit patterns in JSON
    if stdout_file.exists():
        stdout_content = stdout_file.read_text()
        rate_info = detect_rate_limit(stdout_content, "", source="agent")
        if rate_info:
            return False, f"Rate limit in stdout JSON: {rate_info.error_message}"

    # Load run_result.json if exists and check for invalid run indicators
    if run_result_file.exists():
        import json

        with open(run_result_file) as f:
            data = json.load(f)

        # Check for rate limit indicators in judge_reasoning
        judge_reasoning = data.get("judge_reasoning", "")
        if "Unable to evaluate agent output" in judge_reasoning and data.get("exit_code") == -1:
            return False, "Run failed with exit_code=-1 and invalid judge output"

    return True, None


def check_api_rate_limit_status() -> RateLimitInfo | None:
    """Check if we're currently rate limited by making a lightweight API call.

    Uses a minimal prompt to check status without burning tokens.
    Returns RateLimitInfo if rate limited, None if OK.

    Returns:
        RateLimitInfo if rate limited, None otherwise

    """
    # Use claude CLI to check status with minimal prompt
    try:
        result = subprocess.run(
            ["claude", "--print", "ping"],  # Minimal interaction
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )

        if "rate limit" in result.stderr.lower() or "hit your limit" in result.stderr.lower():
            return RateLimitInfo(
                source="agent",
                retry_after_seconds=parse_retry_after(result.stderr),
                error_message=result.stderr.strip(),
                detected_at=datetime.now(timezone.utc).isoformat(),
            )

        return None

    except subprocess.TimeoutExpired:
        return None  # Timeout is not a rate limit
    except Exception as e:
        logger.debug(
            "Unexpected error during rate limit detection, treating as no rate limit: %s", e
        )
        return None
