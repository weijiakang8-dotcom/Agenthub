from __future__ import annotations

from pathlib import Path

import app.adapters
import app.kernel
from app.adapters.capability_mapping import (
    LEGACY_CAPABILITY_MAP,
    classify_legacy_tool,
)
from app.adapters.execution_adapter import LegacyExecutionAdapter
from app.adapters.legacy_models import (
    LegacyExecution,
    LegacyToolCall,
    LegacyWorkflow,
)
from app.adapters.result_adapter import LegacyResultAdapter
from app.adapters.shadow import ShadowRunner
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.retry import RetryPolicy
from app.kernel.effects.simulator import DeterministicWorldSimulator
from app.kernel.effects.simulator_port import SimulatorEffectPort
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.runtime.loop import KernelRuntime
from app.kernel.runtime.model import TerminationReason
from app.kernel.state.model import ObservedWorldState


def _legacy(
    *,
    final_output: str = "分析报告",
    status: str = "completed",
    tool_calls: list[LegacyToolCall] | None = None,
) -> LegacyExecution:
    return LegacyExecution(
        execution_id="e1",
        workflow=LegacyWorkflow(name="chat", agent_chain=["agent-1"]),
        user_input="分析新能源",
        final_output=final_output,
        status=status,
        tool_calls=tool_calls or [],
    )


def _query_db_legacy(
    *,
    sql: str = "SELECT 1",
    external: bool = False,
    final_output: str = "查询结果",
    status: str = "completed",
) -> LegacyExecution:
    params = {"sql": sql}
    if external:
        params["external"] = True
    return _legacy(
        final_output=final_output,
        status=status,
        tool_calls=[
            LegacyToolCall(
                tool_name="query_db",
                input_params=params,
                output_result={"rows": [{"id": 1}]},
            )
        ],
    )


def _forbidden_deps() -> set[str]:
    return {
        "fastapi",
        "langgraph",
        "langchain",
        "celery",
        "redis",
        "sqlalchemy",
        "asyncpg",
        "psycopg",
        "httpx",
        "openai",
        "anthropic",
        "smtplib",
        "uvicorn",
        "requests",
    }


def _import_lines(directory: Path) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    for path in directory.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                result.append((path, stripped))
    return result


def test_93_legacy_to_kernel_state_adapter():
    legacy = _legacy(
        tool_calls=[
            LegacyToolCall(tool_name="search_web", input_params={"query": "新能源"})
        ]
    )
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)

    knowledge = adapter.to_knowledge_state(legacy, store)

    assert "derived:final_output" in knowledge.entries
    assert (
        knowledge.entries["derived:final_output"].evidence_level
        == EvidenceLevel.L1_INFERRED
    )
    assert "fact:search_web" in knowledge.entries
    assert (
        knowledge.entries["fact:search_web"].evidence_level
        == EvidenceLevel.L2_SUPPORTED
    )


def test_94_legacy_final_output_is_not_observation():
    legacy = _legacy(final_output="LLM 生成的结论")
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)

    knowledge = adapter.to_knowledge_state(legacy, store)

    assert (
        knowledge.entries["derived:final_output"].evidence_level
        == EvidenceLevel.L1_INFERRED
    )
    assert ObservedWorldState().observations == {}


def test_95_legacy_tool_call_is_not_observation():
    mapping = LEGACY_CAPABILITY_MAP["search_web"]

    assert mapping.produces_observation is False
    assert mapping.classification == "PURE"


def test_96_legacy_completed_is_not_kernel_satisfied():
    legacy = _legacy(final_output="预测成功", status="completed")
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    registry = build_standard_registry()
    executor = SimulatorEffectPort(
        DeterministicWorldSimulator(), RetryPolicy(max_retries=1)
    )

    runtime_input = adapter.to_runtime_input(
        legacy,
        registry=registry,
        store=store,
        executor=executor,
        goal=adapter.to_goal(required_evidence=EvidenceLevel.L3_OBSERVED),
    )
    output = KernelRuntime().run(runtime_input)

    assert legacy.status == "completed"
    assert output.goal_result.status.value == "NOT_SATISFIED"


def test_97_legacy_execution_to_kernel_runtime_input():
    legacy = _legacy()
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    registry = build_standard_registry()
    executor = SimulatorEffectPort(
        DeterministicWorldSimulator(), RetryPolicy(max_retries=1)
    )

    runtime_input = adapter.to_runtime_input(
        legacy,
        registry=registry,
        store=store,
        executor=executor,
    )

    assert runtime_input.plan.tasks[0].capability_id == CapabilityId.RETRIEVE
    output = KernelRuntime().run(runtime_input)
    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED


def test_98_kernel_runtime_output_to_legacy_result():
    legacy = _legacy()
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    registry = build_standard_registry()
    executor = SimulatorEffectPort(
        DeterministicWorldSimulator(), RetryPolicy(max_retries=1)
    )
    runtime_input = adapter.to_runtime_input(
        legacy,
        registry=registry,
        store=store,
        executor=executor,
    )
    output = KernelRuntime().run(runtime_input)

    result = LegacyResultAdapter().to_legacy_result(legacy, output)

    assert result.legacy_status == "completed"
    assert result.kernel_goal_status == "SATISFIED"
    assert "!=" in result.note


