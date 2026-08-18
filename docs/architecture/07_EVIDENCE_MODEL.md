# Evidence Model

## What

EvidenceLevel 是 Knowledge 条目"离现实有多近"的唯一度量：

| Level | 含义 |
|---|---|
| `L1_INFERRED` | 由推理/计算/综合得出，无外部支撑 |
| `L2_SUPPORTED` | 有 Artifact 支撑，但未经 Effectful Observation |
| `L3_OBSERVED` | 由 Effectful 执行结果（Observation）证实 |
| `L4_ATTESTED` | 由可信系统或 Human Approval 证实 |

## Why

如果允许 `L1` 直接变成 `L4`，或允许 `Prediction` 冒充 `Observation`，Goal 判定就失去意义，幻觉会被当作现实。证据分级是 Kernel 阻断幻觉级联的核心机制。

## Formal Model

```python
from __future__ import annotations

from pydantic import BaseModel

from app.kernel.state import EvidenceLevel


class EvidenceTransition(BaseModel):
    from_level: EvidenceLevel
    to_level: EvidenceLevel
    requires_artifact: bool = False
    requires_observation: bool = False
    requires_attestation: bool = False


LEGAL_TRANSITIONS: dict[tuple[EvidenceLevel, EvidenceLevel], EvidenceTransition] = {
    (EvidenceLevel.L1_INFERRED, EvidenceLevel.L2_SUPPORTED): EvidenceTransition(
        from_level=EvidenceLevel.L1_INFERRED,
        to_level=EvidenceLevel.L2_SUPPORTED,
        requires_artifact=True,
    ),
    (EvidenceLevel.L2_SUPPORTED, EvidenceLevel.L3_OBSERVED): EvidenceTransition(
        from_level=EvidenceLevel.L2_SUPPORTED,
        to_level=EvidenceLevel.L3_OBSERVED,
        requires_observation=True,
    ),
    (EvidenceLevel.L3_OBSERVED, EvidenceLevel.L4_ATTESTED): EvidenceTransition(
        from_level=EvidenceLevel.L3_OBSERVED,
        to_level=EvidenceLevel.L4_ATTESTED,
        requires_attestation=True,
    ),
}
```

## Invariants

- 只能通过 `LEGAL_TRANSITIONS` 提升。
- `L1 -> L2` 必须存在 Artifact。
- `L2 -> L3` 必须存在 Effectful Observation。
- `L3 -> L4` 必须存在可信系统或 Human Approval。
- 业务代码不能直接修改 `evidence_level`。

## Forbidden

- `L1 -> L4`、`L2 -> L4`（跳级）。
- `Prediction -> Observed`、`Reason -> Observed`。
- 用 LLM 输出包装成 `L3_OBSERVED`。
- 用 `ToolCall.status == success` 直接视为外部世界事实。
- 用测试预测结果代替真实观察结果。

## Runtime Enforcement

- `EvidenceLedger.promote(entry, to_level, proof)` 校验 `LEGAL_TRANSITIONS` 与 proof 类型。
- 缺失 Artifact/Observation/Attestation 时抛错，不回退。
- `GoalEvaluator` 只读取 `EvidenceLedger` 的最终 level。

## Failure Cases

1. 尝试 `L1 -> L3` 但无 Observation → 拒绝。
2. 尝试 `L2 -> L4` → 拒绝。
3. 把 `PREDICTION` 条目提升到 `L3` 但 proof 是模型输出 → 拒绝。
4. 缺失 Artifact 时 `L1 -> L2` → 拒绝。

## Test Requirements

- `TEST_04_EVIDENCE`：L1→L2 合法、L2→L3 必须 Observation、Prediction 不得变 Observation。
- 非法跳级全部拒绝的用例。
- `TEST_08_ARCHITECTURE_FAILURE_REGRESSION` 直接依赖本文档。

