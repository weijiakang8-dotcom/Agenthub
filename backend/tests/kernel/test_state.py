from __future__ import annotations

from app.kernel.artifact.model import Artifact
from app.kernel.artifact.store import ArtifactStore
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeState,
    ObservedWorldState,
    State,
)
from app.kernel.state.projector import StateProjector


def _context() -> ExecutionContext:
    return ExecutionContext(run_id="run-1")


def test_state_projection_keeps_refs_and_materializes_from_store():
    store = ArtifactStore()
    artifact = Artifact.create(
        artifact_id="art-1",
        artifact_type="text/plain",
        content=b"report-body",
        evidence_level=EvidenceLevel.L2_SUPPORTED,
        producer="test",
    )
    ref = store.put(artifact)

    entry = KnowledgeEntry(
        id="k1",
        kind=KnowledgeKind.DERIVED_ARTIFACT,
        statement="derived report",
        evidence_level=EvidenceLevel.L2_SUPPORTED,
        artifact_refs=[ref],
    )
    knowledge = KnowledgeState(entries={"k1": entry})
    observed = ObservedWorldState()
    projector = StateProjector(store)

    state = projector.project(
        context=_context(),
        knowledge=knowledge,
        observed=observed,
    )

    assert state.knowledge.entries["k1"].artifact_refs == [ref]
    assert (
        state.knowledge.entries["k1"].artifact_refs[0].content_hash == ref.content_hash
    )
    assert projector.materialize(ref) is artifact


def test_prediction_in_knowledge_is_not_in_observed():
    prediction = KnowledgeEntry(
        id="p1",
        kind=KnowledgeKind.PREDICTION,
        statement="test_valid_login PASS",
        evidence_level=EvidenceLevel.L1_INFERRED,
    )
    state = State(
        knowledge=KnowledgeState(entries={"p1": prediction}),
        observed=ObservedWorldState(),
        context=_context(),
    )

    assert state.knowledge.entries["p1"].kind == KnowledgeKind.PREDICTION
    assert state.observed.observations == {}


def test_state_is_frozen_value_object():
    assert State.model_config.get("frozen") is True
    assert KnowledgeState.model_config.get("frozen") is True
    assert ObservedWorldState.model_config.get("frozen") is True


def test_state_json_roundtrip_is_deterministic():
    state = State(
        knowledge=KnowledgeState(
            entries={
                "f1": KnowledgeEntry(
                    id="f1",
                    kind=KnowledgeKind.FACT,
                    statement="observed fact",
                    evidence_level=EvidenceLevel.L3_OBSERVED,
                )
            }
        ),
        observed=ObservedWorldState(),
        context=_context(),
    )

    payload = state.model_dump_json()
    reloaded = State.model_validate_json(payload)

    assert reloaded == state
    assert reloaded.model_dump_json() == payload
