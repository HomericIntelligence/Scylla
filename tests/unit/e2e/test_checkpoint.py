"""Unit tests for checkpoint module functions and exceptions.

Tests coverage for functions and exception handling not covered by test_resume.py.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from scylla.e2e.checkpoint import (
    CheckpointError,
    ConfigMismatchError,
    E2ECheckpoint,
    compute_config_hash,
    get_experiment_status,
    load_checkpoint,
    save_checkpoint,
)
from scylla.e2e.models import (
    ExperimentConfig,
    TierID,
)


@pytest.fixture
def experiment_config() -> ExperimentConfig:
    """Create a minimal experiment configuration for testing."""
    return ExperimentConfig(
        experiment_id="test-config",
        task_repo="https://github.com/test/repo",
        task_commit="abc123",
        task_prompt_file=Path("/tmp/prompt.md"),
        language="mojo",
        models=["claude-sonnet-4-6"],
        runs_per_subtest=3,
        tiers_to_run=[TierID.T0],
        judge_models=["claude-opus-4-6"],
        timeout_seconds=300,
    )


class TestComputeConfigHash:
    """Tests for compute_config_hash() function."""

    def test_compute_config_hash_returns_16_char_hex(
        self, experiment_config: ExperimentConfig
    ) -> None:
        """Verify hash is 16-character hex string."""
        hash_value = compute_config_hash(experiment_config)
        assert len(hash_value) == 16
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_compute_config_hash_deterministic(self, experiment_config: ExperimentConfig) -> None:
        """Verify same config produces same hash."""
        hash1 = compute_config_hash(experiment_config)
        hash2 = compute_config_hash(experiment_config)
        assert hash1 == hash2

    def test_compute_config_hash_different_for_different_configs(
        self, experiment_config: ExperimentConfig
    ) -> None:
        """Verify different configs produce different hashes."""
        hash1 = compute_config_hash(experiment_config)

        # Modify a field that affects results
        experiment_config.runs_per_subtest = 5
        hash2 = compute_config_hash(experiment_config)

        assert hash1 != hash2

    def test_compute_config_hash_ignores_max_subtests(
        self, experiment_config: ExperimentConfig
    ) -> None:
        """Verify max_subtests doesn't affect hash (development/testing only)."""
        hash1 = compute_config_hash(experiment_config)

        # Create a copy with max_subtests set
        experiment_config_copy = ExperimentConfig(
            experiment_id=experiment_config.experiment_id,
            task_repo=experiment_config.task_repo,
            task_commit=experiment_config.task_commit,
            task_prompt_file=experiment_config.task_prompt_file,
            language=experiment_config.language,
            models=experiment_config.models,
            runs_per_subtest=experiment_config.runs_per_subtest,
            tiers_to_run=experiment_config.tiers_to_run,
            judge_models=experiment_config.judge_models,
            timeout_seconds=experiment_config.timeout_seconds,
            max_subtests=5,  # Add max_subtests
        )
        hash2 = compute_config_hash(experiment_config_copy)

        # Hash should be the same (max_subtests is excluded)
        assert hash1 == hash2


class TestGetExperimentStatus:
    """Tests for get_experiment_status() function."""

    def test_get_experiment_status_no_checkpoint(self, tmp_path: Path) -> None:
        """Verify status when no checkpoint exists."""
        status = get_experiment_status(tmp_path)
        assert status["running"] is False
        assert status["status"] == "unknown"

    def test_get_experiment_status_with_checkpoint(self, tmp_path: Path) -> None:
        """Verify status reads checkpoint data."""
        # Create checkpoint
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="test-hash",
            completed_runs={"T0": {"T0_00": {1: "passed", 2: "passed"}}},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="paused_rate_limit",
            rate_limit_until="2026-02-13T00:00:00Z",
        )
        checkpoint_path = tmp_path / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        status = get_experiment_status(tmp_path)
        assert status["status"] == "paused_rate_limit"
        assert status["completed_runs"] == 2
        assert status["rate_limit_until"] == "2026-02-13T00:00:00Z"

    def test_get_experiment_status_corrupted_checkpoint(self, tmp_path: Path) -> None:
        """Verify status handles corrupted checkpoint gracefully."""
        checkpoint_path = tmp_path / "checkpoint.json"
        checkpoint_path.write_text("{ invalid json")

        status = get_experiment_status(tmp_path)
        assert status["running"] is False
        assert status["status"] == "unknown"

    def test_get_experiment_status_running_process(self, tmp_path: Path) -> None:
        """Verify status detects running process."""
        pid_path = tmp_path / "experiment.pid"
        current_pid = os.getpid()
        pid_path.write_text(str(current_pid))

        status = get_experiment_status(tmp_path)
        assert status["running"] is True
        assert status["pid"] == current_pid

    def test_get_experiment_status_dead_process(self, tmp_path: Path) -> None:
        """Verify status detects dead process."""
        pid_path = tmp_path / "experiment.pid"
        # Use a PID that doesn't exist (very high number unlikely to exist)
        dead_pid = 999999
        pid_path.write_text(str(dead_pid))

        status = get_experiment_status(tmp_path)
        assert status["running"] is False
        assert status["pid"] is None

    def test_get_experiment_status_invalid_pid_file(self, tmp_path: Path) -> None:
        """Verify status handles invalid PID file gracefully."""
        pid_path = tmp_path / "experiment.pid"
        pid_path.write_text("not-a-number")

        status = get_experiment_status(tmp_path)
        assert status["running"] is False
        assert status["pid"] is None


