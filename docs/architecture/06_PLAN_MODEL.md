# Plan Model

## What

Plan 是一条 **State Transition Path**：它描述 Task、依赖、前置条件与期望的状态变化，但不绑定 Agent。

## Why

旧架构的 `Workflow.agent_chain` / `dag_definition` 把 Agent 绑定进 Plan，导致：

1. Plan 无法脱离具体 Agent 复用。
2. Scheduler 无法根据负载/能力重新分配。
3. "计划"与"执行者"耦合，无法做纯计划层面的确定性验证。

Plan 只回答"要发生哪些 Transition、以什么顺序、依赖什么前置状态"，不回答"谁来做"。

## Formal Model

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class Dependency(BaseModel):
    task_id: str
    on_task_id: str


class ExpectedTransition(BaseModel):
    from_state_hash: str | None = None
    to_state_hash: str | None = None
    assertion: str | None = None


class PlanStep(BaseModel):
    step_id: str
    task_id: str
    preconditions: list[str] = Field(default_factory=list)
    expected_transition: ExpectedTransition | None = None


class Plan(BaseModel):
    plan_id: str
    steps: list[PlanStep]
    dependencies: list[Dependency] = Field(default_factory=list)
    goal_ref: str | None = None
```

Plan 的执行由 `TransitionEngine` 做拓扑排序，违反依赖或前置条件则拒绝该步。

## Invariants

- Plan 不含 `agent_id` / 角色字段。
- 每个 `PlanStep.task_id` 指向合法 Task。
- `dependencies` 必须构成 DAG（无环）。
- 前置条件必须可由 State 确定性判定。

## Forbidden

- 在 Plan 中绑定 Agent。
- 用 Plan 直接承载业务角色。
- 在 Plan 里写 LLM prompt。
- 让 Plan 依赖随机数或当前时间。

## Runtime Enforcement

- `TransitionEngine` 对 Plan 做拓扑排序与环检测。
- 每一步 apply 前重新检查 Precondition（Plan 中的 Precondition 是声明，运行时仍以当前 State 为准）。
- 违反依赖顺序的步骤被跳过并标记 INVALID。

## Failure Cases

1. Plan 有环 → 拒绝执行。
2. 依赖缺失 → 该步 INVALID。
3. Precondition 不再满足 → 该步不执行，进入 Replan。
4. Plan 中出现 `agent_id` → Schema 校验拒绝。

## Test Requirements

- 拓扑排序测试。
- 环检测测试。
- "Plan 不绑定 Agent"的 Schema 级测试。
- Precondition 运行时重校验测试。

