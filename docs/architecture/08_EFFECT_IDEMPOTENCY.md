# Effect Idempotency & Lifecycle

## What

所有 Effectful 操作（Observe / Mutate）必须走完整生命周期：

```text
Command -> Execution -> Receipt -> Observation -> ObservedWorldState
```

每个 Mutate 必须携带 `idempotency_key`。retry 必须复用同一个 key，并且能证明不会制造第二个外部副作用。

## Why

分布式/外部世界最常见的故障是"提交成功但 ACK 丢失"（TIMEOUT_BUT_COMMITTED）。没有 Command/Receipt/Observation 分离，系统无法区分：

- 没提交
- 提交了但没收到回执
- 提交了且已确认

没有 idempotency_key，retry 会重复下单、重复发信、重复写库。

## Formal Model

```python
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.kernel.state import EvidenceLevel


class CommandStatus(StrEnum):
    ISSUED = "ISSUED"
    ACCEPTED = "ACCEPTED"
    TIMEOUT = "TIMEOUT"
    COMMITTED = "COMMITTED"
    REJECTED = "REJECTED"


class Command(BaseModel):
    command_id: str
    idempotency_key: str
    operation: str
    payload: dict[str, Any]
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ExecutionReceipt(BaseModel):
    command_id: str
    status: CommandStatus
    attempted_at: str
    completed_at: str | None = None
    error: str | None = None
    external_reference: str | None = None


class Observation(BaseModel):
    command_id: str
    observation_source: str
    observed_at: str
    external_state: dict[str, Any]
    evidence_level: EvidenceLevel
```

`Observation` 与 `02_STATE_MODEL.md` 中的定义一致；Phase 2 实现时只保留一份（以 `EvidenceLevel` 为最终类型）。

## Invariants

- 每个 Mutate 都产生一个 `Command`，且必须带 `idempotency_key`。
- 每个 `Command` 执行后产生一个 `ExecutionReceipt`。
- 只有 `Observation`（绑定 `command_id`）能写入 `ObservedWorldState`。
- retry 复用同一 `idempotency_key`，不生成新的逻辑 Effect。
- `command_id` 是执行实例标识；`idempotency_key` 是逻辑 Effect 标识。

## Forbidden

- Effectful Capability 直接 mutate `ObservedWorldState`。
- 跳过 Receipt 直接产生 Observation。
- retry 使用新的 `idempotency_key`。
- 把 `TIMEOUT` 状态当作"外部一定未发生"或"外部一定已发生"。
- 用模型预测的结果填充 `external_state`。

## Runtime Enforcement

- `EffectLedger.issue(command)` 记录 Command。
- `EffectLedger.record_receipt(receipt)` 只接受已有 `command_id`。
- `EffectLedger.record_observation(observation)` 校验 `command_id` 已有 Receipt。
- `TransitionEngine` 对 Mutate 的返回值只接受"挂起 Command"，不直接投影 `observed`。

## Failure Cases

1. `TIMEOUT_BUT_COMMITTED`：Mutate 已提交但 ACK 超时 → Receipt 为 TIMEOUT，`observed` 置 UNKNOWN。
2. 随后 Observe 发现 external state 已 COMMITTED → 写入 `L3_OBSERVED` 的 Observation。
3. 重复请求：同 `idempotency_key` 第二次执行 → 复用第一次结果，不产生第二个 Effect。
4. `TIMEOUT_NOT_COMMITTED`：Observe 发现外部无记录 → 可安全重试。
5. `UNKNOWN_RESULT`：Observe 无法确定 → 保持 UNKNOWN，等待人工介入。

## Test Requirements

- `TEST_05_EFFECT_LIFECYCLE`：不可跳步。
- `TEST_06_TIMEOUT_GHOST`：TIMEOUT_BUT_COMMITTED 全流程。
- `TEST_07_IDEMPOTENCY`：retry 不产生第二个外部效果。
- DeterministicWorldSimulator 必须覆盖 SUCCESS / TIMEOUT_BUT_COMMITTED / TIMEOUT_NOT_COMMITTED / DUPLICATE_REQUEST / UNKNOWN_RESULT。
