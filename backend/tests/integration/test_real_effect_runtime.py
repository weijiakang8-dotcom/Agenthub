from __future__ import annotations

import os
import uuid
from pathlib import Path

import app.kernel
import httpx
import pytest
from app.adapters.real_effect_executor import RealEffectExecutor
from app.kernel.artifact.store import ArtifactStore
from app.kernel.capability.contracts import build_standard_registry
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.command import Command
from app.kernel.evidence.model import EvidenceLevel
from app.kernel.goal.model import Goal, GoalPredicate
from app.kernel.plan.model import Dependency, Plan
from app.kernel.runtime.loop import KernelRuntime
from app.kernel.runtime.model import RuntimeInput, TerminationReason
from app.kernel.state.model import (
    ExecutionContext,
    KnowledgeState,
    ObservedWorldState,
    State,
)
from app.kernel.task.model import Task

EXT_BASE = os.getenv("EXTERNAL_SERVICE_URL", "http://127.0.0.1:8081")
MAILHOG_API = os.getenv("MAILHOG_API", "http://127.0.0.1:8025")


def _services_up() -> bool:
    try:
        httpx.get(f"{EXT_BASE}/api/external/data", params={"query": "ping"}, timeout=2)
        httpx.get(f"{MAILHOG_API}/api/v2/messages", timeout=2)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _services_up(),
    reason="external-test-service or MailHog not running",
)


def _observe_goal() -> Goal:
    return Goal(
        goal_id="g",
        predicate=GoalPredicate(name="observation_exists"),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )


def _committed_goal() -> Goal:
    return Goal(
        goal_id="g-committed",
        predicate=GoalPredicate(
            name="observation_committed_equals",
            params={"value": True},
        ),
        required_evidence=EvidenceLevel.L3_OBSERVED,
    )


def _always_false_goal() -> Goal:
    return Goal(
        goal_id="g-false",
        predicate=GoalPredicate(name="always_false"),
        required_evidence=EvidenceLevel.L1_INFERRED,
    )


def _empty_state() -> State:
    return State(
        knowledge=KnowledgeState(),
        observed=ObservedWorldState(),
        context=ExecutionContext(run_id="r"),
    )


def _runtime_input(plan: Plan, goal: Goal, executor) -> RuntimeInput:
    return RuntimeInput(
        initial_state=_empty_state(),
        plan=plan,
        goal=goal,
        capability_registry=build_standard_registry(),
        artifact_store=ArtifactStore(),
        effect_port=executor,
    )


def _effect_entries(output):
    return [
        entry
        for entry in output.effect_history
        if entry.receipt_status in {"SUCCESS", "TIMEOUT", "DUPLICATE", "UNKNOWN"}
    ]


def _mailhog_messages() -> list[dict]:
    return (
        httpx.get(f"{MAILHOG_API}/api/v2/messages", timeout=5).json().get("items", [])
    )


def _mailhog_message(message_id: str) -> dict | None:
    for item in _mailhog_messages():
        headers = item.get("Content", {}).get("Headers", {})
        if message_id in (headers.get("Message-ID") or []):
            return item
    return None


def test_real_smtp_mutate_through_kernel_runtime():
    executor = RealEffectExecutor()
    recipient = "receiver@example.com"
    subject = f"AgentHub-Phase46-{uuid.uuid4().hex[:8]}"
    body = "real smtp e2e body"
    message_id = f"<phase46-smtp-{uuid.uuid4().hex}@mailhog.local>"
    key = f"smtp-{uuid.uuid4().hex[:8]}"

    mutate = Task(
        task_id="t-smtp-mutate",
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": key,
            "payload": {
                "transport": "smtp",
                "to": recipient,
                "subject": subject,
                "body": body,
                "message_id": message_id,
            },
        },
    )
    observe = Task(
        task_id="t-smtp-observe",
        capability_id=CapabilityId.OBSERVE,
        input_arguments={
            "idempotency_key": f"{key}-observe",
            "payload": {
                "url": f"{EXT_BASE}/api/external/mailhog/verify",
                "params": {"message_id": message_id},
            },
        },
    )
    plan = Plan(
        plan_id="p-smtp",
        tasks=[mutate, observe],
        dependencies=[Dependency(task_id=observe.task_id, on_task_id=mutate.task_id)],
    )
    output = KernelRuntime().run(_runtime_input(plan, _committed_goal(), executor))

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.goal_result.status.value == "SATISFIED"
    observations = list(output.final_state.observed.observations.values())
    assert observations != []
    assert observations[-1].external_state.get("committed") is True
    assert any(
        entry.reconciliation == "CONFIRMED_COMMITTED"
        for entry in _effect_entries(output)
    )

    mailhog_item = _mailhog_message(message_id)
    assert mailhog_item is not None
    headers = mailhog_item["Content"]["Headers"]
    assert headers["To"][0] == recipient
    assert headers["Subject"][0] == subject
    assert mailhog_item["Content"]["Body"] == body


