# AgentHub CURRENT REALITY — FINAL（Living Baseline）

> 使命：Agent Production Runtime 产品化交付（自主执行，Evidence over narrative）
> 启动：2026-08-21；由 [CURRENT_REALITY_BASELINE.md](./CURRENT_REALITY_BASELINE.md) 继承并持续更新
> 原则：历史报告仅作起点；一切结论以当前代码、当前测试、当前生产运行证据为准

## 0. 当前真相（每次重大变更后更新）

| 项 | 初始事实（审计 08-21） | 当前状态 | 证据 |
|---|---|---|---|
| 产品定位 | Agent Orchestration / Workflow Executor MVP + 3 tools | 进行中 | — |
| 生产工具 | search_web / query_db / send_email | 进行中 | tool_registry.py |
| 生产工具 | search_web / query_db / search_knowledge / send_email | ✅ 4 个 + GET /api/tools + 前端工具页 | tool_registry.py + 生产验证 |
| CI | 红（backend import path / Playwright 无后端） | 本地修复完成；GitHub 待 workflow token 推送 | pytest.ini + ci.yml（本地） |
| Observability | Jaeger 0 服务 / Prometheus target down | ✅ Jaeger 有 agenthub-backend；Prometheus target up；collector 689 指标 | 生产验证 08-21 |
| query_db 失败闭环 | 失败后空输出 | ✅ 安全聚合 + 禁止空输出；生产 E2E 成功 | 生产 E2E eff7b8ee |
| RAG | hash embedding | ✅ Ollama nomic-embed-text 语义向量（768d）已重嵌入 | 生产检索命中验证 |
| Multi-Agent | 角色提示词模拟 | 待评估/补齐 | graph.py |
| T24 | 实现=契约（显式 mismatch→abort） | 保持不动 | 61 tests passed |
| Benchmark | Phase 0/1A/1B 报告存在（gitignored） | 待入库/生成机制 | reports/ |

## 1. 能力矩阵（LIVE）

（与 CURRENT_REALITY_BASELINE §6 一致，随实现逐项翻转；每项必须带测试/生产证据）

## 2. 自愈日志

