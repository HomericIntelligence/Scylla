"""Back-compat shim — experiment_result_writer moved to scylla.persistence in #1940."""

from scylla.persistence.experiment_result_writer import (
    ExperimentResultWriter as ExperimentResultWriter,
)
