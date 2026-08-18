from __future__ import annotations

from pathlib import Path

import app.kernel
from app.kernel.artifact.model import Artifact
from app.kernel.artifact.store import ArtifactStore
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.retry import RetryPolicy
from app.kernel.effects.simulator import DeterministicWorldSimulator
from app.kernel.effects.simulator_port import SimulatorEffectPort
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.goal.model import Goal, GoalPredicate
from app.kernel.goal.result import GoalStatus
from app.kernel.plan.model import Dependency, Plan
from app.kernel.runtime.loop import KernelRuntime
from app.kernel.runtime.model import RuntimeInput, TerminationReason
from app.kernel.state.model import ExecutionContext, KnowledgeKind, State
from app.kernel.task.model import Task


def _state() -> State:
    return State(context=ExecutionContext(run_id="run-1"))


def _store() -> ArtifactStore:
    store = ArtifactStore()
    store.put(
        Artifact.create(
            artifact_id="a1",
            artifact_type="text/plain",
            content=b"data",
            evidence_level=EvidenceLevel.L2_SUPPORTED,
            producer="test",
        )
    )
    return store


def _input(
    plan: Plan,
    goal: Goal,
    *,
    max_retries: int = 1,
    max_steps: int = 100,
) -> tuple[RuntimeInput, DeterministicWorldSimulator]:
    simulator = DeterministicWorldSimulator()
    executor = SimulatorEffectPort(simulator, RetryPolicy(max_retries=max_retries))
    return (
        RuntimeInput(
            initial_state=_state(),
            plan=plan,
            goal=goal,
            capability_registry=build_standard_registry(),
            artifact_store=_store(),
            effect_port=executor,
            max_steps=max_steps,
        ),
        simulator,
    )


def _goal(
    name: str = "always_true",
    required: EvidenceLevel = EvidenceLevel.L1_INFERRED,
    **params,
) -> Goal:
    return Goal(
        goal_id="g1",
        predicate=GoalPredicate(name=name, params=params),
        required_evidence=required,
    )


def _retrieve(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.RETRIEVE,
        input_artifacts=["a1"],
        input_arguments={"artifact_id": "a1"},
    )


def _reason(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.REASON,
        input_arguments={"premises": ["p1"]},
    )


def _mutate(task_id: str = "t1", key: str = "K", outcome: str = "SUCCESS") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.MUTATE,
        input_arguments={"idempotency_key": key, "world_outcome": outcome},
    )


def _observe(task_id: str = "t1", key: str = "K") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.OBSERVE,
        input_arguments={"idempotency_key": key},
    )


def test_63_pure_task_transitions_state():
    plan = Plan(plan_id="p", tasks=[_retrieve()])
    goal = _goal(name="knowledge_entry_exists", kind="CANDIDATE_ARTIFACT")
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.applied_tasks == ["t1"]
    assert "retrieved:a1" in output.final_state.knowledge.entries


def test_64_multi_task_plan_executes_in_dependency_order():
    plan = Plan(
        plan_id="p",
        tasks=[_reason("t2"), _retrieve("t1")],
        dependencies=[Dependency(task_id="t2", on_task_id="t1")],
    )
    goal = _goal(name="knowledge_entry_exists", kind="HYPOTHESIS")
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.applied_tasks == ["t1", "t2"]


def test_65_reason_cannot_satisfy_l3_goal():
    plan = Plan(plan_id="p", tasks=[_reason()])
    goal = _goal(
        name="knowledge_entry_exists",
        required=EvidenceLevel.L3_OBSERVED,
        kind="HYPOTHESIS",
    )
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_NO_PATH
    assert output.goal_result.status == GoalStatus.NOT_SATISFIED
    assert output.final_state.observed.observations == {}


