# Runtime Semantics

## What

Phase 2 Runtime 是一个 **单线程、确定性、内存态** 的状态转移循环：

```text
State
  -> Check Preconditions
  -> Apply Capability
  -> Validate Postconditions
  -> Project New State
  -> Evaluate Goal
  -> Continue / Replan / Stop
```

## Why

Kernel 的价值是"可被证明正确"，而不是"能跑得快"。确定性、单线程、无外部依赖让每一个 Transition 可复现、可回放、可测试。并发、分布式、真实网络、真实数据库全部推迟到 Application Runtime。

## Formal Model

```python
from __future__ import annotations

from dataclasses import dataclass

from app.kernel.goal import GoalEvaluator, GoalStatus
from app.kernel.registry import CapabilityRegistry
from app.kernel.state import State


@dataclass(frozen=True)
class TransitionResult:
    state: State
    status: str  # APPLIED / PRECONDITION_FAILED / POSTCONDITION_FAILED / EFFECT_PENDING
    detail: str | None = None


class TransitionEngine:
    def __init__(self, registry: CapabilityRegistry, goal_evaluator: GoalEvaluator):
        self.registry = registry
        self.goal_evaluator = goal_evaluator

    def apply(self, state: State, capability_id: str, args: dict) -> TransitionResult:
        capability = self.registry.get(capability_id)
        if capability is None:
            return TransitionResult(state, "INVALID_CAPABILITY")
        if not self._check_preconditions(state, capability, args):
            return TransitionResult(state, "PRECONDITION_FAILED")
        next_state = capability.apply(state, args)
        if not self._check_postconditions(next_state, capability):
            return TransitionResult(state, "POSTCONDITION_FAILED")
        return TransitionResult(next_state, "APPLIED")

    def run(
        self,
        state: State,
        plan: list[tuple[str, dict]],
        goal,
    ) -> tuple[State, GoalStatus]:
        for capability_id, args in plan:
            result = self.apply(state, capability_id, args)
            if result.status in {"PRECONDITION_FAILED", "POSTCONDITION_FAILED"}:
                return result.state, GoalStatus.BLOCKED
            state = result.state
            status = self.goal_evaluator.evaluate(state, goal)
            if status in {GoalStatus.SATISFIED, GoalStatus.BLOCKED}:
                return state, status
        return state, self.goal_evaluator.evaluate(state, goal)
```

## Invariants

- 单线程：同一时刻只有一个 Transition 在执行。
- 确定性：同 `(InitialState, Goal, Plan)` 必产生同 `(State, GoalStatus)`。
- 不可变 State：每次 Transition 返回新 State，不原地修改。
- 无外部依赖：无网络、无 DB、无文件系统、无 LLM、无随机、无时钟决策。
- `EFFECT_PENDING` 状态交给 EffectLedger，不直接投影 `observed`。

## Forbidden

- 引入真实网络、真实数据库、真实文件、LLM、随机性、外部 API。
- 用 `time.time()` / `random.random()` 参与逻辑分支。
- 用 UUID 参与逻辑决策（可生成 UUID 作为标识，但不得参与排序/分支）。
- 让 Transition 依赖共享可变全局状态。

## Runtime Enforcement

- Phase 2 的 `TransitionEngine` 是普通同步 Python（`apply` 可同步可异步，但语义必须是可终止的确定计算）。
- Capability 必须来自 Registry；禁止字符串动态执行。
- `GoalEvaluator` 是唯一终止来源。

## Failure Cases

1. Precondition 不满足 → 不执行，状态不变。
2. Postcondition 不满足 → 不回投影，返回 BLOCKED。
3. 同一输入重复运行 → 输出一致。
4. 外部 Effect 未完成 → 返回 EFFECT_PENDING，等待 Observation。

## Test Requirements

- `TEST_02_PRECONDITION`：不满足则不执行。
- Determinism：同一输入两次运行结果逐字节相等。
- 未知 capability → INVALID_CAPABILITY。
- Postcondition 失败 → BLOCKED。

