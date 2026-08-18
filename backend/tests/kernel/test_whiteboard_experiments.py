from __future__ import annotations

from app.kernel.artifact.model import Artifact, ArtifactRef
from app.kernel.artifact.store import ArtifactStore
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.retry import RetryPolicy
from app.kernel.effects.simulator import DeterministicWorldSimulator
from app.kernel.effects.simulator_port import SimulatorEffectPort
from app.kernel.evidence.model import EvidenceLevel, satisfies_required_evidence
from app.kernel.goal.evaluator import GoalEvaluator
from app.kernel.goal.model import Goal, GoalPredicate
from app.kernel.goal.result import GoalStatus
from app.kernel.plan.model import Plan
from app.kernel.runtime.loop import KernelRuntime
from app.kernel.runtime.model import RuntimeInput, TerminationReason
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeState,
    Observation,
    ObservedWorldState,
    State,
)
from app.kernel.task.model import Task


def _state() -> State:
    return State(context=ExecutionContext(run_id="run-1"))


def _store() -> ArtifactStore:
    store = ArtifactStore()
    store.put(
        Artifact.create(
            artifact_id="a1",
            artifact_type="text/plain",
            content=b"source-data",
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
) -> tuple[RuntimeInput, DeterministicWorldSimulator]:
    simulator = DeterministicWorldSimulator()
    return (
        RuntimeInput(
            initial_state=_state(),
            plan=plan,
            goal=goal,
            capability_registry=build_standard_registry(),
            artifact_store=_store(),
            effect_port=SimulatorEffectPort(
                simulator, RetryPolicy(max_retries=max_retries)
            ),
        ),
        simulator,
    )


def _goal(name: str, required: EvidenceLevel, **params) -> Goal:
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


def _extract(task_id: str = "t2") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.EXTRACT,
        input_artifacts=["a1"],
        input_arguments={"source_artifact_id": "a1", "facts": ["fact-1"]},
    )


def _compute(task_id: str = "t3") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.COMPUTE,
        input_arguments={"operation": "sum", "inputs": ["1", "2"]},
    )


