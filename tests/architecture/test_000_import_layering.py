from __future__ import annotations

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
