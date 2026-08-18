from __future__ import annotations

from pathlib import Path

import app.kernel
from app.adapters.capability_mapping import classify_legacy_tool
from app.adapters.execution_adapter import LegacyExecutionAdapter
from app.adapters.legacy_models import (
    LegacyExecution,
    LegacyToolCall,
    LegacyWorkflow,
)
from app.adapters.result_adapter import LegacyResultRecord
from app.adapters.shadow import ShadowRunner
from app.kernel.capability.contracts import build_standard_registry
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
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeState,
    ObservedWorldState,
    State,
)


def _external_legacy(world_outcome: str = "SUCCESS") -> LegacyExecution:
    return LegacyExecution(
        execution_id="e-ext",
        workflow=LegacyWorkflow(name="external", agent_chain=["agent-1"]),
        user_input="查询外部订单状态",
        final_output="外部查询结果",
        status="completed",
        tool_calls=[
            LegacyToolCall(
                tool_name="query_db",
                input_params={
                    "external": True,
                    "sql": "SELECT * FROM external_orders",
                    "world_outcome": world_outcome,
                },
                output_result={"rows": [{"status": "paid"}]},
                status="success",
            )
        ],
    )


def _run_external(legacy: LegacyExecution):
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


def test_120_query_db_external_maps_to_observe():
    mapping = classify_legacy_tool("query_db", {"external": True, "sql": "SELECT 1"})

    assert mapping is not None
    assert mapping.capabilities == ["observe"]


def test_121_query_db_external_is_effectful():
    mapping = classify_legacy_tool("query_db", {"external": True, "sql": "SELECT 1"})

    assert mapping.classification == "EFFECTFUL"


def test_122_query_db_external_generates_command():
    output, _ = _run_external(_external_legacy())

    assert output.effect_history[0].command_id != ""


def test_123_command_produces_receipt():
    output, _ = _run_external(_external_legacy())

    assert output.effect_history[0].receipt_status == ReceiptStatus.SUCCESS.value


def test_124_receipt_is_not_observation():
    output, _ = _run_external(_external_legacy())

    assert output.final_state.observed.receipts != {}
    assert output.final_state.observed.observations != {}
    assert set(output.final_state.observed.receipts) != set(
        output.final_state.observed.observations
    )


def test_125_observe_produces_l3_observation():
    output, _ = _run_external(_external_legacy())

    observations = list(output.final_state.observed.observations.values())
    assert all(
        observation.evidence_level == EvidenceLevel.L3_OBSERVED
        for observation in observations
    )


def test_126_observation_enters_observed_world_state():
    output, _ = _run_external(_external_legacy())

    assert output.final_state.observed.observations != {}


