from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_github_actions_hardening as hardening  # noqa: E402
import generate_ai_bom as gen_ai_bom  # noqa: E402
import generate_release_attestation as gen_attestation  # noqa: E402
import generate_sbom as gen_sbom  # noqa: E402
import validate_ai_bom as val_ai_bom  # noqa: E402
import validate_audit_schema as val_audit  # noqa: E402
import validate_sbom as val_sbom  # noqa: E402


def test_ai_bom_roundtrip(tmp_path: Path) -> None:
    context = gen_ai_bom.resolve_context(
        release_id="v-test",
        commit="abc123",
        generated_at="2026-01-01T00:00:00+00:00",
    )
    data = gen_ai_bom.build_ai_bom(context)
    out = tmp_path / "ai-bom.json"
    gen_ai_bom.write_ai_bom(out, data)
    val_ai_bom.validate_ai_bom_file(out)


def test_sbom_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    (repo / "b.py").write_text("print('x')", encoding="utf-8")

    sbom_data = gen_sbom.build_sbom(repo)
    out = tmp_path / "sbom.json"
    gen_sbom.write_sbom(out, sbom_data)
    val_sbom.validate_sbom(out)


def test_release_attestation_roundtrip(tmp_path: Path) -> None:
    ai_bom = tmp_path / "ai-bom.json"
    sbom = tmp_path / "sbom.json"

    context = gen_ai_bom.resolve_context(
        release_id="v-test",
        commit="abc123",
        generated_at="2026-01-01T00:00:00+00:00",
    )
    gen_ai_bom.write_ai_bom(ai_bom, gen_ai_bom.build_ai_bom(context))
    gen_sbom.write_sbom(
        sbom,
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "metadata": {"timestamp": "2026-01-01T00:00:00+00:00"},
            "components": [{"type": "file", "name": "a", "version": "1"}],
        },
    )

    data = gen_attestation.build_release_attestation(
        ai_bom_path=ai_bom,
        sbom_path=sbom,
        release_id="v-test",
        commit="abc123",
    )
    out = tmp_path / "release-attestation.json"
    gen_attestation.write_attestation(out, data)
    val_audit.validate_release_attestation(out)


def test_workflow_hardening_detects_placeholder(tmp_path: Path) -> None:
    wf = tmp_path / "test.yml"
    wf.write_text(
        "name: x\npermissions: {}\njobs:\n  placeholder:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    failures = hardening.check_workflow_hardening([wf])
    assert failures
    assert any("placeholder pattern" in f or "disallowed pattern" in f for f in failures)


def test_workflow_hardening_detects_unpinned_action(tmp_path: Path) -> None:
    wf = tmp_path / "unpinned.yml"
    wf.write_text(
        (
            "name: x\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: test-${{ github.ref }}\n"
            "  cancel-in-progress: true\n"
            "jobs:\n"
            "  check:\n"
            "    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 10\n"
            "    steps:\n"
            "      - uses: actions/checkout@v4\n"
        ),
        encoding="utf-8",
    )
    failures = hardening.check_workflow_hardening([wf])
    assert any("SHA-pinned or trusted major tag" in f for f in failures)


def test_workflow_hardening_allows_trusted_major_tags(tmp_path: Path) -> None:
    wf = tmp_path / "trusted-major.yml"
    wf.write_text(
        (
            "name: x\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: test-${{ github.ref }}\n"
            "  cancel-in-progress: true\n"
            "jobs:\n"
            "  check:\n"
            "    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 10\n"
            "    steps:\n"
            "      - uses: github/codeql-action/init@v4\n"
        ),
        encoding="utf-8",
    )
    failures = hardening.check_workflow_hardening([wf])
    assert not failures


def test_repository_structure_validation(tmp_path: Path) -> None:
    for rel in val_audit.REQUIRED_GOVERNANCE_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
    for rel in val_audit.REQUIRED_GOVERNANCE_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    val_audit.validate_repository_structure(tmp_path)


def test_repository_structure_allows_german_docs(tmp_path: Path) -> None:
    for rel in val_audit.REQUIRED_GOVERNANCE_FILES:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
    for rel in val_audit.REQUIRED_GOVERNANCE_DIRS:
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)

    de_doc = tmp_path / "docs" / "de" / "architecture" / "EU-Compliant-Roadmap-for-MAS.md"
    de_doc.parent.mkdir(parents=True, exist_ok=True)
    de_doc.write_text("ok", encoding="utf-8")

    val_audit.validate_repository_structure(tmp_path)


