from __future__ import annotations

import pytest

from app.kernel.artifact.model import Artifact
from app.kernel.artifact.store import ArtifactStore
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import (
    CapabilityDefinition,
    CapabilityId,
    Classification,
    Predicate,
    SideEffectPolicy,
)
from app.kernel.capability.registry import CapabilityRegistry
from app.kernel.effects.command import Command
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.plan.errors import CycleDetectedError
from app.kernel.plan.model import Dependency, Plan
from app.kernel.plan.validator import topological_order, validate_plan
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeKind,
    KnowledgeState,
    State,
)
from app.kernel.task.model import Task
from app.kernel.transition.engine import TransitionEngine
from app.kernel.transition.model import PlanExecutionStatus, TransitionStatus


def _state() -> State:
    return State(context=ExecutionContext(run_id="run-1"))


def _command() -> Command:
    return Command(
        command_id="cmd-1",
        idempotency_key="idem-1",
        capability_id="mutate",
    )


def _put_artifact(store: ArtifactStore, artifact_id: str = "a1") -> Artifact:
    artifact = Artifact.create(
        artifact_id=artifact_id,
        artifact_type="text/plain",
        content=b"data",
        evidence_level=EvidenceLevel.L2_SUPPORTED,
        producer="test",
    )
    store.put(artifact)
    return artifact


def _retrieve_task(task_id: str = "t1", artifact_id: str = "a1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.RETRIEVE,
        input_artifacts=[artifact_id],
        input_arguments={"artifact_id": artifact_id},
    )


def _reason_task(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.REASON,
        input_arguments={"premises": ["test_valid_login PASS"]},
    )


def _mutate_task(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.MUTATE,
        input_arguments={"command": _command()},
    )


def _observe_task(task_id: str = "t1") -> Task:
    return Task(
        task_id=task_id,
        capability_id=CapabilityId.OBSERVE,
        input_arguments={"command": _command()},
    )


def test_23_task_is_capability_instance():
    task = _retrieve_task()

    assert task.capability_id == CapabilityId.RETRIEVE
    assert task.task_id == "t1"


def test_24_task_has_no_agent_semantics():
    forbidden = {"agent_id", "role", "prompt", "model", "workflow_id"}

    assert forbidden.isdisjoint(Task.model_fields)


def test_plan_contains_no_agent_semantics():
    forbidden = {"agent_id", "role", "prompt", "model", "workflow"}

    assert forbidden.isdisjoint(Plan.model_fields)
    assert forbidden.isdisjoint(Dependency.model_fields)


def test_25_unknown_capability_rejected():
    engine = TransitionEngine(CapabilityRegistry(), ArtifactStore())

    result = engine.apply_task(_state(), _retrieve_task())

    assert result.status == TransitionStatus.INVALID_CAPABILITY
    assert result.next_state is None


def test_26_task_precondition_failure():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())

    result = engine.apply_task(_state(), _retrieve_task(artifact_id="missing"))

    assert result.status == TransitionStatus.PRECONDITION_FAILED
    assert result.next_state is None


def test_27_task_postcondition_failure():
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            capability_id=CapabilityId.COMPUTE,
            classification=Classification.PURE,
            side_effect_policy=SideEffectPolicy.NONE,
        ),
        lambda state, args, store: KnowledgeState(),
    )
    engine = TransitionEngine(registry, ArtifactStore())
    task = Task(
        task_id="t1",
        capability_id=CapabilityId.COMPUTE,
        postconditions=[
            Predicate(name="artifact_created", params={"artifact_type": "computation"})
        ],
    )

    result = engine.apply_task(_state(), task)

    assert result.status == TransitionStatus.POSTCONDITION_FAILED


def test_28_transition_is_immutable():
    store = ArtifactStore()
    _put_artifact(store)
    engine = TransitionEngine(build_standard_registry(), store)
    state = _state()

    result = engine.apply_task(state, _retrieve_task())

    assert result.previous_state.context.trace == []
    assert result.next_state.context.trace == ["t1"]
    assert state.context.trace == []


