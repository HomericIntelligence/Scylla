"""Data loader for experiment results.

Loads experiment data from the fullruns/ directory hierarchy and converts
to structured dataclasses for analysis. Uses existing e2e.models data
structures to avoid duplication.

This module is a thin facade — its implementation lives in
:mod:`scylla.analysis.loader_internals`. The public API (every name listed
in ``__all__``) is preserved for backward compatibility.
"""

from __future__ import annotations

from scylla.analysis.loader_internals.experiment_loader import (
    load_all_experiments as load_all_experiments,
)
from scylla.analysis.loader_internals.experiment_loader import (
    load_experiment as load_experiment,
)
from scylla.analysis.loader_internals.experiment_loader import (
    load_rubric_weights as load_rubric_weights,
)
from scylla.analysis.loader_internals.models import (
    CriterionScore as CriterionScore,
)
from scylla.analysis.loader_internals.models import (
    ItemScore as ItemScore,
)
from scylla.analysis.loader_internals.models import (
    JudgeEvaluation as JudgeEvaluation,
)
from scylla.analysis.loader_internals.models import (
    ModelUsage as ModelUsage,
)
from scylla.analysis.loader_internals.models import (
    RubricConflict as RubricConflict,
)
from scylla.analysis.loader_internals.models import (
    RubricConflictError as RubricConflictError,
)
from scylla.analysis.loader_internals.models import (
    RunData as RunData,
)
from scylla.analysis.loader_internals.run_loader import (
    load_agent_result as load_agent_result,
)
from scylla.analysis.loader_internals.run_loader import (
    load_judgment as load_judgment,
)
from scylla.analysis.loader_internals.run_loader import (
    load_run as load_run,
)
from scylla.analysis.loader_internals.run_loader import (
    model_id_to_display as model_id_to_display,
)
from scylla.analysis.loader_internals.run_loader import (
    parse_judge_model as parse_judge_model,
)
from scylla.analysis.loader_internals.run_loader import (
    resolve_agent_model as resolve_agent_model,
)
from scylla.analysis.loader_internals.validators import (
    validate_bool as validate_bool,
)
from scylla.analysis.loader_internals.validators import (
    validate_int as validate_int,
)
from scylla.analysis.loader_internals.validators import (
    validate_numeric as validate_numeric,
)

__all__ = [
    "CriterionScore",
    "ItemScore",
    "JudgeEvaluation",
    "ModelUsage",
    "RubricConflict",
    "RubricConflictError",
    "RunData",
    "load_agent_result",
    "load_all_experiments",
    "load_experiment",
    "load_judgment",
    "load_rubric_weights",
    "load_run",
    "model_id_to_display",
    "parse_judge_model",
    "resolve_agent_model",
    "validate_bool",
    "validate_int",
    "validate_numeric",
]
