"""Architecture tests for the runtime step contract."""

from __future__ import annotations

import json

import pytest

from src.exporters.json_export import export_run
from src.orchestration.run_context import RunContext
from src.orchestration.runtime_step import (
    MAX_REFLECTION_CHARS,
    RuntimeStepValidationError,
    build_narrated_step,
    make_idempotency_key,
    runtime_ref,
    validate_runtime_step,
)
from src.orchestration.step_bus import InMemoryStepSink, StepBus, StepEmitter, StepTraceConsumer


def _step(**overrides):
    payload = {
        "run_id": "20260520T120000Z",
        "sequence": 1,
        "phase": "first_pass",
        "actor": "PipelineRunner",
        "actor_role": "runtime",
        "goal": "Test step",
        "action_kind": "state_transition",
        "action_target": "test.transition",
        "action_payload": {"value": "ok"},
        "decision": "completed",
        "reflection": "Step completed.",
        "stop_reason": "complete",
    }
    payload.update(overrides)
    return build_narrated_step(**payload)


def test_runtime_ref_contract_accepts_artifact_uri_and_inline_refs():
    refs = [
        runtime_ref(kind="artifact_id", value="run_context"),
        runtime_ref(kind="uri", value="postgres://run_checkpoints/run/after_first_pass/1"),
        runtime_ref(kind="inline", value="small value", mime_type="text/plain"),
    ]
    step = _step(input_refs=refs, output_refs=refs)

    assert validate_runtime_step(step)["intent"]["input_refs"] == refs
    assert validate_runtime_step(step)["outcome"]["output_refs"] == refs


def test_narrated_step_requires_terminal_status():
    with pytest.raises(RuntimeStepValidationError):
        _step(status="running")


def test_reflection_is_truncated_with_marker():
    step = _step(reflection="x" * (MAX_REFLECTION_CHARS + 100))

    reflection = step["outcome"]["reflection"]
    assert len(reflection) == MAX_REFLECTION_CHARS
    assert reflection.endswith("[truncated by RuntimeStep validator]")


def test_idempotency_key_canonicalizes_payload_whitespace_and_key_order():
    action_a = {
        "kind": "state_transition",
        "target": "department.assign",
        "payload": {"b": "two   words", "a": "one"},
    }
    action_b = {
        "target": "department.assign",
        "payload": {"a": "one", "b": "two words"},
        "kind": "state_transition",
    }

    assert make_idempotency_key(
        run_id="20260520T120000Z",
        parent_step_id=None,
        mode="narrated",
        planned_action=action_a,
        task_key="company_fundamentals",
        attempt=1,
    ) == make_idempotency_key(
        run_id="20260520T120000Z",
        parent_step_id=None,
        mode="narrated",
        planned_action=action_b,
        task_key="company_fundamentals",
        attempt=1,
    )


def test_step_trace_consumer_deduplicates_by_idempotency_key():
    trace: list[dict] = []
    consumer = StepTraceConsumer(trace)
    first = _step(sequence=1, reflection="first")
    second = _step(sequence=2, reflection="second", idempotency_key=first["identity"]["idempotency_key"])

    consumer.consume(first)
    consumer.consume(second)

    assert len(trace) == 1
    assert trace[0]["outcome"]["reflection"] == "second"


def test_step_emitter_blocks_secret_payload_without_publishing():
    sink = InMemoryStepSink()
    emitter = StepEmitter(
        run_id="20260520T120000Z",
        bus=StepBus([sink]),
        enabled=True,
    )

    result = emitter.emit_narrated(
        phase="first_pass",
        actor="PipelineRunner",
        actor_role="runtime",
        goal="Secret test",
        action_kind="state_transition",
        action_target="test.secret",
        action_payload={"payload": "api_key=0000000000000000"},
        decision="blocked",
        reflection="Should not publish.",
        stop_reason="secret_guard",
    )

    assert result is None
    assert sink.steps == []
    assert emitter.blocked_errors


