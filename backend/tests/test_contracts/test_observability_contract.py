from __future__ import annotations

from app.engine import events

EXPECTED_EVENTS = {
    "status",
    "token",
    "step",
    "tool_call",
    "tool_result",
    "approval_required",
    "error",
    "execution_completed",
    "execution_failed",
    "waiting_for_approval",
    "done",
}


def test_event_names_are_closed_set():
    constants = {
        events.EVENT_STATUS,
        events.EVENT_TOKEN,
        events.EVENT_STEP,
        events.EVENT_TOOL_CALL,
        events.EVENT_TOOL_RESULT,
        events.EVENT_APPROVAL_REQUIRED,
        events.EVENT_ERROR,
        events.EVENT_COMPLETED,
        events.EVENT_FAILED,
        events.EVENT_WAITING,
        events.EVENT_DONE,
    }
    assert constants == EXPECTED_EVENTS


def test_build_event_contract_fields():
    event = events.build_event("token", "exec-1", correlation_id="trace-1", token="x")
    assert {"event_id", "execution_id", "correlation_id", "ts", "event"} <= set(event)
    assert event["execution_id"] == "exec-1"
    assert event["correlation_id"] == "trace-1"