def _reason(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.REASON,
        input_arguments={"premises": ["test_valid_login PASS"]},
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


def test_78_whiteboard_experiment_1_pure_knowledge_derivation():
    plan = Plan(
        plan_id="p",
        tasks=[_retrieve("t1"), _extract("t2"), _compute("t3")],
    )
    goal = _goal(
        "knowledge_entry_exists",
        EvidenceLevel.L2_SUPPORTED,
        kind="DERIVED_ARTIFACT",
    )
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.goal_result.status == GoalStatus.SATISFIED
    assert output.final_state.observed.observations == {}
    assert output.final_state.observed.receipts == {}
    assert all(entry.action == "PURE_TRANSITION" for entry in output.execution_trace)


def test_79_whiteboard_experiment_2_prediction_cannot_become_reality():
    plan = Plan(plan_id="p", tasks=[_reason()])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status == GoalStatus.NOT_SATISFIED
    assert output.final_state.observed.observations == {}


def test_80_whiteboard_experiment_2_observation_satisfies_l3():
    plan = Plan(plan_id="p", tasks=[_reason("t1"), _observe("t2", "K")])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.goal_result.status == GoalStatus.SATISFIED
    assert output.final_state.observed.observations != {}


def test_81_whiteboard_experiment_3_mutate_success():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K"), _observe("t2", "K")])
    goal = _goal(
        "observation_committed_equals",
        EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, simulator = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert simulator.committed_keys() == ["K"]
    assert output.final_state.observed.observations != {}


def test_82_whiteboard_experiment_3_timeout_but_committed():
    plan = Plan(
        plan_id="p",
        tasks=[_mutate("t1", "K", "TIMEOUT_BUT_COMMITTED"), _observe("t2", "K")],
    )
    goal = _goal(
        "observation_committed_equals",
        EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, simulator = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    mutate_history = [e for e in output.effect_history if e.receipt_status == "TIMEOUT"]
    assert len(mutate_history) == 1
    assert mutate_history[0].reconciliation == "CONFIRMED_COMMITTED"
    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED


def test_83_whiteboard_experiment_3_timeout_not_committed_retry():
    plan = Plan(
        plan_id="p",
        tasks=[_mutate("t1", "K", "TIMEOUT_NOT_COMMITTED"), _observe("t2", "K")],
    )
    goal = _goal(
        "observation_committed_equals",
        EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, simulator = _input(plan, goal, max_retries=1)

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    assert len(output.effect_history) == 3
    assert output.effect_history[0].receipt_status == "TIMEOUT"
    assert output.effect_history[1].receipt_status == "SUCCESS"
    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED


def test_84_idempotency_key_reuse():
    plan = Plan(
        plan_id="p",
        tasks=[_mutate("t1", "K", "TIMEOUT_NOT_COMMITTED"), _observe("t2", "K")],
    )
    goal = _goal(
        "observation_committed_equals",
        EvidenceLevel.L3_OBSERVED,
        value=True,
    )
    runtime_input, _ = _input(plan, goal, max_retries=1)

    output = KernelRuntime().run(runtime_input)
    mutate_history = [
        e for e in output.effect_history if e.receipt_status in {"TIMEOUT", "SUCCESS"}
    ]

    assert mutate_history[0].idempotency_key == mutate_history[1].idempotency_key
    assert mutate_history[0].command_id != mutate_history[1].command_id


def test_85_no_duplicate_external_effect():
    plan = Plan(
        plan_id="p",
        tasks=[_mutate("t1", "K", "SUCCESS"), _mutate("t2", "K", "SUCCESS")],
    )
    runtime_input, simulator = _input(
        plan,
        _goal("always_false", EvidenceLevel.L1_INFERRED),
    )

    output = KernelRuntime().run(runtime_input)

    assert simulator.committed_keys() == ["K"]
    assert output.effect_history[1].receipt_status == "DUPLICATE"


def test_86_state_immutability():
    for model in (
        State,
        KnowledgeState,
        ObservedWorldState,
        ExecutionContext,
        Artifact,
        ArtifactRef,
        Observation,
        KnowledgeEntry,
    ):
        assert model.model_config.get("frozen") is True, model


def test_87_evidence_invariant():
    assert (
        satisfies_required_evidence(
            EvidenceLevel.L1_INFERRED, EvidenceLevel.L3_OBSERVED
        )
        is False
    )
    assert (
        satisfies_required_evidence(
            EvidenceLevel.L2_SUPPORTED, EvidenceLevel.L3_OBSERVED
        )
        is False
    )
    assert (
        satisfies_required_evidence(
            EvidenceLevel.L3_OBSERVED, EvidenceLevel.L3_OBSERVED
        )
        is True
    )
    assert (
        satisfies_required_evidence(
            EvidenceLevel.L4_ATTESTED, EvidenceLevel.L3_OBSERVED
        )
        is True
    )

    forged_knowledge = KnowledgeState(
        entries={
            "k": KnowledgeEntry(
                id="k",
                kind=KnowledgeKind.FACT,
                statement="forged",
                evidence_level=EvidenceLevel.L4_ATTESTED,
            )
        }
    )
    forged_state = State(
        knowledge=forged_knowledge,
        observed=ObservedWorldState(),
        context=ExecutionContext(run_id="r"),
    )
    result = GoalEvaluator().evaluate(
        forged_state,
        _goal("always_true", EvidenceLevel.L4_ATTESTED),
    )
    assert result.evidence_result == "INVALID"


def test_88_receipt_is_not_observation():
    plan = Plan(plan_id="p", tasks=[_mutate("t1", "K", "SUCCESS")])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status == GoalStatus.NOT_SATISFIED
    assert output.final_state.observed.observations == {}
    assert output.final_state.observed.receipts != {}


def test_89_prediction_is_not_observation():
    plan = Plan(plan_id="p", tasks=[_reason()])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status == GoalStatus.NOT_SATISFIED
    assert output.final_state.observed.observations == {}


def test_90_deterministic_execution_trace():
    plan = Plan(plan_id="p", tasks=[_retrieve("t1"), _mutate("t2", "K", "SUCCESS")])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)

    def run():
        runtime_input, _ = _input(plan, goal)
        return KernelRuntime().run(runtime_input)

    first = run()
    second = run()

    assert first.model_dump() == second.model_dump()


def test_91_runtime_cannot_shortcut_goal_evaluator():
    plan = Plan(plan_id="p", tasks=[_reason()])
    goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    runtime_input, _ = _input(plan, goal)

    output = KernelRuntime().run(runtime_input)

    assert output.termination_reason != TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.goal_result.status == GoalStatus.NOT_SATISFIED


def test_92_architecture_failure_regression():
    wrong = Plan(plan_id="p", tasks=[_reason()])
    wrong_goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    wrong_input, _ = _input(wrong, wrong_goal)
    wrong_output = KernelRuntime().run(wrong_input)
    assert wrong_output.goal_result.status == GoalStatus.NOT_SATISFIED

    right = Plan(plan_id="p", tasks=[_reason("t1"), _observe("t2", "K")])
    right_goal = _goal("observation_exists", EvidenceLevel.L3_OBSERVED)
    right_input, _ = _input(right, right_goal)
    right_output = KernelRuntime().run(right_input)
    assert right_output.goal_result.status == GoalStatus.SATISFIED
