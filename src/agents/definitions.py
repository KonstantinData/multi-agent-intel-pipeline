"""Compatibility shim — use specs.py and runtime_factory.py directly."""
from src.agents.specs import AGENT_SPECS
from src.agents.runtime_factory import create_runtime_agents

__all__ = ["AGENT_SPECS", "create_runtime_agents"]
