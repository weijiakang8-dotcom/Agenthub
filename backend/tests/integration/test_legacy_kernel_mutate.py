from __future__ import annotations

from pathlib import Path

import app.kernel
import pytest
from app.adapters.capability_mapping import classify_legacy_tool
from app.adapters.errors import InvalidLegacyToolError
from app.adapters.execution_adapter import LegacyExecutionAdapter
from app.adapters.legacy_models import (
    LegacyExecution,
    LegacyToolCall,
    LegacyWorkflow,
)
from app.adapters.result_adapter import LegacyResultRecord
from app.adapters.shadow import ShadowRunner
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.command import Command
from app.kernel.effects.executor import EffectExecutor
from app.kernel.effects.receipt import ExecutionReceipt, ReceiptStatus
from app.kernel.effects.retry import RetryPolicy
from app.kernel.effects.simulator import DeterministicWorldSimulator, WorldOutcome
from app.kernel.effects.simulator_port import SimulatorEffectPort
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.goal.evaluator import GoalEvaluator
from app.kernel.goal.model import Goal, GoalPredicate
from app.kernel.runtime.loop import KernelRuntime
from app.kernel.runtime.model import TerminationReason
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeState,
    ObservedWorldState,
    State,
)


def _email_legacy(
    *,
    world_outcome: str = "SUCCESS",
    to: str | None = "a@b.com",
    subject: str | None = "hi",
    body: str | None = "hello",
) -> LegacyExecution:
    params: dict = {"world_outcome": world_outcome}
    if to is not None:
        params["to"] = to
    if subject is not None:
        params["subject"] = subject
    if body is not None:
        params["body"] = body
    return LegacyExecution(
        execution_id="e-email",
        workflow=LegacyWorkflow(name="email", agent_chain=["agent-1"]),
        user_input="发邮件",
        final_output="已发送",
        status="completed",
        tool_calls=[
            LegacyToolCall(
                tool_name="send_email", input_params=params, status="success"
            )
        ],
    )


def _run_email(legacy: LegacyExecution):
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    registry = build_standard_registry()
    simulator = DeterministicWorldSimulator()
    executor = SimulatorEffectPort(simulator, RetryPolicy(max_retries=1))
    runtime_input = adapter.to_runtime_input(
        legacy,
        registry=registry,
        store=store,
        executor=executor,
    )
    output = KernelRuntime().run(runtime_input)
    return output, simulator


def test_143_send_email_maps_to_mutate():
    mapping = classify_legacy_tool("send_email")

    assert mapping is not None
    assert mapping.capabilities == ["mutate"]


def test_144_send_email_is_effectful():
    mapping = classify_legacy_tool("send_email")

    assert mapping.classification == "EFFECTFUL"


def test_145_send_email_generates_command():
    output, _ = _run_email(_email_legacy())

    assert output.effect_history[0].command_id != ""


def test_146_command_capability_id_is_mutate():
    plan = LegacyExecutionAdapter().to_plan(_email_legacy())

    assert plan.tasks[0].capability_id == CapabilityId.MUTATE


def test_147_command_payload_is_legal_email():
    plan = LegacyExecutionAdapter().to_plan(_email_legacy())

    assert plan.tasks[0].input_arguments["payload"] == {
        "to": "a@b.com",
        "subject": "hi",
        "body": "hello",
    }


def test_148_receipt_success_is_not_observation():
    output, _ = _run_email(_email_legacy())

    assert output.final_state.observed.receipts != {}
    assert output.final_state.observed.observations != {}
    assert set(output.final_state.observed.receipts) != set(
        output.final_state.observed.observations
    )


