from __future__ import annotations

import pytest

from src.orchestration.run_paths import InvalidRunIdError, resolve_run_dir


@pytest.mark.parametrize("run_id", ["../outside", "..\\outside", "/tmp/x", "C:\\temp\\x", "a/../b"])
def test_resolve_run_dir_rejects_path_traversal(run_id: str, tmp_path):
    with pytest.raises(InvalidRunIdError):
        resolve_run_dir(run_id, runs_root=tmp_path)


@pytest.mark.parametrize("run_id", ["20260503T120102Z", "baseline_run_20260329", "integration-roundtrip"])
def test_resolve_run_dir_accepts_timestamp_and_fixture_ids(run_id: str, tmp_path):
    resolved = resolve_run_dir(run_id, runs_root=tmp_path)
    assert resolved == (tmp_path / run_id).resolve()