def test_29_transition_is_deterministic():
    def run():
        store = ArtifactStore()
        _put_artifact(store)
        engine = TransitionEngine(build_standard_registry(), store)
        return engine.apply_task(_state(), _retrieve_task())

    first = run()
    second = run()

    assert first == second
    assert first.model_dump() == second.model_dump()


def test_30_plan_dependency_validation():
    registry = build_standard_registry()
    plan = Plan(
        plan_id="p1",
        tasks=[_retrieve_task("t1"), _reason_task("t2")],
        dependencies=[Dependency(task_id="t2", on_task_id="missing")],
    )

    report = validate_plan(plan, _state(), registry)

    assert report.valid is False
    assert any("unknown task" in issue for issue in report.issues)


def test_31_plan_cycle_rejected():
    registry = build_standard_registry()
    plan = Plan(
        plan_id="p1",
        tasks=[_reason_task("t1"), _reason_task("t2")],
        dependencies=[
            Dependency(task_id="t1", on_task_id="t2"),
            Dependency(task_id="t2", on_task_id="t1"),
        ],
    )

    report = validate_plan(plan, _state(), registry)

    assert report.valid is False
    assert any("cycle" in issue.lower() for issue in report.issues)
    with pytest.raises(CycleDetectedError):
        topological_order(plan)


def test_32_plan_execution_order():
    store = ArtifactStore()
    _put_artifact(store)
    engine = TransitionEngine(build_standard_registry(), store)
    plan = Plan(
        plan_id="p1",
        tasks=[_reason_task("t2"), _retrieve_task("t1")],
        dependencies=[Dependency(task_id="t2", on_task_id="t1")],
    )

    execution = engine.execute_plan(_state(), plan)

    assert execution.status == PlanExecutionStatus.COMPLETED
    assert [result.task_id for result in execution.results] == ["t1", "t2"]


def test_33_pure_task_does_not_change_observed_state():
    store = ArtifactStore()
    _put_artifact(store)
    engine = TransitionEngine(build_standard_registry(), store)
    state = _state()

    result = engine.apply_task(state, _retrieve_task())

    assert result.next_state.observed == state.observed
    assert result.observation is None
    assert result.receipt is None


def test_34_reason_cannot_create_observation():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())

    result = engine.apply_task(_state(), _reason_task())

    assert result.observation is None
    assert result.next_state.observed.observations == {}
    entry = next(iter(result.next_state.knowledge.entries.values()))
    assert entry.kind == KnowledgeKind.HYPOTHESIS
    assert entry.evidence_level == EvidenceLevel.L1_INFERRED


def test_35_mutate_does_not_directly_create_observation():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())

    result = engine.apply_task(_state(), _mutate_task())

    assert result.receipt is not None
    assert result.observation is None
    assert result.next_state.observed.observations == {}
    assert result.next_state.observed.receipts != {}


def test_36_observe_can_create_observation():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())

    result = engine.apply_task(_state(), _observe_task())

    assert result.observation is not None
    assert result.observation.evidence_level == EvidenceLevel.L3_OBSERVED
    assert result.next_state.observed.observations != {}


def test_37_invalid_plan_rejected_before_execution():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())
    plan = Plan(
        plan_id="p1",
        tasks=[_reason_task("t1"), _reason_task("t2")],
        dependencies=[
            Dependency(task_id="t1", on_task_id="t2"),
            Dependency(task_id="t2", on_task_id="t1"),
        ],
    )

    execution = engine.execute_plan(_state(), plan)

    assert execution.status == PlanExecutionStatus.REJECTED
    assert execution.results == []


def test_prediction_cannot_satisfy_observed_goal():
    engine = TransitionEngine(build_standard_registry(), ArtifactStore())

    result = engine.apply_task(_state(), _reason_task())

    assert result.status == TransitionStatus.APPLIED
    assert result.next_state.observed.observations == {}
    entry = next(iter(result.next_state.knowledge.entries.values()))
    assert entry.kind == KnowledgeKind.HYPOTHESIS
    assert entry.evidence_level == EvidenceLevel.L1_INFERRED
