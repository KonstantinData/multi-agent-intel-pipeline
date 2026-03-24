"""Pure architecture tests for speaker selector guardrails.

Validates:
- Tool-call routing to executor
- Executor-done routing to lead
- Loop prevention
- Lead-driven agent addressing
- No workflow_step in department selector
- Non-lead text turns route back to lead

Uses MagicMock fakes — NO real AG2 agents or GroupChat runtime.
The speaker_selector module uses TYPE_CHECKING for autogen imports,
so it can be imported without AG2 installed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.orchestration.speaker_selector import build_department_selector


class TestSelectorGuardrails:
    def _make_selector(self):
        guardrail_state: dict = {}
        agents = {name: MagicMock(name=name) for name in
                  ["Lead", "Researcher", "Critic", "Judge", "Coding", "Executor"]}
        for name, agent in agents.items():
            agent.name = name
        selector = build_department_selector(
            guardrail_state=guardrail_state,
            agent_map=agents,
            lead_name="Lead",
            researcher_name="Researcher",
            critic_name="Critic",
            judge_name="Judge",
            coding_name="Coding",
            executor_name="Executor",
        )
        return selector, agents, guardrail_state

    def _fake_gc(self, messages):
        gc = MagicMock()
        gc.messages = messages
        return gc

    def test_tool_call_routes_to_executor(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Researcher", "tool_calls": [{"function": "run_research"}]}])
        result = selector(agents["Researcher"], gc)
        assert result.name == "Executor"

    def test_executor_done_routes_to_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Executor", "content": "tool result"}])
        result = selector(agents["Executor"], gc)
        assert result.name == "Lead"

    def test_loop_prevention_forces_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Researcher", "content": "I will search"}])
        for _ in range(3):
            result = selector(agents["Researcher"], gc)
        assert result.name == "Lead"

    def test_lead_addressing_researcher_routes_to_researcher(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Researcher, please call run_research(task_key=company_fundamentals)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Researcher"

    def test_lead_addressing_critic_routes_to_critic(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Critic, please review_research(task_key=company_fundamentals)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Critic"

    def test_lead_addressing_judge_routes_to_judge(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Judge, please call judge_decision(task_key=peer_companies)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Judge"

    def test_lead_addressing_coding_routes_to_coding(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Lead", "content": "Coding, please suggest_refined_queries(task_key=market_situation)"}])
        result = selector(agents["Lead"], gc)
        assert result.name == "Coding"

    def test_selector_has_no_workflow_step(self):
        """Selector must not reference workflow_step in department selector code."""
        import src.orchestration.speaker_selector as sel_mod
        import inspect
        source = inspect.getsource(sel_mod)
        lines = source.split("\n")
        in_dept_selector = False
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if '"""' in line or "'''" in line:
                in_docstring = not in_docstring
            if "def build_department_selector" in line:
                in_dept_selector = True
                in_docstring = False
            if in_dept_selector and "def build_synthesis_selector" in line:
                in_dept_selector = False
            if (
                in_dept_selector
                and not in_docstring
                and "workflow_step" in line
                and not stripped.startswith("#")
                and not stripped.startswith('"""')
                and not stripped.startswith("'''")
            ):
                raise AssertionError(
                    f"workflow_step still used as code in build_department_selector: {line!r}"
                    "\n — the Lead owns the workflow."
                )

    def test_non_lead_text_turn_routes_back_to_lead(self):
        selector, agents, _ = self._make_selector()
        gc = self._fake_gc([{"name": "Critic", "content": "The research looks weak."}])
        result = selector(agents["Critic"], gc)
        assert result.name == "Lead"
