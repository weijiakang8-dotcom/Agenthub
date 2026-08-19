# PHASE9_LONG_RUNNING_REPORT

日期：2026-08-19。范围：Production Long-Running Hardening & Final Acceptance。

## 1. Production Baseline

- `REAL_USER_BASELINE_UNAVAILABLE`（POST-deploy 窗口 0 真实请求；验证流量已清理，不冒充）
- 验证流量（30min soak，本地）：Chat TTFT p50≈185ms / p95≈210ms；Chat TTL 3.3–15s；TASK TTL 24–41s；KNOWLEDGE TTL 3.5–89s（会话上下文增长影响）；ACTION approval→completed 全链
- 可派生指标（baseline_report）：TTL/LLM/RAG latency p50/p95、token、cost、fallback、error、dlq、approval_mismatch 均可从 executions/tool_calls/spans/Redis 稳定获得；TTFT 需流式埋点（保持 None，不伪造）

## 2. Long-Running Stability（30min soak，本地）

- 时长：≈30min；35 周期（CHAT 18 / TASK 6 / KNOWLEDGE 6 / ACTION 5）
- 完成：30/35 done（CHAT/TASK/KNOWLEDGE 全部 done；ACTION 5 次中 1 次 completed，4 次失败——根因=工具层 duplicate 被标记 FAILED，已修复并部署）
- 资源：executions 68→108、tool_calls 34→52、checkpoints 212→318、DB 13.7→14.9MB、Redis memory 1.94→2.03M、queue=0
- 结论：线性可控增长（checkpoint 增长符合预期，由 retention 清理约束）；无泄漏/无队列积压；测试数据已清理回基线（68/212）

## 3. Failure Injection

- LLM timeout/5xx：ModelGateway 重试/fallback 控制流测试 PASS（stub 双 provider）
- Worker crash after claim：第二次执行 unknown，provider 不重放（PASS）
- Provider success + DB write crash：unknown，provider 仅 1 次（PASS）
- 并发 claim：provider 恰 1 次（PASS）
- IN_FLIGHT：fail-closed（PASS）；FAILED：不重试（PASS）
- SSE disconnect：Chat 中断不留永久 PENDING（reconciliation 收敛，套件 PASS）
- 工具层 duplicate：修复为 SUCCESS 幂等结果（新测试 + 生产 3 连发 ACTION 复验 PASS）

## 4. Approval Contract

- PASS（契约测试 22 + 生产 ACTION：approval_required → tool_calls=0 → resume → frozen proposal 执行 → completed；mismatch → audit+FAILED 由契约测试覆盖）

## 5. Idempotency Contract

- PASS（PENDING→claim→IN_FLIGHT；SUCCESS→duplicate；FAILED→不重试；REJECTED→不执行；IN_FLIGHT→unknown；生产并发/顺序实测 provider 最多 1 次）

## 6. Reconciliation

- PASS（stale PENDING→FAILED+audit；fresh 未动；重入 0；orphan/legacy/IN_FLIGHT 语义套件覆盖；生产 legacy PENDING 按阈值待 manual 标记）

## 7. DLQ

- remaining=0；replayable=0；manual_review=0（Phase 8 已安全处置 11 条，备份+audit+验证）

## 8. Checkpoint

- retention=7d 可配置；仅 terminated+expired 删除；active/pending/recent 保留；二次运行 removed=0；audit 存在；不影响 resume/history（PASS）

## 9. Alerting

- threshold 来自配置；cooldown 15min（含过期后重新触发测试）；alert_events 持久化（生产 dlq_growth 记录）；/metrics 实时刷新 gauge；alert task 独立不阻塞业务（PASS）

## 10. Cost

- known→numeric；unknown→NULL；多次调用求和；fallback 独立计价；cost_unknown_executions 正确；历史数据不回填（COST_UNKNOWN）

## 11. Cross Provider

- `CONTROL FLOW VERIFIED`；`REAL_CROSS_PROVIDER_NOT_VERIFIED`（生产仍单 Provider 家族；未改 secrets/config）

## 12. Security

- /api/{executions,conversations,memories,documents} = 401；公网仅 80/443；内部 127.0.0.1；TLS 有效至 2026-11-16；secrets 未入 git；Approval/Idempotency 契约未改（PASS）

## 13. Tests

- pytest：528 passed / 20 skipped / 0 failed
- ruff：PASS；black --check：PASS；compileall：PASS

## 14. Git

- local HEAD：见最终 commit；remote HEAD：a06e22d；working tree clean；migration：0019

## 15. BLOCKER

- 无

## 16. WARNING

- REAL_CROSS_PROVIDER_NOT_VERIFIED
- REAL_USER_BASELINE_UNAVAILABLE
- 历史 cost COST_UNKNOWN（不回填）
- 历史 failed executions 15 条（预部署，保留审计）
- Approval resume 存在 UX 竞态（approval_required 早于 DB waiting 状态；前端需等待 waiting 后再审批；soak 中脚本侧 409 属该竞态，非契约违反）

## 17. PRO_REVIEW_REQUIRED

- NO

## 18. FINAL DECISION

- `PRODUCTION READY — WARNINGS REMAIN`
