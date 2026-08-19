from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.adapters.composition import build_effect_port
from app.adapters.errors import UnsupportedKernelWorkflowError
from app.adapters.kernel_execution_adapter import (
    build_runtime_input,
    is_kernel_workflow,
)
from app.kernel.capability.model import CapabilityId
from app.kernel.effects.simulator_port import SimulatorEffectPort


def _execution(execution_id: uuid.UUID | None = None):
    return SimpleNamespace(id=execution_id or uuid.uuid4())


def _workflow(dag: dict | None):
    return SimpleNamespace(dag_definition=dag)


def test_is_kernel_workflow_detects_explicit_plan():
    workflow = _workflow(
        {
            "kernel_plan": {
                "goal": {"predicate": "observation_exists"},
                "tasks": [
                    {
                        "task_id": "t1",
                        "capability_id": "observe",
                        "payload": {"url": "http://127.0.0.1:8081/api/external/data"},
                    }
                ],
            }
        }
    )

    assert is_kernel_workflow(workflow) is True


def test_is_kernel_workflow_rejects_legacy_workflow():
    assert is_kernel_workflow(_workflow({"nodes": []})) is False
    assert is_kernel_workflow(_workflow(None)) is False


def test_build_runtime_input_maps_observe_task():
    execution = _execution()
    workflow = _workflow(
        {
            "kernel_plan": {
                "goal": {
                    "predicate": "observation_exists",
                    "required_evidence": "L3_OBSERVED",
                },
                "tasks": [
                    {
                        "task_id": "t-observe",
                        "capability_id": "observe",
                        "idempotency_key": "observe-key",
                        "payload": {
                            "url": "http://127.0.0.1:8081/api/external/data",
                            "params": {"query": "ping"},
                        },
                    }
                ],
            }
        }
    )

    runtime_input = build_runtime_input(execution, workflow, effect_port=object())

    assert len(runtime_input.plan.tasks) == 1
    assert runtime_input.plan.tasks[0].capability_id == CapabilityId.OBSERVE
    assert runtime_input.goal.predicate.name == "observation_exists"


def test_build_runtime_input_rejects_unsupported_capability():
    execution = _execution()
    workflow = _workflow(
        {
            "kernel_plan": {
                "goal": {"predicate": "always_false"},
                "tasks": [{"task_id": "t-reason", "capability_id": "reason"}],
            }
        }
    )

    with pytest.raises(UnsupportedKernelWorkflowError):
        build_runtime_input(execution, workflow, effect_port=object())


def test_build_effect_port_real_executor():
    settings = SimpleNamespace(REAL_EFFECT_MODE=True)
    executor = build_effect_port(settings)

    from app.adapters.real_effect_executor import RealEffectExecutor

    assert isinstance(executor, RealEffectExecutor)


def test_build_effect_port_simulator():
    settings = SimpleNamespace(REAL_EFFECT_MODE=False)
    executor = build_effect_port(settings)

    assert isinstance(executor, SimulatorEffectPort)
