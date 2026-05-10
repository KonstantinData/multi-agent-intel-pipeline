from __future__ import annotations

from pathlib import Path

import pytest

from src.exporters.json_export import _ensure_within_runs_dir
from src.orchestration.run_paths import (
    InvalidRunIdError,
    resolve_path_within_runs_root,
    resolve_run_dir,
)


def _make_dir_symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are not available in this environment: {exc}")


@pytest.mark.parametrize("run_id", ["../outside", "..\\outside", "/tmp/x", "C:\\temp\\x", "a/../b"])
def test_resolve_run_dir_rejects_path_traversal(run_id: str, tmp_path):
    with pytest.raises(InvalidRunIdError):
        resolve_run_dir(run_id, runs_root=tmp_path)


@pytest.mark.parametrize("run_id", ["20260503T120102Z", "baseline_run_20260329", "integration-roundtrip"])
def test_resolve_run_dir_accepts_timestamp_and_fixture_ids(run_id: str, tmp_path):
    resolved = resolve_run_dir(run_id, runs_root=tmp_path)
    assert resolved == (tmp_path / run_id).resolve()


def test_resolve_path_within_runs_root_rejects_absolute_in_root(tmp_path: Path):
    absolute_in_root = (tmp_path / "run_1" / "artifact.json").resolve()
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root(absolute_in_root, runs_root=tmp_path)


def test_resolve_path_within_runs_root_rejects_absolute_out_of_root(tmp_path: Path):
    outside = (tmp_path.parent / "outside.json").resolve()
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root(outside, runs_root=tmp_path)


def test_resolve_path_within_runs_root_rejects_relative_traversal(tmp_path: Path):
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root("../escape.json", runs_root=tmp_path)


@pytest.mark.parametrize(
    "candidate_path",
    [
        r"C:temp\\x",
        r"C:\\temp\\x",
        r"\\\\server\\share\\x",
        r"..\\..//escape",
        r"a\\..\\b",
        "  ../escape.json  ",
        "   ",
    ],
)
def test_resolve_path_within_runs_root_rejects_windows_unc_mixed_and_whitespace_variants(
    candidate_path: str,
    tmp_path: Path,
):
    with pytest.raises(InvalidRunIdError):
        resolve_path_within_runs_root(candidate_path, runs_root=tmp_path)


@pytest.mark.parametrize(
    ("candidate_path", "expected_relative"),
    [
        ("  run_1/artifact.json  ", Path("run_1") / "artifact.json"),
        ("\trun_2/artifact.json\n", Path("run_2") / "artifact.json"),
    ],
)
def test_resolve_path_within_runs_root_strips_whitespace_for_otherwise_valid_relative_paths(
    candidate_path: str,
    expected_relative: Path,
    tmp_path: Path,
):
    resolved = resolve_path_within_runs_root(candidate_path, runs_root=tmp_path)
    assert resolved == (tmp_path / expected_relative).resolve()


@pytest.mark.parametrize("name", ["artifact.lock", ".artifact.tmp"])
def test_resolve_path_within_runs_root_allows_lock_and_tempfile_siblings(tmp_path: Path, name: str):
    resolved = resolve_path_within_runs_root(name, runs_root=tmp_path)
    assert resolved == (tmp_path / name).resolve()


@pytest.mark.parametrize("run_id", [r"C:temp\\x", r"C:\\temp\\x", r"\\\\server\\share\\x", "  C:\\temp\\x  "])
def test_resolve_run_dir_rejects_windows_drive_and_unc_forms(run_id: str, tmp_path: Path):
    with pytest.raises(InvalidRunIdError):
        resolve_run_dir(run_id, runs_root=tmp_path)


@pytest.mark.parametrize("run_id", [" 20260503T120102Z ", "\tbaseline_run_20260329\n"])
def test_resolve_run_dir_accepts_whitespace_wrapped_valid_ids(run_id: str, tmp_path: Path):
    expected = run_id.strip()
    resolved = resolve_run_dir(run_id, runs_root=tmp_path)
    assert resolved == (tmp_path / expected).resolve()


def test_resolve_run_dir_with_symlinked_runs_root_stays_contained(tmp_path: Path):
    real_runs_root = tmp_path / "real-runs"
    real_runs_root.mkdir()
    symlink_runs_root = tmp_path / "runs-link"
    _make_dir_symlink_or_skip(symlink_runs_root, real_runs_root)

    resolved = resolve_run_dir("20260503T120102Z", runs_root=symlink_runs_root)
    assert resolved == (real_runs_root / "20260503T120102Z").resolve()
    resolved.relative_to(real_runs_root.resolve())


def test_resolve_path_within_runs_root_with_symlinked_root_stays_contained(tmp_path: Path):
    real_runs_root = tmp_path / "real-runs"
    real_runs_root.mkdir()
    symlink_runs_root = tmp_path / "runs-link"
    _make_dir_symlink_or_skip(symlink_runs_root, real_runs_root)

    resolved = resolve_path_within_runs_root("run_1/artifact.json", runs_root=symlink_runs_root)
    assert resolved == (real_runs_root / "run_1" / "artifact.json").resolve()
    resolved.relative_to(real_runs_root.resolve())


def test_json_export_containment_uses_shared_rules_for_absolute_and_relative(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.exporters.json_export.RUNS_DIR", tmp_path)

    with pytest.raises(ValueError, match="Refusing to write outside runs directory"):
        _ensure_within_runs_dir((tmp_path / "run_meta.json").resolve())

    with pytest.raises(ValueError, match="Refusing to write outside runs directory"):
        _ensure_within_runs_dir((tmp_path.parent / "oops.json").resolve())

    with pytest.raises(ValueError, match="Invalid relative artifact path"):
        _ensure_within_runs_dir("../oops.json")
