# Architecture Failure Regression Spec

## What

本文档是 Kernel 的**失败回归规范**。它定义 8 个强制测试（TEST_01..TEST_08），其中 TEST_08 是最高优先级的架构失败回归：**Prediction 不得被当成 Observation**。

## Why

旧架构的完成条件建立在"模型输出了 final_output"之上。这会让：

```text
Prediction: test_valid_login = PASS
```

在没有真实 Observation 的情况下，被当作"登录测试真的通过了"。这类错误无法靠加 Agent、加 Prompt 或加评测兜住，必须由 Kernel 语义在结构上拒绝。

## Formal Model

每个测试对应一个"旧架构失败 / 新 Kernel 通过"的断言：

| 测试 | 断言 |
|---|---|
| `TEST_01_PURE_TRANSITION` | Pure 改 Knowledge，不改 Observed |
| `TEST_02_PRECONDITION` | Precondition 不满足则能力不执行 |
| `TEST_03_STATE_PROJECTION` | State 与 Artifact Store 分离 |
| `TEST_04_EVIDENCE` | L1→L2 合法；L2→L3 需 Observation；Prediction 不得变 Observation |
| `TEST_05_EFFECT_LIFECYCLE` | Command→Receipt→Observation 不可跳步 |
| `TEST_06_TIMEOUT_GHOST` | TIMEOUT_BUT_COMMITTED 全流程 |
| `TEST_07_IDEMPOTENCY` | 同 idempotency_key retry 不产生第二个 Effect |
| `TEST_08_ARCHITECTURE_FAILURE_REGRESSION` | Prediction ≠ Observation，Goal 要求 L3 → `NOT_SATISFIED` |

## Invariants

- TEST_08 在旧架构上必须失败（旧架构无法区分 Prediction/Observation）。
- TEST_08 在新 Kernel 上必须通过。
- 若有人修改 Kernel 使 TEST_08 通过"放宽语义"的方式变成通过，视为破坏 Constitution。

## Forbidden

- 用 mock/alias 让 TEST_08 在新 Kernel 上"看起来通过"。
- 把模型输出的字符串包装成 `Observation`。
- 把 `ToolCall.status == success` 直接视为外部事实。
- 为了让 TEST_08 通过而删除 `required_evidence`。

## Runtime Enforcement

- TEST_08 作为 CI 门禁与 Kernel Readiness 门禁。
- `GoalEvaluator` 对 `required_evidence == L3_OBSERVED` 且无 Observation 的断言，永远返回 `NOT_SATISFIED`。

## Failure Cases

1. TEST_08 通过但 Kernel 允许 Prediction→Observation → 架构失败。
2. TEST_08 在新 Kernel 失败 → Kernel 不得宣布 Ready。
3. 任何测试为了通过而放宽 Constitution → 该测试无效。

## Test Requirements

- Phase 2 必须实现全部 8 个测试。
- TEST_08 必须显式包含：只有 Prediction、无 Observation、Goal 要求 L3，断言 `NOT_SATISFIED`。
- TEST_06 必须覆盖 TIMEOUT_BUT_COMMITTED。

