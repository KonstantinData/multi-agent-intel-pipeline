from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_dependency_light_architecture_modules_do_not_import_runtime_heavy_modules():
    code = """
import sys
import src.orchestration.contracts
import src.orchestration.contract_validation
import src.orchestration.followup_config
import src.orchestration.meeting_questions
import src.orchestration.run_paths

forbidden = {"autogen", "openai", "pypdf", "reportlab"}
loaded = forbidden & set(sys.modules)
if loaded:
    raise SystemExit(f"Runtime-heavy modules imported: {sorted(loaded)}")
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_architecture_tests_do_not_import_runtime_heavy_dependencies():
    architecture_dir = Path(__file__).parent
    forbidden_tokens = (
        "import openai",
        'importorskip("openai")',
        "import pypdf",
        'importorskip("pypdf")',
        "import reportlab",
        'importorskip("reportlab")',
        "src.exporters.pdf_report",
        "src.agents.worker",
    )

    offenders: dict[str, list[str]] = {}
    for path in architecture_dir.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        found = [token for token in forbidden_tokens if token in text]
        if found:
            offenders[str(path.relative_to(architecture_dir.parent.parent))] = found

    assert offenders == {}
