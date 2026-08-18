from __future__ import annotations

from app.kernel.effects.receipt import ExecutionReceipt, ReceiptStatus
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.goal.evaluator import GoalEvaluator
from app.kernel.goal.model import Constraint, Goal, GoalPredicate
from app.kernel.goal.result import GoalStatus
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeEntry,
    KnowledgeKind,
    KnowledgeState,
    Observation,
    ObservedWorldState,
    State,
)


def _state(
    *,
    knowledge: KnowledgeState | None = None,
    observed: ObservedWorldState | None = None,
) -> State:
    return State(
        knowledge=knowledge or KnowledgeState(),
        observed=observed or ObservedWorldState(),
        context=ExecutionContext(run_id="run-1"),
    )


def _goal(
    predicate_name: str = "always_true",
    required: EvidenceLevel = EvidenceLevel.L3_OBSERVED,
    *,
    constraints: list[Constraint] | None = None,
    params: dict | None = None,
) -> Goal:
    return Goal(
        goal_id="g1",
        predicate=GoalPredicate(name=predicate_name, params=params or {}),
        required_evidence=required,
        constraints=constraints or [],
    )


def _observation(committed: bool = True) -> Observation:
    return Observation(
        observation_id="obs-1",
        source="deterministic-simulator",
        observed_at="",
        external_state={"committed": committed},
        evidence_level=EvidenceLevel.L3_OBSERVED,
    )


def test_49_basic_predicate_true_satisfied():
    goal = _goal(required=EvidenceLevel.L1_INFERRED)

    result = GoalEvaluator().evaluate(_state(), goal)

    assert result.status == GoalStatus.SATISFIED


def test_50_predicate_false_not_satisfied():
    goal = _goal(predicate_name="always_false", required=EvidenceLevel.L1_INFERRED)

    result = GoalEvaluator().evaluate(_state(), goal)

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.predicate_result is False


def test_51_l1_does_not_satisfy_l3():
    knowledge = KnowledgeState(
        entries={
            "k1": KnowledgeEntry(
                id="k1",
                kind=KnowledgeKind.HYPOTHESIS,
                statement="delivered",
                evidence_level=EvidenceLevel.L1_INFERRED,
            )
        }
    )

    result = GoalEvaluator().evaluate(_state(knowledge=knowledge), _goal())

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.evidence_result == "INSUFFICIENT"
    assert result.reasons["actual"] == "L1_INFERRED"


def test_52_l2_does_not_satisfy_l3():
    knowledge = KnowledgeState(
        entries={
            "k1": KnowledgeEntry(
                id="k1",
                kind=KnowledgeKind.FACT,
                statement="delivered",
                evidence_level=EvidenceLevel.L2_SUPPORTED,
            )
        }
    )

    result = GoalEvaluator().evaluate(_state(knowledge=knowledge), _goal())

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.reasons["actual"] == "L2_SUPPORTED"


def test_53_l3_satisfies_l3():
    observed = ObservedWorldState(observations={"obs-1": _observation()})

    result = GoalEvaluator().evaluate(_state(observed=observed), _goal())

    assert result.status == GoalStatus.SATISFIED
    assert result.evidence_result == "SUFFICIENT"


def test_54_l4_satisfies_l3():
    observation = Observation(
        observation_id="obs-1",
        source="attested",
        observed_at="",
        external_state={"committed": True},
        evidence_level=EvidenceLevel.L4_ATTESTED,
    )
    observed = ObservedWorldState(observations={"obs-1": observation})

    result = GoalEvaluator().evaluate(_state(observed=observed), _goal())

    assert result.status == GoalStatus.SATISFIED


def test_55_prediction_is_not_observation():
    knowledge = KnowledgeState(
        entries={
            "p1": KnowledgeEntry(
                id="p1",
                kind=KnowledgeKind.PREDICTION,
                statement="email delivered",
                evidence_level=EvidenceLevel.L1_INFERRED,
            )
        }
    )
    goal = _goal(
        predicate_name="knowledge_entry_exists",
        params={"kind": "PREDICTION"},
    )

    result = GoalEvaluator().evaluate(_state(knowledge=knowledge), goal)

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.predicate_result is True
    assert result.evidence_result == "INSUFFICIENT"
    assert result.reasons["actual"] == "L1_INFERRED"


def test_56_receipt_success_is_not_observation():
    receipt = ExecutionReceipt(
        receipt_id="r1",
        command_id="c1",
        idempotency_key="K",
        status=ReceiptStatus.SUCCESS,
    )
    observed = ObservedWorldState(receipts={"r1": receipt})

    result = GoalEvaluator().evaluate(_state(observed=observed), _goal())

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.evidence_result == "INSUFFICIENT"
    assert result.reasons["actual"] == "L1_INFERRED"


def test_57_observe_committed_satisfies_goal():
    observed = ObservedWorldState(observations={"obs-1": _observation(True)})
    goal = _goal(
        predicate_name="observation_committed_equals",
        params={"value": True},
    )

    result = GoalEvaluator().evaluate(_state(observed=observed), goal)

    assert result.status == GoalStatus.SATISFIED
    assert result.predicate_result is True
    assert result.evidence_result == "SUFFICIENT"


def test_58_constraint_failure_not_satisfied():
    observed = ObservedWorldState(observations={"obs-1": _observation()})
    goal = _goal(constraints=[Constraint(name="always_false")])

    result = GoalEvaluator().evaluate(_state(observed=observed), goal)

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.constraint_result is False


def test_59_all_conditions_satisfied():
    observed = ObservedWorldState(observations={"obs-1": _observation(True)})
    goal = _goal(
        predicate_name="observation_committed_equals",
        params={"value": True},
        constraints=[Constraint(name="always_true")],
    )

    result = GoalEvaluator().evaluate(_state(observed=observed), goal)

    assert result.status == GoalStatus.SATISFIED


def test_60_illegal_l4_knowledge_rejected():
    knowledge = KnowledgeState(
        entries={
            "k1": KnowledgeEntry(
                id="k1",
                kind=KnowledgeKind.FACT,
                statement="forged attested fact",
                evidence_level=EvidenceLevel.L4_ATTESTED,
            )
        }
    )
    goal = _goal(required=EvidenceLevel.L4_ATTESTED)

    result = GoalEvaluator().evaluate(_state(knowledge=knowledge), goal)

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.evidence_result == "INVALID"


def test_61_goal_evaluation_is_deterministic():
    observed = ObservedWorldState(observations={"obs-1": _observation(True)})
    goal = _goal(
        predicate_name="observation_committed_equals",
        params={"value": True},
    )
    state = _state(observed=observed)

    first = GoalEvaluator().evaluate(state, goal)
    second = GoalEvaluator().evaluate(state, goal)
    third = GoalEvaluator().evaluate(state, goal)

    assert first == second == third
    assert first.model_dump() == second.model_dump() == third.model_dump()


def test_62_structured_reasons_identify_failure():
    goal = _goal(predicate_name="always_false")

    result = GoalEvaluator().evaluate(_state(), goal)

    assert result.status == GoalStatus.NOT_SATISFIED
    assert result.reasons["predicate"] == "FALSE"
    assert result.reasons["evidence"] == "INSUFFICIENT"
    assert result.reasons["constraints"] == "SATISFIED"
    assert result.reasons["required"] == "L3_OBSERVED"
    assert result.reasons["actual"] == "L1_INFERRED"
