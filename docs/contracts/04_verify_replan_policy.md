# 04 Verify & Replan Policy v1

## Verify 分级

```text
CHAT / KNOWLEDGE       → 不 Verify
LOW / MEDIUM TASK      → 不 Verify
HIGH TASK              → Verify 一次
ACTION                 → 执行前 Approval + 执行后结果确认
```

## Verify 职权

- 输出只有 PASS / FAIL，不得重新发明任务。
- FAIL → 最多一次 replan。

## Replan 规则

- 只能重排/降级只读步骤；副作用集合不可变。
- replan 产物必须重新经过 Plan Validator、Risk/Budget Validator；
  副作用集合变化必须重新 Approval。
- Verify/replan 不得绕过任何安全闸门。
