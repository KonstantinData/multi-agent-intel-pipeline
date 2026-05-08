"""Report-level runtime wrapper around ReportWriterAgent."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.agents.report_writer import ReportWriterAgent

MessageHook = Callable[[dict[str, Any]], None] | None


class ReportWriterRuntime:
    """Expose report assembly as a real runtime node."""

    def __init__(self) -> None:
        self.agent = ReportWriterAgent()

    def run(
        self,
        *,
        pipeline_data: dict[str, Any],
        department_packages: dict[str, dict[str, Any]],
        on_message: MessageHook = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        report_package = self.agent.build_report_package(
            pipeline_data=pipeline_data,
            department_packages=department_packages,
        )
        message = {
            "agent": "ReportWriter",
            "type": "agent_message",
            "content": json.dumps(
                {"section": "report_package", "payload": report_package},
                ensure_ascii=False,
            ),
        }
        if on_message:
            on_message(message)
        return report_package, [message]

