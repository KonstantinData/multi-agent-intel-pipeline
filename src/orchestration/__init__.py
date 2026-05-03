"""Supervisor-centric orchestration helpers."""

__all__ = ["RunContext"]


def __getattr__(name: str):
    if name == "RunContext":
        from src.orchestration.run_context import RunContext

        return RunContext
    raise AttributeError(name)

