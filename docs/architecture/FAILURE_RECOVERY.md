# FAILURE_RECOVERY

## Failure 分层（core/failure.py）

- TRANSIENT / TIMEOUT / PROVIDER → LLM 层重试（ModelGateway，≤3）
- INFRASTRUCTURE / TRANSIENT → Celery 层重试
- PERMANENT / BUSINESS / APPROVAL → 不重试
- 副作用失败：立即终止 + audit，不自动 retry/replan

## Reconciliation（beat：5min）

- stale PENDING Execution → FAILED + execution_reconciled（CAS，幂等，fresh 不动）
- 孤儿 PENDING tool_call（终止 execution）→ FAILED + audit，绝不执行
- IN_FLIGHT 超时 → 保持 + side_effect_unknown_reconciled（fail-closed）
- 历史无 key PENDING → 保持 + tool_call_manual_required
- 幂等：重复运行零状态变化、零重复审计；manual / unknown 审计按
  (resource_id, action, tool_call_id) 确定性去重，reconcile(reconcile(x)) == reconcile(x)

## DLQ（人工 CLI）

- stats / replay / discard + audit
- replay 仅 PENDING/RUNNING；终止态 skip；副作用/UNKNOWN 禁止自动 replay；无 Approval 绕过；无无限重试
- 生产历史 11 条已分类处置（备份 + 11 audit），当前 DLQ=0

## Checkpoint Retention（beat：1h）

- 仅删除 terminated 且 completed_at < now-7d；active/pending/recent 保留
- 幂等（二次 removed=0）、audit、不影响 resume/history

## Alerting（beat：60s）

- 阈值可配置（DLQ/PENDING/IN_FLIGHT/approval_mismatch/fallback rate/latency p95/db/redis）
- cooldown 15min；alert_events 持久化；/metrics 实时 gauge；告警任务独立不阻塞业务
