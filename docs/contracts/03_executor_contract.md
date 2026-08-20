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

### 副作用工具 Retry 边界（Reliability Contract Fix）

- 副作用工具 claim 成功后，provider invocation 最多一次。
- TIMEOUT / TRANSIENT / 连接丢失 / 无法确定是否已执行的错误：
  禁止再次调用 provider，结果记为 `UNKNOWN`，tool_call 保持 `IN_FLIGHT`（fail-closed），
  由 reconciliation / query_effect 裁决（CONFIRMED_COMMITTED / NOT_COMMITTED / STILL_UNKNOWN）。
- `UNKNOWN` 不等于 `FAILED`；不允许猜测性重放；只有能确定 `NOT_COMMITTED` 时才允许未来重新执行。
- 只读工具保留既有 failure policy 的合理 retry（≤3 次）。
- 副作用判定以 `ToolSpec.side_effect` 为准（与 Capability.side_effect 同源，
  在工具边界显式化，不引入第二套能力体系）。

### Verify 判定状态机（ADR-005，Fail-Closed）

- `PASS`：LLM 输出 trim 后、大小写不敏感的精确 `PASS` → 验证通过，继续 COMPLETED。
- `FAIL`：精确 `FAIL` → 触发一次 replan（维持 `revision_count==0` 才 replan、≤1）。
- `UNKNOWN`：输出为空 / None / 任何非精确 PASS/FAIL 内容（含 `PAS`、`OK`、`满足`）
  → 不算 PASS；不触发 replan；审计 `verify_unknown` + span error；业务结果保留（未验证）。
- `ERROR`：LLM 调用异常 / 超时 / 解析异常 → 不算 PASS；不触发 replan；
  审计 `verify_error` + span error；业务结果保留（未验证）。
- 不变式：UNKNOWN/ERROR 一律不得成为 PASS；不得触发 replan；verify 预算仍 ≤1；
  PASS/FAIL 之外的任何状态必须有审计与 span 记录，不能静默。

## 恢复

- 每个已提交步骤后 checkpoint；从最后已提交步骤继续。
- 已执行的副作用不因 replan/resume 再次执行。
