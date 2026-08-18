from __future__ import annotations

from pathlib import Path

import app.kernel
from app.adapters.runtime_bridge import (
    LegacyRuntimeBridge,
    build_legacy_snapshot,
    run_shadow_after_execution,
)
from app.kernel.evidence.model import EvidenceLevel


def _snapshot(
    *, tool_calls=None, final_output: str = "结果", status: str = "completed"
):
    return build_legacy_snapshot(
        execution_id="e1",
        user_input="任务",
        final_output=final_output,
        status=status,
        workflow_name="chat",
        agent_chain=["agent-1"],
        tool_calls=tool_calls,
    )


def _search_snapshot():
    return _snapshot(
        tool_calls=[{"tool_name": "search_web", "input_params": {"query": "新能源"}}]
    )


def _send_email_snapshot():
    return _snapshot(
        tool_calls=[
            {
                "tool_name": "send_email",
                "input_params": {"to": "a@b.com", "subject": "hi", "body": "hello"},
            }
        ]
    )


def test_172_real_snapshot_enters_shadow_adapter():
    result = run_shadow_after_execution(
        execution_id="e1",
        user_input="任务",
        final_output="结果",
        status="completed",
        workflow_name="chat",
        tool_calls=[{"tool_name": "search_web", "input_params": {"query": "新能源"}}],
    )

    assert result.shadow_status == "SUCCESS"


def test_173_shadow_adapter_does_not_modify_snapshot():
    snapshot = _search_snapshot()
    before = snapshot.model_dump()

    LegacyRuntimeBridge().run_shadow(snapshot)

    assert snapshot.model_dump() == before


def test_174_shadow_kernel_failure_does_not_affect_legacy():
    class FailingRunner:
        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    bridge = LegacyRuntimeBridge(runner=FailingRunner())
    snapshot = _search_snapshot()
    before = snapshot.model_dump()

    result = bridge.run_shadow(snapshot)

    assert result.shadow_status == "FAILED"
    assert result.error_type == "RuntimeError"
    assert result.error_message == "boom"
    assert snapshot.model_dump() == before


def test_175_kernel_failure_does_not_cause_legacy_runtime_failure():
    class FailingRunner:
        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    result = LegacyRuntimeBridge(runner=FailingRunner()).run_shadow(_search_snapshot())

    assert result.shadow_status == "FAILED"


def test_176_legacy_completed_is_not_kernel_satisfied():
    snapshot = _snapshot(final_output="email sent", tool_calls=[])

    result = LegacyRuntimeBridge().run_shadow(
        snapshot,
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert result.kernel_goal_status == "NOT_SATISFIED"
    assert result.semantic_match is False


def test_177_final_output_is_not_observation():
    snapshot = _snapshot(final_output="email sent", tool_calls=[])

    result = LegacyRuntimeBridge().run_shadow(
        snapshot,
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert result.kernel_goal_status == "NOT_SATISFIED"
    assert result.violations == []


def test_178_tool_call_success_is_not_observation():
    result = LegacyRuntimeBridge().run_shadow(_search_snapshot())

    assert result.violations == []
    assert result.evidence_level == "L2_SUPPORTED"


def test_179_search_web_shadow_stays_l2():
    result = LegacyRuntimeBridge().run_shadow(_search_snapshot())

    assert result.evidence_level == "L2_SUPPORTED"
    assert result.kernel_goal_status == "SATISFIED"


def test_180_query_db_internal_shadow_stays_l2():
    snapshot = _snapshot(
        tool_calls=[
            {
                "tool_name": "query_db",
                "input_params": {"sql": "SELECT 1"},
                "output_result": {"rows": []},
            }
        ]
    )

    result = LegacyRuntimeBridge().run_shadow(snapshot)

    assert result.evidence_level == "L2_SUPPORTED"


def test_181_query_db_external_shadow_produces_l3():
    snapshot = _snapshot(
        tool_calls=[
            {
                "tool_name": "query_db",
                "input_params": {"external": True, "sql": "SELECT 1"},
            }
        ]
    )

    result = LegacyRuntimeBridge().run_shadow(snapshot)

    assert result.evidence_level == "L3_OBSERVED"
    assert result.kernel_goal_status == "SATISFIED"


def test_182_send_email_shadow_receipt_is_not_observation():
    result = LegacyRuntimeBridge().run_shadow(_send_email_snapshot())

    actions = [entry["action"] for entry in result.trace]
    assert "MUTATE" in actions
    assert "OBSERVE" in actions
    observe = next(entry for entry in result.trace if entry["action"] == "OBSERVE")
    assert observe.get("observation_id")
    assert result.evidence_level == "L3_OBSERVED"
    assert result.violations == []


def test_183_semantic_comparison_distinguishes_evidence():
    l2 = LegacyRuntimeBridge().run_shadow(_search_snapshot())
    l3 = LegacyRuntimeBridge().run_shadow(
        _snapshot(
            tool_calls=[
                {
                    "tool_name": "query_db",
                    "input_params": {"external": True, "sql": "SELECT 1"},
                }
            ]
        )
    )
    l3_required = LegacyRuntimeBridge().run_shadow(
        _search_snapshot(),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert l2.evidence_level == "L2_SUPPORTED"
    assert l3.evidence_level == "L3_OBSERVED"
    assert l3_required.semantic_match is False
    assert l3_required.kernel_goal_status == "NOT_SATISFIED"


def test_184_shadow_same_input_is_deterministic():
    first = LegacyRuntimeBridge().run_shadow(_send_email_snapshot())
    second = LegacyRuntimeBridge().run_shadow(_send_email_snapshot())

    assert first.model_dump() == second.model_dump()


def test_185_kernel_shadow_does_not_reverse_import_legacy():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            lowered = stripped.lower()
            if any(
                token in lowered
                for token in (
                    "app.adapters",
                    "app.engine",
                    "app.api",
                    "app.models",
                    "app.core",
                )
            ):
                offenders.append(f"{path}: {stripped}")

    assert offenders == []


def test_186_shadow_off_leaves_legacy_unchanged():
    bridge = LegacyRuntimeBridge(shadow_enabled=False)
    snapshot = _search_snapshot()
    before = snapshot.model_dump()

    result = bridge.run_shadow(snapshot)

    assert result.shadow_status == "DISABLED"
    assert snapshot.model_dump() == before
