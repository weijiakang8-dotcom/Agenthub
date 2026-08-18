# Task Model

## What

Task 是 **Capability Contract 的一次可调度实例**。它不是 DAG Node，不是 Agent，不是业务角色。

## Why

旧架构把 DAG Node 直接当成"一个 Agent 节点"，导致：

1. 角色（research/analyze/execute）写死进编排。
2. 一个 Node 可能隐式承担多个能力，无法做 Precondition/Postcondition 校验。
3. Scheduler 无法把 Task 独立映射到不同 Agent。

把 Task 定义为"能力契约实例"后，调度才可能发生，且调度不改变 Kernel 语义。

## Formal Model

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    INVALID = "INVALID"


class Task(BaseModel):
    task_id: str
    capability_id: str
    input_artifacts: list[str] = Field(default_factory=list)
    expected_output: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
```

Task 明确**不包含**：

- `agent_id` / `agent_identity`（禁止绑定 Agent）。
- 业务角色字段（禁止 `researcher`/`analyst`/`writer`）。
- LLM prompt 或模型配置（Phase 2 无 LLM）。

## Invariants

- `capability_id` 必须存在于 `CapabilityRegistry`。
- `input_artifacts` 中的每个引用必须是合法 `ArtifactRef`。
- Task 只能在 `TransitionEngine` 中被标记状态迁移。
- Task 不保存完整 Artifact 内容。

## Forbidden

- 把 Task 当 Capability。
- 把 DAG Node 当 Task。
- 给 Task 绑定 Agent。
- 在 Task 中嵌入业务角色或 prompt。
- 由业务代码直接改 `Task.status`。

## Runtime Enforcement

- `TransitionEngine` 在创建 Task 时校验 `capability_id` 在 Registry 中存在。
- `Scheduler` 是 Phase 2 之后才出现的组件；Phase 2 中 Task→Agent 的映射不实现，Task 直接由 Kernel 按 Plan 顺序执行。
- 状态迁移集中在 `TransitionEngine`，禁止散落。

## Failure Cases

1. `capability_id` 未注册 → Task 创建失败。
2. `input_artifacts` 引用 checksum 不匹配 → Task 置 INVALID。
3. Task 被 DAG Node 逻辑误用 → 通过类型与 Registry 校验拦截。

## Test Requirements

- Task 创建成功/失败（未注册 capability）两个用例。
- Task 不包含 `agent_id` 字段的 Schema 级测试。
- `TEST_06` 系列（Effect Lifecycle）中的 Mutate 必须经由 Task 实例化。