class TestCheckpointExceptions:
    """Tests for checkpoint exception classes."""

    def test_checkpoint_error_can_be_raised(self) -> None:
        """Verify CheckpointError can be raised."""
        with pytest.raises(CheckpointError, match="Test error"):
            raise CheckpointError("Test error")

    def test_checkpoint_error_is_exception(self) -> None:
        """Verify CheckpointError is an Exception."""
        assert issubclass(CheckpointError, Exception)

    def test_config_mismatch_error_can_be_raised(self) -> None:
        """Verify ConfigMismatchError can be raised."""
        with pytest.raises(ConfigMismatchError, match="Config mismatch"):
            raise ConfigMismatchError("Config mismatch")

    def test_config_mismatch_error_is_checkpoint_error(self) -> None:
        """Verify ConfigMismatchError is a CheckpointError."""
        assert issubclass(ConfigMismatchError, CheckpointError)


class TestCheckpointVersionMismatch:
    """Tests for from_dict version mismatch handling."""

    def test_from_dict_raises_on_version_1_0(self, tmp_path: Path) -> None:
        """Verify from_dict raises CheckpointError for v1.0."""
        data = {
            "version": "1.0",
            "experiment_id": "test-exp",
            "experiment_dir": str(tmp_path),
            "config_hash": "test-hash",
            "completed_runs": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }

        with pytest.raises(
            CheckpointError,
            match=r"Incompatible checkpoint version 1\.0",
        ):
            E2ECheckpoint.from_dict(data)

    def test_from_dict_raises_on_unknown_version(self, tmp_path: Path) -> None:
        """Verify from_dict raises CheckpointError for unknown version."""
        data = {
            "version": "9.9",
            "experiment_id": "test-exp",
            "experiment_dir": str(tmp_path),
            "config_hash": "test-hash",
            "completed_runs": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }

        with pytest.raises(
            CheckpointError,
            match=r"Incompatible checkpoint version 9\.9",
        ):
            E2ECheckpoint.from_dict(data)


