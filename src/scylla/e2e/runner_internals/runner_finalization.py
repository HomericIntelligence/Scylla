"""RunnerFinalization collaborator — result writing, summary, cleanup.

Owns: aggregating tier results, writing tier/final result files, generating
hierarchical reports, emitting metrics, handling experiment interrupts, and
marking the checkpoint complete.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from scylla.e2e.checkpoint_finalizer import CheckpointFinalizer
from scylla.persistence.experiment_result_writer import ExperimentResultWriter
from scylla.e2e.models import (
    ExperimentResult,
    ExperimentState,
    TierID,
    TierResult,
)

if TYPE_CHECKING:
    from scylla.e2e.runner_internals.runner_core import E2ERunner

logger = logging.getLogger(__name__)


class RunnerFinalization:
    """Result writing, summary, cleanup, and metric emission."""

    def __init__(self, runner: E2ERunner) -> None:
        """Bind this collaborator to the owning :class:`E2ERunner`."""
        self._runner = runner

    def result_writer(self) -> ExperimentResultWriter:
        """Create an ExperimentResultWriter bound to current state."""
        runner = self._runner
        return ExperimentResultWriter(
            experiment_dir=runner.experiment_dir,
            tier_manager=runner.tier_manager,
        )

    def finalizer(self) -> CheckpointFinalizer:
        """Create a CheckpointFinalizer bound to current state."""
        runner = self._runner
        return CheckpointFinalizer(runner.config, runner.results_base_dir)

    def aggregate_results(
        self,
        tier_results: dict[TierID, TierResult],
        start_time: datetime,
    ) -> ExperimentResult:
        """Aggregate tier results into an ExperimentResult."""
        return self.result_writer().aggregate_results(self._runner.config, tier_results, start_time)

    def save_tier_result(self, tier_id: TierID, result: TierResult) -> None:
        """Save a single tier's result and generate hierarchical reports."""
        self.result_writer().save_tier_result(tier_id, result)

    def save_final_results(self, result: ExperimentResult) -> None:
        """Save the final experiment result."""
        self.result_writer().save_final_results(result)

    def generate_report(self, result: ExperimentResult) -> None:
        """Generate hierarchical experiment reports."""
        self.result_writer().generate_report(result)

    def handle_experiment_interrupt(self, checkpoint_path: Path) -> None:
        """Handle graceful shutdown on interrupt."""
        runner = self._runner
        self.finalizer().handle_experiment_interrupt(runner.checkpoint, checkpoint_path)

    def validate_filesystem_on_resume(self, current_state: ExperimentState) -> None:
        """Cross-validate filesystem against checkpoint state on resume."""
        runner = self._runner
        if not runner.experiment_dir:
            return
        self.finalizer().validate_filesystem_on_resume(runner.experiment_dir, current_state)

    def mark_checkpoint_completed(self) -> None:
        """Mark the checkpoint as completed if state is consistent."""
        runner = self._runner
        if runner.checkpoint and runner.experiment_dir:
            self.finalizer().mark_checkpoint_completed(runner.checkpoint, runner.experiment_dir)

    def emit_experiment_metrics(
        self,
        tier_results: dict[TierID, TierResult],
        result: ExperimentResult,
    ) -> None:
        """Emit per-tier counters and gauges via the configured MetricEmitter.

        Failures in the emitter must not break experiment finalization.
        """
        del result  # currently only per-tier metrics; reserved for future use
        runner = self._runner
        experiment_id = runner.config.experiment_id
        try:
            for tier_id, tier_result in tier_results.items():
                tier_label = tier_id.value
                best = (
                    tier_result.subtest_results.get(tier_result.best_subtest)
                    if tier_result.best_subtest
                    else None
                )
                pass_rate = best.pass_rate if best is not None else 0.0
                outcome = "pass" if pass_rate > 0 else "fail"
                runner._emitter.emit_counter(
                    "scylla_tier_runs_total",
                    1,
                    labels={"tier": tier_label, "outcome": outcome},
                )

                pass_runs = 0
                fail_runs = 0
                for subtest in tier_result.subtest_results.values():
                    for run in subtest.runs:
                        if run.judge_passed:
                            pass_runs += 1
                        else:
                            fail_runs += 1
                if pass_runs:
                    runner._emitter.emit_counter(
                        "scylla_subtest_runs_total",
                        pass_runs,
                        labels={"tier": tier_label, "outcome": "pass"},
                    )
                if fail_runs:
                    runner._emitter.emit_counter(
                        "scylla_subtest_runs_total",
                        fail_runs,
                        labels={"tier": tier_label, "outcome": "fail"},
                    )

                labels = {"experiment": experiment_id, "tier": tier_label}
                runner._emitter.emit_gauge(
                    "scylla_experiment_pass_rate", float(pass_rate), labels=labels
                )
                cop = tier_result.cost_of_pass
                if cop != float("inf"):
                    runner._emitter.emit_gauge(
                        "scylla_experiment_cost_of_pass_usd",
                        float(cop),
                        labels=labels,
                    )
                runner._emitter.emit_gauge(
                    "scylla_experiment_latency_seconds",
                    float(tier_result.total_duration),
                    labels=labels,
                )
        except Exception as e:  # emitter must never break finalization
            logger.warning(f"Metric emission failed (non-fatal): {e}")
