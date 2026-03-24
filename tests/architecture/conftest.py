"""Architecture test conftest — auto-applies the 'architecture' marker.

Tests in this directory MUST NOT depend on AG2/autogen or OpenAI SDK.
They validate contracts, state transitions, memory boundaries, selector
guardrail logic, package assembly, and follow-up evidence selection.
"""
from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.architecture)
        item.add_marker(pytest.mark.contract)
