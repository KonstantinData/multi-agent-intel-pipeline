"""Runtime test conftest — auto-applies the 'runtime' marker."""
from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.runtime)
