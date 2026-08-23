from __future__ import annotations

from pathlib import Path

import pytest

import app.kernel
from app.kernel.artifact.store import ArtifactStore
from app.kernel.capability.boundary import CapabilityBoundary
from app.kernel.capability.classification import Classification, classify
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.errors import (
    DuplicateCapabilityError,
    InvalidClassificationError,
    UnknownCapabilityError,
)
from app.kernel.capability.model import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityOutcome,
    Predicate,
    SideEffectPolicy,
)
from app.kernel.capability.registry import CapabilityRegistry
from app.kernel.effects.command import Command
from app.kernel.evidence.model import (
    EvidenceEventType,
    EvidenceLevel,
    promote_evidence,
    satisfies_required_evidence,
)
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeKind,
    KnowledgeState,
    State,
)


def _state() -> State:
    return State(context=ExecutionContext(run_id="run-1"))


def _command() -> Command:
    return Command(
        command_id="cmd-1",
        idempotency_key="idem-1",
        capability_id="mutate",
    )


def test_09_capability_registry_unique_ids():
    registry = build_standard_registry()

    assert len(registry.ids()) == 8
    assert len(set(registry.ids())) == 8

    duplicate = CapabilityDefinition(
        capability_id=CapabilityId.RETRIEVE,
        classification=Classification.PURE,
        side_effect_policy=SideEffectPolicy.NONE,
    )
    with pytest.raises(DuplicateCapabilityError):
        registry.register(duplicate, lambda *a, **k: KnowledgeState())


def test_10_unknown_capability_rejected():
    registry = CapabilityRegistry()

    assert registry.get(CapabilityId.RETRIEVE) is None
    with pytest.raises(UnknownCapabilityError):
        registry.resolve(CapabilityId.RETRIEVE)


def test_11_capability_classification():
    assert classify(CapabilityId.RETRIEVE) == Classification.PURE
    assert classify(CapabilityId.EXTRACT) == Classification.PURE
    assert classify(CapabilityId.COMPUTE) == Classification.PURE
    assert classify(CapabilityId.VALIDATE) == Classification.PURE
    assert classify(CapabilityId.REASON) == Classification.PURE
    assert classify(CapabilityId.SYNTHESIZE) == Classification.PURE
    assert classify(CapabilityId.OBSERVE) == Classification.EFFECTFUL
    assert classify(CapabilityId.MUTATE) == Classification.EFFECTFUL

    registry = CapabilityRegistry()
    wrong = CapabilityDefinition(
        capability_id=CapabilityId.REASON,
        classification=Classification.EFFECTFUL,
        side_effect_policy=SideEffectPolicy.NONE,
    )
    with pytest.raises(InvalidClassificationError):
        registry.register(wrong, lambda *a, **k: KnowledgeState())


def test_12_pure_capability_no_command():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.REASON,
        state=_state(),
        args={"premises": ["a"]},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.APPLIED
    assert result.command is None


def test_13_pure_capability_cannot_update_observed_state():
    boundary = CapabilityBoundary(build_standard_registry())
    state = _state()

    result = boundary.apply(
        CapabilityId.REASON,
        state=state,
        args={"premises": ["a"]},
        artifact_store=ArtifactStore(),
    )

    assert result.observation is None
    assert result.receipt is None
    assert result.knowledge is not None


def test_14_reason_creates_hypothesis_not_observation():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.REASON,
        state=_state(),
        args={"premises": ["a", "b"]},
        artifact_store=ArtifactStore(),
    )

    assert result.observation is None
    entry = next(iter(result.knowledge.entries.values()))
    assert entry.kind == KnowledgeKind.HYPOTHESIS
    assert entry.evidence_level == EvidenceLevel.L1_INFERRED


def test_15_effectful_requires_command():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.MUTATE,
        state=_state(),
        args={},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.PRECONDITION_FAILED


def test_16_mutate_returns_receipt_not_observation():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.MUTATE,
        state=_state(),
        args={"command": _command()},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.APPLIED
    assert result.receipt is not None
    assert result.observation is None
    assert result.receipt.command_id == "cmd-1"


def test_17_observe_creates_observation():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.OBSERVE,
        state=_state(),
        args={"command": _command()},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.APPLIED
    assert result.observation is not None
    assert result.observation.evidence_level == EvidenceLevel.L3_OBSERVED


def test_18_observation_can_promote_evidence_to_l3():
    boundary = CapabilityBoundary(build_standard_registry())
    result = boundary.apply(
        CapabilityId.OBSERVE,
        state=_state(),
        args={"command": _command()},
        artifact_store=ArtifactStore(),
    )

    assert result.observation.evidence_level == EvidenceLevel.L3_OBSERVED
    assert (
        promote_evidence(
            EvidenceLevel.L2_SUPPORTED,
            EvidenceEventType.OBSERVATION_RECORDED,
        )
        == EvidenceLevel.L3_OBSERVED
    )


def test_19_precondition_failure_blocks_transition():
    boundary = CapabilityBoundary(build_standard_registry())

    result = boundary.apply(
        CapabilityId.RETRIEVE,
        state=_state(),
        args={"artifact_id": "missing"},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.PRECONDITION_FAILED
    assert result.knowledge is None


def test_20_postcondition_failure_rejects_transition():
    registry = CapabilityRegistry()
    definition = CapabilityDefinition(
        capability_id=CapabilityId.COMPUTE,
        classification=Classification.PURE,
        postconditions=[
            Predicate(name="artifact_created", params={"artifact_type": "computation"})
        ],
        side_effect_policy=SideEffectPolicy.NONE,
    )

    def bad_compute(state, args, store):
        return KnowledgeState()

    registry.register(definition, bad_compute)
    boundary = CapabilityBoundary(registry)

    result = boundary.apply(
        CapabilityId.COMPUTE,
        state=_state(),
        args={},
        artifact_store=ArtifactStore(),
    )

    assert result.outcome == CapabilityOutcome.POSTCONDITION_FAILED


def test_21_registry_is_deterministic():
    first = build_standard_registry()
    second = build_standard_registry()

    assert first.ids() == second.ids()
    assert first.ids() == sorted(first.ids())
    assert first.resolve(CapabilityId.REASON)[0] is first.get(CapabilityId.REASON)


def test_22_no_kernel_external_dependencies():
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


def test_08_capability_boundary_regression():
    boundary = CapabilityBoundary(build_standard_registry())

    reason_result = boundary.apply(
        CapabilityId.REASON,
        state=_state(),
        args={"premises": ["test_valid_login PASS"]},
        artifact_store=ArtifactStore(),
    )
    reason_entry = next(iter(reason_result.knowledge.entries.values()))

    assert reason_entry.evidence_level == EvidenceLevel.L1_INFERRED
    assert reason_result.observation is None
    assert (
        satisfies_required_evidence(
            reason_entry.evidence_level,
            EvidenceLevel.L3_OBSERVED,
        )
        is False
    )

    observe_result = boundary.apply(
        CapabilityId.OBSERVE,
        state=_state(),
        args={"command": _command()},
        artifact_store=ArtifactStore(),
    )

    assert observe_result.observation.evidence_level == EvidenceLevel.L3_OBSERVED
    assert (
        satisfies_required_evidence(
            observe_result.observation.evidence_level,
            EvidenceLevel.L3_OBSERVED,
        )
        is True
    )
