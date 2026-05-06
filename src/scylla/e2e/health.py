"""Health monitoring for E2E experiments — zombie detection and heartbeat.

A "zombie" experiment is one where:
  - checkpoint.status == "running"
  - The PID in experiment.pid is dead (process no longer exists)
  - The last_heartbeat timestamp is stale (older than heartbeat_timeout_seconds)

Zombie experiments occur when a process is killed externally (OOM killer,
SIGKILL, cloud VM termination) without a clean shutdown path.

On resume, the zombie check auto-detects this condition and resets the
experiment state to "interrupted" so it can be safely resumed.

Usage:
    # In background thread during run
    heartbeat = HeartbeatThread(checkpoint, checkpoint_path, interval=30)
    heartbeat.start()
    ...
    heartbeat.stop()

    # On resume, before running
    if is_zombie(checkpoint, experiment_dir, timeout=120):
        checkpoint = reset_zombie_checkpoint(checkpoint, checkpoint_path)
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scylla.e2e.checkpoint import E2ECheckpoint

logger = logging.getLogger(__name__)

# Default timeout: if heartbeat is older than this, treat as zombie
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 120


def _pid_is_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive.

    Uses signal 0 which doesn't kill the process but checks existence.

    Args:
        pid: Process ID to check

    Returns:
        True if process exists, False otherwise

    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def _heartbeat_is_stale(last_heartbeat: str, timeout_seconds: int) -> bool:
    """Check if the last heartbeat timestamp is older than timeout_seconds.

    Args:
        last_heartbeat: ISO timestamp string (empty string treated as stale)
        timeout_seconds: Maximum age in seconds before considered stale

    Returns:
        True if heartbeat is stale or missing, False if fresh

    """
    if not last_heartbeat:
        return True

    try:
        hb_time = datetime.fromisoformat(last_heartbeat)
        if hb_time.tzinfo is None:
            hb_time = hb_time.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - hb_time).total_seconds()
        return age_seconds > timeout_seconds
    except (ValueError, TypeError):
        # Unparseable timestamp -> treat as stale
        return True


def is_zombie(
    checkpoint: E2ECheckpoint,
    experiment_dir: Path,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
) -> bool:
    """Check if a running checkpoint represents a zombie experiment.

    A zombie is detected when ALL of these are true:
    1. checkpoint.status == "running"
    2. The PID referenced in the checkpoint (or experiment.pid file) is dead
    3. The last heartbeat is stale (older than heartbeat_timeout_seconds)

    Args:
        checkpoint: E2ECheckpoint loaded from disk
        experiment_dir: Path to experiment directory (for experiment.pid)
        heartbeat_timeout_seconds: Seconds after which a heartbeat is stale

    Returns:
        True if this looks like a zombie experiment

    """
    if checkpoint.status != "running":
        return False

    # Check PID from checkpoint or PID file
    pid = checkpoint.pid
    if pid is None:
        pid_file = experiment_dir / "experiment.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
            except (ValueError, OSError):
                pid = None

    # If we can confirm the process is still alive, not a zombie
    if pid is not None and _pid_is_alive(pid):
        return False

    # PID is dead (or unknown) — check heartbeat staleness
    if _heartbeat_is_stale(checkpoint.last_heartbeat, heartbeat_timeout_seconds):
        logger.warning(
            f"Zombie detected: status=running, pid={pid} dead, "
            f"last_heartbeat={checkpoint.last_heartbeat!r} stale "
            f"(>{heartbeat_timeout_seconds}s)"
        )
        return True

    return False


def reset_zombie_checkpoint(checkpoint: E2ECheckpoint, checkpoint_path: Path) -> E2ECheckpoint:
    """Reset a zombie checkpoint to 'interrupted' status.

    Preserves all run state data so the experiment can be resumed
    from where it left off. Only the top-level status is changed.

    Args:
        checkpoint: E2ECheckpoint to reset (mutated in place)
        checkpoint_path: Path to checkpoint file for atomic save

    Returns:
        The updated checkpoint (same object, mutated)

    """
    from scylla.e2e.checkpoint import save_checkpoint

    logger.info(
        f"Resetting zombie checkpoint {checkpoint.experiment_id} from 'running' to 'interrupted'"
    )
    checkpoint.status = "interrupted"
    checkpoint.last_updated_at = datetime.now(timezone.utc).isoformat()
    save_checkpoint(checkpoint, checkpoint_path)
    return checkpoint


class HeartbeatThread(threading.Thread):
    """Background thread that periodically updates the checkpoint heartbeat.

    Keeps the checkpoint's last_heartbeat timestamp fresh so that the zombie
    detection logic knows the process is still alive.

    The heartbeat is written at most once per interval_seconds. If the
    checkpoint cannot be saved (e.g., disk full), a warning is logged
    but the thread continues.

    Example:
        >>> heartbeat = HeartbeatThread(checkpoint, checkpoint_path, interval=30)
        >>> heartbeat.start()
        >>> # ... run experiment ...
        >>> heartbeat.stop()

    """

    def __init__(
        self,
        checkpoint: E2ECheckpoint,
        checkpoint_path: Path,
        interval_seconds: int = 30,
    ) -> None:
        """Initialize the heartbeat thread.

        Args:
            checkpoint: E2ECheckpoint to update (mutated in place periodically)
            checkpoint_path: Path to checkpoint file
            interval_seconds: How often to write heartbeat (default 30s)

        """
        super().__init__(daemon=True, name="HeartbeatThread")
        self._checkpoint = checkpoint
        self._checkpoint_path = checkpoint_path
        self._interval = interval_seconds
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Update heartbeat on a fixed interval until stop() is called."""
        logger.debug(f"HeartbeatThread started (interval={self._interval}s)")
        self._check_count = 0
        while not self._stop_event.wait(timeout=self._interval):
            self._write_heartbeat()
            # Log resource usage every 5 heartbeats (~2.5 min at 30s interval)
            self._check_count += 1
            if self._check_count % 5 == 0:
                _log_resource_usage()
        logger.debug("HeartbeatThread stopped")

    def stop(self) -> None:
        """Signal the thread to stop after the current interval completes."""
        self._stop_event.set()

    def _write_heartbeat(self) -> None:
        """Update only the heartbeat timestamp on disk, preserving all other state.

        Reads the current checkpoint from disk, updates only last_heartbeat,
        and writes it back atomically. This prevents overwriting run_states and
        other fields written by worker processes.
        """
        from scylla.e2e.checkpoint import CheckpointError, load_checkpoint, save_checkpoint

        try:
            # Read from disk to get the latest state written by worker processes
            current = load_checkpoint(self._checkpoint_path)
            current.update_heartbeat()
            save_checkpoint(current, self._checkpoint_path)
            logger.debug(f"Heartbeat updated: {current.last_heartbeat}")
        except CheckpointError as e:
            logger.warning(f"Failed to write heartbeat: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error writing heartbeat: {e}")