def test_validate_ai_bom_rejects_missing_models(tmp_path: Path) -> None:
    invalid = {
        "release_id": "x",
        "commit": "y",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "legal_scope": {
            "role": "REVIEW_REQUIRED",
            "use_case": "REVIEW_REQUIRED",
            "deployment_context": "REVIEW_REQUIRED",
            "cra_scope": "REVIEW_REQUIRED",
            "foss_scope": "REVIEW_REQUIRED",
            "reviewed_at": "2026-01-01",
        },
        "models": [],
        "agents": [{"id": "a", "version": "1", "role": "r", "permissions": []}],
        "tools": [{"id": "t", "version": "1", "scope": "ci"}],
        "datasets": [],
    }
    path = tmp_path / "invalid-ai-bom.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(SystemExit):
        val_ai_bom.validate_ai_bom_file(path)


def test_validate_attestation_rejects_failed_gate(tmp_path: Path) -> None:
    invalid = {
        "release_id": "v-test",
        "commit": "abc123",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "repository": "owner/repo",
        "workflow_run_id": "1",
        "workflow_run_url": "https://github.com/owner/repo/actions/runs/1",
        "artifacts": {
            "ai_bom": {"path": "bom/ai-bom/ai-bom.json", "sha256": "x"},
            "sbom": {"path": "bom/sbom/sbom.json", "sha256": "y"},
        },
        "gate_results": {
            "governance": "PASSED",
            "security": "FAILED",
            "release_integrity": "PASSED",
        },
    }
    path = tmp_path / "invalid-attestation.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(SystemExit):
        val_audit.validate_release_attestation(path)


def test_codeowners_high_impact_paths_have_independent_review_paths() -> None:
    codeowners = ROOT / ".github" / "CODEOWNERS"
    lines = [
        line.strip()
        for line in codeowners.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    required = [
        "/src/orchestration/",
        "/src/agents/",
        "/src/memory/",
        "/knowledge/",
        "/.github/workflows/",
        "/requirements.txt",
        "/requirements.lock",
        "/pyproject.toml",
    ]
    by_pattern = {line.split()[0]: line.split()[1:] for line in lines}
    missing = [pattern for pattern in required if pattern not in by_pattern]
    assert not missing, f"Missing high-impact CODEOWNERS patterns: {missing}"
    single_owner = [pattern for pattern in required if len(set(by_pattern[pattern])) < 2]
    assert not single_owner, f"High-impact paths need at least two review owners: {single_owner}"


def test_init_multi_role_task_generates_current_task(tmp_path: Path) -> None:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required to execute init_multi_role_task.ps1")

    script = SCRIPTS_DIR / "init_multi_role_task.ps1"
    output = tmp_path / "current-task.md"
    subprocess.run(
        [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-Task",
            "Update security workflow hardening",
            "-TargetState",
            "Release-ready",
            "-Scope",
            ".github/workflows scripts",
            "-BlockingThreshold",
            "P0",
            "-OutputPath",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    text = output.read_text(encoding="utf-8")
    assert "Task: Update security workflow hardening" in text
    assert "Target State: Release-ready" in text
    assert "Blocking Threshold: P0" in text
    assert "security-architect - Goal:" in text
    assert "ai-compliance-owner - Goal:" in text
    assert "release-manager - Goal:" in text
    assert "code-reviewer - Goal:" in text
    assert "maintainer - Goal:" in text
    assert (
        "Conflict resolver: security-architect > ai-compliance-owner > release-manager"
        in text
    )