def test_real_timeout_but_committed_through_kernel_runtime():
    executor = RealEffectExecutor()
    operation_id = str(uuid.uuid4())
    key = f"http-tc-{uuid.uuid4().hex[:8]}"

    mutate = Task(
        task_id="t-http-timeout-committed",
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": key,
            "payload": {
                "transport": "http",
                "url": f"{EXT_BASE}/api/external/effect",
                "operation_id": operation_id,
                "mode": "timeout_committed",
                "delay_ms": 2500,
                "timeout_ms": 300,
            },
        },
    )
    observe = Task(
        task_id="t-http-observe-committed",
        capability_id=CapabilityId.OBSERVE,
        input_arguments={
            "idempotency_key": f"{key}-observe",
            "payload": {"url": f"{EXT_BASE}/api/external/effect/{operation_id}"},
        },
    )
    plan = Plan(
        plan_id="p-timeout-committed",
        tasks=[mutate, observe],
        dependencies=[Dependency(task_id=observe.task_id, on_task_id=mutate.task_id)],
    )
    output = KernelRuntime().run(_runtime_input(plan, _committed_goal(), executor))

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    assert output.goal_result.status.value == "SATISFIED"
    timeout_entries = [
        entry for entry in _effect_entries(output) if entry.receipt_status == "TIMEOUT"
    ]
    assert len(timeout_entries) == 1
    assert timeout_entries[0].reconciliation == "CONFIRMED_COMMITTED"

    operation = httpx.get(
        f"{EXT_BASE}/api/external/effect/{operation_id}", timeout=5
    ).json()
    assert operation["committed"] is True
    assert operation["execution_count"] == 1


def test_real_timeout_not_committed_through_kernel_runtime():
    executor = RealEffectExecutor()
    operation_id = str(uuid.uuid4())
    key = f"http-tnc-{uuid.uuid4().hex[:8]}"
    task_id = "t-http-timeout-not-committed"

    mutate = Task(
        task_id=task_id,
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": key,
            "payload": {
                "transport": "http",
                "url": f"{EXT_BASE}/api/external/effect",
                "operation_id": operation_id,
                "mode": "timeout_not_committed",
                "delay_ms": 2500,
                "timeout_ms": 300,
            },
        },
    )
    observe = Task(
        task_id="t-http-observe-not-committed",
        capability_id=CapabilityId.OBSERVE,
        input_arguments={
            "idempotency_key": f"{key}-observe",
            "payload": {"url": f"{EXT_BASE}/api/external/effect/{operation_id}"},
        },
    )
    plan = Plan(
        plan_id="p-timeout-not-committed",
        tasks=[mutate, observe],
        dependencies=[Dependency(task_id=observe.task_id, on_task_id=mutate.task_id)],
    )
    output = KernelRuntime().run(_runtime_input(plan, _committed_goal(), executor))

    assert output.termination_reason == TerminationReason.TERMINATED_GOAL_SATISFIED
    mutate_entries = [
        entry
        for entry in output.effect_history
        if entry.command_id.startswith(task_id) or entry.command_id.startswith(key)
    ]
    assert len(mutate_entries) == 2
    assert mutate_entries[0].receipt_status == "TIMEOUT"
    assert mutate_entries[0].reconciliation == "CONFIRMED_NOT_COMMITTED"
    assert mutate_entries[1].receipt_status == "SUCCESS"
    assert mutate_entries[1].reconciliation == "CONFIRMED_COMMITTED"
    assert mutate_entries[0].idempotency_key == mutate_entries[1].idempotency_key
    assert mutate_entries[0].command_id != mutate_entries[1].command_id

    operation = httpx.get(
        f"{EXT_BASE}/api/external/effect/{operation_id}", timeout=5
    ).json()
    assert operation["committed"] is True
    assert operation["execution_count"] == 1


def test_real_duplicate_request_through_kernel_runtime():
    executor = RealEffectExecutor()
    key = f"http-dup-{uuid.uuid4().hex[:8]}"
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    first = Task(
        task_id="t-dup-1",
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": key,
            "payload": {
                "transport": "http",
                "url": f"{EXT_BASE}/api/external/effect",
                "operation_id": first_id,
                "mode": "success",
            },
        },
    )
    second = Task(
        task_id="t-dup-2",
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": key,
            "payload": {
                "transport": "http",
                "url": f"{EXT_BASE}/api/external/effect",
                "operation_id": second_id,
                "mode": "success",
            },
        },
    )
    plan = Plan(plan_id="p-duplicate", tasks=[first, second])
    output = KernelRuntime().run(_runtime_input(plan, _always_false_goal(), executor))

    duplicate_entries = [
        entry for entry in output.effect_history if entry.receipt_status == "DUPLICATE"
    ]
    assert len(duplicate_entries) == 1
    assert duplicate_entries[0].reconciliation == "DUPLICATE_CONFIRMED"
    assert duplicate_entries[0].idempotency_key == key

    first_operation = httpx.get(
        f"{EXT_BASE}/api/external/effect/{first_id}", timeout=5
    ).json()
    assert first_operation["execution_count"] == 1
    second_response = httpx.get(
        f"{EXT_BASE}/api/external/effect/{second_id}", timeout=5
    )
    assert second_response.status_code == 404


