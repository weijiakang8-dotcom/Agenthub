# Legacy Tool → Capability Mapping

> Phase 3.0 基线。每条映射都必须明确 Evidence 语义；无法安全映射的标记 BLOCKED。

| Legacy Tool | classification | Kernel Capability | Evidence Level | Command | Receipt | Observation | GoalEvaluator 可入 |
|---|---|---|---|---|---|---|---|
| `search_web` | Pure | `Retrieve` + `Extract` | `L2_SUPPORTED` | 否 | 否 | 否 | 是（Knowledge） |
| `query_db`（内部库） | Pure | `Retrieve` | `L2_SUPPORTED` | 否 | 否 | 否 | 是（Knowledge） |
| `query_db`（外部世界状态） | Effectful | `Observe` | `L3_OBSERVED` | 是（Observe Command） | 是（ExecutionReceipt） | 是 | 是（Observed） |
| `send_email` | Effectful | `Mutate` | `L3_OBSERVED`（仅 Observation 后） | 是 | 是 | 否（需独立 Observe） | 否（直接） |

## 明确禁止

- `search_web` 的搜索结果 ≠ Observation。
- `query_db` 的内部库行 ≠ Observation。
- `send_email` 的 SMTP success ≠ Observation。
- 未经真实外部 Observe，任何 Legacy 输出不得提升为 `L3_OBSERVED`。

## BLOCKED

- unknown tool 仍 BLOCKED（无 fallback）。

## 已实现

- `query_db` internal → `Retrieve`（Pure，L2）。
- `query_db` external → `Observe`（Effectful，Command → Receipt → Observation → Reconciliation → L3）。
- `send_email` → `Mutate`（Effectful，Command → Receipt → Reconciliation）；再经独立 `Observe` → Observation(L3) → GoalEvaluator。
