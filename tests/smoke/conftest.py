"""Smoke test conftest — auto-applies the 'smoke' marker."""
from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.smoke)