def test_real_unknown_result_through_kernel_runtime():
    executor = RealEffectExecutor()
    operation_id = str(uuid.uuid4())

    mutate = Task(
        task_id="t-http-unknown",
        capability_id=CapabilityId.MUTATE,
        input_arguments={
            "idempotency_key": f"http-unknown-{uuid.uuid4().hex[:8]}",
            "payload": {
                "transport": "http",
                "url": f"{EXT_BASE}/api/external/effect",
                "operation_id": operation_id,
                "mode": "unknown",
            },
        },
    )
    plan = Plan(plan_id="p-unknown", tasks=[mutate])
    output = KernelRuntime().run(_runtime_input(plan, _observe_goal(), executor))

    assert output.termination_reason == TerminationReason.TERMINATED_UNKNOWN_EFFECT
    assert output.goal_result.status.value == "NOT_SATISFIED"
    assert output.final_state.observed.observations == {}
    entries = _effect_entries(output)
    assert len(entries) == 1
    assert entries[0].reconciliation == "STILL_UNKNOWN"

    operation = httpx.get(
        f"{EXT_BASE}/api/external/effect/{operation_id}", timeout=5
    ).json()
    assert operation["committed"] is None
    assert operation["execution_count"] == 0


def test_real_effect_failure_isolation():
    executor = RealEffectExecutor()
    command = Command(
        command_id="c7",
        idempotency_key="k7",
        capability_id="observe",
        payload={"url": "http://127.0.0.1:1/nope"},
    )
    import asyncio

    result = asyncio.run(executor.execute(command))

    assert result.status in {"error", "timeout"}


def test_kernel_import_regression():
    import app.kernel.effects
    import app.kernel.state.model

    assert app.kernel is not None


def test_kernel_forbidden_dependency():
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
                    "fastapi",
                    "langgraph",
                    "langchain",
                    "celery",
                    "redis",
                    "sqlalchemy",
                    "asyncpg",
                    "httpx",
                    "openai",
                    "smtplib",
                    "app.adapters",
                    "app.engine",
                    "app.api",
                    "app.models",
                    "app.core",
                )
            ):
                offenders.append(f"{path}: {stripped}")
    assert offenders == []


def test_real_http_observe_through_kernel_runtime():

    executor = RealEffectExecutor()
    task = Task(
        task_id="t-observe",
        capability_id=CapabilityId.OBSERVE,
        input_arguments={
            "idempotency_key": f"kr-{uuid.uuid4().hex[:8]}",
            "payload": {
                "url": f"{EXT_BASE}/api/external/data",
                "params": {"query": "kernel-runtime"},
            },
        },
    )
    plan = Plan(plan_id="p", tasks=[task])
    goal = _observe_goal()
    runtime_input = RuntimeInput(
        initial_state=State(
            knowledge=KnowledgeState(),
            observed=ObservedWorldState(),
            context=ExecutionContext(run_id="r"),
        ),
        plan=plan,
        goal=goal,
        capability_registry=build_standard_registry(),
        artifact_store=__import__(
            "app.kernel.artifact.store", fromlist=["ArtifactStore"]
        ).ArtifactStore(),
        effect_port=executor,
    )

    output = KernelRuntime().run(runtime_input)

    assert output.goal_result.status.value == "SATISFIED"
    assert output.final_state.observed.observations != {}


def test_real_http_unavailable_does_not_satisfy_observation_exists():
    executor = RealEffectExecutor()
    task = Task(
        task_id="t-http-unavailable-observe",
        capability_id=CapabilityId.OBSERVE,
        input_arguments={
            "idempotency_key": f"http-down-{uuid.uuid4().hex[:8]}",
            "payload": {"url": "http://127.0.0.1:1/nope"},
        },
    )
    plan = Plan(plan_id="p-http-down", tasks=[task])
    output = KernelRuntime().run(_runtime_input(plan, _observe_goal(), executor))

    assert output.termination_reason == TerminationReason.TERMINATED_RETRY_EXHAUSTED
    assert output.goal_result.status.value == "NOT_SATISFIED"
    assert output.final_state.observed.observations == {}
