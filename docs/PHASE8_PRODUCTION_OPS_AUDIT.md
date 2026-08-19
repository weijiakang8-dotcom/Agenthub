# PHASE8_PRODUCTION_OPS_AUDIT

日期：2026-08-19。范围：Production Operations & Final Architecture Audit。

## DLQ disposition（11 条，全部处置）

逐条分析（execution_id / status / created_at / tool_calls / email_success）：

- 11 条全部 `failed`（error=“All connection attempts failed”，预部署 e9b3756 构建，2026-08-18~19）
- 10 条无 tool_calls；1 条（d224ed03）仅 read-only query_db failed（无 idempotency key，非副作用）
- 所有条目 `send_email success = 0` → 无副作用已发生 → 无重复副作用风险
- replay 条件：全部终止态 → `dlq_replay` 必然 skip（已实测 idx0 skip + audit）

分类：11 条全部 `ALREADY_OBSOLETE` + `SAFE_TO_DISCARD`；无 `SAFE_TO_REPLAY`、无 `REQUIRES_MANUAL_REVIEW`、无 `REQUIRES_REVIEW` 条目。

处置（READ→BACKUP→SHOW→EXECUTE→VERIFY→AUDIT）：

- 备份：`/home/ubuntu/phase8_dlq_backup_20260819_200012.txt`（11 行原始 JSON）
- 目标：11 条（上述 id 清单）
- 执行：`dlq_discard` ×11（actor=phase8）
- 验证：DLQ count 11 → 0；audit `dlq_discard` = 11
- 执行历史（executions 行）未删除，仅清队列

## Cross-Provider

- 审计结论：ModelGateway `select()` 按 model_configs 构造独立 `ChatOpenAI`（各自 base_url/api_key/model/provider），`invoke()/stream()` 按列表顺序 fallback，与 provider 无关 → 代码支持真正跨 Provider（情况 A）
- 新增测试：`select()` 返回两个不同 provider/base_url 配置（stub）；既有 fallback 控制流测试（A failure → B success、attempts/cost/span）
- 生产配置仍为同一 DeepSeek 系列 → `CONTROL FLOW ONLY`，`REAL_CROSS_PROVIDER_NOT_VERIFIED` 保持 WARNING；未修改生产配置/secrets
- PRO_REVIEW_REQUIRED：否

## Production Baseline

- 新增只读 `app/core/baseline_report.py`（POST_DEPLOY_BASELINE），从 executions/tool_calls/audit spans/Redis 聚合：requests（chat/knowledge/task/action）、TTL、LLM/RAG latency p50/p95、token、cost、fallback、error、5xx、dlq、approval_mismatch、side_effect_unknown
- 生产窗口（部署后 11:47 UTC → 现在）：**0 请求**（验证流量已清理、无真实用户）→ `REAL_USER_BASELINE_UNAVAILABLE`
- 明确区分：verification traffic（Phase 7 验证流量，已清理）≠ real user traffic（无）
- TTFT/queue latency：无法从现有存储稳定获得 → 保持 None，不伪造

## Checkpoint

- retention 可配置（`CHECKPOINT_RETENTION_DAYS=7`）
- 仅删除 terminated 且 completed_at < now-retention；active/pending/recent 保留（代码+Phase7 实测）
- 幂等（二次 removed=0）、audit `checkpoint_cleanup`、不影响 execution history（不删 executions）
- 结论：PASS，未修改代码

## Alerting

- threshold 全部来自 Settings（可配置）；cooldown 15min 生效（实测第二次 0 新增）
- alert_events 持久化（生产存在真实 `dlq_growth` active 记录）；Prometheus gauge 由 `/metrics` 抓取时刷新（backend 进程）
- alert task 为独立 Celery 任务，失败不影响 execute_workflow（业务隔离）
- 结论：PASS

## Cost

- known rate → numeric（实测 0.000688）；unknown rate → NULL；不使用 0 冒充
- 多次 LLM call 求和；fallback 每次调用独立计价（代码+测试）
- 历史（预部署）cost 列为 legacy 估算/0 → 无法回填，标记 `COST_UNKNOWN`，不猜测价格
- usage API `cost_unknown_executions` 正确

## Security

- 公网仅 80/443；8000/5433/6379 绑定 127.0.0.1
- TLS：Let's Encrypt 有效至 2026-11-16；未授权 API 401
- secrets：未入 git、未修改；Approval/Idempotency 契约未变

## Architecture consistency

- Approval：plan_hash/approval_id/side_effect_proposals（step_id/capability/tool/params_canonical）冻结；mismatch → audit + FAILED + 重新审批（契约测试+生产 ACTION 验证）
- Idempotency：唯一事实源 tool_calls；PENDING/IN_FLIGHT/SUCCESS/FAILED/REJECTED 状态机；SUCCESS 不重执行、FAILED 不自动重试、REJECTED 不执行、IN_FLIGHT fail-closed（生产实测）
- Checkpoint 只决定继续位置，不决定副作用是否发生（代码+测试）

## Tests

- 全量：`527 passed, 20 skipped, 0 failed`
- ruff / black --check / compileall：PASS

## Verdict

- `PRODUCTION READY — WARNINGS REMAIN`
