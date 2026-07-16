"""E2E testing framework for Scylla.

This module provides a progressive optimization framework for evaluating
AI agent capabilities across tiers T0-T6. Each tier can have multiple
sub-tests, and the best-performing sub-test becomes the baseline for
the next tier.

Primary class:
    EvalOrchestrator: Coordinates end-to-end experiment execution,
        managing tier progression, checkpoint persistence, rate limiting,
        and LLM API calls for judging.
"""

from scylla.e2e.llm_judge import run_llm_judge
from scylla.e2e.llm_judge_models import JudgeResult
from scylla.e2e.models import (
    E2ERunResult,
    ExperimentConfig,
    ExperimentResult,
    SubTestConfig,
    SubTestResult,
    TierConfig,
    TierID,
    TierResult,
)
from scylla.e2e.orchestrator import EvalOrchestrator, OrchestratorConfig
from scylla.e2e.rate_limit import (
    RateLimitError,
    RateLimitInfo,
    detect_rate_limit,
    parse_retry_after,
    wait_for_rate_limit,
)
from scylla.e2e.subtest_state_machine import SubtestStateMachine
from scylla.persistence.checkpoint import (
    CheckpointError,
    ConfigMismatchError,
    E2ECheckpoint,
    compute_config_hash,
    get_experiment_status,
    load_checkpoint,
    save_checkpoint,
    validate_checkpoint_config,
)

__all__ = [
    # Checkpoint
    "CheckpointError",
    "ConfigMismatchError",
    "E2ECheckpoint",
    "E2ERunResult",
    "EvalOrchestrator",
    "ExperimentConfig",
    "ExperimentResult",
    "JudgeResult",
    "OrchestratorConfig",
    "RateLimitError",
    "RateLimitInfo",
    "SubTestConfig",
    "SubTestResult",
    # State machines
    "SubtestStateMachine",
    "TierConfig",
    "TierID",
    "TierResult",
    "compute_config_hash",
    "detect_rate_limit",
    "get_experiment_status",
    "load_checkpoint",
    "parse_retry_after",
    "run_llm_judge",
    "save_checkpoint",
    "validate_checkpoint_config",
    "wait_for_rate_limit",
]
