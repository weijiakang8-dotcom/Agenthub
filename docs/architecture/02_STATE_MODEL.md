# State Model

## What

Kernel 的 State 是一个不可变值对象，严格分为三层：

```text
State {
    knowledge: KnowledgeState
    observed: ObservedWorldState
    context: ExecutionContext
}
```

State 是 `(State, Capability) -> State'` 中的节点；State Graph 的每个节点都是 State，每条边都是 Capability Transition。

## Why

把"模型相信的东西"和"现实世界已经确认的东西"混在同一个扁平字典里，是现有 AgentHub 所有幻觉级联、虚假完成、跨租户污染的根因。分层之后：

1. `KnowledgeState` 可以自由推理、假设、预测，且天然被怀疑。
2. `ObservedWorldState` 只能被真实 Effect 的 Observation 写入，天然可信。
3. `ExecutionContext` 只记录"这次运行"的元信息，不参与知识或现实判断。

## Formal Model

Python + Pydantic 表达（Phase 2 实现语言）：

```python
from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceLevel(StrEnum):
    L1_INFERRED = "L1_INFERRED"
    L2_SUPPORTED = "L2_SUPPORTED"
    L3_OBSERVED = "L3_OBSERVED"
    L4_ATTESTED = "L4_ATTESTED"


class KnowledgeKind(StrEnum):
    FACT = "FACT"
    HYPOTHESIS = "HYPOTHESIS"
    PREDICTION = "PREDICTION"
    PLAN = "PLAN"
    CANDIDATE_ARTIFACT = "CANDIDATE_ARTIFACT"
    DERIVED_ARTIFACT = "DERIVED_ARTIFACT"


class KnowledgeEntry(BaseModel):
    id: str
    kind: KnowledgeKind
    statement: str
    evidence_level: EvidenceLevel
    artifact_refs: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: float | None = None


class KnowledgeState(BaseModel):
    entries: dict[str, KnowledgeEntry] = Field(default_factory=dict)


class Observation(BaseModel):
    command_id: str
    observation_source: str
    observed_at: str
    external_state: dict[str, Any]
    evidence_level: EvidenceLevel


class ObservedWorldState(BaseModel):
    observations: dict[str, Observation] = Field(default_factory=dict)
    receipts: dict[str, "ExecutionReceipt"] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    run_id: str
    goal_ref: str | None = None
    plan_ref: str | None = None
    trace: list[str] = Field(default_factory=list)


class State(BaseModel):
    knowledge: KnowledgeState = Field(default_factory=KnowledgeState)
    observed: ObservedWorldState = Field(default_factory=ObservedWorldState)
    context: ExecutionContext
```

`ExecutionReceipt` 在 `08_EFFECT_IDEMPOTENCY.md` 中定义；这里以字符串引用避免循环，Phase 2 实现时用同包直接导入。

## Invariants

- `ObservedWorldState` 只包含 `Observation` 与 `ExecutionReceipt`。
- `KnowledgeState` 中的 `PREDICTION`/`HYPOTHESIS` 永远不能出现在 `ObservedWorldState`。
- 每个 `KnowledgeEntry` 必须有 `evidence_level`。
- State 不可被原地修改；每次 Transition 产生新的 State 值。
- State 不直接持有完整 Artifact 内容，只持有 `artifact_refs`。

## Forbidden

- 把 `KnowledgeState` 当 `ObservedWorldState`。
- 把 `Prediction` 标记为 `Observation`。
- 把 `Hypothesis` 标记为 `FACT`。
- 伪造外部世界状态。
- Pure Capability 写 `ObservedWorldState`。
- 业务代码直接构造 `Observation` 而不经过 Effect Lifecycle。

## Runtime Enforcement

- `TransitionEngine` 只允许 Pure Capability 写 `knowledge`。
- `EffectLedger` 是唯一能 append `Observation` 的组件。
- State 的 Pydantic 类型在运行期即可阻止层级混用；Phase 2 用 `pydantic.validate_call` 与显式构造器强化边界。

## Failure Cases

1. Pure Capability 试图返回 `observed` 变更 → Postcondition 校验拒绝。
2. `KnowledgeEntry.evidence_level` 缺失 → 构造失败。
3. `Prediction` 条目出现在 `ObservedWorldState` → 类型/校验拒绝。
4. 两个 Transition 共享同一 State 引用并原地修改 → 确定性被破坏（必须用不可变值）。

## Test Requirements

- `TEST_01_PURE_TRANSITION`：Pure 可改 Knowledge，不能改 Observed。
- `TEST_03_STATE_PROJECTION`：State 与 Artifact Store 分离。
- `TEST_04_EVIDENCE`：Prediction 不得变成 Observation。