def test_127_receipt_alone_cannot_satisfy_l3_goal():
    receipt = ExecutionReceipt(
        receipt_id="r1",
        command_id="c1",
        idempotency_key="K",
        status=ReceiptStatus.SUCCESS,
    )
    receipt_state = State(
        knowledge=KnowledgeState(entries={}),
        observed=ObservedWorldState(receipts={"r1": receipt}),
        context=ExecutionContext(run_id="r"),
    )
    goal = Goal(
        goal_id="g",
        predicate=GoalPredicate(name="observation_exists"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    result = GoalEvaluator().evaluate(receipt_state, goal)

    assert result.status.value == "NOT_SATISFIED"


def test_128_l2_internal_query_cannot_satisfy_l3_goal():
    legacy = LegacyExecution(
        execution_id="e-int",
        workflow=LegacyWorkflow(name="internal", agent_chain=["agent-1"]),
        user_input="内部查询",
        final_output=None,
        status="completed",
        tool_calls=[
            LegacyToolCall(
                tool_name="query_db",
                input_params={"sql": "SELECT 1"},
                output_result={"rows": []},
            )
        ],
    )
    shadow = ShadowRunner().run(
        legacy,
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    assert shadow.kernel_goal_status == "NOT_SATISFIED"


def test_129_l1_prediction_cannot_satisfy_l3_goal():
    state = State(
        knowledge=KnowledgeState(
            entries={
                "p1": KnowledgeEntry(
                    id="p1",
                    kind=KnowledgeKind.PREDICTION,
                    statement="external paid",
                    evidence_level=EvidenceLevel.L1_INFERRED,
                )
            }
        ),
        observed=ObservedWorldState(),
        context=ExecutionContext(run_id="r"),
    )
    goal = Goal(
        goal_id="g",
        predicate=GoalPredicate(name="observation_exists"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )

    result = GoalEvaluator().evaluate(state, goal)

    assert result.status.value == "NOT_SATISFIED"


def test_130_external_observation_satisfies_goal():
    output, _ = _run_external(_external_legacy())

    assert output.goal_result.status.value == "SATISFIED"


def test_131_timeout_but_committed_no_duplicate_effect():
    output, simulator = _run_external(
        _external_legacy(world_outcome="TIMEOUT_BUT_COMMITTED")
    )

    assert simulator.committed_keys() == ["query_db_external:e-ext"]
    assert output.effect_history[0].reconciliation == "CONFIRMED_COMMITTED"
    assert len(output.effect_history) == 1


def test_132_timeout_not_committed_retries():
    output, simulator = _run_external(
        _external_legacy(world_outcome="TIMEOUT_NOT_COMMITTED")
    )

    assert simulator.committed_keys() == ["query_db_external:e-ext"]
    assert len(output.effect_history) == 2
    assert output.effect_history[1].receipt_status == "SUCCESS"


def test_133_retry_reuses_idempotency_key():
    output, _ = _run_external(_external_legacy(world_outcome="TIMEOUT_NOT_COMMITTED"))

    assert (
        output.effect_history[0].idempotency_key
        == output.effect_history[1].idempotency_key
    )
    assert output.effect_history[0].command_id != output.effect_history[1].command_id


def test_134_unknown_result_terminates():
    output, _ = _run_external(_external_legacy(world_outcome="UNKNOWN_RESULT"))

    assert output.termination_reason == TerminationReason.TERMINATED_UNKNOWN_EFFECT


def test_135_duplicate_request_no_second_effect():
    simulator = DeterministicWorldSimulator()
    executor = EffectExecutor(simulator, RetryPolicy(max_retries=1))
    first = Command(command_id="c1", idempotency_key="K", capability_id="observe")
    second = Command(command_id="c2", idempotency_key="K", capability_id="observe")

    executor.execute(first, WorldOutcome.SUCCESS)
    duplicate = executor.execute(second, WorldOutcome.SUCCESS)

    assert duplicate.status == ReceiptStatus.DUPLICATE
    assert simulator.committed_keys() == ["K"]


def test_136_tool_call_success_is_not_observation():
    mapping = classify_legacy_tool("query_db", {"external": True, "sql": "SELECT 1"})

    assert mapping.produces_observation is True
    legacy = _external_legacy()
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    knowledge = adapter.to_knowledge_state(legacy, store)

    assert all(
        entry.kind != KnowledgeKind.PREDICTION
        or entry.evidence_level != EvidenceLevel.L3_OBSERVED
        for entry in knowledge.entries.values()
    )


def test_137_legacy_completed_is_not_observation():
    assert (
        "!="
        in LegacyResultRecord(
            legacy_status="completed",
            kernel_goal_status="SATISFIED",
            kernel_termination="x",
        ).note
    )


def test_138_same_input_is_deterministic():
    first = ShadowRunner().run(_external_legacy())
    second = ShadowRunner().run(_external_legacy())

    assert first.model_dump() == second.model_dump()


def test_139_internal_and_external_are_isolated():
    internal_mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})
    external_mapping = classify_legacy_tool(
        "query_db", {"external": True, "sql": "SELECT 1"}
    )

    assert internal_mapping.classification == "PURE"
    assert external_mapping.classification == "EFFECTFUL"


def test_140_unknown_tool_is_blocked():
    assert classify_legacy_tool("does_not_exist") is None


def test_141_send_email_maps_to_mutate():
    mapping = classify_legacy_tool("send_email")

    assert mapping is not None
    assert mapping.capabilities == ["mutate"]


def test_142_adapter_does_not_pollute_kernel():
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