def test_99_shadow_mode_does_not_alter_legacy_result():
    legacy = _legacy(final_output="报告")
    before = legacy.model_dump()

    ShadowRunner().run(legacy)

    assert legacy.model_dump() == before


def test_100_semantic_comparison():
    pure_shadow = ShadowRunner().run(_legacy(final_output="报告"))
    assert pure_shadow.semantic_match is True

    l3_shadow = ShadowRunner().run(
        _legacy(final_output="预测"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )
    assert l3_shadow.semantic_match is False
    assert l3_shadow.kernel_goal_status == "NOT_SATISFIED"


def test_101_information_loss_detection():
    shadow = ShadowRunner().run(_legacy())

    assert "agent identity dropped from plan" in shadow.information_loss
    assert "final_output demoted to L1_INFERRED" in shadow.information_loss


def test_102_adapter_dependency_direction():
    kernel_dir = Path(app.kernel.__file__).parent
    adapters_dir = Path(app.adapters.__file__).parent

    kernel_imports = _import_lines(kernel_dir)
    assert all("app.adapters" not in line for _, line in kernel_imports)

    adapter_imports = _import_lines(adapters_dir)
    assert any("app.kernel" in line for _, line in adapter_imports)


def test_103_kernel_remains_dependency_clean():
    kernel_dir = Path(app.kernel.__file__).parent
    forbidden = _forbidden_deps() | {"app.adapters"}
    offenders: list[str] = []

    for path, line in _import_lines(kernel_dir):
        lowered = line.lower()
        for dependency in forbidden:
            if dependency in lowered:
                offenders.append(f"{path}: {line}")

    assert offenders == []


def test_104_end_to_end_shadow_execution():
    legacy = _legacy(
        final_output="分析报告",
        tool_calls=[LegacyToolCall(tool_name="search_web")],
    )

    shadow = ShadowRunner().run(legacy)

    assert shadow.legacy_status == "completed"
    assert shadow.kernel_goal_status == "SATISFIED"
    assert shadow.kernel_termination == "TERMINATED_GOAL_SATISFIED"
    assert shadow.violations == []
    assert len(shadow.trace) == 1


def test_105_query_db_internal_maps_to_retrieve():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping is not None
    assert mapping.capabilities == ["retrieve"]


def test_106_query_db_internal_is_pure():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.classification == "PURE"


def test_107_query_db_internal_is_l2_supported():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.evidence_level == "L2_SUPPORTED"


def test_108_query_db_internal_produces_no_command():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.produces_command is False


def test_109_query_db_internal_produces_no_receipt():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.produces_receipt is False


def test_110_query_db_internal_produces_no_observation():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.produces_observation is False


def test_111_query_db_internal_satisfies_goal_without_observation():
    legacy = _query_db_legacy()
    adapter = LegacyExecutionAdapter()
    store = adapter.build_artifact_store(legacy)
    registry = build_standard_registry()
    executor = SimulatorEffectPort(
        DeterministicWorldSimulator(), RetryPolicy(max_retries=1)
    )
    runtime_input = adapter.to_runtime_input(
        legacy,
        registry=registry,
        store=store,
        executor=executor,
    )

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status.value == "SATISFIED"
    assert output.final_state.observed.observations == {}
    assert output.final_state.observed.receipts == {}


def test_112_query_db_external_maps_to_observe():
    mapping = classify_legacy_tool("query_db", {"external": True, "sql": "SELECT 1"})

    assert mapping is not None
    assert mapping.capabilities == ["observe"]


def test_113_send_email_maps_to_mutate():
    mapping = classify_legacy_tool("send_email")

    assert mapping is not None
    assert mapping.capabilities == ["mutate"]


def test_114_unknown_tool_has_no_fallback():
    assert classify_legacy_tool("does_not_exist") is None


def test_115_tool_call_success_is_not_observation():
    mapping = classify_legacy_tool("query_db", {"sql": "SELECT 1"})

    assert mapping.produces_observation is False

    legacy = _query_db_legacy(status="completed")
    shadow = ShadowRunner().run(legacy)
    assert shadow.violations == []


def test_116_legacy_completed_is_not_kernel_satisfied():
    legacy = _query_db_legacy(status="completed")
    shadow = ShadowRunner().run(legacy, required_evidence=EvidenceLevel.L3_OBSERVED)

    assert legacy.status == "completed"
    assert shadow.kernel_goal_status == "NOT_SATISFIED"


def test_117_query_db_internal_shadow_semantic_comparison():
    pure_shadow = ShadowRunner().run(_query_db_legacy(status="completed"))
    assert pure_shadow.semantic_match is True

    l3_shadow = ShadowRunner().run(
        _query_db_legacy(status="completed"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )
    assert l3_shadow.semantic_match is False
    assert l3_shadow.kernel_goal_status == "NOT_SATISFIED"


def test_118_query_db_internal_is_deterministic():
    first = ShadowRunner().run(_query_db_legacy(status="completed"))
    second = ShadowRunner().run(_query_db_legacy(status="completed"))

    assert first.model_dump() == second.model_dump()


def test_119_adapter_does_not_pollute_kernel():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path, line in _import_lines(kernel_dir):
        lowered = line.lower()
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
            offenders.append(f"{path}: {line}")

    assert offenders == []
