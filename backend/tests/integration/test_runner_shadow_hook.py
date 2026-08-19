from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import app.kernel
import pytest
from app.adapters.runtime_bridge import (
    LegacyRuntimeBridge,
    ShadowExecutionResult,
    build_legacy_snapshot,
    run_shadow_after_execution,
)
from app.engine import runner
from app.kernel.evidence.model import EvidenceLevel


def _fake_execution() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), user_input="任务")


def _fake_workflow() -> SimpleNamespace:
    return SimpleNamespace(name="chat", agent_chain=["agent-1"])


def _enable_shadow(monkeypatch, *, tool_calls=None, bridge=None):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        return tool_calls or []

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)
    if bridge is not None:
        monkeypatch.setattr(
            "app.adapters.runtime_bridge.run_shadow_after_execution",
            bridge,
        )


def test_187_real_run_execution_can_trigger_shadow_hook(monkeypatch):
    recorded = []

    def fake_bridge(**kwargs):
        recorded.append(kwargs)
        return ShadowExecutionResult(
            shadow_status="SUCCESS",
            kernel_goal_status="SATISFIED",
            evidence_level="L2_SUPPORTED",
        )

    _enable_shadow(monkeypatch, bridge=fake_bridge)

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert recorded != []
    assert result.shadow_status == "SUCCESS"


def test_188_shadow_disabled_does_not_run_kernel(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", False)
    recorded = []

    def fake_bridge(**kwargs):
        recorded.append(kwargs)
        return ShadowExecutionResult(shadow_status="SUCCESS")

    monkeypatch.setattr(
        "app.adapters.runtime_bridge.run_shadow_after_execution",
        fake_bridge,
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert result is None
    assert recorded == []


def test_189_shadow_enabled_runs_kernel(monkeypatch):
    recorded = []

    def fake_bridge(**kwargs):
        recorded.append(kwargs)
        return ShadowExecutionResult(shadow_status="SUCCESS")

    _enable_shadow(monkeypatch, bridge=fake_bridge)
    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert result.shadow_status == "SUCCESS"
    assert recorded != []


def test_190_191_192_shadow_does_not_modify_legacy_result(monkeypatch):
    execution = _fake_execution()
    workflow = _fake_workflow()
    before = (execution.id, execution.user_input, workflow.name, workflow.agent_chain)

    _enable_shadow(
        monkeypatch,
        bridge=lambda **kwargs: ShadowExecutionResult(shadow_status="SUCCESS"),
    )
    asyncio.run(runner.run_shadow_hook(execution, workflow, "final"))

    assert (
        execution.id,
        execution.user_input,
        workflow.name,
        workflow.agent_chain,
    ) == before


@pytest.mark.parametrize("error", [RuntimeError, ValueError, KeyError])
def test_193_194_195_shadow_exception_does_not_affect_legacy(monkeypatch, error):
    def failing_bridge(**kwargs):
        raise error("boom")

    _enable_shadow(monkeypatch, bridge=failing_bridge)
    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert result is None


def test_196_invalid_shadow_input_does_not_affect_legacy(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        raise ValueError("invalid")

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert result is None


def test_197_shadow_failed_is_structured():
    class FailingRunner:
        def run(self, *args, **kwargs):
            raise RuntimeError("boom")

    snapshot = build_legacy_snapshot(
        execution_id="e1",
        user_input="任务",
        final_output="结果",
        status="completed",
        workflow_name="chat",
    )
    result = LegacyRuntimeBridge(runner=FailingRunner()).run_shadow(snapshot)

    assert result.shadow_status == "FAILED"
    assert result.error_type == "RuntimeError"
    assert result.error_message == "boom"


def test_198_search_web_runner_shadow_l2(monkeypatch):
    _enable_shadow(
        monkeypatch,
        tool_calls=[{"tool_name": "search_web", "input_params": {"query": "新能源"}}],
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )

    assert result.evidence_level == "L2_SUPPORTED"
    assert result.kernel_goal_status == "SATISFIED"


def test_199_query_db_internal_runner_shadow_l2(monkeypatch):
    _enable_shadow(
        monkeypatch,
        tool_calls=[{"tool_name": "query_db", "input_params": {"sql": "SELECT 1"}}],
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )

    assert result.evidence_level == "L2_SUPPORTED"


def test_200_query_db_external_runner_shadow_l3(monkeypatch):
    _enable_shadow(
        monkeypatch,
        tool_calls=[
            {
                "tool_name": "query_db",
                "input_params": {"external": True, "sql": "SELECT 1"},
            }
        ],
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )

    assert result.evidence_level == "L3_OBSERVED"
    assert result.kernel_goal_status == "SATISFIED"


def test_201_send_email_runner_shadow_receipt_is_not_observation(monkeypatch):
    _enable_shadow(
        monkeypatch,
        tool_calls=[
            {
                "tool_name": "send_email",
                "input_params": {"to": "a@b.com", "subject": "hi", "body": "hello"},
            }
        ],
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "已发送")
    )

    actions = [entry["action"] for entry in result.trace]
    assert "MUTATE" in actions
    assert "OBSERVE" in actions
    assert result.evidence_level == "L3_OBSERVED"
    assert result.violations == []


def test_202_legacy_completed_is_not_kernel_satisfied():
    result = run_shadow_after_execution(
        execution_id="e1",
        user_input="任务",
        final_output="email sent",
        status="completed",
        workflow_name="chat",
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert result.kernel_goal_status == "NOT_SATISFIED"


def test_203_final_output_is_not_observation():
    result = run_shadow_after_execution(
        execution_id="e1",
        user_input="任务",
        final_output="email sent",
        status="completed",
        workflow_name="chat",
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert result.kernel_goal_status == "NOT_SATISFIED"
    assert result.violations == []


def test_204_tool_call_success_is_not_observation():
    result = run_shadow_after_execution(
        execution_id="e1",
        user_input="任务",
        final_output="结果",
        status="completed",
        workflow_name="chat",
        tool_calls=[
            {
                "tool_name": "search_web",
                "input_params": {"query": "q"},
                "status": "success",
            }
        ],
    )

    assert result.violations == []
    assert result.evidence_level == "L2_SUPPORTED"


def test_205_shadow_same_input_is_deterministic(monkeypatch):
    _enable_shadow(
        monkeypatch,
        tool_calls=[
            {
                "tool_name": "send_email",
                "input_params": {"to": "a@b.com", "subject": "hi", "body": "hello"},
            }
        ],
    )

    first = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "已发送")
    )
    second = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "已发送")
    )

    assert first.model_dump() == second.model_dump()


def test_206_shadow_does_not_reverse_pollute_kernel():
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


def test_207_kernel_does_not_import_legacy():
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
                for token in ("app.engine", "app.api", "app.models", "app.core")
            ):
                offenders.append(f"{path}: {stripped}")

    assert offenders == []


def test_208_shadow_disabled_legacy_result_unchanged(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", False)
    execution = _fake_execution()
    workflow = _fake_workflow()
    before = (execution.id, execution.user_input, workflow.name, workflow.agent_chain)

    result = asyncio.run(runner.run_shadow_hook(execution, workflow, "final"))

    assert result is None
    assert (
        execution.id,
        execution.user_input,
        workflow.name,
        workflow.agent_chain,
    ) == before