def test_66_observe_satisfies_l3_goal():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K"), _observe("t2", "K")])
    goal = _goal(
        name="observation_committed_equals",
        required=EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.final_state.observed.observations != {}


def test_67_receipt_success_is_not_observation():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K", "SUCCESS")])
    goal = _goal(
        name="observation_exists",
        required=EvidenceLevel.L3_OBSERVED,
    )
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.final_state.observed.observations == {}
    assert output.final_state.observed.receipts != {}
    assert output.goal_result.status == GoalStatus.NOT_SATISFIED


def test_68_timeout_but_committed_no_duplicate_effect():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K", "TIMEOUT_BUT_COMMITTED")])
    goal = _goal(
        name="observation_committed_equals",
        required=EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, simulator = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    assert len(output.effect_history) == 1
    assert output.effect_history[0].receipt_status == "TIMEOUT"
    assert output.effect_history[0].reconciliation == "CONFIRMED_COMMITTED"


def test_69_timeout_not_committed_retries_with_same_idempotency_key():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K", "TIMEOUT_NOT_COMMITTED")])
    goal = _goal(
        name="observation_committed_equals",
        required=EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, simulator = _input(plan, goal, max_retries=1)

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    assert len(output.effect_history) == 2
    assert output.effect_history[0].reconciliation == "CONFIRMED_NOT_COMMITTED"
    assert output.effect_history[1].receipt_status == "SUCCESS"
    assert (
        output.effect_history[0].idempotency_key
        == output.effect_history[1].idempotency_key
    )
    assert output.effect_history[0].command_id != output.effect_history[1].command_id


def test_70_duplicate_request_no_second_effect():
    plan = Plan(
        plan_id="p",
        tasks=[_mutate("t1", "K", "SUCCESS"), _mutate("t2", "K", "SUCCESS")],
    )
    runtime_input, simulator = _input(plan, _goal(name="always_false"))

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    assert output.effect_history[1].receipt_status == "DUPLICATE"


def test_71_unknown_result_terminates_deterministically():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K", "UNKNOWN_RESULT")])
    runtime_input, _ = _input(plan, _goal(name="always_false"))

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_UNKNOWN_EFFECT


def test_72_no_executable_task_terminates_no_path():
    plan = Plan(plan_id="p", tasks=[])
    runtime_input, _ = _input(plan, _goal(name="always_false"))

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_NO_PATH


def test_73_max_steps_terminates_deterministically():
    plan = Plan(plan_id="p", tasks=[_reason("t1"), _reason("t2")])
    runtime_input, _ = _input(plan, _goal(name="always_false"), max_steps=1)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_MAX_STEPS


def test_74_same_input_identical_trace():
    plan = Plan(plan_id="p", tasks=[_retrieve("t1"), _mutate("t2", "K", "SUCCESS")])
    goal = _goal()

    def run():
        runtime_input, _ = _input(plan, goal)
        return KernelRuntime().run(runtime_input)

    first = run()
    second = run()

    assert first == second
    assert first.model_dump() == second.model_dump()


def test_75_runtime_does_not_mutate_previous_state():
    plan = Plan(plan_id="p", tasks=[_retrieve()])
    goal = _goal(name="knowledge_entry_exists", kind="CANDIDATE_ARTIFACT")
    runtime_input, _ = _input(plan, goal)
    previous = runtime_input.initial_state

    output = KernelRuntime().run(runtime_input)

    assert previous.context.trace == []
    assert output.final_state != previous


def test_76_kernel_has_no_legacy_runtime_dependency():
    forbidden = {
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
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            lowered = stripped.lower()
            for dependency in forbidden:
                if dependency in lowered:
                    offenders.append(f"{path}: {stripped}")

    assert offenders == []


def test_77_architecture_failure_regression():
    plan = Plan(plan_id="p", tasks=[_reason()])
    goal = _goal(
        name="knowledge_entry_exists",
        required=EvidenceLevel.L3_OBSERVED,
        kind="HYPOTHESIS",
    )
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status == GoalStatus.NOT_SATISFIED
    assert output.final_state.observed.observations == {}
    entry = next(iter(output.final_state.knowledge.entries.values()))
    assert entry.kind == KnowledgeKind.HYPOTHESIS
    assert entry.evidence_level == EvidenceLevel.L1_INFERRED
