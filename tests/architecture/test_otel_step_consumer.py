"""Architecture tests for ADR-002 RuntimeStep telemetry mapping."""

from __future__ import annotations

from src.orchestration.otel_step_consumer import (
    InMemoryTelemetrySink,
    OpenTelemetryStepConsumer,
    build_otel_step_consumer_from_env,
    summarize_compactable_ag2_noops,
)
from src.orchestration.runtime_step import build_narrated_step
from src.orchestration.step_bus import InMemoryStepSink, StepBus


def _step(**overrides):
    payload = {
        "run_id": "20260520T120000Z",
        "sequence": 1,
        "phase": "first_pass",
        "actor": "PipelineRunner",
        "actor_role": "runtime",
        "goal": "Test telemetry mapping",
        "action_kind": "state_transition",
        "action_target": "checkpoint.write",
        "action_payload": {"raw_prompt": "this must not become an OTel attribute"},
        "state_transitions": [
            {
                "kind": "checkpoint_write",
                "checkpoint_id": "after_first_pass",
                "phase": "first_pass",
                "sequence": 1,
                "content_hash": "abc123",
            }
        ],
        "decision": "written",
        "reflection": "Checkpoint written.",
        "stop_reason": "checkpoint_written",
    }
    payload.update(overrides)
    return build_narrated_step(**payload)


def test_otel_consumer_exports_only_allowlisted_step_attributes():
    sink = InMemoryTelemetrySink()
    consumer = OpenTelemetryStepConsumer(sink=sink)

    consumer.consume(_step())

    assert [span["name"] for span in sink.spans] == ["runtime.run", "runtime.first_pass"]
    step_attrs = sink.spans[1]["attributes"]
    assert step_attrs["phase"] == "first_pass"
    assert step_attrs["action.target"] == "checkpoint.write"
    assert "raw_prompt" not in step_attrs
    assert all("prompt" not in str(value).lower() for value in step_attrs.values())
    assert sink.spans[1]["events"][0]["attributes"]["checkpoint_id"] == "after_first_pass"


def test_ag2_noop_turns_are_exported_as_department_events_not_child_spans():
    sink = InMemoryTelemetrySink()
    consumer = OpenTelemetryStepConsumer(sink=sink)
    step = _step(
        phase="department_groupchat",
        actor="CompanyResearcher",
        actor_role="researcher",
        department="CompanyDepartment",
        action_kind="no_op",
        action_target="ag2.turn",
        action_payload={"content_length": 9999},
        observations=[
            {
                "kind": "ag2_message_preview",
                "content_preview": "High-cardinality message preview must stay out of OTel.",
            }
        ],
        state_transitions=[],
        decision="recorded",
        reflection="Recorded AG2 turn.",
        stop_reason="ag2_turn_recorded",
    )

    consumer.consume(step)

    assert [span["name"] for span in sink.spans] == ["runtime.run"]
    assert sink.events == [
        {
            "scope_name": "department.companydepartment",
            "name": "department_groupchat.no_op",
            "attributes": {
                "step.id": step["identity"]["step_id"],
                "step.sequence": 1,
                "step.status": "completed",
                "phase": "department_groupchat",
                "department": "CompanyDepartment",
                "actor.role": "researcher",
                "action.kind": "no_op",
                "action.target": "ag2.turn",
            },
        }
    ]


def test_usage_metrics_are_emitted_from_execution_usage():
    sink = InMemoryTelemetrySink()
    consumer = OpenTelemetryStepConsumer(sink=sink)
    consumer.consume(
        _step(
            usage={
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.001,
                "retry_count": 2,
            }
        )
    )

    metric_values = {item["name"]: item["value"] for item in sink.metrics}
    assert metric_values["runtime.tokens.prompt"] == 10
    assert metric_values["runtime.tokens.completion"] == 5
    assert metric_values["runtime.tokens.total"] == 15
    assert metric_values["runtime.cost.estimated_usd"] == 0.001
    assert metric_values["runtime.retry.count"] == 2
    assert any(item["attributes"].get("model.family") == "gpt-4.1" for item in sink.metrics)


def test_step_bus_keeps_runtime_path_when_otel_sink_fails():
    class FailingSink:
        def emit_span(self, name, attributes, events=None):
            raise RuntimeError("otel down")

        def emit_event(self, scope_name, name, attributes):
            raise RuntimeError("otel down")

        def emit_metric(self, name, value, attributes):
            raise RuntimeError("otel down")

    trace_sink = InMemoryStepSink()
    bus = StepBus([OpenTelemetryStepConsumer(sink=FailingSink()), trace_sink])

    bus.publish(_step())

    assert len(trace_sink.steps) == 1


def test_otel_consumer_factory_respects_feature_flag(monkeypatch):
    monkeypatch.setenv("LIQUISTO_OTEL_ENABLED", "0")
    assert build_otel_step_consumer_from_env() is None

    class FakeSdkSink(InMemoryTelemetrySink):
        pass

    monkeypatch.setenv("LIQUISTO_OTEL_ENABLED", "1")
    monkeypatch.setattr("src.orchestration.otel_step_consumer.OpenTelemetrySdkSink", FakeSdkSink)
    assert build_otel_step_consumer_from_env() is not None


def test_ag2_noop_compaction_summary_keeps_bounded_counts():
    steps = [
        _step(
            sequence=index,
            phase="department_groupchat",
            actor=f"Agent{index}",
            actor_role="researcher" if index % 2 else "critic",
            department="MarketDepartment",
            action_kind="no_op",
            action_target="ag2.turn",
            state_transitions=[],
            decision="recorded",
            reflection="Recorded AG2 turn.",
            stop_reason="ag2_turn_recorded",
        )
        for index in range(1, 5)
    ]

    summaries = summarize_compactable_ag2_noops(steps, noop_threshold=2)

    assert summaries == [
        {
            "kind": "department_groupchat_noop_compaction",
            "run_id": "20260520T120000Z",
            "department": "MarketDepartment",
            "count": 4,
            "first_sequence": 1,
            "last_sequence": 4,
            "actor_role_counts": {"critic": 2, "researcher": 2},
            "task_key_counts": {},
            "error_count": 0,
        }
    ]


def test_otel_consumer_ignores_unsupported_schema_version():
    sink = InMemoryTelemetrySink()
    step = _step()
    step["identity"]["schema_version"] = "1900-01-01.1"

    OpenTelemetryStepConsumer(sink=sink).consume(step)

    assert sink.spans == []
    assert sink.events == []
    assert sink.metrics == []
