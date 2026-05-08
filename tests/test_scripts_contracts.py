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
import generate_actions_bom as gen_actions_bom  # noqa: E402
import generate_ai_bom as gen_ai_bom  # noqa: E402
import generate_release_attestation as gen_attestation  # noqa: E402
import generate_sbom as gen_sbom  # noqa: E402
import validate_actions_bom as val_actions_bom  # noqa: E402
import validate_ai_bom as val_ai_bom  # noqa: E402
import validate_audit_schema as val_audit  # noqa: E402
import validate_dependency_policy as val_dep_policy  # noqa: E402
import validate_ruleset_config as val_ruleset  # noqa: E402
import validate_sbom as val_sbom  # noqa: E402
import validate_secret_scan as val_secret_scan  # noqa: E402
import check_scorecard_policy as scorecard_policy  # noqa: E402
import check_workflow_needs_result as needs_checker  # noqa: E402
import dependency_diff as dep_diff  # noqa: E402
import generate_trivyignore as gen_trivyignore  # noqa: E402


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
        container_image="ghcr.io/liquisto/test",
        image_digest="sha256:" + "a" * 64,
        provenance_attested=True,
        sbom_attested=True,
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
    assert any("full-length SHA" in f for f in failures)


def test_workflow_hardening_rejects_trusted_major_tags(tmp_path: Path) -> None:
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
    assert any("full-length SHA" in f for f in failures)


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
            "container_image": "ghcr.io/owner/repo",
            "image_digest": "sha256:" + "a" * 64,
            "slsa_target": "build-l2",
            "provenance_attested": True,
            "sbom_attested": True,
            "artifacts": {
                "ai_bom": {"path": "bom/ai-bom/ai-bom.json", "sha256": "x"},
                "sbom": {"path": "bom/sbom/sbom.json", "sha256": "y"},
                "container_image": {
                    "image": "ghcr.io/owner/repo",
                    "digest": "sha256:" + "a" * 64,
                },
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


def test_validate_attestation_rejects_missing_image_digest(tmp_path: Path) -> None:
    ai_bom = tmp_path / "ai-bom.json"
    sbom = tmp_path / "sbom.json"
    ai_bom.write_text("{}", encoding="utf-8")
    sbom.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        gen_attestation.build_release_attestation(
            ai_bom_path=ai_bom,
            sbom_path=sbom,
            container_image="ghcr.io/liquisto/test",
            image_digest="not-a-digest",
            provenance_attested=True,
            sbom_attested=True,
        )


def test_validate_sbom_rejects_library_without_purl(tmp_path: Path) -> None:
    invalid = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "app"}},
        "components": [{"type": "library", "name": "pkg", "version": "1"}],
    }
    path = tmp_path / "invalid-sbom.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(SystemExit):
        val_sbom.validate_sbom(path)


def test_validate_sbom_rejects_duplicate_components(tmp_path: Path) -> None:
    component = {
        "type": "library",
        "name": "pkg",
        "version": "1",
        "purl": "pkg:pypi/pkg@1",
    }
    invalid = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "app"}},
        "components": [component, dict(component)],
    }
    path = tmp_path / "duplicate-sbom.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(SystemExit):
        val_sbom.validate_sbom(path)


def test_validate_ruleset_config_accepts_main_policy() -> None:
    val_ruleset.validate_ruleset(ROOT / ".github" / "rulesets" / "main-protection.json")


def test_validate_ruleset_config_rejects_missing_required_check(tmp_path: Path) -> None:
    path = tmp_path / "ruleset.json"
    data = json.loads((ROOT / ".github" / "rulesets" / "main-protection.json").read_text(encoding="utf-8"))
    checks_rule = next(rule for rule in data["rules"] if rule["type"] == "required_status_checks")
    checks_rule["parameters"]["required_status_checks"] = [{"context": "pipeline-status"}]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit):
        val_ruleset.validate_ruleset(path)


