# 03 Executor Contract v1

## 执行顺序

```text
Plan Validator → Risk/Budget Validator → (ACTION: Approval) → Execution
  → Checkpoint → Verify（按 04 策略）→ Respond
```

- 验证必须先于审批；用户不得批准未经验证的计划。

## 预算（物理边界）

- 步数 ≤6；replan ≤1；verify ≤1。
- wall-clock / token / cost 预算默认值在阶段 1 基准确定。
- 只读任务超限：停止继续执行，保留已有结果，返回
  `partial_result + budget_exceeded`。
- 副作用任务超限：立即停止、禁止继续副作用、checkpoint + audit +
  `budget_exceeded`；**禁止自动 replan**。

## 失败与重试

- 只读步骤瞬态失败：Tool 层重试 ≤3（`failure.py` 分类）。
- LLM/Provider 失败：Model Gateway 层处理。
- 基础设施失败：Celery 层处理。
- 业务/永久失败：该步失败；最多一次 replan（只读步骤）。
- 副作用步骤失败：立即终止 + audit，不重试、不重排。
- 副作用步骤必须幂等（idempotency_key），恢复不重复执行。

## 恢复

- 每个已提交步骤后 checkpoint；从最后已提交步骤继续。
- 已执行的副作用不因 replan/resume 再次执行。
