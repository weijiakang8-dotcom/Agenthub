# Goal Evaluator

## What

GoalEvaluator 是唯一能判定 `SATISFIED / NOT_SATISFIED / BLOCKED` 的组件。Goal 由三部分组成：

```text
Goal {
    predicate: Predicate
    required_evidence: EvidenceLevel
    constraints: list[Constraint]
}
```

## Why

旧架构的完成条件是"graph.ainvoke 返回 final_output"，等价于"最后一个节点跑完"。这是虚假完成。Goal 必须同时满足：

1. Predicate 成立。
2. Evidence 达到 `required_evidence`。
3. Hard Constraints 全部成立。
4. `ObservedWorldState` 提供现实支持。

否则一律 `NOT_SATISFIED`。

## Formal Model

```python
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.kernel.state import EvidenceLevel, State


class GoalStatus(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    BLOCKED = "BLOCKED"


class Predicate(BaseModel):
    expression: str
    # 运行期由 safe_expression 风格的 AST 白名单求值器解析，
    # 只允许引用 State 的 knowledge / observed / context。


class Constraint(BaseModel):
    name: str
    expression: str
    hard: bool = True


class Goal(BaseModel):
    goal_id: str
    predicate: Predicate
    required_evidence: EvidenceLevel
    constraints: list[Constraint] = Field(default_factory=list)


class GoalEvaluator:
    def evaluate(self, state: State, goal: Goal) -> GoalStatus:
        ...
```

判定顺序（确定性）：

1. 检查所有 hard constraints。
2. 检查 Predicate。
3. 检查 Predicate 所依赖的 Knowledge 条目，其 `evidence_level >= goal.required_evidence`。
4. 若 `required_evidence >= L3_OBSERVED`，则 Predicate 中涉及"现实已发生"的断言必须在 `ObservedWorldState` 中有对应 Observation。
5. 全部通过才返回 `SATISFIED`。

## Invariants

- GoalEvaluator 是唯一能返回 `SATISFIED` 的组件。
- `L1/L2` 永远不能满足 `required_evidence == L3_OBSERVED`。
- 没有 Observation 的"外部事实"断言永远判 False。
- 约束违反时，即使 Predicate 成立也返回 `BLOCKED` 或 `NOT_SATISFIED`。

## Forbidden

- 用"最后一个 Node 完成"代替 Goal 判定。
- 用 `final_output` 非空代替 SATISFIED。
- 用 Prediction 满足 L3/L4。
- 用 LLM-as-Judge 的文本分数代替 Predicate。
- 让业务代码直接返回 `SATISFIED`。

## Runtime Enforcement

- Runtime Loop 在每个 Transition 后调用 `GoalEvaluator.evaluate`。
- `SATISFIED` → Stop；`BLOCKED` → 人工介入；`NOT_SATISFIED` → Continue/Replan。
- Predicate 求值器基于白名单 AST（复用现有 `app/core/safe_expression.py` 的思路，但只允许 Kernel State 命名空间）。

## Failure Cases

1. Goal 要求 L3，但只有 L2 → `NOT_SATISFIED`。
2. Predicate 成立但硬约束违反 → `BLOCKED`。
3. 外部事实断言没有 Observation → Predicate 判 False。
4. `final_output` 非空但 Predicate 为 False → `NOT_SATISFIED`。

## Test Requirements

- `TEST_08_ARCHITECTURE_FAILURE_REGRESSION`：只有 Prediction 没有 Observation，Goal 要求 L3，必须返回 `NOT_SATISFIED`。
- 约束违反、证据不足、Predicate 通过三种组合的确定性测试。
- 证明 `L1/L2` 无法通过 L3 门槛。