def test_secret_scan_validators_reject_findings(tmp_path: Path) -> None:
    detect_report = tmp_path / "detect.json"
    detect_report.write_text(
        json.dumps({"results": {"file.py": [{"type": "Secret", "line_number": 1}]}}),
        encoding="utf-8",
    )
    gitleaks_report = tmp_path / "gitleaks.json"
    gitleaks_report.write_text(json.dumps([{"RuleID": "generic-api-key"}]), encoding="utf-8")

    with pytest.raises(SystemExit):
        val_secret_scan.validate_detect_secrets(detect_report)
    with pytest.raises(SystemExit):
        val_secret_scan.validate_gitleaks(gitleaks_report)


def test_secret_scan_validators_accept_clean_reports(tmp_path: Path) -> None:
    detect_report = tmp_path / "detect.json"
    detect_report.write_text(json.dumps({"results": {}}), encoding="utf-8")
    gitleaks_report = tmp_path / "gitleaks.json"
    gitleaks_report.write_text(json.dumps([]), encoding="utf-8")

    val_secret_scan.validate_detect_secrets(detect_report)
    val_secret_scan.validate_gitleaks(gitleaks_report)


def test_gitleaks_validator_fails_clearly_when_report_missing(tmp_path: Path) -> None:
    missing = tmp_path / "no-report.json"
    with pytest.raises(SystemExit, match="Secret scan report missing"):
        val_secret_scan.validate_gitleaks(missing)


def test_gitleaks_validator_fails_clearly_when_report_missing_detect_secrets(tmp_path: Path) -> None:
    missing = tmp_path / "no-report.json"
    with pytest.raises(SystemExit, match="Secret scan report missing"):
        val_secret_scan.validate_detect_secrets(missing)


def test_workflow_hardening_rejects_pull_request_target(tmp_path: Path) -> None:
    wf = tmp_path / "bad.yml"
    wf.write_text(
        (
            "name: bad\n"
            "on:\n"
            "  pull_request_target:\n"
            "    branches: [main]\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: bad-${{ github.ref }}\n"
            "  cancel-in-progress: true\n"
            "jobs:\n"
            "  j:\n"
            "    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 10\n"
            "    steps: []\n"
        ),
        encoding="utf-8",
    )
    failures = hardening.check_workflow_hardening([wf])
    assert any("pull_request_target" in f for f in failures)


def test_workflow_hardening_rejects_optional_codeql_guard(tmp_path: Path) -> None:
    wf = tmp_path / "codeql.yml"
    wf.write_text(
        (
            "name: codeql\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: codeql-${{ github.ref }}\n"
            "  cancel-in-progress: true\n"
            "jobs:\n"
            "  analyze:\n"
            "    if: ${{ vars.ENABLE_CODEQL == 'true' }}\n"
            "    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 10\n"
        ),
        encoding="utf-8",
    )
    failures = hardening.check_workflow_hardening([wf])
    assert any("ENABLE_CODEQL" in f for f in failures)