class TestCheckpointV31Migration:
    """Tests for v3.0 -> v3.1 migration."""

    def test_workspace_configured_maps_to_config_committed(self, tmp_path: Path) -> None:
        """workspace_configured maps to config_committed in v3.1."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {"T0": {"00": {"1": "workspace_configured"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00", 1) == "config_committed"

    def test_agent_ready_maps_to_replay_generated(self, tmp_path: Path) -> None:
        """agent_ready maps to replay_generated in v3.1."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {"T0": {"00": {"1": "agent_ready"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00", 1) == "replay_generated"

    def test_judge_ready_maps_to_judge_prompt_built(self, tmp_path: Path) -> None:
        """judge_ready maps to judge_prompt_built in v3.1."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {"T0": {"00": {"1": "judge_ready"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00", 1) == "judge_prompt_built"

    def test_run_complete_maps_to_report_written(self, tmp_path: Path) -> None:
        """run_complete maps to report_written in v3.1 (included report generation)."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {"T0": {"00": {"1": "run_complete"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00", 1) == "report_written"

    def test_unchanged_states_pass_through(self, tmp_path: Path) -> None:
        """States not in the mapping are preserved unchanged."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {
                "T0": {
                    "00": {
                        "1": "pending",
                        "2": "worktree_created",
                        "3": "baseline_captured",
                        "4": "agent_complete",
                        "5": "judge_complete",
                        "6": "checkpointed",
                        "7": "worktree_cleaned",
                        "8": "failed",
                    }
                }
            },
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00", 1) == "pending"
        assert checkpoint.get_run_state("T0", "00", 2) == "worktree_created"
        assert checkpoint.get_run_state("T0", "00", 3) == "baseline_captured"
        assert checkpoint.get_run_state("T0", "00", 4) == "agent_complete"
        assert checkpoint.get_run_state("T0", "00", 5) == "judge_complete"
        assert checkpoint.get_run_state("T0", "00", 6) == "checkpointed"
        assert checkpoint.get_run_state("T0", "00", 7) == "worktree_cleaned"
        assert checkpoint.get_run_state("T0", "00", 8) == "failed"

    def test_version_bumped_to_3_1(self, tmp_path: Path) -> None:
        """After migration, checkpoint version is 3.1."""
        data = {
            "version": "3.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.version == "3.1"

    def test_from_dict_accepts_version_2_0_and_migrates_to_v3_1(self, tmp_path: Path) -> None:
        """Verify from_dict migrates v2.0 to v3.1 automatically (via v3.0 → v3.1)."""
        data = {
            "version": "2.0",
            "experiment_id": "test-exp",
            "experiment_dir": str(tmp_path),
            "config_hash": "test-hash",
            "completed_runs": {"T0": {"00-empty": {"1": "passed", "2": "failed"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }

        checkpoint = E2ECheckpoint.from_dict(data)
        # Should be migrated to v3.1
        assert checkpoint.version == "3.1"
        assert checkpoint.experiment_id == "test-exp"
        # completed_runs should be preserved with int keys
        assert 1 in checkpoint.completed_runs["T0"]["00-empty"]
        assert 2 in checkpoint.completed_runs["T0"]["00-empty"]
        # run_states should be derived — v3.0 migration maps "passed"/"failed" -> "run_complete"
        # then v3.1 migration maps "run_complete" -> "report_written"
        assert checkpoint.get_run_state("T0", "00-empty", 1) == "report_written"
        assert checkpoint.get_run_state("T0", "00-empty", 2) == "report_written"

    def test_from_dict_accepts_version_3_0_and_migrates_to_v3_1(self, tmp_path: Path) -> None:
        """Verify from_dict migrates v3.0 to v3.1 automatically."""
        data = {
            "version": "3.0",
            "experiment_id": "test-exp",
            "experiment_dir": str(tmp_path),
            "config_hash": "test-hash",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {
                "T0": {
                    "00-empty": {
                        "1": "workspace_configured",
                        "2": "agent_ready",
                        "3": "judge_ready",
                        "4": "run_complete",
                    }
                }
            },
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }

        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.version == "3.1"
        assert checkpoint.experiment_id == "test-exp"
        assert checkpoint.experiment_state == "tiers_running"
        # Old states should be remapped
        assert checkpoint.get_run_state("T0", "00-empty", 1) == "config_committed"
        assert checkpoint.get_run_state("T0", "00-empty", 2) == "replay_generated"
        assert checkpoint.get_run_state("T0", "00-empty", 3) == "judge_prompt_built"
        assert checkpoint.get_run_state("T0", "00-empty", 4) == "report_written"

    def test_from_dict_accepts_version_3_1(self, tmp_path: Path) -> None:
        """Verify from_dict accepts version 3.1 directly."""
        data = {
            "version": "3.1",
            "experiment_id": "test-exp",
            "experiment_dir": str(tmp_path),
            "config_hash": "test-hash",
            "completed_runs": {},
            "experiment_state": "tiers_running",
            "tier_states": {},
            "subtest_states": {},
            "run_states": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_heartbeat": "",
            "status": "running",
        }

        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.version == "3.1"
        assert checkpoint.experiment_id == "test-exp"
        assert checkpoint.experiment_state == "tiers_running"


class TestCheckpointV3StateHelpers:
    """Tests for v3.0 state helper methods."""

    def test_get_run_state_returns_pending_for_unknown(self) -> None:
        """Verify get_run_state() returns pending for an unknown run."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        assert checkpoint.get_run_state("T0", "00", 1) == "pending"

    def test_set_and_get_run_state(self) -> None:
        """Verify set_run_state() and get_run_state() round-trip correctly."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        checkpoint.set_run_state("T0", "00", 1, "agent_complete")
        assert checkpoint.get_run_state("T0", "00", 1) == "agent_complete"

    def test_get_tier_state_returns_pending_for_unknown(self) -> None:
        """Verify get_tier_state() returns pending for an unknown tier."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        assert checkpoint.get_tier_state("T0") == "pending"

    def test_set_and_get_tier_state(self) -> None:
        """Verify set_tier_state() and get_tier_state() round-trip correctly."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        checkpoint.set_tier_state("T0", "subtests_running")
        assert checkpoint.get_tier_state("T0") == "subtests_running"

    def test_get_subtest_state_returns_pending_for_unknown(self) -> None:
        """Verify get_subtest_state() returns pending for an unknown subtest."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        assert checkpoint.get_subtest_state("T0", "00") == "pending"

    def test_set_and_get_subtest_state(self) -> None:
        """Verify set_subtest_state() and get_subtest_state() round-trip correctly."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        checkpoint.set_subtest_state("T0", "00", "runs_in_progress")
        assert checkpoint.get_subtest_state("T0", "00") == "runs_in_progress"

    def test_update_heartbeat(self) -> None:
        """Verify update_heartbeat() sets a non-empty timestamp."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        assert checkpoint.last_heartbeat == ""
        checkpoint.update_heartbeat()
        assert checkpoint.last_heartbeat != ""

    def test_set_run_state_updates_last_updated_at(self) -> None:
        """Verify set_run_state() updates last_updated_at timestamp."""
        checkpoint = E2ECheckpoint(experiment_id="test", experiment_dir=".", config_hash="abc")
        before = checkpoint.last_updated_at
        checkpoint.set_run_state("T0", "00", 1, "agent_complete")
        assert checkpoint.last_updated_at >= before


