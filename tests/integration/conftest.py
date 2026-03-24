"""Integration test conftest — auto-applies the 'integration' marker.

Tests in this directory MAY depend on AG2/autogen and OpenAI SDK.
They are skipped automatically if AG2 is not installed.
"""
from __future__ import annotations

import pytest

try:
    import autogen  # noqa: F401
    _HAS_AG2 = True
except ImportError:
    _HAS_AG2 = False


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.runtime)
        if not _HAS_AG2:
            item.add_marker(pytest.mark.skip(reason="AG2/autogen not installed"))