def test_149_receipt_success_alone_cannot_satisfy():
    receipt = ExecutionReceipt(
        receipt_id="r1",
        command_id="c1",
        idempotency_key="K",
        status=ReceiptStatus.SUCCESS,
    )
    state = State(
        knowledge=KnowledgeState(entries={}),
        observed=ObservedWorldState(receipts={"r1": receipt}),
        context=ExecutionContext(run_id="r"),
    )
    goal = Goal(
        goal_id="g",
        predicate=GoalPredicate(name="observation_exists"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    result = GoalEvaluator().evaluate(state, goal)

    assert result.status.value == "NOT_SATISFIED"


def test_150_observe_produces_l3_observation():
    output, _ = _run_email(_email_legacy())

    observations = list(output.final_state.observed.observations.values())
    assert all(
        observation.evidence_level == EvidenceLevel.L3_OBSERVED
        for observation in observations
    )


def test_151_observation_committed_true_satisfies_goal():
    output, _ = _run_email(_email_legacy())

    assert output.goal_result.status.value == "SATISFIED"


def test_152_tool_call_success_is_not_observation():
    mapping = classify_legacy_tool("send_email")

    assert mapping.produces_observation is False


def test_153_legacy_completed_is_not_observation():
    record = LegacyResultRecord(
        legacy_status="completed",
        kernel_goal_status="SATISFIED",
        kernel_termination="TERMINATED_GOAL_SATISFIED",
    )

    assert "!=" in record.note


def test_154_timeout_but_committed_does_not_retry():
    output, _ = _run_email(_email_legacy(world_outcome="TIMEOUT_BUT_COMMITTED"))

    mutate_history = [
        entry for entry in output.effect_history if entry.receipt_status == "TIMEOUT"
    ]
    assert len(mutate_history) == 1
    assert mutate_history[0].reconciliation == "CONFIRMED_COMMITTED"


def test_155_timeout_but_committed_effect_count_is_one():
    _, simulator = _run_email(_email_legacy(world_outcome="TIMEOUT_BUT_COMMITTED"))

    assert len(simulator.committed_keys()) == 1


def test_156_timeout_not_committed_retries():
    output, _ = _run_email(_email_legacy(world_outcome="TIMEOUT_NOT_COMMITTED"))

    mutate_history = [
        entry
        for entry in output.effect_history
        if entry.receipt_status in {"TIMEOUT", "SUCCESS"}
    ]
    assert len(mutate_history) == 2


def test_157_retry_has_new_command_id():
    output, _ = _run_email(_email_legacy(world_outcome="TIMEOUT_NOT_COMMITTED"))

    mutate_history = [
        entry
        for entry in output.effect_history
        if entry.receipt_status in {"TIMEOUT", "SUCCESS"}
    ]
    assert mutate_history[0].command_id != mutate_history[1].command_id


def test_158_retry_reuses_idempotency_key():
    output, _ = _run_email(_email_legacy(world_outcome="TIMEOUT_NOT_COMMITTED"))

    mutate_history = [
        entry
        for entry in output.effect_history
        if entry.receipt_status in {"TIMEOUT", "SUCCESS"}
    ]
    assert mutate_history[0].idempotency_key == mutate_history[1].idempotency_key


def test_159_retry_final_effect_count_is_one():
    _, simulator = _run_email(_email_legacy(world_outcome="TIMEOUT_NOT_COMMITTED"))

    assert len(simulator.committed_keys()) == 1


def test_160_unknown_result_does_not_auto_retry():
    output, _ = _run_email(_email_legacy(world_outcome="UNKNOWN_RESULT"))

    assert output.termination_reason == TerminationReason.TERMINATED_UNKNOWN_EFFECT


def test_161_unknown_result_terminates():
    output, _ = _run_email(_email_legacy(world_outcome="UNKNOWN_RESULT"))

    assert output.termination_reason == TerminationReason.TERMINATED_UNKNOWN_EFFECT


def test_162_duplicate_request_no_second_effect():
    simulator = DeterministicWorldSimulator()
    executor = EffectExecutor(simulator, RetryPolicy(max_retries=1))
    first = Command(command_id="c1", idempotency_key="K", capability_id="mutate")
    second = Command(command_id="c2", idempotency_key="K", capability_id="mutate")

    executor.execute(first, WorldOutcome.SUCCESS)
    duplicate = executor.execute(second, WorldOutcome.SUCCESS)

    assert duplicate.status == ReceiptStatus.DUPLICATE
    assert simulator.committed_keys() == ["K"]


def test_163_same_idempotency_key_dedup():
    simulator = DeterministicWorldSimulator()
    executor = EffectExecutor(simulator, RetryPolicy(max_retries=1))
    first = Command(command_id="c1", idempotency_key="email-id", capability_id="mutate")
    second = Command(
        command_id="c2", idempotency_key="email-id", capability_id="mutate"
    )

    executor.execute(first, WorldOutcome.SUCCESS)
    assert (
        executor.execute(second, WorldOutcome.SUCCESS).status == ReceiptStatus.DUPLICATE
    )


@pytest.mark.parametrize("field", ["to", "subject", "body"])
def test_164_166_missing_required_field_is_invalid(field):
    legacy = _email_legacy(**{field: None})

    with pytest.raises(InvalidLegacyToolError):
        LegacyExecutionAdapter().to_plan(legacy)


def test_167_same_input_is_deterministic():
    first = ShadowRunner().run(_email_legacy())
    second = ShadowRunner().run(_email_legacy())

    assert first.model_dump() == second.model_dump()


def test_168_send_email_isolated_from_external_query_db():
    assert classify_legacy_tool("send_email").capabilities == ["mutate"]
    assert classify_legacy_tool(
        "query_db", {"external": True, "sql": "SELECT 1"}
    ).capabilities == ["observe"]


def test_169_send_email_isolated_from_internal_query_db():
    assert classify_legacy_tool("send_email").classification == "EFFECTFUL"
    assert (
        classify_legacy_tool("query_db", {"sql": "SELECT 1"}).classification == "PURE"
    )


def test_170_unknown_tool_is_blocked():
    assert classify_legacy_tool("does_not_exist") is None


def test_171_adapter_does_not_pollute_kernel():
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
