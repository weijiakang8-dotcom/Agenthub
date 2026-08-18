# Capability Contract

## What

Capability 是 Kernel 中最小的、被 Registry 承认的执行契约。Phase 2 只允许 8 个：

| id | classification | 作用 |
|---|---|---|
| `retrieve` | Pure | 从给定输入/引用中取出素材 |
| `extract` | Pure | 从素材中抽取结构化事实 |
| `compute` | Pure | 确定性计算 |
| `validate` | Pure | 校验约束/后置条件 |
| `reason` | Pure | 从 Knowledge 推出新的 Knowledge |
| `synthesize` | Pure | 把多个 Artifact 合成为一个 Artifact |
| `observe` | Effectful | 读取外部世界并产生 Observation |
| `mutate` | Effectful | 通过 Command 改变外部世界 |

任何业务动作（搜索、发邮件、写报告、改数据库）都不是 Capability，而是多个 Capability 的组合 Task。

## Why

把"能力"固定为 8 个正交原语，才能：

1. 让 Kernel 保持最小、可验证、可终止。
2. 让 Pure/Effectful 边界变成类型边界而非约定。
3. 让 Registry 成为唯一真相源，杜绝字符串动态执行和隐藏副作用。
4. 让业务 Agent 变成 Kernel 的使用者，而不是 Kernel 的一部分。

## Formal Model

```python
from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.kernel.state import State


class CapabilityId(StrEnum):
    RETRIEVE = "retrieve"
    EXTRACT = "extract"
    COMPUTE = "compute"
    VALIDATE = "validate"
    REASON = "reason"
    SYNTHESIZE = "synthesize"
    OBSERVE = "observe"
    MUTATE = "mutate"


class Classification(StrEnum):
    PURE = "pure"
    EFFECTFUL = "effectful"


class SideEffect(BaseModel):
    target: str
    kind: str
    idempotency_required: bool = False


class CapabilityContract(BaseModel):
    id: CapabilityId
    classification: Classification
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    cost_estimate: float = 0.0
    latency_estimate: float = 0.0
    side_effects: list[SideEffect] = Field(default_factory=list)


class Capability(Protocol):
    contract: CapabilityContract

    async def apply(self, state: State, args: dict[str, Any]) -> State:
        ...
```

`apply` 的语义约束：

- Pure：返回的新 `State` 只允许 `knowledge` 变化，`observed` 必须与输入完全相同。
- Effectful：不直接返回 `observed` 变更，而是返回包含 `Command` 的挂起状态（见 `08_EFFECT_IDEMPOTENCY.md`）。

## Invariants

- Registry 是唯一 Capability 真相源。
- 运行时执行前必须 `registry.get(capability_id)`。
- 禁止字符串直接动态执行能力。
- `classification` 必须与 `apply` 的副作用一致。
- 8 个之外的能力一律拒绝注册。

## Forbidden

- 新增第 9 个 Capability（必须先走 `ARCHITECTURE_CHANGE_REQUEST.md`）。
- 把业务动作注册为 Capability。
- Pure Capability 产生副作用。
- Effectful Capability 直接 mutate `observed`。
- 绕过 Registry 直接调用 `apply`。

## Runtime Enforcement

- `CapabilityRegistry.register` 校验 `id ∈ CapabilityId` 且 contract 完整。
- `TransitionEngine` 执行前检查 `preconditions`，执行后检查 `postconditions`。
- `TransitionEngine` 对 Pure 返回的 State 做 `observed == input.observed` 校验。
- `EffectLedger` 拦截 Effectful 返回，强制走 Command→Receipt→Observation。

## Failure Cases

1. 注册未知 capability id → Registry 拒绝。
2. Pure capability 返回的 State 改了 `observed` → Transition 拒绝。
3. 执行前 `preconditions` 不满足 → 不执行。
4. 执行后 `postconditions` 不满足 → Transition 标记 invalid。
5. Effectful capability 返回了直接 `observed` 变更而非 Command → EffectLedger 拒绝。

## Test Requirements

- 每个 Capability 必须有 contract 存在性测试。
- Pure 8 个中除 `observe`/`mutate` 外全部覆盖。
- 必须有"非法能力被拒绝注册"测试。
- `TEST_01_PURE_TRANSITION` 与 `TEST_05_EFFECT_LIFECYCLE` 直接依赖本文档。

