"""Configuration loader for Scylla.

This module provides the ConfigLoader class for loading and merging YAML
configuration files with a three-level priority hierarchy:
    test-specific > model defaults > global defaults
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .models import (
    ConfigurationError,
    DefaultsConfig,
    EvalCase,
    ModelConfig,
    Rubric,
    ScyllaConfig,
    TierConfig,
)
from .validation import (
    validate_defaults_filename,
    validate_filename_model_id_consistency,
    validate_filename_tier_consistency,
    validate_model_config_referenced,
    validate_tier_config_referenced,
)

logger = logging.getLogger(__name__)

_SCHEMAS_DIR = Path(__file__).parent.parent.parent.parent / "schemas"
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


def _validate_schema(data: dict[str, Any], schema_name: str, path: Path) -> None:
    """Validate data against a JSON schema, with module-level caching.

    Reads the schema file from disk on first call for a given schema_name;
    subsequent calls reuse the cached schema dict.

    Args:
        data: Parsed YAML data to validate
        schema_name: Schema filename stem (e.g., "defaults", "tier", "model")
        path: Config file path (used in error messages)

    Raises:
        ConfigurationError: If validation fails

    """
    schema_file = f"{schema_name}.schema.json"
    if schema_file not in _SCHEMA_CACHE:
        schema_path = _SCHEMAS_DIR / schema_file
        with open(schema_path) as f:
            _SCHEMA_CACHE[schema_file] = json.load(f)
    try:
        jsonschema.validate(data, _SCHEMA_CACHE[schema_file])
    except jsonschema.ValidationError as e:
        raise ConfigurationError(
            f"Invalid {schema_name} configuration in {path}: {e.message}"
        ) from e


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Values in override take precedence. Nested dicts are merged recursively.
    Lists are replaced entirely (not appended).

    Args:
        base: Base dictionary
        override: Override dictionary (values take precedence)

    Returns:
        Merged dictionary

    """
    result = base.copy()

    for key, value in override.items():
        if value is None:
            # Skip None values - don't override with None
            continue

        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = _deep_merge(result[key], value)
        else:
            # Override value (including lists)
            result[key] = value

    return result


