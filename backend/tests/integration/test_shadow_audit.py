from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import app.kernel
from app.adapters import shadow_audit
from app.adapters.runtime_bridge import ShadowExecutionResult
from app.adapters.shadow_audit import persist_shadow_audit, to_audit_record
from app.engine import runner
from app.models import ShadowAuditRecord


def _fake_execution() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), user_input="任务")


def _fake_workflow() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="chat", agent_chain=["agent-1"])


def _result(**overrides) -> ShadowExecutionResult:
    values = {"shadow_status": "SUCCESS"}
    values.update(overrides)
    return ShadowExecutionResult(**values)


def test_209_shadow_audit_record_can_be_created():
    record = ShadowAuditRecord(
        execution_id=uuid.uuid4(),
        shadow_status="SUCCESS",
        information_loss=[],
        violations=[],
        trace=[],
    )

    assert record.shadow_status == "SUCCESS"
    assert record.information_loss == []


def test_210_shadow_execution_result_converts_to_audit_record():
    execution_id = str(uuid.uuid4())
    result = _result(
        kernel_goal_status="SATISFIED",
        evidence_level="L3_OBSERVED",
        semantic_match=True,
        information_loss=["x"],
        violations=[],
        trace=[{"action": "MUTATE"}],
    )

    record = to_audit_record(
        result,
        execution_id=execution_id,
        workflow_id=None,
    )

    assert record.execution_id == uuid.UUID(execution_id)
    assert record.kernel_goal_status == "SATISFIED"
    assert record.information_loss == ["x"]
    assert record.trace == [{"action": "MUTATE"}]


def test_211_audit_persistence_success(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = None
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def add(self, obj):
            self.added = obj

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(shadow_audit, "async_session_factory", lambda: FakeSession())

    record = asyncio.run(
        persist_shadow_audit(
            _result(),
            execution_id=str(uuid.uuid4()),
            workflow_id=None,
        )
    )

    assert record is not None


def test_212_audit_serialization_is_deterministic():
    execution_id = str(uuid.uuid4())
    result = _result(
        kernel_goal_status="SATISFIED",
        evidence_level="L2_SUPPORTED",
        semantic_match=True,
        information_loss=["a"],
        violations=[],
        trace=[],
    )

    first = to_audit_record(result, execution_id=execution_id, workflow_id=None)
    second = to_audit_record(result, execution_id=execution_id, workflow_id=None)

    assert (
        first.kernel_goal_status,
        first.evidence_level,
        first.information_loss,
        first.trace,
    ) == (
        second.kernel_goal_status,
        second.evidence_level,
        second.information_loss,
        second.trace,
    )


def test_213_kernel_satisfied_is_recorded():
    record = to_audit_record(
        _result(kernel_goal_status="SATISFIED"),
        execution_id=str(uuid.uuid4()),
        workflow_id=None,
    )

    assert record.kernel_goal_status == "SATISFIED"


def test_214_kernel_not_satisfied_is_recorded():
    record = to_audit_record(
        _result(kernel_goal_status="NOT_SATISFIED"),
        execution_id=str(uuid.uuid4()),
        workflow_id=None,
    )

    assert record.kernel_goal_status == "NOT_SATISFIED"


def test_215_shadow_failed_records_error():
    record = to_audit_record(
        _result(
            shadow_status="FAILED",
            error_type="RuntimeError",
            error_message="boom",
        ),
        execution_id=str(uuid.uuid4()),
        workflow_id=None,
    )

    assert record.shadow_status == "FAILED"
    assert record.error_type == "RuntimeError"
    assert record.error_message == "boom"


def test_216_shadow_disabled_does_not_create_audit(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", False)
    recorded = []

    async def fake_persist(*args, **kwargs):
        recorded.append(1)

    monkeypatch.setattr("app.adapters.shadow_audit.persist_shadow_audit", fake_persist)

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final")
    )

    assert result is None
    assert recorded == []


def test_217_218_audit_db_failure_does_not_affect_legacy(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        return []

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)

    async def fail_persist(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.adapters.shadow_audit.persist_shadow_audit", fail_persist)

    execution = _fake_execution()
    workflow = _fake_workflow()
    before = (execution.id, execution.user_input, workflow.id, workflow.name)

    result = asyncio.run(runner.run_shadow_hook(execution, workflow, "final"))

    assert result is not None
    assert result.shadow_status == "SUCCESS"
    assert (execution.id, execution.user_input, workflow.id, workflow.name) == before


def test_219_shadow_audit_is_not_in_kernel_state():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "shadow_audit" in stripped.lower() or "ShadowAudit" in stripped:
                offenders.append(f"{path}: {stripped}")

    assert offenders == []


def test_220_audit_is_not_observation():
    assert ShadowAuditRecord.__module__.startswith("app.models")
    assert "observation" not in ShadowAuditRecord.__tablename__


def test_221_audit_is_not_evidence():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        text = path.read_text()
        if "ShadowAuditRecord" in text:
            offenders.append(str(path))

    assert offenders == []


def test_222_audit_does_not_produce_satisfied():
    record = to_audit_record(
        _result(kernel_goal_status="SATISFIED"),
        execution_id=str(uuid.uuid4()),
        workflow_id=None,
    )

    assert isinstance(record, ShadowAuditRecord)
    assert not hasattr(record, "predicate_result")


def test_223_final_output_not_modified_by_audit(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        return []

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)
    monkeypatch.setattr(
        "app.adapters.shadow_audit.persist_shadow_audit",
        lambda *args, **kwargs: None,
    )

    execution = _fake_execution()
    before = execution.user_input

    asyncio.run(runner.run_shadow_hook(execution, _fake_workflow(), "final"))

    assert execution.user_input == before


def test_224_tool_call_success_not_upgraded_by_audit(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        return [{"tool_name": "search_web", "input_params": {"query": "q"}}]

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)
    monkeypatch.setattr(
        "app.adapters.shadow_audit.persist_shadow_audit",
        lambda *args, **kwargs: None,
    )

    result = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )

    assert result.violations == []
    assert result.evidence_level == "L2_SUPPORTED"


def test_225_same_execution_audit_fields_are_deterministic(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", True)

    async def collect(_execution_id):
        return [{"tool_name": "search_web", "input_params": {"query": "q"}}]

    monkeypatch.setattr(runner, "_collect_shadow_tool_calls", collect)
    monkeypatch.setattr(
        "app.adapters.shadow_audit.persist_shadow_audit",
        lambda *args, **kwargs: None,
    )

    first = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )
    second = asyncio.run(
        runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "结果")
    )

    assert (
        first.kernel_goal_status,
        first.evidence_level,
        first.information_loss,
        first.violations,
        first.trace,
    ) == (
        second.kernel_goal_status,
        second.evidence_level,
        second.information_loss,
        second.violations,
        second.trace,
    )


def test_226_shadow_disabled_no_persistence_side_effect(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", False)
    recorded = []

    async def fake_persist(*args, **kwargs):
        recorded.append(1)

    monkeypatch.setattr("app.adapters.shadow_audit.persist_shadow_audit", fake_persist)

    asyncio.run(runner.run_shadow_hook(_fake_execution(), _fake_workflow(), "final"))

    assert recorded == []