class TestCheckpointV3Migration:
    """Tests for v2.0 -> v3.0 migration."""

    def test_migration_preserves_completed_runs(self, tmp_path: Path) -> None:
        """completed_runs data is preserved during migration."""
        data = {
            "version": "2.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {"T0": {"00-empty": {"1": "passed"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"

    def test_migration_sets_agent_complete_state(self, tmp_path: Path) -> None:
        """agent_complete status maps to agent_complete run state (unchanged in v3.1)."""
        data = {
            "version": "2.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {"T0": {"00-empty": {"1": "agent_complete"}}},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.get_run_state("T0", "00-empty", 1) == "agent_complete"

    def test_migration_derives_experiment_state(self, tmp_path: Path) -> None:
        """experiment_state is set to tiers_running during migration."""
        data = {
            "version": "2.0",
            "experiment_id": "test",
            "experiment_dir": str(tmp_path),
            "config_hash": "abc",
            "completed_runs": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        checkpoint = E2ECheckpoint.from_dict(data)
        assert checkpoint.experiment_state == "tiers_running"

    def test_v3_1_checkpoint_roundtrip(self, tmp_path: Path) -> None:
        """Save and load v3.1 checkpoint preserves all state fields."""
        checkpoint = E2ECheckpoint(
            experiment_id="test",
            experiment_dir=str(tmp_path),
            config_hash="abc",
            status="running",
            experiment_state="tiers_running",
        )
        checkpoint.set_run_state("T0", "00", 1, "agent_complete")
        checkpoint.set_tier_state("T0", "subtests_running")
        checkpoint.set_subtest_state("T0", "00", "runs_in_progress")
        checkpoint.update_heartbeat()

        path = tmp_path / "checkpoint.json"
        save_checkpoint(checkpoint, path)

        reloaded = load_checkpoint(path)
        assert reloaded.version == "3.1"
        assert reloaded.experiment_state == "tiers_running"
        assert reloaded.get_run_state("T0", "00", 1) == "agent_complete"
        assert reloaded.get_tier_state("T0") == "subtests_running"
        assert reloaded.get_subtest_state("T0", "00") == "runs_in_progress"
        assert reloaded.last_heartbeat != ""


class TestSaveCheckpointErrors:
    """Tests for save_checkpoint error handling."""

    def test_save_checkpoint_raises_on_write_failure(self, tmp_path: Path) -> None:
        """Verify save_checkpoint raises CheckpointError on write failure."""
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="test-hash",
        )

        # Use a path that doesn't exist and can't be created
        invalid_path = tmp_path / "nonexistent" / "checkpoint.json"

        with pytest.raises(CheckpointError, match="Failed to save checkpoint"):
            save_checkpoint(checkpoint, invalid_path)

    def test_save_checkpoint_atomic_write_uses_temp_file(self, tmp_path: Path) -> None:
        """Verify save_checkpoint uses atomic write with temp file."""
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="test-hash",
        )
        checkpoint_path = tmp_path / "checkpoint.json"

        with patch("scylla.persistence.checkpoint.os.getpid", return_value=12345):
            save_checkpoint(checkpoint, checkpoint_path)

        # Verify final file exists
        assert checkpoint_path.exists()

        # Verify temp file was cleaned up (by atomic rename)
        temp_files = list(tmp_path.glob("checkpoint.tmp.*"))
        assert len(temp_files) == 0


class TestLoadCheckpointErrors:
    """Tests for load_checkpoint error handling."""

    def test_load_checkpoint_raises_on_missing_file(self, tmp_path: Path) -> None:
        """Verify load_checkpoint raises CheckpointError when file doesn't exist."""
        missing_path = tmp_path / "missing.json"

        with pytest.raises(CheckpointError, match="Checkpoint file not found"):
            load_checkpoint(missing_path)

    def test_load_checkpoint_raises_on_json_decode_error(self, tmp_path: Path) -> None:
        """Verify load_checkpoint raises CheckpointError on invalid JSON."""
        corrupt_path = tmp_path / "corrupt.json"
        corrupt_path.write_text("{ invalid json")

        with pytest.raises(CheckpointError, match="Failed to load checkpoint"):
            load_checkpoint(corrupt_path)

    def test_load_checkpoint_raises_on_read_permission_error(self, tmp_path: Path) -> None:
        """Verify load_checkpoint raises CheckpointError on read permission error."""
        checkpoint = E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir=str(tmp_path),
            config_hash="test-hash",
        )
        checkpoint_path = tmp_path / "checkpoint.json"
        save_checkpoint(checkpoint, checkpoint_path)

        # Mock open to raise PermissionError
        with patch("scylla.persistence.checkpoint.open", side_effect=PermissionError("No access")):
            with pytest.raises(CheckpointError, match="Failed to load checkpoint"):
                load_checkpoint(checkpoint_path)