class ConfigLoader:
    """Load and merge configuration files for Scylla.

    Supports a three-level priority hierarchy:
        1. config/defaults.yaml (REQUIRED - base configuration)
        2. config/models/<model_id>.yaml (optional - model-specific)
        3. tests/<test_id>/config.yaml (optional - test-specific)

    Priority order: test > model > defaults

    Example:
        loader = ConfigLoader()
        config = loader.load(
            test_id="001-justfile-to-makefile",
            model_id=DEFAULT_JUDGE_MODEL,
        )

    """

    def __init__(self, base_path: str | Path | None = None) -> None:
        """Initialize the ConfigLoader.

        Args:
            base_path: Base path for configuration files. Defaults to current working directory.

        """
        if base_path is None:
            self.base_path = Path.cwd()
        else:
            self.base_path = Path(base_path)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML content as dict

        Raises:
            ConfigurationError: If file cannot be read or parsed

        """
        try:
            with open(path) as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except FileNotFoundError:
            raise ConfigurationError(f"Configuration file not found: {path}") from None
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {path}: {e}") from e
        except PermissionError:
            raise ConfigurationError(f"Permission denied reading: {path}") from None

    def _load_yaml_optional(self, path: Path) -> dict[str, Any] | None:
        """Load a YAML file if it exists.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML content as dict, or None if file doesn't exist

        Raises:
            ConfigurationError: If file exists but cannot be parsed

        """
        if not path.exists():
            return None

        try:
            with open(path) as f:
                content = yaml.safe_load(f)
                return content if content is not None else {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML in {path}: {e}") from e
        except PermissionError:
            raise ConfigurationError(f"Permission denied reading: {path}") from None

    # -------------------------------------------------------------------------
    # Test Case Loading
    # -------------------------------------------------------------------------

    def load_test(self, test_id: str) -> EvalCase:
        """Load a test case configuration.

        Args:
            test_id: Test identifier (e.g., "001-justfile-to-makefile")

        Returns:
            EvalCase model

        Raises:
            ConfigurationError: If test configuration is invalid or missing

        """
        test_path = self.base_path / "tests" / test_id / "test.yaml"
        data = self._load_yaml(test_path)

        if not test_id.startswith("_"):
            _validate_schema(data, "test", test_path)

        try:
            return EvalCase(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid test configuration in {test_path}: {e}") from e

    # -------------------------------------------------------------------------
    # Rubric Loading
    # -------------------------------------------------------------------------

    def load_rubric(self, test_id: str) -> Rubric:
        """Load a rubric for a test case.

        Args:
            test_id: Test identifier

        Returns:
            Rubric model

        Raises:
            ConfigurationError: If rubric is invalid or missing

        """
        rubric_path = self.base_path / "tests" / test_id / "expected" / "rubric.yaml"
        data = self._load_yaml(rubric_path)

        if not test_id.startswith("_"):
            _validate_schema(data, "rubric", rubric_path)

        try:
            return Rubric(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid rubric configuration in {rubric_path}: {e}") from e

    # -------------------------------------------------------------------------
    # Tier Loading
    # -------------------------------------------------------------------------

    def load_tier(self, tier: str) -> TierConfig:
        """Load a tier configuration.

        Args:
            tier: Tier identifier (e.g., "t0", "t1")

        Returns:
            TierConfig model

        Raises:
            ConfigurationError: If tier configuration is invalid or missing

        """
        # Skip normalization for test fixtures (prefixed with _)
        if not tier.startswith("_"):
            tier = tier.lower().strip()
            if not tier.startswith("t"):
                tier = f"t{tier}"

        tier_path = self.base_path / "config" / "tiers" / f"{tier}.yaml"
        data = self._load_yaml(tier_path)

        # Ensure tier field is set
        if "tier" not in data:
            data["tier"] = tier

        if not tier.startswith("_"):
            _validate_schema(data, "tier", tier_path)

        try:
            config = TierConfig(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid tier configuration in {tier_path}: {e}") from e

        warnings = validate_filename_tier_consistency(tier_path, config.tier)
        for warning in warnings:
            logger.warning(warning)

        return config

    def load_all_tiers(self) -> dict[str, TierConfig]:
        """Load all available tier configurations.

        Returns:
            Dict mapping tier names to TierConfig models

        Raises:
            ConfigurationError: If any tier configuration is invalid

        """
        tiers_dir = self.base_path / "config" / "tiers"
        result: dict[str, TierConfig] = {}

        if not tiers_dir.exists():
            return result

        for tier_file in sorted(tiers_dir.glob("*.yaml")):
            # Skip test fixtures (prefixed with _), matching load_all_models() behaviour
            if tier_file.name.startswith("_"):
                continue
            tier_name = tier_file.stem  # e.g., "t0" from "t0.yaml"
            tier_config = self.load_tier(tier_name)

            # Validate that config.tier matches the filename stem.
            # Apply the same normalization as load_tier() to avoid false positives.
            expected = tier_name.lower().strip()
            if not expected.startswith("t"):
                expected = f"t{expected}"

            if tier_config.tier != expected:
                raise ConfigurationError(
                    f"Tier ID mismatch in {tier_file}: "
                    f"filename implies '{expected}' but config declares tier='{tier_config.tier}'"
                )

            result[expected] = tier_config

        # Check for orphaned tier configs (not referenced by config/ or tests/)
        search_roots = [self.base_path / "config", self.base_path / "tests"]
        for tier_file in sorted(tiers_dir.glob("*.yaml")):
            if tier_file.name.startswith("_"):
                continue
            orphan_warnings = validate_tier_config_referenced(tier_file, search_roots)
            for warning in orphan_warnings:
                logger.warning(warning)

        return result

    # -------------------------------------------------------------------------
    # Model Loading
    # -------------------------------------------------------------------------

    def load_model(self, model_id: str) -> ModelConfig | None:
        """Load a model configuration.

        Args:
            model_id: Model identifier

        Returns:
            ModelConfig model, or None if not found

        Raises:
            ConfigurationError: If model configuration exists but is invalid

        """
        model_path = self.base_path / "config" / "models" / f"{model_id}.yaml"
        data = self._load_yaml_optional(model_path)

        if data is None:
            return None

        # Ensure model_id is set
        if "model_id" not in data:
            data["model_id"] = model_id

        if not model_id.startswith("_"):
            _validate_schema(data, "model", model_path)

        try:
            config = ModelConfig(**data)
        except Exception as e:
            raise ConfigurationError(f"Invalid model configuration in {model_path}: {e}") from e

        # Validate filename/model_id consistency
        warnings = validate_filename_model_id_consistency(model_path, config.model_id)
        for warning in warnings:
            logger.warning(warning)

        return config

    def load_all_models(self) -> dict[str, ModelConfig]:
        """Load all available model configurations.

        Returns:
            Dict mapping model keys (from filename) to ModelConfig models

        Raises:
            ConfigurationError: If any model configuration is invalid

        """
        models_dir = self.base_path / "config" / "models"
        result: dict[str, ModelConfig] = {}

        if not models_dir.exists():
            return result

        for model_file in sorted(models_dir.glob("*.yaml")):
            # Skip special files
            if model_file.name.startswith("."):
                continue

            model_key = model_file.stem  # e.g., "claude-opus-4-6" from "claude-opus-4-6.yaml"
            model = self.load_model(model_key)
            if model:
                result[model_key] = model

        # Check for orphaned model configs (not referenced by config/ or tests/)
        # Note: filename/model_id mismatches here are warnings (not errors) because
        # load_model() already logs them individually, and model configs may be loaded
        # by key (filename stem) rather than by the model_id field. Raising here
        # would prevent loading any models when a mismatch exists, which is too strict
        # for an aggregation function. load_all_tiers() raises because tier IDs are
        # always the canonical lookup key and mismatches indicate broken configs.
        search_roots = [self.base_path / "config", self.base_path / "tests"]
        for model_file in sorted(models_dir.glob("*.yaml")):
            if model_file.name.startswith(".") or model_file.stem.startswith("_"):
                continue
            orphan_warnings = validate_model_config_referenced(model_file, search_roots)
            for warning in orphan_warnings:
                logger.warning(warning)

        return result

    # -------------------------------------------------------------------------
    # Defaults Loading
    # -------------------------------------------------------------------------

    def load_defaults(self) -> DefaultsConfig:
        """Load global defaults configuration.

        Loads config/defaults.yaml. Note: DefaultsConfig has no model_id-style
        field, so field-level filename consistency validation (as applied to
        ModelConfig) is intentionally not performed. A stem-only check is
        applied to catch gross misconfiguration (wrong file entirely).

        Returns:
            DefaultsConfig model

        Raises:
            ConfigurationError: If defaults.yaml is missing or invalid

        """
        defaults_path = self.base_path / "config" / "defaults.yaml"
        data = self._load_yaml(defaults_path)

        # Validate filename stem only — DefaultsConfig has no ID field,
        # so model_id↔filename consistency checks are not applicable.
        for warning in validate_defaults_filename(defaults_path):
            logger.warning(warning)

        if not defaults_path.stem.startswith("_"):
            _validate_schema(data, "defaults", defaults_path)

        try:
            config = DefaultsConfig(**data)
        except Exception as e:
            raise ConfigurationError(
                f"Invalid defaults configuration in {defaults_path}: {e}"
            ) from e

        # Apply NATS env var overrides (precedence: env var > YAML > Pydantic default)
        nats_overrides: dict[str, object] = {}
        nats_enabled_env = os.environ.get("NATS_ENABLED", "")
        if nats_enabled_env:
            nats_overrides["enabled"] = nats_enabled_env.lower() in ("1", "true", "yes")
        nats_url_env = os.environ.get("NATS_URL")
        if nats_url_env is not None:
            nats_overrides["url"] = nats_url_env
        nats_stream_env = os.environ.get("NATS_STREAM")
        if nats_stream_env is not None:
            nats_overrides["stream"] = nats_stream_env
        nats_durable_env = os.environ.get("NATS_DURABLE_NAME")
        if nats_durable_env is not None:
            nats_overrides["durable_name"] = nats_durable_env

        if nats_overrides:
            config = config.model_copy(
                update={"nats": config.nats.model_copy(update=nats_overrides)}
            )

        return config

    # -------------------------------------------------------------------------
    # Merged Configuration Loading
    # -------------------------------------------------------------------------

    def load(self, test_id: str, model_id: str) -> ScyllaConfig:
        """Load and merge configuration for a test run.

        Applies three-level priority hierarchy:
            1. config/defaults.yaml (base)
            2. config/models/<model_id>.yaml (optional)
            3. tests/<test_id>/config.yaml (optional)

        Args:
            test_id: Test identifier
            model_id: Model identifier

        Returns:
            ScyllaConfig with merged configuration

        Raises:
            ConfigurationError: If configuration is invalid

        """
        # Load and validate defaults (required) — routes through load_defaults()
        # for schema validation and filename consistency checks.
        defaults = self.load_defaults()

        # Build base config from validated DefaultsConfig
        config_data: dict[str, Any] = {
            "runs_per_tier": defaults.evaluation.runs_per_tier,
            "timeout_seconds": defaults.evaluation.timeout,
            "max_cost_usd": defaults.max_cost_usd,
            "judge": defaults.judge,
            "adapters": defaults.adapters,
            "cleanup": defaults.cleanup,
            "output": defaults.output,
            "logging": defaults.logging,
            "metrics": defaults.metrics,
            "nats": defaults.nats,
        }

        # Load model config (optional)
        model_config = self.load_model(model_id)

        # Apply model overrides
        if model_config:
            if model_config.timeout_seconds is not None:
                config_data["timeout_seconds"] = model_config.timeout_seconds
            if model_config.max_cost_usd is not None:
                config_data["max_cost_usd"] = model_config.max_cost_usd

        # Load test-specific config (optional)
        test_config_path = self.base_path / "tests" / test_id / "config.yaml"
        test_config_data = self._load_yaml_optional(test_config_path)

        if test_config_data:
            config_data = _deep_merge(config_data, test_config_data)

        # Add context
        config_data["test_id"] = test_id
        config_data["model_id"] = model_id
        config_data["model"] = model_config

        try:
            return ScyllaConfig(**config_data)
        except Exception as e:
            raise ConfigurationError(f"Failed to create merged configuration: {e}") from e
