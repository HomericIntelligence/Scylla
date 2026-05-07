"""ResourceManifest model for tracking subtest resource usage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ResourceManifest(BaseModel):
    """Records which resources were used for a subtest run.

    Enables reproducibility without copying files. Instead of duplicating
    CLAUDE.md and .claude/ to results directories, this manifest records
    exactly what was used so runs can be reproduced by re-reading the
    fixture config.

    Attributes:
        tier_id: The tier identifier
        subtest_id: The subtest identifier
        fixture_config_path: Path to original config.yaml in fixtures/
        resources: The resolved resource specification
        composed_at: ISO timestamp when config was composed
        claude_md_hash: SHA256 of composed CLAUDE.md for verification
        inherited_from: Previous tier's resources (for inheritance chain)

    """

    tier_id: str
    subtest_id: str
    fixture_config_path: str
    resources: dict[str, Any]
    composed_at: str
    claude_md_hash: str | None = None
    inherited_from: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")

    def save(self, path: Path) -> None:
        """Save manifest to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> ResourceManifest:
        """Load manifest from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            tier_id=data["tier_id"],
            subtest_id=data["subtest_id"],
            fixture_config_path=data["fixture_config_path"],
            resources=data["resources"],
            composed_at=data["composed_at"],
            claude_md_hash=data.get("claude_md_hash"),
            inherited_from=data.get("inherited_from"),
        )