def test_step_emitter_attaches_default_reasoning_policy():
    sink = InMemoryStepSink()
    emitter = StepEmitter(
        run_id="20260520T120000Z",
        bus=StepBus([sink]),
        enabled=True,
    )

    result = emitter.emit_narrated(
        phase="after_first_pass",
        actor="RuntimeCheckpoint",
        actor_role="runtime",
        goal="Write checkpoint",
        action_kind="state_transition",
        action_target="checkpoint.write",
        action_payload={"checkpoint_id": "after_first_pass"},
        decision="written",
        reflection="Checkpoint written.",
        stop_reason="checkpoint_written",
    )

    assert result is not None
    policy = result["intent"]["reasoning_policy"]
    assert policy["effort"] == "none"
    assert policy["policy_source"] == "rule"
    assert policy["reason"] == "deterministic checkpoint"


def test_step_emitter_resolves_reasoning_policy_for_reasoning_capable_role(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_MEETING_READINESS_GATE", "gpt-5-mini")
    monkeypatch.setenv("OPENAI_STRUCTURED_MODEL_MEETING_READINESS_GATE", "gpt-4.1-mini")
    sink = InMemoryStepSink()
    emitter = StepEmitter(
        run_id="20260520T120000Z",
        bus=StepBus([sink]),
        enabled=True,
    )

    result = emitter.emit_narrated(
        phase="finalization",
        actor="MeetingReadinessGate",
        actor_role="runtime_gate",
        goal="Evaluate meeting readiness",
        action_kind="state_transition",
        action_target="meeting_readiness.evaluate",
        action_payload={"blocker_count": 0},
        decision="meeting_ready",
        reflection="Meeting readiness evaluated.",
        stop_reason="meeting_readiness_evaluated",
    )

    assert result is not None
    policy = result["intent"]["reasoning_policy"]
    assert policy["effort"] == "high"
    assert policy["max_thinking_tokens"] == 32_000
    assert policy["policy_source"] == "rule"
    assert policy["reason"] == "final readiness gate"


def test_step_emitter_derives_reasoning_realized_from_usage():
    sink = InMemoryStepSink()
    emitter = StepEmitter(
        run_id="20260520T120000Z",
        bus=StepBus([sink]),
        enabled=True,
    )

    result = emitter.emit_narrated(
        phase="finalization",
        actor="MeetingReadinessGate",
        actor_role="runtime_gate",
        goal="Evaluate meeting readiness",
        action_kind="state_transition",
        action_target="meeting_readiness.evaluate",
        action_payload={"blocker_count": 0},
        usage={
            "provider": "openai",
            "model": "gpt-5-mini",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "thinking_tokens": 3,
        },
        decision="meeting_ready",
        reflection="Meeting readiness evaluated.",
        stop_reason="meeting_readiness_evaluated",
    )

    assert result is not None
    realized = result["execution"]["reasoning_realized"]
    assert realized["effort_used"] == result["intent"]["reasoning_policy"]["effort"]
    assert realized["thinking_tokens"] == 3
    assert realized["reasoning_summary_available"] is False


def test_run_context_snapshot_round_trips_step_trace():
    context = RunContext(
        run_id="20260520T120000Z",
        intake={"company_name": "Example", "web_domain": "example.com"},
    )
    context.step_trace.append(_step())

    restored = RunContext.from_snapshot(context.snapshot())

    assert restored.step_trace[0]["identity"]["run_id"] == "20260520T120000Z"


def test_export_run_writes_step_trace_artifact(tmp_path):
    run_id = "20260520T120000Z"
    run_dir = tmp_path / run_id
    context = RunContext(
        run_id=run_id,
        intake={"company_name": "Example", "web_domain": "example.com"},
    )
    context.step_trace.append(_step(run_id=run_id))

    export_run(
        run_dir=run_dir,
        run_id=run_id,
        company_name="Example",
        web_domain="example.com",
        status="meeting_ready",
        messages=[],
        pipeline_data={},
        run_context=context.snapshot(),
    )

    payload = json.loads((run_dir / "step_trace.json").read_text(encoding="utf-8"))
    assert payload[0]["identity"]["run_id"] == run_id
