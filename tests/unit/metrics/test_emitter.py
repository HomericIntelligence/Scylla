"""Unit tests for :mod:`scylla.metrics.emitter`."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from scylla.metrics.emitter import (
    MetricEmitter,
    NoOpEmitter,
    PrometheusTextfileEmitter,
    get_default_emitter,
)


def test_noop_emitter_is_silent(tmp_path: Path) -> None:
    """NoOpEmitter calls return without raising and write nothing to disk."""
    emitter = NoOpEmitter()
    # Calls execute and produce no side effects.
    emitter.emit_counter("foo", 1)
    emitter.emit_gauge("bar", 2.5, labels={"k": "v"})
    # Nothing was written to disk.
    assert list(tmp_path.iterdir()) == []


def test_prometheus_textfile_emitter_writes_counter_line(tmp_path: Path) -> None:
    """A counter emit produces one Prometheus-format line."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_counter("scylla_runs_total", 7)

    content = out.read_text()
    assert content == "scylla_runs_total 7.0\n"


def test_prometheus_textfile_emitter_writes_gauge_line(tmp_path: Path) -> None:
    """A gauge emit produces one Prometheus-format line."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_gauge("scylla_pass_rate", 0.42)

    content = out.read_text()
    assert content == "scylla_pass_rate 0.42\n"


def test_prometheus_textfile_emitter_appends_subsequent_emits(
    tmp_path: Path,
) -> None:
    """Successive emits append lines to the destination file."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_counter("a", 1)
    emitter.emit_gauge("b", 2.0)

    lines = out.read_text().splitlines()
    assert lines == ["a 1.0", "b 2.0"]


def test_prometheus_textfile_emitter_renders_labels(tmp_path: Path) -> None:
    """Labels render as ``{key="value",...}`` sorted by key."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_gauge(
        "scylla_cop_dollars",
        1.23,
        labels={"tier": "T2", "model": "haiku"},
    )

    content = out.read_text()
    # Labels render sorted by key.
    assert content == 'scylla_cop_dollars{model="haiku",tier="T2"} 1.23\n'


def test_prometheus_textfile_emitter_escapes_label_values(tmp_path: Path) -> None:
    """Backslash, double-quote, and newline are escaped in label values."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_counter(
        "x",
        1,
        labels={"path": 'a"b\\c\nd'},
    )

    content = out.read_text()
    assert content == 'x{path="a\\"b\\\\c\\nd"} 1.0\n'


def test_prometheus_textfile_emitter_creates_parent_dir(tmp_path: Path) -> None:
    """Missing parent directories are created on construction."""
    out = tmp_path / "nested" / "dir" / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    emitter.emit_counter("c", 1)

    assert out.exists()


def test_prometheus_textfile_emitter_atomic_write_uses_replace(
    tmp_path: Path,
) -> None:
    """The emitter uses os.replace (atomic rename) on the same directory."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)

    # os.replace is the kernel-atomic rename; if the implementation uses a
    # plain open(...,"w") instead, this assertion catches that regression.
    with mock.patch(
        "scylla.metrics.emitter.os.replace",
        wraps=os.replace,
    ) as replace:
        emitter.emit_counter("c", 1)
        assert replace.call_count == 1
        # Source file must be in the same directory as the destination
        # (rename across filesystems is not atomic).
        src = Path(replace.call_args.args[0])
        dst = Path(replace.call_args.args[1])
        assert src.parent == dst.parent == out.parent

    # No leftover .tmp files.
    leftovers = [p for p in out.parent.iterdir() if p.name != out.name]
    assert leftovers == []


def test_prometheus_textfile_emitter_never_partial_on_concurrent_read(
    tmp_path: Path,
) -> None:
    """The destination file is always a complete snapshot between emits."""
    out = tmp_path / "scylla.prom"
    emitter = PrometheusTextfileEmitter(out)
    for i in range(20):
        emitter.emit_counter("c", i)
        # Every read between emits is well-formed (ends with newline,
        # no trailing partial line).
        text = out.read_text()
        assert text.endswith("\n")
        for line in text.splitlines():
            # Each line is "<name>[{labels}] <value>" — i.e. exactly
            # one space between metric and value.
            assert " " in line
            head, _, tail = line.rpartition(" ")
            assert head and tail


def test_get_default_emitter_returns_noop_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without SCYLLA_METRICS_PATH, the default emitter is NoOpEmitter."""
    monkeypatch.delenv("SCYLLA_METRICS_PATH", raising=False)
    assert isinstance(get_default_emitter(), NoOpEmitter)


def test_get_default_emitter_returns_textfile_with_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With SCYLLA_METRICS_PATH set, the default emitter writes to that path."""
    target = tmp_path / "scylla.prom"
    monkeypatch.setenv("SCYLLA_METRICS_PATH", str(target))
    emitter = get_default_emitter()
    assert isinstance(emitter, PrometheusTextfileEmitter)
    # Confirm the configured emitter writes to the requested path.
    emitter.emit_counter("ok", 1)
    assert target.exists()


def test_metric_emitter_is_abstract() -> None:
    """MetricEmitter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        MetricEmitter()  # type: ignore[abstract]
