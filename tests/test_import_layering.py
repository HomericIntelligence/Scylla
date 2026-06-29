"""Import-linter contract enforcement.

Runs ``lint-imports`` as a pytest test so layering violations surface in
the unit test job (not just the lint job).  Failures here mean a DIP
violation was introduced — fix the import, do not weaken the contract.
"""

import shutil
import subprocess


def test_import_layering_contracts() -> None:
    """All import-linter contracts must pass."""
    lint_imports_bin = shutil.which("lint-imports")
    if lint_imports_bin is None:
        # import-linter is in the lint environment; skip gracefully in dev envs
        # that have not installed it.  CI always uses the lint environment.
        import pytest

        pytest.skip("lint-imports not found in PATH; install import-linter to run this check")

    result = subprocess.run(
        [lint_imports_bin, "--config", "pyproject.toml"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "import-linter contract violation detected.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
