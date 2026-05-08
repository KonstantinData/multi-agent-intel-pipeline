from __future__ import annotations

from pathlib import Path

import pytest

from src.exporters.json_export import _ensure_within_runs_dir
from src.orchestration.run_paths import (
    InvalidRunIdError,
    resolve_path_within_runs_root,
    resolve_run_dir,
)


@pytest.mark.parametrize("run_id", ["../outside", "..\\outside", "/tmp/x", "C:\\temp\\x", "a/../b"])
def test_resolve_run_dir_rejects_path_traversal(run_id: str, tmp_path):
    with pytest.raises(InvalidRunIdError):
        resolve_run_dir(run_id, runs_root=tmp_path)


@pytest.mark.parametrize("run_id", ["20260503T120102Z", "baseline_run_20260329", "integration-roundtrip"])
def test_resolve_run_dir_accepts_timestamp_and_fixture_ids(run_id: str, tmp_path):
    resolved = resolve_run_dir(run_id, runs_root=tmp_path)
    assert resolved == (tmp_path / run_id).resolve()


def test_resolve_path_within_runs_root_accepts_absolute_in_root(tmp_path: Path):
    absolute_in_root = (tmp_path / "run_1" / "artifact.json").resolve()
    resolved = resolve_path_within_runs_root(absolute_in_root, runs_root=tmp_path)
    assert resolved == absolute_in_root


def test_resolve_path_within_runs_root_rejects_absolute_out_of_root(tmp_path: Path):
    outside = (tmp_path.parent / "outside.json").resolve()
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root(outside, runs_root=tmp_path)


def test_resolve_path_within_runs_root_rejects_relative_traversal(tmp_path: Path):
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root("../escape.json", runs_root=tmp_path)


@pytest.mark.parametrize("name", ["artifact.lock", ".artifact.tmp"])
def test_resolve_path_within_runs_root_allows_lock_and_tempfile_siblings(tmp_path: Path, name: str):
    resolved = resolve_path_within_runs_root(name, runs_root=tmp_path)
    assert resolved == (tmp_path / name).resolve()


def test_json_export_containment_uses_shared_rules_for_absolute_and_relative(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.exporters.json_export.RUNS_DIR", tmp_path)

    safe_absolute = _ensure_within_runs_dir((tmp_path / "run_meta.json").resolve())
    assert safe_absolute.path == (tmp_path / "run_meta.json").resolve()

    with pytest.raises(ValueError, match="Refusing to write outside runs directory"):
        _ensure_within_runs_dir((tmp_path.parent / "oops.json").resolve())

    with pytest.raises(ValueError, match="Invalid relative artifact path"):
        _ensure_within_runs_dir("../oops.json")
