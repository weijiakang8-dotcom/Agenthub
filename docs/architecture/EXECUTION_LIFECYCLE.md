# EXECUTION_LIFECYCLE

Execution 状态（唯一由 Execution 持有）：

PENDING → RUNNING → WAITING_FOR_APPROVAL | COMPLETED | FAILED | ROLLED_BACK

## 运行路径（runner.run_execution）

1. CAS：PENDING→RUNNING
2. workflow plan 规范化 + 校验（非法 → plan_invalid + audit + FAILED）
3. graph.ainvoke（checkpoint）
4. 审批中断：状态先 COMMIT waiting_for_approval，再 emit approval_required（Phase 10 修复，事件不领先持久化状态）
5. resume：CAS waiting_for_approval→RUNNING；并发第二个 409（单 winner）
6. 终止分支：approval_rejected / budget_exceeded / side_effect_failure / plan_invalid → FAILED + audit
7. COMPLETED：final_output + plan(dict) + usage；evaluate_execution_task 异步

## 副作用执行生命周期（tool_calls）

PENDING（provider 从未调用）
→ atomic claim（UPDATE WHERE status='pending' RETURNING，提交后才调用 provider）
→ IN_FLIGHT（已 claim、调用中）
→ SUCCESS（缓存结果，永不重执行）| FAILED（不自动重试/重放）| REJECTED（不执行）

- 唯一事实源：tool_calls(idempotency_key, status)
- checkpoint 只决定从哪步继续，不决定副作用是否发生
- IN_FLIGHT 遇恢复 → UNKNOWN → fail-closed（side_effect_unknown audit，人工）
- 历史无 key PENDING → fail-closed（tool_call_manual_required）
