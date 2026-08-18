from __future__ import annotations

from app.kernel.effects.command import Command
from app.kernel.effects.executor import EffectExecutor
from app.kernel.effects.receipt import ExecutionReceipt, ReceiptStatus
from app.kernel.effects.reconciliation import ReconciliationResult
from app.kernel.effects.retry import RetryPolicy
from app.kernel.effects.simulator import (
    DeterministicWorldSimulator,
    WorldOutcome,
)
from app.kernel.evidence.model import EvidenceLevel, satisfies_required_evidence
from app.kernel.state.model import (
    KnowledgeEntry,
    KnowledgeKind,
    Observation,
    ObservedWorldState,
)


def _command(command_id: str = "c1", key: str = "K") -> Command:
    return Command(
        command_id=command_id,
        idempotency_key=key,
        capability_id="mutate",
    )


def _executor(
    max_retries: int = 1,
) -> tuple[EffectExecutor, DeterministicWorldSimulator]:
    simulator = DeterministicWorldSimulator()
    executor = EffectExecutor(simulator, RetryPolicy(max_retries=max_retries))
    return executor, simulator


def test_38_success_returns_receipt_not_observation():
    executor, simulator = _executor()
    command = _command()

    receipt = executor.execute(command, WorldOutcome.SUCCESS)

    assert receipt.status == ReceiptStatus.SUCCESS
    assert receipt.external_reference == "ext:c1"
    assert not isinstance(receipt, Observation)
    assert simulator.committed_keys() == ["K"]


def test_39_timeout_but_committed_keeps_unknown_before_observe():
    executor, simulator = _executor()
    command = _command()

    receipt = executor.execute(command, WorldOutcome.TIMEOUT_BUT_COMMITTED)

    assert receipt.status == ReceiptStatus.TIMEOUT
    assert simulator.committed_keys() == ["K"]

    observation = executor.observe(command)
    result = executor.reconcile(receipt, observation)

    assert observation.external_state["committed"] is True
    assert result == ReconciliationResult.CONFIRMED_COMMITTED


def test_40_timeout_then_observe_confirmed_prevents_retry():
    executor, _ = _executor(max_retries=1)
    command = _command()

    receipt = executor.execute(command, WorldOutcome.TIMEOUT_BUT_COMMITTED)
    observation = executor.observe(command)
    result = executor.reconcile(receipt, observation)

    assert result == ReconciliationResult.CONFIRMED_COMMITTED
    assert executor.retry_eligible(result, attempt_count=0) is False


def test_41_timeout_not_committed_allows_retry():
    executor, _ = _executor(max_retries=1)
    command = _command()

    receipt = executor.execute(command, WorldOutcome.TIMEOUT_NOT_COMMITTED)
    observation = executor.observe(command)
    result = executor.reconcile(receipt, observation)

    assert result == ReconciliationResult.CONFIRMED_NOT_COMMITTED
    assert executor.retry_eligible(result, attempt_count=0) is True


def test_42_retry_preserves_idempotency_key():
    executor, _ = _executor()
    original = _command(command_id="c1", key="K")

    retry = executor.build_retry_command(original, attempt=1)

    assert retry.command_id != original.command_id
    assert retry.idempotency_key == original.idempotency_key
    assert retry.capability_id == original.capability_id


def test_43_duplicate_request_is_not_a_new_effect():
    executor, simulator = _executor()
    original = _command(command_id="c1", key="K")
    executor.execute(original, WorldOutcome.SUCCESS)

    retry = executor.build_retry_command(original, attempt=1)
    duplicate = executor.execute(retry, WorldOutcome.SUCCESS)

    assert duplicate.status == ReceiptStatus.DUPLICATE
    assert simulator.committed_keys() == ["K"]


def test_44_retry_produces_deduplication_proof_with_observation():
    executor, _ = _executor()
    original = _command(command_id="c1", key="K")
    executor.execute(original, WorldOutcome.SUCCESS)

    retry = executor.build_retry_command(original, attempt=1)
    duplicate = executor.execute(retry, WorldOutcome.SUCCESS)
    observation = executor.observe(retry)
    result = executor.reconcile(duplicate, observation)
    proof = executor.build_dedup_proof(original, retry, observation, result)

    assert result == ReconciliationResult.DUPLICATE_CONFIRMED
    assert proof.idempotency_key == "K"
    assert proof.original_command_id == "c1"
    assert proof.retry_command_id == retry.command_id
    assert proof.deduplication_result == "DUPLICATE_CONFIRMED"
    assert proof.evidence["external_state"]["committed"] is True


def test_45_receipt_is_not_observation():
    executor, _ = _executor()
    command = _command()

    receipt = executor.execute(command, WorldOutcome.SUCCESS)
    observation = executor.observe(command)

    assert isinstance(receipt, ExecutionReceipt)
    assert not isinstance(receipt, Observation)
    assert isinstance(observation, Observation)

    observed = ObservedWorldState(receipts={receipt.receipt_id: receipt})
    assert observed.observations == {}
    assert observed.receipts[receipt.receipt_id] == receipt


def test_46_prediction_cannot_become_observation():
    executor, _ = _executor()
    command = _command()

    prediction = KnowledgeEntry(
        id="pred-1",
        kind=KnowledgeKind.PREDICTION,
        statement="delivered",
        evidence_level=EvidenceLevel.L1_INFERRED,
    )

    assert prediction.evidence_level == EvidenceLevel.L1_INFERRED
    assert (
        satisfies_required_evidence(
            prediction.evidence_level,
            EvidenceLevel.L3_OBSERVED,
        )
        is False
    )

    observation = executor.observe(command)
    observed = ObservedWorldState(
        observations={observation.observation_id: observation}
    )

    assert observed.observations[observation.observation_id].evidence_level == (
        EvidenceLevel.L3_OBSERVED
    )


def test_47_timeout_cannot_directly_trigger_retry():
    executor, _ = _executor(max_retries=1)
    command = _command(command_id="c1", key="K")

    receipt = executor.execute(command, WorldOutcome.TIMEOUT_BUT_COMMITTED)
    retry = executor.build_retry_command(command, attempt=1)
    duplicate = executor.execute(retry, WorldOutcome.SUCCESS)

    assert receipt.status == ReceiptStatus.TIMEOUT
    assert duplicate.status == ReceiptStatus.DUPLICATE

    observation = executor.observe(command)
    result = executor.reconcile(receipt, observation)
    assert result == ReconciliationResult.CONFIRMED_COMMITTED
    assert executor.retry_eligible(result, attempt_count=0) is False


def test_48_timeout_but_committed_prevents_duplicate_effect():
    executor, simulator = _executor()
    command = _command(command_id="c1", key="K")

    receipt = executor.execute(command, WorldOutcome.TIMEOUT_BUT_COMMITTED)
    retry = executor.build_retry_command(command, attempt=1)
    duplicate = executor.execute(retry, WorldOutcome.SUCCESS)
    observation = executor.observe(command)
    result = executor.reconcile(duplicate, observation)
    proof = executor.build_dedup_proof(command, retry, observation, result)

    assert receipt.status == ReceiptStatus.TIMEOUT
    assert duplicate.status == ReceiptStatus.DUPLICATE
    assert simulator.committed_keys() == ["K"]
    assert result == ReconciliationResult.DUPLICATE_CONFIRMED
    assert proof.evidence["external_state"]["committed"] is True