| 日期 | 问题 | 根因 | 修复 | 回归 |
|---|---|---|---|---|
| 08-21 | CI backend 全红 | pytest 无 pythonpath 配置 | pytest.ini 增加 pythonpath/testpaths | 待 CI |
| 08-21 | CI Playwright 全红 | E2E 无真实后端 | CI 拆分 e2e job + postgres/redis + uvicorn | 待 CI |
| 08-21 | 生产查询失败空输出 | query_db 拒绝 COUNT + 无兜底 | 安全聚合 + fail-visible | 生产 E2E 通过 |
| 08-21 | OTel 空转/不生效 | .env 未声明字段不被 os.getenv 读取 | Settings.OTEL_SDK_DISABLED 字段 | 单测 + 生产验证 |
| 08-21 | 工具不可发现 | 只有后端注册表 | GET /api/tools + 前端工具页 | Playwright 4/4 |
| 08-21 | README 与现状不符 | 历史营销口径 | 重写为证据版 README | 文档审查 |
| 08-21 | 备份/恢复无证据 | 无脚本/演练 | scripts/backup.sh + restore.sh；生产 drill 通过（70 行对账一致） | 生产演练 |
| 08-21 | RAG 非语义 | 生产 EMBEDDING_PROVIDER=hash | 内置 ollama embedding 服务 + 重嵌入 CLI；4 文档检索命中（score 0.65-0.80） | 生产验证 |
| 08-21 | 租户预算/并发缺失 | 无配额/backpressure | Redis 原子 token/cost 预算 + 并发闸门；/api/quotas + 前端用量卡；生产硬阻断验证（budget=50 被阻止，恢复 0 后正常） | 生产验证 |
| 08-21 | 备份无定时 | 仅手动脚本 | install-backup-cron.sh 已装到生产 crontab（每日 03:00） | crontab -l |
| 08-21 | benchmark 证据未入库 | 报告目录 gitignore | 报告已版本化（Phase 0/1A/1B + evaluation） | git log |
| 08-21 | 跨租户 API 隔离缺回归 | 仅 query_db 单测 | integration test：executions/conversations/tool_calls 跨 org 404/空 | 全量 602 passed |
| 08-21 | Phase 0 harness 未验证可复现 | 依赖专用 DB | 全新 DB 重跑 44 runs / 50.0% 一致，报告已更新 | pytest + report diff |
| 08-21 | 记忆只对聊天生效 | Agent 任务无记忆/历史工具 | user_id ContextVar 透传 + recall_memory/recall_executions；生产直调验证 | 生产验证 |
| 08-21 | 部署脚本缺闭环 | pull --ff-only 在分叉历史失败、nginx DNS 未刷新 | fetch+reset、embedding 服务、frontend restart、回滚目标=上一 origin/main；生产真实 deploy+rollback+redeploy 演练 | DEPLOY_OK / ROLLBACK_OK / health gate |
| 08-21 | 只读工具失败无恢复 | 失败后仅兜底文字 | tool_failure_replan：≤1 次安全 replan（带失败结果重规划），路由单测 + 全量回归 | 602 passed |
| 08-21 | 工具成功但合成空文本 | 用户拿到通用兜底 | 成功兜底附结果预览；无工具步骤空输出透传上一步结果；生产 E2E 返回真实数据 | 生产验证 |
| 08-21 | 失败后无重试入口 | 用户需手动重输任务 | ExecutionDetail「重新发起」→ /chat?draft=原任务；Playwright 6/6 | 生产部署验证 |
| 08-21 | 记忆无生命周期 | 永不过期且无清理 | MEMORY_DEFAULT_TTL_DAYS + delete_expired_memories + 每小时 beat 任务；生产直调验证 | 605 passed |
| 08-21 | 新鲜安装/密钥泄露无回归 | 未校验 env example 与序列化 | env example 加载测试 + compose config 校验 + UserRead/Model 序列化不泄露 + audit 脱敏测试 | 609 passed |
| 08-21 | Trace 页无 span 时间线 | span 按 correlation_id 存储，端点只查 execution_id | spans API（execution_id OR correlation_id）+ 前端 Span 时间线；生产 chat trace 返回 intent/llm/memory/respond | Playwright 6/6 + 生产验证 |
| 08-21 | API Key 无轮换 | 只能增删/启停 | POST /user-api-keys/{id}/rotate + 设置页「轮换」；所有权校验 + 解密断言；Playwright 7/7 | 610 passed |
| 08-21 | SLO 告警无回归 | 阈值/冷却幂等未锁定 | 阈值单测 + mismatch→AlertEvent 落库一次 + 冷却抑制；生产直调 0 新事件、beat 调度确认、历史事件存在 | 612 passed |
| 08-21 | 配额不可管理 | 仅 env 全局只读 | Redis per-org 覆盖 + PUT /api/quotas（admin）+ 用量页编辑；生产 set 123→GET 123→reset 验证 | 614 passed + Playwright 7/7 |

## 3. 已知 P0/P1（见基线 §23）

## 4. 最终闸门

CI 绿 → 生产部署 → 真实 E2E → GitHub=生产 → README=现实 → 才允许 COMPLETE。

## 5. 最终一致性验证（2026-08-21）

- 本地后端全量：592 passed / 20 skipped / 0 failed。
- 本地前端：typecheck / vitest 22 / lint 0 err / build 通过；Playwright E2E 4/4。
- 生产综合 E2E（临时租户，已清理）：
  - 登录 ✅；GET /api/tools 返回 4 个真实工具 ✅；
  - “有多少条执行记录” → query_db COUNT 成功并返回可见结果 ✅（exec a6c53b8a）；
  - “今天上海天气” → search_web 成功、回答带来源 ✅（exec 129b3d56）；
  - “AgentHub 动态整理成邮件” → 搜索预检 → 实时正文提案 → 审批拒绝 → 零发信 ✅（exec 3dbeb5bc）。
- 观测：Jaeger 有 `agenthub-backend`；Prometheus `agenthub_llm_calls_24h` 实时增长。
- 备份/恢复：生产 drill 行数对账一致，临时库已删。
- 遗留 blocker：`.github/workflows/ci.yml` 已修复并本地等价验证，但推送 GitHub 需要
  **workflow scope** 的 token（当前 token 无此权限）。
