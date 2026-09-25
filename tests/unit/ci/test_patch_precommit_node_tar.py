"""Behavior tests for the CI image's pre-commit Node tar patch."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PATCH_SCRIPT = PROJECT_ROOT / "ci" / "patch_precommit_node_tar.py"
CONTAINERFILE = PROJECT_ROOT / "ci" / "Containerfile"
FIXED_TAR_VERSION = "7.5.22"
FIXED_TAR_SHA512 = (
    "3053bf433bed00e9896e484e6824ef6c670537d2fd6fe26e9c8b03c1a2a58d239"
    "d70b31e6b7349d64f54b33feb8dd7d25d3ab875fcdf792ed6e29e1838000778"
)


def _write_package(directory: Path, version: str) -> None:
    directory.mkdir(parents=True)
    (directory / "package.json").write_text(
        json.dumps({"name": "tar", "version": version}),
        encoding="utf-8",
    )
    (directory / "index.js").write_text("module.exports = {};\n", encoding="utf-8")


def _run_patch(cache_root: Path, source: Path, version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "patch",
            "--cache-root",
            str(cache_root),
            "--source",
            str(source),
            "--expected-version",
            version,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_markdownlint(cache_root: Path) -> None:
    executable = cache_root / "repo-one" / "node_env-default" / "bin" / "markdownlint-cli2"
    executable.parent.mkdir(parents=True)
    node = executable.parent / "node"
    node.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        "import sys\n"
        "document = Path(sys.argv[2])\n"
        "raise SystemExit(0 if document.read_text() == '# CI image smoke test\\n' else 2)\n",
        encoding="utf-8",
    )
    node.chmod(0o755)
    executable.write_text(
        "#!/usr/bin/env node\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def _run_verify(
    cache_root: Path,
    minimum_version: str,
    *,
    active_cache_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(PATCH_SCRIPT),
            "verify",
            "--cache-root",
            str(cache_root),
            "--minimum-version",
            minimum_version,
        ],
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "PATH": "/usr/bin:/bin",
            "PRE_COMMIT_HOME": str(active_cache_root or cache_root),
        },
        text=True,
    )


def test_replaces_every_npm_bundled_tar_copy(tmp_path: Path) -> None:
    """The patch replaces all npm-bundled tar copies in the pre-commit cache."""
    source = tmp_path / "source"
    cache_root = tmp_path / "cache"
    targets = [
        cache_root
        / repo
        / "node_env-default"
        / "lib"
        / "node_modules"
        / "npm"
        / "node_modules"
        / "tar"
        for repo in ("repo-one", "repo-two")
    ]
    _write_package(source, "7.5.22")
    for target in targets:
        _write_package(target, "7.5.19")

    result = _run_patch(cache_root, source, "7.5.22")

    assert result.returncode == 0, result.stderr
    for target in targets:
        package = json.loads((target / "package.json").read_text(encoding="utf-8"))
        assert package["version"] == "7.5.22"
        assert (target / "index.js").is_file()


def test_verify_uses_active_cache_and_runs_markdownlint(tmp_path: Path) -> None:
    """Runtime verification uses PRE_COMMIT_HOME and executes its Markdown hook."""
    cache_root = tmp_path / "pre-commit-cache"
    target = (
        cache_root
        / "repo-one"
        / "node_env-default"
        / "lib"
        / "node_modules"
        / "npm"
        / "node_modules"
        / "tar"
    )
    _write_package(target, "7.5.22")
    _write_markdownlint(cache_root)

    result = _run_verify(cache_root, "7.5.21")

    assert result.returncode == 0, result.stderr


def test_verify_rejects_a_cache_other_than_precommit_home(tmp_path: Path) -> None:
    """Runtime verification cannot validate an inactive cache by mistake."""
    cache_root = tmp_path / "candidate-cache"
    active_cache_root = tmp_path / "active-cache"
    target = (
        cache_root
        / "repo-one"
        / "node_env-default"
        / "lib"
        / "node_modules"
        / "npm"
        / "node_modules"
        / "tar"
    )
    _write_package(target, "7.5.22")
    _write_markdownlint(cache_root)
    active_cache_root.mkdir()

    result = _run_verify(
        cache_root,
        "7.5.21",
        active_cache_root=active_cache_root,
    )

    assert result.returncode != 0
    assert "does not match PRE_COMMIT_HOME" in result.stderr


def test_verify_rejects_vulnerable_tar_in_the_active_cache(tmp_path: Path) -> None:
    """The active cache fails verification when npm still contains vulnerable tar."""
    cache_root = tmp_path / "pre-commit-cache"
    target = (
        cache_root
        / "repo-one"
        / "node_env-default"
        / "lib"
        / "node_modules"
        / "npm"
        / "node_modules"
        / "tar"
    )
    _write_package(target, "7.5.19")
    _write_markdownlint(cache_root)

    result = _run_verify(cache_root, "7.5.21")

    assert result.returncode != 0
    assert "7.5.19 < 7.5.21" in result.stderr


def test_fails_closed_when_no_npm_bundled_tar_exists(tmp_path: Path) -> None:
    """An empty cache cannot produce a successful patch result."""
    source = tmp_path / "source"
    cache_root = tmp_path / "cache"
    _write_package(source, "7.5.22")
    cache_root.mkdir()

    result = _run_patch(cache_root, source, "7.5.22")

    assert result.returncode != 0


def test_rejects_a_source_below_the_security_floor(tmp_path: Path) -> None:
    """The patch rejects tar versions that do not fix CVE-2026-73566."""
    source = tmp_path / "source"
    cache_root = tmp_path / "cache"
    target = (
        cache_root
        / "repo-one"
        / "node_env-default"
        / "lib"
        / "node_modules"
        / "npm"
        / "node_modules"
        / "tar"
    )
    _write_package(source, "7.5.19")
    _write_package(target, "7.5.19")

    result = _run_patch(cache_root, source, "7.5.19")

    assert result.returncode != 0
    package = json.loads((target / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == "7.5.19"


def test_container_patches_tar_in_the_hook_install_layer() -> None:
    """The vulnerable hook cache never survives in an intermediate image layer."""
    text = CONTAINERFILE.read_text(encoding="utf-8")
    hook_layer = text.split("RUN git init .", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

    assert "COPY ci/patch_precommit_node_tar.py /tmp/patch_precommit_node_tar.py" in text
    assert "uv run pre-commit install-hooks" in hook_layer
    assert f"tar-{FIXED_TAR_VERSION}.tgz" in hook_layer
    assert FIXED_TAR_SHA512 in hook_layer
    assert "python3 /tmp/patch_precommit_node_tar.py patch" in hook_layer
    assert '--cache-root "$PRE_COMMIT_HOME"' in hook_layer
    assert f"--expected-version {FIXED_TAR_VERSION}" in hook_layer


def test_final_ci_user_uses_the_patched_cache_at_its_build_path() -> None:
    """The final ci user consumes and validates the cache without relocating it."""
    text = CONTAINERFILE.read_text(encoding="utf-8")
    builder_stage = text.split(" AS builder", maxsplit=1)[1].split("\nFROM ", maxsplit=1)[0]
    runtime_stage = text.rsplit("\nFROM ", maxsplit=1)[1]
    builder_home = re.search(r"PRE_COMMIT_HOME=([^ \\\n]+)", builder_stage)
    runtime_home = re.search(r"PRE_COMMIT_HOME=([^ \\\n]+)", runtime_stage)

    assert builder_home is not None, "builder must set PRE_COMMIT_HOME"
    assert runtime_home is not None, "runtime must set PRE_COMMIT_HOME"
    cache_root = builder_home.group(1)
    assert cache_root == runtime_home.group(1)
    assert cache_root.startswith("/")

    copy = f"COPY --from=builder --chown=ci:ci {cache_root} {cache_root}"
    assert copy in runtime_stage
    assert '--cache-root "$PRE_COMMIT_HOME"' in builder_stage
    assert "cp -r /root/.cache/pre-commit" not in runtime_stage
    assert "2>/dev/null || true" not in runtime_stage

    user_index = runtime_stage.index("USER ci")
    verify_index = runtime_stage.index("patch_precommit_node_tar.py verify")
    assert user_index < verify_index
    assert '--cache-root "$PRE_COMMIT_HOME"' in runtime_stage
    assert "--minimum-version 7.5.21" in runtime_stage
