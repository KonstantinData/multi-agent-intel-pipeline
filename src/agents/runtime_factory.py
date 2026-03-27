"""Runtime agent factory — imports AG2-dependent modules."""
from __future__ import annotations

from src.agents.supervisor import SupervisorAgent
from src.orchestration.department_runtime import DepartmentRuntime
from src.orchestration.synthesis_runtime import SynthesisRuntime


def create_runtime_agents() -> dict[str, object]:
    """Instantiate the runtime agents used by the pipeline."""
    shared_search_cache: dict = {}
    return {
        "supervisor": SupervisorAgent(),
        "departments": {
            "CompanyDepartment": DepartmentRuntime("CompanyDepartment", search_cache=shared_search_cache),
            "MarketDepartment": DepartmentRuntime("MarketDepartment", search_cache=shared_search_cache),
            "BuyerDepartment": DepartmentRuntime("BuyerDepartment", search_cache=shared_search_cache),
            "ContactDepartment": DepartmentRuntime("ContactDepartment", search_cache=shared_search_cache),
        },
        "synthesis": SynthesisRuntime(),
    }