class TestLoadCheckpointBakFallback:
    """Tests for load_checkpoint() .bak fallback on primary corruption."""

    def _make_checkpoint(self, tmp_path: Path, experiment_id: str = "bak-test") -> E2ECheckpoint:
        """Return a minimal valid checkpoint with the given experiment_id."""
        return E2ECheckpoint(
            experiment_id=experiment_id,
            experiment_dir=str(tmp_path),
            config_hash="abc",
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )

    def test_save_checkpoint_creates_bak_on_second_save(self, tmp_path: Path) -> None:
        """Second save_checkpoint() call produces a .bak file."""
        path = tmp_path / "checkpoint.json"
        checkpoint = self._make_checkpoint(tmp_path)
        save_checkpoint(checkpoint, path)
        # No .bak yet after first save (nothing to back up)
        bak_path = path.with_suffix(".json.bak")
        # First save: may or may not create .bak depending on whether file existed
        # Second save: must create .bak
        save_checkpoint(checkpoint, path)
        assert bak_path.exists(), ".bak must exist after second save"

    def test_load_checkpoint_falls_back_to_bak_when_primary_corrupt(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """load_checkpoint returns .bak content and logs a warning when primary is corrupt."""
        path = tmp_path / "checkpoint.json"
        checkpoint = self._make_checkpoint(tmp_path, experiment_id="good-data")

        # Write a good checkpoint (creates primary)
        save_checkpoint(checkpoint, path)
        # Write again so .bak is the good file
        save_checkpoint(checkpoint, path)

        # Corrupt the primary
        path.write_text("{ this is not valid json }")

        with caplog.at_level(logging.WARNING, logger="scylla.e2e.checkpoint"):
            loaded = load_checkpoint(path)

        assert loaded.experiment_id == "good-data"
        # Structured warning must be present
        assert any(
            "fallback" in r.message.lower() or "backup" in r.message.lower()
            for r in caplog.records
            if r.levelno == logging.WARNING
        ), f"Expected fallback warning, got: {[r.message for r in caplog.records]}"

    def test_load_checkpoint_raises_when_both_primary_and_bak_corrupt(self, tmp_path: Path) -> None:
        """load_checkpoint raises CheckpointError when both primary and .bak are corrupt."""
        path = tmp_path / "checkpoint.json"
        bak_path = path.with_suffix(".json.bak")

        # Write corrupt primary and backup
        path.write_text("{ bad primary json")
        bak_path.write_text("{ bad bak json")

        with pytest.raises(CheckpointError, match="Both primary checkpoint"):
            load_checkpoint(path)

    def test_load_checkpoint_does_not_use_bak_when_primary_valid(self, tmp_path: Path) -> None:
        """load_checkpoint returns primary content when it is valid (bak is not consulted)."""
        path = tmp_path / "checkpoint.json"
        bak_path = path.with_suffix(".json.bak")

        checkpoint_primary = self._make_checkpoint(tmp_path, experiment_id="primary-id")
        save_checkpoint(checkpoint_primary, path)

        # Write a deliberately different bak (simulates older snapshot)
        checkpoint_old = self._make_checkpoint(tmp_path, experiment_id="old-bak-id")
        import json

        bak_path.write_text(json.dumps(checkpoint_old.model_dump(), indent=2))

        loaded = load_checkpoint(path)
        # Must come from primary
        assert loaded.experiment_id == "primary-id"

    def test_load_checkpoint_raises_when_no_bak_exists_and_primary_corrupt(
        self, tmp_path: Path
    ) -> None:
        """load_checkpoint raises CheckpointError when primary is corrupt and no .bak exists."""
        path = tmp_path / "checkpoint.json"
        path.write_text("{ bad json")

        with pytest.raises(CheckpointError, match="Failed to load checkpoint"):
            load_checkpoint(path)


class TestSetRunStateBackwardCompat:
    """Tests for set_run_state() backward compat sync to completed_runs."""

    @pytest.fixture
    def checkpoint(self) -> E2ECheckpoint:
        """Create a fresh checkpoint for testing."""
        return E2ECheckpoint(
            experiment_id="test-exp",
            experiment_dir="/tmp/test",
            config_hash="abc123",
        )

    def test_set_run_state_run_finalized_syncs_passed(self, checkpoint: E2ECheckpoint) -> None:
        """run_finalized state (v3.1) syncs to completed_runs as 'passed' by default."""
        checkpoint.set_run_state("T0", "00-empty", 1, "run_finalized")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"
        assert checkpoint.is_run_completed("T0", "00-empty", 1)

    def test_set_run_state_report_written_syncs_passed(self, checkpoint: E2ECheckpoint) -> None:
        """report_written state (v3.1) syncs to completed_runs as 'passed' by default."""
        checkpoint.set_run_state("T0", "00-empty", 1, "report_written")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"

    def test_set_run_state_run_complete_syncs_passed(self, checkpoint: E2ECheckpoint) -> None:
        """run_complete state (v3.0 compat) syncs to completed_runs as 'passed' by default."""
        checkpoint.set_run_state("T0", "00-empty", 1, "run_complete")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"
        assert checkpoint.is_run_completed("T0", "00-empty", 1)

    def test_set_run_state_checkpointed_syncs_passed(self, checkpoint: E2ECheckpoint) -> None:
        """Checkpointed state syncs to completed_runs as 'passed' by default."""
        checkpoint.set_run_state("T0", "00-empty", 1, "checkpointed")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"

    def test_set_run_state_worktree_cleaned_syncs_passed(self, checkpoint: E2ECheckpoint) -> None:
        """worktree_cleaned state syncs to completed_runs as 'passed' by default."""
        checkpoint.set_run_state("T0", "00-empty", 1, "worktree_cleaned")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"

    def test_set_run_state_preserves_existing_failed_status(
        self, checkpoint: E2ECheckpoint
    ) -> None:
        """run_finalized state preserves existing 'failed' status in completed_runs."""
        # Pre-mark as failed
        checkpoint.mark_run_completed("T0", "00-empty", 1, status="failed")

        # Advance to run_finalized — should preserve "failed"
        checkpoint.set_run_state("T0", "00-empty", 1, "run_finalized")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "failed"

    def test_set_run_state_preserves_existing_passed_status(
        self, checkpoint: E2ECheckpoint
    ) -> None:
        """run_finalized state preserves existing 'passed' status in completed_runs."""
        checkpoint.mark_run_completed("T0", "00-empty", 1, status="passed")
        checkpoint.set_run_state("T0", "00-empty", 1, "run_finalized")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"

    def test_set_run_state_agent_complete_syncs_agent_complete(
        self, checkpoint: E2ECheckpoint
    ) -> None:
        """agent_complete state syncs to completed_runs as 'agent_complete'."""
        checkpoint.set_run_state("T0", "00-empty", 1, "agent_complete")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "agent_complete"

    def test_set_run_state_failed_syncs_failed(self, checkpoint: E2ECheckpoint) -> None:
        """Failed state syncs to completed_runs as 'failed'."""
        checkpoint.set_run_state("T0", "00-empty", 1, "failed")

        assert checkpoint.get_run_status("T0", "00-empty", 1) == "failed"

    def test_set_run_state_pending_does_not_sync(self, checkpoint: E2ECheckpoint) -> None:
        """Pending state does not create a completed_runs entry."""
        checkpoint.set_run_state("T0", "00-empty", 1, "pending")

        assert checkpoint.get_run_status("T0", "00-empty", 1) is None

    def test_set_run_state_worktree_created_does_not_sync(self, checkpoint: E2ECheckpoint) -> None:
        """Intermediate states do not create completed_runs entries."""
        checkpoint.set_run_state("T0", "00-empty", 1, "worktree_created")

        assert checkpoint.get_run_status("T0", "00-empty", 1) is None

    def test_set_run_state_syncs_run_states_and_completed_runs_together(
        self, checkpoint: E2ECheckpoint
    ) -> None:
        """set_run_state updates both run_states and completed_runs."""
        checkpoint.set_run_state("T0", "00-empty", 1, "run_finalized")

        # Both views are consistent
        assert checkpoint.get_run_state("T0", "00-empty", 1) == "run_finalized"
        assert checkpoint.get_run_status("T0", "00-empty", 1) == "passed"
        assert checkpoint.is_run_completed("T0", "00-empty", 1)


class TestSaveCheckpointThreadSafety:
    """Tests for save_checkpoint() thread-safety fix (dryrun3 Bug 1).

    Multiple threads calling save_checkpoint() concurrently must not produce
    ENOENT errors from simultaneous temp-file renames.
    """

    def _make_checkpoint(self, tmp_path: Path) -> E2ECheckpoint:
        """Return a minimal valid checkpoint."""
        return E2ECheckpoint(
            experiment_id="thread-test",
            experiment_dir=str(tmp_path),
            config_hash="abc",
            completed_runs={},
            started_at=datetime.now(timezone.utc).isoformat(),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            status="running",
        )

    def test_concurrent_saves_do_not_raise(self, tmp_path: Path) -> None:
        """N concurrent threads calling save_checkpoint() must all succeed."""
        checkpoint_path = tmp_path / "checkpoint.json"
        checkpoint = self._make_checkpoint(tmp_path)
        errors: list[Exception] = []

        def save_worker() -> None:
            try:
                save_checkpoint(checkpoint, checkpoint_path)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=save_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent saves raised: {errors}"
        # Final file must be valid JSON
        assert checkpoint_path.exists()
        import json

        data = json.loads(checkpoint_path.read_text())
        assert data["experiment_id"] == "thread-test"

    def test_no_stale_tmp_files_after_concurrent_saves(self, tmp_path: Path) -> None:
        """After concurrent saves, no .tmp.* files should remain."""
        checkpoint_path = tmp_path / "checkpoint.json"
        checkpoint = self._make_checkpoint(tmp_path)

        threads = [
            threading.Thread(target=save_checkpoint, args=(checkpoint, checkpoint_path))
            for _ in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        tmp_files = list(tmp_path.glob("checkpoint.tmp.*.json"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"

    def test_sequential_saves_still_work(self, tmp_path: Path) -> None:
        """Regression: single-threaded save_checkpoint() still produces valid output."""
        checkpoint_path = tmp_path / "checkpoint.json"
        checkpoint = self._make_checkpoint(tmp_path)

        save_checkpoint(checkpoint, checkpoint_path)

        assert checkpoint_path.exists()
        loaded = load_checkpoint(checkpoint_path)
        assert loaded.experiment_id == "thread-test"