def _get_memory_info() -> tuple[int, int] | None:
    """Read available and total RAM from /proc/meminfo (Linux only).

    Returns:
        Tuple of (available_mb, total_mb) or None if not available.

    """
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
        total_kb = meminfo.get("MemTotal", 0)
        avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        return (avail_kb // 1024, total_kb // 1024)
    except (OSError, ValueError, KeyError):
        return None


def _log_resource_usage() -> None:
    """Log current memory and disk usage at INFO level."""
    import shutil

    mem = _get_memory_info()
    if mem:
        avail_mb, total_mb = mem
        used_pct = ((total_mb - avail_mb) / total_mb * 100) if total_mb > 0 else 0
        level = logging.WARNING if avail_mb < 2048 else logging.DEBUG
        logger.log(
            level,
            f"Memory: {avail_mb}MB available / {total_mb}MB total ({used_pct:.0f}% used)",
        )

    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        used_pct = (usage.used / usage.total * 100) if usage.total > 0 else 0
        level = logging.WARNING if free_gb < 20 else logging.DEBUG
        logger.log(
            level,
            f"Disk: {free_gb:.1f}GB free / {total_gb:.1f}GB total ({used_pct:.0f}% used)",
        )
    except OSError:
        pass


# Warning thresholds (low-resource notice; recoverable):
WARN_RAM_MB = 4096
WARN_DISK_GB = 50

# Critical thresholds (hard abort regardless of fail_on_warn flag).
# Set conservatively so a typical CI runner (16GB RAM / 50+GB disk) never
# trips them — only genuinely under-provisioned hosts do.
CRITICAL_RAM_MB = 512
CRITICAL_DISK_GB = 5


class ResourcePreflightError(RuntimeError):
    """Raised when log_resource_preflight() refuses to proceed.

    Raised in two cases:
    1. A critical-threshold breach (RAM < CRITICAL_RAM_MB or disk <
       CRITICAL_DISK_GB) regardless of any flag — the host is so
       under-provisioned that proceeding will almost certainly corrupt
       the experiment.
    2. A warning-threshold breach (RAM < WARN_RAM_MB or disk <
       WARN_DISK_GB) when the caller passes ``fail_on_warn=True``,
       typically wired to a ``--fail-on-resource-check`` CLI flag.
    """


def log_resource_preflight(*, fail_on_warn: bool = False) -> None:
    """Log resource availability before an experiment starts.

    Always raises :class:`ResourcePreflightError` when RAM or disk is
    below the critical thresholds (:data:`CRITICAL_RAM_MB`,
    :data:`CRITICAL_DISK_GB`), so a wildly under-provisioned host is
    caught even if the operator misses log lines.

    Warns when RAM or disk is below the warning thresholds
    (:data:`WARN_RAM_MB`, :data:`WARN_DISK_GB`). When
    ``fail_on_warn=True`` (typically wired from a
    ``--fail-on-resource-check`` CLI flag), warning-level breaches also
    raise instead of just logging.

    Args:
        fail_on_warn: When True, warning-level shortages also raise
            :class:`ResourcePreflightError`. Defaults to False so
            existing callers see no behaviour change at the warning
            thresholds.

    Raises:
        ResourcePreflightError: On a critical-threshold breach, or on a
            warning-threshold breach when ``fail_on_warn=True``.

    """
    import shutil

    breaches: list[str] = []

    mem = _get_memory_info()
    if mem:
        avail_mb, total_mb = mem
        logger.info(f"Pre-flight: {avail_mb}MB RAM available / {total_mb}MB total")
        if avail_mb < CRITICAL_RAM_MB:
            breaches.append(
                f"CRITICAL: only {avail_mb}MB RAM available (threshold {CRITICAL_RAM_MB}MB)"
            )
        elif avail_mb < WARN_RAM_MB:
            msg = (
                f"Low memory warning: only {avail_mb}MB available. "
                f"Consider reducing --threads or --max-concurrent-agents."
            )
            logger.warning(msg)
            if fail_on_warn:
                breaches.append(msg)

    try:
        usage = shutil.disk_usage("/")
        free_gb = usage.free / (1024**3)
        logger.info(f"Pre-flight: {free_gb:.1f}GB disk free")
        if free_gb < CRITICAL_DISK_GB:
            breaches.append(
                f"CRITICAL: only {free_gb:.1f}GB disk free (threshold {CRITICAL_DISK_GB}GB)"
            )
        elif free_gb < WARN_DISK_GB:
            msg = (
                f"Low disk warning: only {free_gb:.1f}GB free. "
                f"Consider cleaning up old experiment workspaces."
            )
            logger.warning(msg)
            if fail_on_warn:
                breaches.append(msg)
    except OSError:
        pass

    if breaches:
        raise ResourcePreflightError("; ".join(breaches))