def test_dockerfile_hardening_rejects_unpinned_base_image(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(
        (
            "FROM python:3.12-slim-bookworm\n"
            "USER liquisto\n"
            'CMD ["python", "-m", "streamlit", "run", "ui/app.py", "--server.address=0.0.0.0"]\n'
        ),
        encoding="utf-8",
    )
    failures = hardening.check_dockerfile_hardening(dockerfile)
    assert any("pinned by sha256" in f for f in failures)


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
        "/docs/drawio/",
        "/docs/target_runtime_architecture.md",
        "/tests/",
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


def test_codeowners_contains_architecture_docs_and_tests_rules() -> None:
    codeowners = ROOT / ".github" / "CODEOWNERS"
    lines = [
        line.strip()
        for line in codeowners.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    by_pattern = {line.split()[0]: line.split()[1:] for line in lines}

    assert "@liquisto/runtime-review" in by_pattern.get("/docs/drawio/", [])
    assert "@liquisto/runtime-review" in by_pattern.get("/docs/target_runtime_architecture.md", [])
    assert "@KonstantinData" in by_pattern.get("/tests/", [])
    assert "@liquisto/security-governance" in by_pattern.get("/tests/", [])
    assert "@liquisto/runtime-review" in by_pattern.get("/tests/", [])


# ---------------------------------------------------------------------------
# P1: Actions-BOM contract tests
# ---------------------------------------------------------------------------


def test_actions_bom_accepts_sha_pinned(tmp_path: Path) -> None:
    wf = tmp_path / "pinned.yml"
    wf.write_text(
        (
            "name: x\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: x-${{ github.ref }}\n"
            "  cancel-in-progress: true\n"
            "jobs:\n"
            "  check:\n"
            "    runs-on: ubuntu-latest\n"
            "    timeout-minutes: 10\n"
            "    steps:\n"
            "      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd\n"
        ),
        encoding="utf-8",
    )
    data = gen_actions_bom.build_actions_bom(tmp_path)
    bom_path = tmp_path / "actions-bom.json"
    gen_actions_bom.write_actions_bom(bom_path, data)
    val_actions_bom.validate_actions_bom_file(bom_path)  # must not raise


def test_actions_bom_rejects_tag_pinned(tmp_path: Path) -> None:
    wf = tmp_path / "tag.yml"
    wf.write_text(
        (
            "name: x\n"
            "permissions:\n"
            "  contents: read\n"
            "concurrency:\n"
            "  group: x-${{ github.ref }}\n"
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
    data = gen_actions_bom.build_actions_bom(tmp_path)
    bom_path = tmp_path / "actions-bom.json"
    gen_actions_bom.write_actions_bom(bom_path, data)
    with pytest.raises(SystemExit):
        val_actions_bom.validate_actions_bom_file(bom_path)


def test_actions_bom_rejects_branch_pinned(tmp_path: Path) -> None:
    wf = tmp_path / "branch.yml"
    wf.write_text(
        "name: x\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@main\n",
        encoding="utf-8",
    )
    data = gen_actions_bom.build_actions_bom(tmp_path)
    bom_path = tmp_path / "actions-bom.json"
    gen_actions_bom.write_actions_bom(bom_path, data)
    with pytest.raises(SystemExit):
        val_actions_bom.validate_actions_bom_file(bom_path)


# ---------------------------------------------------------------------------
# P1: Dependency policy contract tests
# ---------------------------------------------------------------------------


def test_dependency_registry_rejects_missing_owner(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("requests>=2.0\n", encoding="utf-8")
    registry = {"schema_version": "1.0", "registry": []}  # requests not registered
    failures = val_dep_policy.validate_direct_dependency_registry(registry, req_file=req)
    assert any("requests" in f for f in failures)


def test_dependency_registry_accepts_registered_package(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("requests>=2.0\n", encoding="utf-8")
    registry = {
        "schema_version": "1.0",
        "registry": [
            {"package": "requests", "owner": "@owner", "purpose": "HTTP", "risk_tier": "low", "reviewed_at": "2026-01-01"}
        ],
    }
    failures = val_dep_policy.validate_direct_dependency_registry(registry, req_file=req)
    assert not failures


def test_cve_exceptions_rejects_expired(tmp_path: Path) -> None:
    exceptions_data = {
        "exceptions": [
            {
                "id": "CVE-2020-0001",
                "package": "somepkg",
                "owner": "@owner",
                "reason": "no fix available",
                "expires": "2020-01-01",
                "accepted_risk": "low",
            }
        ]
    }
    failures = val_dep_policy.validate_cve_exceptions(exceptions_data)
    assert any("CVE-2020-0001" in f for f in failures)


def test_cve_exceptions_rejects_missing_fields(tmp_path: Path) -> None:
    exceptions_data = {
        "exceptions": [
            {"id": "CVE-2099-9999", "package": "pkg"}  # missing owner, reason, expires, accepted_risk
        ]
    }
    failures = val_dep_policy.validate_cve_exceptions(exceptions_data)
    assert failures


def test_cve_exceptions_accepts_valid_future(tmp_path: Path) -> None:
    exceptions_data = {
        "exceptions": [
            {
                "id": "CVE-2099-9999",
                "package": "somepkg",
                "owner": "@owner",
                "reason": "no fix",
                "expires": "2099-12-31",
                "accepted_risk": "low",
            }
        ]
    }
    failures = val_dep_policy.validate_cve_exceptions(exceptions_data)
    assert not failures


# ---------------------------------------------------------------------------
# Opt 1: License-Normalisierung
# ---------------------------------------------------------------------------


def test_normalize_license_handles_common_freitext_variants() -> None:
    n = val_dep_policy._normalize_license
    assert n("MIT License") == "MIT"
    assert n("The MIT License") == "MIT"
    assert n("Apache 2.0") == "Apache-2.0"
    assert n("Apache License 2.0") == "Apache-2.0"
    assert n("Apache Software License") == "Apache-2.0"
    assert n("BSD") == "BSD-3-Clause"
    assert n("BSD license") == "BSD-3-Clause"
    assert n("New BSD") == "BSD-3-Clause"
    assert n("Simplified BSD") == "BSD-2-Clause"
    assert n("ISC License (ISCL)") == "ISC"
    assert n("PSFL") == "PSF-2.0"
    assert n("Python Software Foundation License") == "PSF-2.0"
    assert n("Mozilla Public License 2.0 (MPL 2.0)") == "MPL-2.0"
    assert n("The Unlicense") == "Unlicense"


def test_normalize_license_passthrough_spdx_identifiers() -> None:
    n = val_dep_policy._normalize_license
    assert n("MIT") == "MIT"
    assert n("Apache-2.0") == "Apache-2.0"
    assert n("BSD-3-Clause") == "BSD-3-Clause"
    assert n("BSD-2-Clause") == "BSD-2-Clause"
    assert n("ISC") == "ISC"
    assert n("MPL-2.0") == "MPL-2.0"
    assert n("PSF-2.0") == "PSF-2.0"


def test_normalize_license_handles_fulltext_mit() -> None:
    fulltext = (
        "Copyright (c) 2023 Example Corp\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
        "of this software..."
    )
    assert val_dep_policy._normalize_license(fulltext) == "MIT"


def test_normalize_license_handles_fulltext_bsd() -> None:
    fulltext = (
        "Copyright (c) 2023, Example\nAll rights reserved.\n\n"
        "Redistribution and use in source and binary forms, with or without\n"
        "modification, are permitted provided that the following conditions are met:\n"
    )
    assert val_dep_policy._normalize_license(fulltext) == "BSD-3-Clause"


def test_normalize_license_handles_fulltext_apache() -> None:
    fulltext = (
        "                                 Apache License\n"
        "                           Version 2.0, January 2004\n"
    )
    assert val_dep_policy._normalize_license(fulltext) == "Apache-2.0"


def test_validate_licenses_skips_packages_not_in_lockfile(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("", encoding="utf-8")  # empty lock → nothing to check
    policy = {"allowed": ["MIT"], "denied": ["GPL-3.0"], "unknown_action": "block"}
    # Even in an environment with many installed packages, empty lock means no failures
    failures = val_dep_policy.validate_licenses(policy, lock_file=lock)
    assert not failures, f"Expected no failures for empty lockfile, got: {failures}"


def test_validate_licenses_checks_packages_in_lockfile(tmp_path: Path) -> None:
    # Only pip itself is universally available; use a real package name from the env
    import importlib.metadata
    # Find any actually installed package to use as a sentinel
    dist = next(iter(importlib.metadata.distributions()))
    pkg_name = (dist.metadata["Name"] or "").lower().replace("-", "_")
    version = dist.metadata["Version"] or "0"
    lock = tmp_path / "requirements.lock"
    lock.write_text(f"{pkg_name}=={version}\n", encoding="utf-8")
    # Denied policy for everything – should catch the locked package
    policy = {"allowed": [], "denied": [], "unknown_action": "block"}
    failures = val_dep_policy.validate_licenses(policy, lock_file=lock)
    # Package is in the lock, so it IS checked; its license is likely not in allowed (empty set)
    assert any(pkg_name.replace("_", "-") in f.lower() or pkg_name in f.lower() for f in failures)


# ---------------------------------------------------------------------------
# P1: Dependency diff contract tests
# ---------------------------------------------------------------------------


def test_dependency_diff_detects_added_package(tmp_path: Path) -> None:
    base = tmp_path / "base.lock"
    head = tmp_path / "head.lock"
    base.write_text("requests==2.28.0\n", encoding="utf-8")
    head.write_text("requests==2.28.0\nhttpx==0.27.0\n", encoding="utf-8")
    diff = dep_diff.compute_diff(dep_diff._parse_lockfile(base), dep_diff._parse_lockfile(head))
    assert "httpx" in diff["added"]
    assert not diff["removed"]


def test_dependency_diff_detects_version_change(tmp_path: Path) -> None:
    base = tmp_path / "base.lock"
    head = tmp_path / "head.lock"
    base.write_text("requests==2.28.0\n", encoding="utf-8")
    head.write_text("requests==2.31.0\n", encoding="utf-8")
    diff = dep_diff.compute_diff(dep_diff._parse_lockfile(base), dep_diff._parse_lockfile(head))
    assert "requests" in diff["changed"]
    assert diff["changed"]["requests"] == {"from": "2.28.0", "to": "2.31.0"}


def test_dependency_diff_detects_removed_package(tmp_path: Path) -> None:
    base = tmp_path / "base.lock"
    head = tmp_path / "head.lock"
    base.write_text("requests==2.28.0\nhttpx==0.27.0\n", encoding="utf-8")
    head.write_text("requests==2.28.0\n", encoding="utf-8")
    diff = dep_diff.compute_diff(dep_diff._parse_lockfile(base), dep_diff._parse_lockfile(head))
    assert "httpx" in diff["removed"]


# ---------------------------------------------------------------------------
# P1: scorecard-policy contract tests
# ---------------------------------------------------------------------------

def _make_clean_repo(tmp_path: Path, action_ref: str = "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd") -> Path:
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "ci.yml").write_text(
        f"name: ci\npermissions:\n  contents: read\njobs:\n  j:\n    steps:\n      - uses: {action_ref}\n",
        encoding="utf-8",
    )
    (wf_dir / "codeql.yml").write_text("name: codeql\npermissions:\n  contents: read\n", encoding="utf-8")
    (wf_dir / "release-attestation.yml").write_text("name: ra\npermissions:\n  contents: read\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("ok", encoding="utf-8")
    return tmp_path


def test_scorecard_policy_accepts_clean_repo(tmp_path: Path) -> None:
    root = _make_clean_repo(tmp_path)
    assert not scorecard_policy.check_scorecard_policy(root)


def test_scorecard_policy_detects_unpinned_action(tmp_path: Path) -> None:
    root = _make_clean_repo(tmp_path, action_ref="actions/checkout@v4")
    failures = scorecard_policy.check_scorecard_policy(root)
    assert any("unpinned" in f for f in failures)


def test_scorecard_policy_detects_missing_permissions(tmp_path: Path) -> None:
    root = _make_clean_repo(tmp_path)
    wf = root / ".github" / "workflows" / "noperms.yml"
    wf.write_text("name: noperms\njobs:\n  j:\n    steps: []\n", encoding="utf-8")
    failures = scorecard_policy.check_scorecard_policy(root)
    assert any("missing permissions" in f for f in failures)


def test_scorecard_policy_detects_missing_codeql(tmp_path: Path) -> None:
    root = _make_clean_repo(tmp_path)
    (root / ".github" / "workflows" / "codeql.yml").unlink()
    failures = scorecard_policy.check_scorecard_policy(root)
    assert any("codeql.yml missing" in f for f in failures)


def test_scorecard_policy_detects_missing_security_md(tmp_path: Path) -> None:
    root = _make_clean_repo(tmp_path)
    (root / "SECURITY.md").unlink()
    failures = scorecard_policy.check_scorecard_policy(root)
    assert any("SECURITY.md missing" in f for f in failures)


# ---------------------------------------------------------------------------
# Opt 2: pipeline-status / needs-result contract tests
# ---------------------------------------------------------------------------


def _needs(*pairs: tuple[str, str]) -> dict:
    return {name: {"result": result} for name, result in pairs}


def test_needs_result_accepts_all_success() -> None:
    needs = _needs(("lint", "success"), ("type-check", "success"), ("bandit-sast", "success"))
    assert not needs_checker.evaluate_needs(needs)


def test_needs_result_accepts_allowed_skip_integration_tests() -> None:
    needs = _needs(("lint", "success"), ("integration-tests", "skipped"))
    assert not needs_checker.evaluate_needs(needs)


def test_needs_result_accepts_allowed_skip_provenance_gate() -> None:
    needs = _needs(("lint", "success"), ("provenance-gate", "skipped"))
    assert not needs_checker.evaluate_needs(needs)


def test_needs_result_accepts_both_allowed_skips_simultaneously() -> None:
    needs = _needs(
        ("lint", "success"),
        ("integration-tests", "skipped"),
        ("provenance-gate", "skipped"),
    )
    assert not needs_checker.evaluate_needs(needs)


def test_needs_result_rejects_failed_gate() -> None:
    needs = _needs(("lint", "failure"), ("type-check", "success"))
    failures = needs_checker.evaluate_needs(needs)
    assert "lint" in failures


def test_needs_result_rejects_cancelled_gate() -> None:
    needs = _needs(("lint", "success"), ("bandit-sast", "cancelled"))
    failures = needs_checker.evaluate_needs(needs)
    assert "bandit-sast" in failures


def test_needs_result_rejects_unexpected_skip_of_required_gate() -> None:
    # A required gate that is not in ALLOWED_SKIPS must not be skipped
    needs = _needs(("lint", "skipped"))
    failures = needs_checker.evaluate_needs(needs)
    assert "lint" in failures


def test_needs_result_rejects_integration_tests_failure_not_just_skip() -> None:
    # An allowed-skip job that actually *fails* must still block
    needs = _needs(("lint", "success"), ("integration-tests", "failure"))
    failures = needs_checker.evaluate_needs(needs)
    assert "integration-tests" in failures


# ---------------------------------------------------------------------------
# P2-1: generate_trivyignore contract tests
# ---------------------------------------------------------------------------


def _exceptions_file(tmp_path: Path, exceptions: list) -> Path:
    f = tmp_path / "dependency-risk-exceptions.json"
    f.write_text(json.dumps({"schema_version": "1.0", "exceptions": exceptions}), encoding="utf-8")
    return f


def test_generate_trivyignore_empty_exceptions(tmp_path: Path) -> None:
    ef = _exceptions_file(tmp_path, [])
    content = gen_trivyignore.generate_trivyignore(ef)
    assert "exp:" not in content
    assert "Auto-generated" in content


def test_generate_trivyignore_writes_valid_entry(tmp_path: Path) -> None:
    ef = _exceptions_file(tmp_path, [{
        "id": "CVE-2099-1234",
        "package": "somepkg",
        "owner": "@owner",
        "reason": "no fix available",
        "expires": "2099-12-31",
        "accepted_risk": "low",
    }])
    content = gen_trivyignore.generate_trivyignore(ef)
    assert "CVE-2099-1234 exp:2099-12-31" in content
    assert "@owner" in content
    assert "no fix available" in content


def test_generate_trivyignore_blocks_expired_exception(tmp_path: Path) -> None:
    ef = _exceptions_file(tmp_path, [{
        "id": "CVE-2020-0001",
        "package": "oldpkg",
        "owner": "@owner",
        "reason": "accepted",
        "expires": "2020-01-01",
        "accepted_risk": "low",
    }])
    with pytest.raises(SystemExit, match="CVE-2020-0001"):
        gen_trivyignore.generate_trivyignore(ef)


def test_generate_trivyignore_multiple_entries_all_valid(tmp_path: Path) -> None:
    ef = _exceptions_file(tmp_path, [
        {"id": "CVE-2099-0001", "package": "a", "owner": "@o", "reason": "r1",
         "expires": "2099-01-01", "accepted_risk": "low"},
        {"id": "CVE-2099-0002", "package": "b", "owner": "@o", "reason": "r2",
         "expires": "2099-06-01", "accepted_risk": "medium"},
    ])
    content = gen_trivyignore.generate_trivyignore(ef)
    assert content.count("exp:") == 2


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
