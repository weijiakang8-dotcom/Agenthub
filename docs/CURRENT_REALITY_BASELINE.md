# AgentHub CURRENT REALITY BASELINE

> 审计类型：CTO / Principal Engineer / SRE / Agent Runtime Architect 逆向审计
> 审计日期：2026-08-21（Asia/Shanghai）
> 数据来源：仓库代码逐文件追踪 + 本地真实运行测试 + 生产只读检查 + 生产真实 E2E（临时租户，已清理）
> 状态：**只读审计，未修改任何生产代码，未 commit**
> 证据等级：L0 NOT_IMPLEMENTED / L1 DECLARED / L2 PARTIAL / L3 INTEGRATION_VERIFIED / L4 PRODUCTION_VERIFIED

---

## 0. Executive Summary

AgentHub 当前的真实状态是：

**一个“以 LangGraph 串行执行图为内核、以 DeepSeek 为唯一模型族、以 3 个真实工具为全部能力、以审批冻结/幂等/审计/恢复为可靠性层”的 Agent 任务执行 MVP。**

它**不是**完整的产品级 Agent Production Runtime，**不是** Multi-Agent 协作平台，**没有** MCP，工具生态极薄（生产可用工具 = 3 个），RAG 是真链路但生产使用哈希向量（非语义 embedding），监控栈在跑但 trace/metrics 管道断链（Jaeger 0 服务、Prometheus 抓取目标 down）。

亮点（有证据）：聊天 / 知识问答 / 数据库只读查询 / 邮件（SMTP）全链路真实跑通；Approval Freeze（T24）当前实现与契约一致（显式 mismatch → abort → 零副作用）；幂等 claim、IN_FLIGHT fail-closed、reconciliation、checkpoint/resume 有真实实现与集成测试；Phase 1A（60 runs）与 Phase 1B（416 runs）真实模型报告存在（本地未入库）。

硬伤（有证据）：CI 连续多次红（backend pytest、frontend Playwright、benchmark gate 均失败），Deploy workflow 永远 skip；生产 E2E 中“查执行记录数量”任务真实失败（query_db 拒绝 COUNT，模型未恢复，最终输出为空）；R1/R2 任务在 Phase 1B 中 SSR 仅 70.4% / 52.5%（模拟工具环境）；工具注册表只有 3 个工具，`send_sms / create_ticket / refund_order / ticket_assign / list_unpaid_tickets` 只存在于 benchmark fixture。

**一句话结论：可靠性层设计扎实、实现过半；能力层（工具生态）与产品闭环是当前最大瓶颈；监控与 CI/CD 是“看起来有、实际断”的重灾区。**

---

## 1. Evidence Grading

| 等级 | 定义 | 本报告使用条件 |
|---|---|---|
| L0 NOT_IMPLEMENTED | 无可执行实现 | 代码/路由/文档均无 |
| L1 DECLARED | 有接口/类/配置/文档声明 | 无真实运行证据 |
| L2 PARTIAL | 部分链路真实，存在 stub/mock/断链 | 有真实环节但缺口明确 |
| L3 INTEGRATION_VERIFIED | 真实 DB/Redis/Worker/API/Runtime 跑通并有测试证据 | 本会话重跑或生产 E2E |
| L4 PRODUCTION_VERIFIED | 正常+边界+并发+故障+恢复+安全+多租户+观测+成本+部署全验证 | 本项目当前**没有任何功能达到 L4** |

**结论：当前无任何能力达到 L4。**

---

## 2. Repository Map

```
AgentHub/
├── frontend/                  React+Vite+TS+Tailwind；真实 UI；typecheck/test/build 通过
│   ├── src/pages/Chat.tsx     SSE 聊天/审批；真实调用 /api/conversations/{id}/stream
│   ├── src/hooks/useExecutionWebSocket.ts  WebSocket 事件订阅（真实）
│   └── e2e/app.spec.ts        Playwright E2E 存在；CI 中失败，本地未验证
├── backend/app/
│   ├── api/                   FastAPI 路由：auth/conversations/executions/tool_calls/...
│   ├── engine/                核心：intent → planner → graph → tool_executor → approval
│   ├── kernel/                确定性内核（Plan/State/Effect/Goal）；生产未启用
│   ├── adapters/              Legacy 能力映射 / RealEffectExecutor / kernel bridge
│   ├── core/                  model_gateway / security / telemetry / rate_limit / billing
│   ├── rag/                   chunking → embedder → vector_store → retrieval（真实链路）
│   ├── memory/                长期记忆（hash embedding + pgvector 余弦）
│   ├── models/                29 张表的 SQLAlchemy 模型
│   └── alembic/versions/      0019 迁移链；全新库 0001→0019 已在本审计重跑通过
├── backend/tests/
│   ├── unit + contracts       大量契约测试
│   ├── integration            可靠性/幂等/T24/审批超时等真实 DB 集成测试
│   ├── kernel                 Kernel 单测 102 通过
│   ├── migration              全新库迁移测试（本审计重跑 2 passed）
│   └── benchmark/             Phase 0/1A/1B harness + 报告（报告目录被 gitignore）
├── docker/                    compose：backend/worker/frontend/postgres/redis/mailhog + 监控栈
├── docs/                      契约、架构、部署报告、resume.md（营销口径）
└── .github/workflows/         CI / Deploy / staging（CI 红，Deploy 永远 skip）
```

各目录成熟度：engine/core/rag/models 进入生产执行路径；kernel 未进入生产路径（RUNTIME_MODE 默认 legacy）；benchmark 报告本地存在但未入库；CI/CD 配置存在但未绿。

---

## 3. Real Runtime Data Flow

实际链路（代码追踪 + 生产 E2E 验证）：

```
Frontend (Chat.tsx)
  → POST /api/conversations/{id}/stream (conversations.py)
  → Auth: JWT (Bearer) + rate_limit middleware
  → Execution 行创建（status=pending）
  → IntentRouter.classify (intent.py, DeepSeek via ModelGateway)
  → runtime=AGENT ? execute_workflow_task.delay(Celery→Redis) : 直接流式
  → Agent: run_execution → LangGraph (graph.py)
      prepare → [search_preflight（needs_web_search=true 时）] → plan
      → Planner.plan (planner.py) → validate_plan
      → side_effect 存在 → _propose_side_effect_calls（冻结提案）
      → waiting_for_approval (LangGraph interrupt) → DB waiting_for_approval
      → resume → capability node → tool_calls 绑定
      → side_effect: _execute_frozen_side_effect（T24 比对）→ tool_executor.execute_tool
      → create_tool_call(pending) → atomic claim(IN_FLIGHT) → provider 调用 ≤1
      → result → _finish_tool_call(SUCCESS/FAILED/UNKNOWN)
  → AuditLog + ToolCall + spans(audit_logs) + SSE 事件 → Frontend
```

理想产品 Data Flow 与真实 Data Flow 的差异：

| 环节 | 理想 | 真实 |
|---|---|---|
| 工具选择 | 丰富工具生态 | 仅 search_web / query_db / send_email |
| 并行执行 | 支持 DAG 并行 | 串行（contract 02 明确 V1 串行） |
| Multi-Agent | Agent 间通信/聚合/评审 | 角色 system prompt 模拟 |
| MCP | 标准协议接入 | 不存在（L0） |
| 观测 | OTel→Jaeger/Grafana | 容器在跑，Jaeger 0 服务、Prometheus target down；DB spans 在工作 |
| 失败恢复 | 模型能从工具失败中恢复 | 真实 E2E：query_db 失败后最终输出为空 |

---

## 4. Architecture

控制面（真实）：意图分类、规划、审批中断/恢复、验证、审计。
数据面（真实但很薄）：3 个工具 + PostgreSQL/Redis/SMTP/Tavily。
可靠性面（真实）：Approval Freeze、Idempotency claim、IN_FLIGHT fail-closed、reconciliation、checkpoint/resume、budget。
观测面（部分断）：audit_logs spans 可用；OTel/Jaeger/Prometheus 链路断。
评估面（真实但未入库）：Phase 0/1A/1B harness 与报告存在（gitignored）；Oracle 为代码判定 + LLM judge 混合。

---

## 5. Database

生产：PostgreSQL 16 + pgvector，alembic head=0019（本审计重跑全新库 upgrade/downgrade/upgrade 通过）。

核心表（29 张）：

| 表 | 作用 | 关键点 | 真实参与 |
|---|---|---|---|
| organizations / users | 租户/用户 | email 唯一索引；租户隔离以 organization_id 贯穿 | 是 |
| executions | 执行状态机 | pending/running/waiting_for_approval/completed/failed/rolled_back | 是（66 行） |
| tool_calls | 工具审计 + 幂等 | 唯一索引 (execution_id, idempotency_key) WHERE key IS NOT NULL | 是（24 行） |
| audit_logs | 审计 + span 存储 | action/resource_id 索引；span:* 139 条 | 是（713 行） |
| conversations | 对话 | messages 为 JSON 数组（无独立 messages 表） | 是（30 行） |
| checkpoints / checkpoint_writes / checkpoint_blobs | LangGraph 断点 | 395 行，resume 真实依赖 | 是 |
| document_chunks | RAG 向量 | pgvector 余弦；生产 4 条（1 文档） | 是（弱） |
| model_configs | 模型路由/价格 | deepseek-chat 2 条（org + 全局） | 是 |
| user_memories | 长期记忆 | hash embedding + importance 加权 | 是（0 行） |
| alert_rules / alert_events | 告警 | 表在，规则 0 条 | 部分 |
| eval_runs / eval_datasets | 评测 | 表在，0 行（benchmark 报告未入库） | 否 |
| approvals | 不存在 | 审批载荷存在 executions.checkpoint_data / plan_meta | — |

索引/约束：主键齐全；tool_calls 幂等唯一约束存在；executions/organization_id、tool_calls/execution_id、audit_logs/action 等索引存在。未发现针对 audit 去重、checkpoint 清理的独立唯一约束（由代码 CAS/审计存在性保证）。

race condition 风险点：审批 resume 用 CAS 状态更新（真实）；tool claim 用原子 UPDATE（真实）；同一 execution 的并发 resume 被状态机挡住（集成测试覆盖）。

迁移问题：C-2（0008/0019 重复列）已被修复并重跑验证；报告目录 gitignore 导致基准证据不随仓库走。

---

## 6. Capability Matrix（60 项抽查）

| 能力 | 状态 | 证据 | 真实链路 | 测试 | 缺口 |
|---|---|---|---|---|---|
| Authentication | L3 | auth.py JWT/PBKDF2/email code/rate limit | 是 | 有 | 无 MFA/SSO |
| Authorization | L2 | deps + JWT org claim | 是 | 部分 | 权限粒度粗（role 基本仅 admin） |
| RBAC | L1/L2 | require_permission 存在 | 部分 | 少 | 无细粒度策略 |
| Multi-tenancy | L3 | query_db 强制 org 谓词 + 各表 organization_id | 是 | 有 | 部分 API 需逐一核对 |
| Conversation | L3 | conversations JSON + SSE | 是 | 有 | 无独立 messages 表 |
| Multi-turn context | L3 | context_messages 截断注入 | 是 | 有 | 上限 20 条/12000 字符 |
| Intent detection | L3 | intent.py 真实模型分类 | 是 | 有 | 单模型判断，无确定性兜底 |
| Planner | L3 | planner.py 真实模型规划 + 校验 | 是 | 有 | 上限 6 步 |
| Agent | L3 | LangGraph 执行图 | 是 | 有 | 串行 |
| Multi-Agent collaboration | L1 | 角色 system prompt 模拟 | 否 | 无 | 无 Agent 间通信/并行/评审 |
| Workflow / DAG | L2 | workflows 表 + dag 映射 | 部分 | 部分 | 无并行/条件执行 |
| Parallel execution | L1 | 字段保留 | 否 | 无 | 未实现 |
| Tool calling | L3 | DeepSeek function calling + bound tools | 是 | 有 | 3 个工具 |
| Tool registry | L3 | tool_registry.py | 是 | 有 | 仅 3 个 |
| Tool permissions | L1 | BLOCKED_TOOLS 空 | 否 | 少 | 无 per-tool RBAC |
| Tool credentials | L2 | user_api_keys 加密 | 部分 | 少 | 生产 0 条 |
| Approval | L3 | 计划级审批 + interrupt | 是 | 有 | 无审批 SLA/超时 UX |
| Approval Freeze (T24) | L3 | 显式 mismatch → abort → 零副作用 | 是 | 61 个契约/集成测试通过 | 见 §11 |
| Canonical Params | L3 | canonical.py 全局唯一实现 | 是 | 有 | 仅 3 工具 schema |
| Idempotency | L3 | key=sha256(exec+tool+params)+原子 claim | 是 | 有 | — |
| Atomic Claim | L3 | PENDING→IN_FLIGHT 原子 UPDATE | 是 | 有 | — |
| Retry | L3 | 只读重试；副作用 ≤1 次 | 是 | C-1 测试 | — |
| UNKNOWN | L3 | IN_FLIGHT fail-closed | 是 | 有 | 人工裁决界面弱 |
| Reconciliation | L3 | 3 个 reconcile + CAS + audit | 是 | C-4 测试 | legacy 数据噪音（263 条 manual_required） |
| DLQ | L2 | Redis dead_letter_queue + dlq_discard 审计 | 部分 | 少 | 无 UI/重放 |
| Resume / Recovery | L3 | LangGraph checkpoints + resume API | 是 | 有 | 无自动故障注入演练 |
| RAG | L2（生产）/L3（链路） | chunk→embed→pgvector→retrieve 真实 | 是 | phase3 8 passed | 生产 hash embedding，1 文档 |
| Vector store | L3 | pgvector 余弦 | 是 | 有 | 无 HNSW 索引证据 |
| Chunking | L3 | 固定 800/100 字符滑窗 | 是 | 有 | 无语义分段 |
| Embedding | L2 | 生产 provider=hash（MD5 n-gram） | 是 | 有 | 非语义向量 |
| Retrieval | L3 | top-k + tenant + score 阈值 | 是 | 有 | 无 rerank |
| MCP | L0 | 无代码/无依赖 | 否 | 无 | 完全缺失 |
| Model routing | L3 | model_configs 按 cost/priority | 是 | 有 | 单模型族 |
| Model fallback | L2/L3 | gateway 多客户端循环；OPENAI fallback 关闭 | 是 | 有 | 第二供应商未启用 |
| Cost accounting | L2 | rate×tokens→cost，存 checkpoint_data | 是 | 少 | 无账单/用量报表 |
| Budget | L3 | steps/replans/verifies/wallclock/tokens/cost | 是 | 有 | 无跨请求预算 |
| Rate limit | L3 | IP 300/min + login 5/300s | 是 | 少 | 无租户级配额 |
| Timeout | L3 | LLM 120s / tool 15-30s | 是 | 有 | — |
| Backpressure | L1 | 无队列水位/限流反馈 | 否 | 无 | 缺失 |
| Audit | L3 | middleware + engine 双写 audit_logs | 是 | 有 | 敏感字段脱敏待核 |
| Trace | L2/L3 | audit_logs span:*（139 条） | 是 | phase3 | OTel 断链 |
| OpenTelemetry | L2 | setup_telemetry 真实 | 部分 | 少 | Jaeger 0 服务 |
| Prometheus | L2 | /metrics 有 11 个自定义指标 | 部分 | 少 | 抓取 target down |
| Grafana | L1 | 容器在跑 | 否 | 无 | 无数据源证据 |
| Jaeger | L1 | 容器在跑 | 否 | 无 | 0 服务 |
| Evaluation | L3（harness） | Phase 0/1A/1B 报告存在 | 是 | 有 | 报告 gitignore |
| Golden Set | L3 | golden + oracle1/1b | 是 | 有 | 未入库版本化 |
| Regression Gate | L2 | CI benchmark-gate job | 部分 | CI 红 | 未生效 |
| Frontend | L3 | 22 vitest + build 通过 | 是 | 有 | Playwright CI 红 |
| SSE/WebSocket | L3 | SSE 流式 + WS hook | 是 | 少 | — |
| Admin | L2 | API + 前端设置页 | 部分 | 少 | 无独立 admin 台 |
| Webhook | L2 | notification/alerting 代码 | 部分 | 少 | 生产未配置 URL |
| Deployment | L2 | docker compose + 手动 SSH/patch | 是 | 少 | 无自动部署 |
| Docker | L3 | 镜像可构建、生产容器在跑 | 是 | CI docker job 绿 | — |
| CI/CD | L1/L2 | workflow 存在 | 否 | CI 红 | Deploy 永远 skip |
| Migration | L3 | 全新库重跑 2 passed | 是 | 有 | 报告证据未入库 |
| Testing | L3 | 后端 586+/集成 198/kernel 102/前端 22 | 是 | 有 | 见 §18 |
| Security | L2/L3 | JWT/加密/header/rate limit | 部分 | 有 | 无安全专项/渗透 |

---

## 7. Tool Inventory

**真实注册表只有 3 个工具（tool_registry.py 唯一事实源）：**

| Tool | 代码 | Agent 可选 | 真实执行 | Provider | Mock | Tenant | Idempotency | E2E |
|---|---|---|---|---|---|---|---|---|
| search_web | ✅ | ✅ | ✅ | Tavily（DDG 兜底） | 否 | 否（外部公共信息） | 是（execute_tool 通用） | ✅ 生产 E2E |
| query_db | ✅ | ✅ | ✅ | 本库 PostgreSQL（只读白名单） | 否 | ✅ 强制 org 谓词 | 是 | ⚠️ 生产 E2E 失败（COUNT 被拒，输出空） |
| send_email | ✅ | ✅ | ✅（审批后） | SMTP（Resend 兜底） | 否 | 否 | 是（claim + 内容 hash） | ✅ 生产 E2E（提案→拒绝，未外发） |

| 工具 | 状态 |
|---|---|
| send_sms / create_ticket / refund_order / ticket_assign / list_unpaid_tickets / query_crm / query_tickets / query_invoices / search_kb / get_hr_policy / crm_update_account / ticket_update_status / invoice_draft / internal_api_patch / memo_create_draft / internal_api_post / hr_approval_submit / invoice_finalize / refund_request | **仅存在于 benchmark harness（fixtures1b.py），非生产工具** |

分类：A 真正生产可用 = search_web / send_email / query_db（query_db 有真实失败路径，需模型恢复能力）；其余全部为 F 不可用 / 仅测试夹具。

**结论：Tool Ecosystem 就是当前产品瓶颈，3 个工具不可能支撑 “Agent Production Runtime” 的客户叙事。**

---

## 8. Agent / Multi-Agent Reality

- Planner / Intent / Memory / Tool Selection / Tool Execution / State / Verify：真实存在（L3）。
- Reflection / Reviewer / Writer：无独立结构。
- Multi-Agent：**当前是角色提示词模拟**（answer/research/web_search/knowledge/query_db/analysis/execute/send_email 是不同 system prompt + 同一串行图），不是 Agent 间消息传递、并行执行、结果聚合、评审、冲突消解。
- docs/resume.md 自称“多智能体协作平台”——与实现不符，属于营销口径。

---

## 9. RAG Reality

链路真实存在：Document → split_text(800/100) → embed_text → pgvector(DocumentChunk.embedding) → cosine 检索 → top-k → 上下文注入 → LLM。

但：
- 生产 `EMBEDDING_PROVIDER=hash`：MD5 n-gram 词袋向量，**不是语义 embedding**（无 ollama/sentence-transformers）。
- 生产数据：documents=1、document_chunks=4。
- 有 tenant 过滤、MIN_SIMILARITY=0.3、top-k=5、无 rerank、无 citation 强制（仅提示词要求）。
- 有真实检索集成测试（phase3 real db 8 passed）。

结论：**“有 RAG”是真的，但它是“哈希向量 + pgvector”的最小 RAG；不是语义检索级 RAG。**

---

## 10. Reliability Layer

本审计重跑（本地真实 DB）：

- C-1 tool retry：✅（集成测试通过）
- C-2 migration：✅（全新库 0001→0019 + downgrade 0010 + upgrade head 重跑通过）
- C-4 reconciliation 幂等：✅
- T24 Approval Freeze：✅（61 个契约/集成测试通过）
- Idempotency / Atomic Claim / UNKNOWN / Approval Timeout / Verify fail-closed：✅（对应集成测试通过）
- Kernel 单测：102 passed

Phase 0 报告（本地，gitignored）：44 runs，safe_pass_rate=50%，纯确定性 stub（不调真实 LLM），用于验证 harness 与 Reliability Layer 本身。

---

## 11. Approval Freeze Conflict（Contract vs Implementation vs Benchmark）

用户提示词中的指控：“冻结 A → 运行时 B 被忽略 → 继续执行 A”。

**审计结论：当前代码中该指控不成立。**

证据：
1. Contract（docs/architecture/APPROVAL_AND_IDEMPOTENCY.md）：tool/params 不一致 → approval_mismatch → audit → FAILED → 重新审批。
2. 实现（backend/app/engine/graph.py `_execute_frozen_side_effect`）：先取冻结 proposal，再比对 runtime tool/params（`proposal_mismatch_reason`），任何不一致 → audit approval_mismatch → 返回 side_effect_failure，**provider 调用 0 次**。
3. 集成测试（test_t24_approval_runtime_mismatch.py，TEST-1..6）：A+A → provider=1；A+B → provider=0 + mismatch audit；参数漂移 → provider=0；重入 2 次仍 0 副作用；重新审批 B 后才执行 B。本审计重跑全部通过。
4. Phase 0 报告（C-3）曾记录旧语义“按构造冻结、篡改不生效”——该观察**早于 T24 裁决**，与当前代码不一致，属过期证据。
5. Phase 1B T24：ON 臂 SSR=0%（业务未完成）但 SOR=100%、GCR=1.0 → 所有篡改都被拦截，零不安全副作用。这正是契约期望的 “SAFE_CONTAINED”。

**结论：Contract = Implementation（当前一致）；P0 CONTRACT 冲突不存在。真正的问题是：Phase 0 证据基线过期 + Phase 1B ON 臂业务完成率为 0（安全优先设计的业务代价），以及“mismatch 后重新审批”的 UX 需要产品化。**

---

## 12. Phase 0 Evidence

- 44 runs，22 safe / 22 unsafe（50% safety pass rate）。
- 使用确定性 stub 模型（不调用真实 LLM），验证 Reliability Layer 与 Oracle/Harness 本身。
- 记录 C-1（RESOLVED-VERIFIED）、C-2（当时 INFRA-DEFECT，现已修复并重跑验证）、C-3（旧 Approval Freeze 语义，已过期）、C-4（RESOLVED-VERIFIED）。
- 报告在 backend/tests/benchmark/reports/phase0_report.json（gitignored）。

---

## 13. Phase 1A Evidence

- 60 runs（5 tasks × 3 trials × 4 arms），真实 DeepSeek（flash/pro），模拟副作用工具。
- 四臂 SSR 全部 100%，SUE/100=0 → **ceiling effect，无法区分模型/可靠性层能力**。
- 成本：A 0.0025 / B 0.0027 / C 0.0060 / D 0.0082 CNY per SS。
- 报告存在：phase1a_report.json + PHASE1A_REPORT.md（gitignored）。

Phase 1A **没证明**“小模型 + Reliability ≈ 大模型裸奔”——它只证明“简单任务四臂都能安全完成”。

---

## 14. Phase 1B Evidence（416 runs，真实存在）

报告：backend/tests/benchmark/phase1/reports/phase1b_report.json（generated 2026-08-20T07:31Z；gitignored）。

| Arm | SSR | SOR | USER | GCR | Cost/SS CNY |
|---|---|---|---|---|---|
| A flash OFF | 70.2% | 70.2% | 12.5% | N/A | 0.0061 |
| B flash ON | 59.6% | 93.3% | 6.7% | 0.8333 | 0.0075 |
| C pro OFF | 70.2% | 70.2% | 9.6% | N/A | 0.0168 |
| D pro ON | 61.5% | 91.3% | 5.8% | 0.8378 | 0.0274 |

关键事实：
- Reliability ON 显著提升 Safe Outcome Rate（+21~23pp）并降低不安全副作用率（-3.8~-5.8pp），拦截率 83~84%。
- 但 SSR 反而下降（ON 臂 59.6%/61.5% vs OFF 70.2%）——因为拒绝/拦截也算业务未完成；这是安全优先设计的业务代价。
- R1=70.4%、R2=52.5%、Hard=38.1% SSR → 模型决策错误率在 Hard 达 58.5%。
- 全部结论 EXPLORATORY：n=5/30 tasks、无 seed、单 provider 家族、模拟副作用。

**Phase 1B 提供了“护栏有效”的证据（GCR 83-84%），但没有提供“小模型 + Layer ≈ 大模型”的证据（该假设在本数据集上不成立：小+ON 与大+OFF SSR 相当甚至更低）。**

---

## 15. Product Gap

目标：Agent Production Runtime。

| 客户要求 | 现状 | 结论 |
|---|---|---|
| Reliable side effects | 审批冻结/幂等/UNKNOWN/恢复齐全，真实 SMTP 已跑通 | 做到 ~70%，但工具只有 1 个副作用工具 |
| Execution boundary | 能力目录静态声明 + plan 校验 + 租户过滤 | 做到 |
| Auditability | audit_logs + tool_calls + spans | 做到（L3） |
| Verifiability | Verify fail-closed（ADR-005） | 做到（L3） |
| Cost control | 模型价格 + 预算 | 部分（无账单/配额） |

差距：没有客户能用的工具生态、没有多租户密钥托管、没有并行、没有 MCP、没有可观测的端到端指标（监控断链）、CI 红、无自动部署/回滚、无备份恢复演练。

---

## 16. Production Gap（CURRENT / REQUIRED / GAP / PRIORITY / COMPLEXITY）

| 项 | CURRENT | REQUIRED | GAP | P | C |
|---|---|---|---|---|---|
| Tool ecosystem | 3 tools | ≥10 真实业务工具 | 极大 | P0 | M |
| CI green | 红（backend/frontend/gate） | 全绿 | 大 | P0 | S |
| Deploy automation | skip | 自动部署+回滚 | 大 | P0 | M |
| Observability pipeline | Jaeger 0 / Prom down | 真实 trace+metrics | 大 | P0 | S |
| RAG semantic quality | hash embedding | 语义 embedding | 中 | P1 | S |
| Multi-tenant credentials | 0 条用户 key | 租户密钥托管 | 中 | P1 | M |
| Backpressure/quotas | 无 | 队列水位+租户配额 | 中 | P1 | M |
| Backup/restore | 无证据 | 自动备份+演练 | 大 | P0/P1 | M |
| Security suite | 基础 | 渗透/密钥轮换/审计脱敏 | 中 | P1 | M |
| E2E query_db recovery | 失败后空输出 | 失败说明+恢复 | 中 | P0 | S |
| Load/chaos | 无 | 基准+故障注入 | 大 | P2 | L |
| SLO/SLA/retention | 无 | 定义+存储策略 | 中 | P2 | M |
| Frontend admin | 基础设置 | 运维控制台 | 中 | P2 | M |

---

## 17. Execution Bottleneck

生产真实数据（小样本）：
- executions：49 completed / 19 failed（≈28% 失败率）。
- tool_calls：query_db failed=9、search_web failed=7（Tavily 接入前）、query_db success=5、search_web success=2、send_email pending=1 / failed=1。
- audit：tool_call_manual_required=263（legacy 无 key PENDING 噪音）、dlq_discard=11、execution_reconciled=3。

本审计真实 E2E 失败案例：**“帮我查一下数据库里有多少条执行记录” → query_db 生成 `SELECT count(status) FROM executions` → 被白名单拒绝（Unsupported SQL construct）→ 模型未恢复 → final_output 为空。**

结论：
1. query_db 语法限制（COUNT/函数括号/ORDER BY 等）与模型习惯冲突，失败后 Agent 不会自我修正 → 用户拿到空回答。
2. 缺少 execution failure taxonomy 的自动统计（当前只能手工 SQL 汇总）。
3. Tool Box 确实几乎为空：3 个工具、其中 2 个有真实失败案例。

---

## 18. Test Matrix

| 层 | 结果 | 说明 |
|---|---|---|
| Backend unit+contracts | 586 passed / 10 skipped / 7 env-failed（完整跑一次） | 7 个失败为外部测试服务/遗留脏数据环境问题；单独重跑通过或正确 skip |
| Reliability contracts + integration | 61 passed（重跑） | C-1/C-4/T24/phase6a/verify/approval-timeout |
| Integration（全部） | 198 passed / 18 skipped（重跑） | skip 为外部服务/obs 开关 |
| Phase3 real DB | 8 passed（重跑，obs 开启） | RAG/观测持久化 |
| Kernel unit | 102 passed | |
| Migration fresh DB | 2 passed（重跑） | 0019 链 |
| Frontend | typecheck ✅ / vitest 22 ✅ / lint 0 err（4 warn）/ build ✅ | |
| Playwright E2E | 存在；CI 中失败 | 本地未跑通验证 |
| Benchmark | Phase0 44 / Phase1A 60 / Phase1B 416 报告存在（gitignored） | 未重新执行（避免消耗模型 API 与覆盖证据） |
| Load / Chaos / Security / Recovery 专项 | 无 / 无 / 部分 / 部分 | |

**没有测试覆盖：MCP（不存在）、并行、多 Agent、Backpressure、备份恢复、租户配额、安全渗透。**

---

## 19. Security

真实：JWT（HS256）、PBKDF2 密码哈希、登录/全局 rate limit、CORS 白名单、安全头、用户 API key 加密存储、query_db 租户强制谓词、计划级审批。
缺口：无 MFA/SSO、无细粒度 RBAC、Prompt Injection 防线“冻结待评审”未实现（按 Frozen Core 规定禁止擅自实现）、无密钥轮换、无渗透测试证据、ADMIN_API_KEY 存在但 admin 接口面未审计。

---

## 20. Observability

真实：audit_logs span:*（139 条：llm 62 / intent 22 / respond 22 / step 12 / tool 10 / memory 8 / plan 2 / verify 1）；/metrics 有 11 个自定义指标。
断链：OTel collector 在跑但 Jaeger 返回 0 服务；Prometheus 的 agenthub-backend target=down（host.docker.internal 不可达），collector 的 prometheus 端点 0 个 agenthub_ 指标；`.env` 中 OTEL_SDK_DISABLED=true 与未关闭的 SDK 初始化并存。

---

## 21. Cost

- model_configs：deepseek-chat ×2（org/global），cost_per_1k_tokens=0.001/0.002。
- ModelGateway 按 tokens×rate 计算并写入 llm_usage/checkpoint_data。
- benchmark cost 以 CNY 计量（cost_usd=null）。
- 无账单页面、无租户配额、无预算告警闭环。

---

## 22. Deployment

- 生产：腾讯云 Ubuntu，docker compose 栈（backend/worker/frontend/postgres/redis/mailhog + 监控栈），nginx 在 frontend 容器。
- 本次部署方式：本地 commit → patch/scp → server `git am` → compose 重建（**未走 CI/CD**）。
- GitHub main 已同步到 37185fd；服务器当前为等价内容（50ebde66，patch 应用产生不同 hash）。
- CI：最近 5+ 次 main 均红（backend pytest、frontend Playwright、benchmark gate）；Deploy workflow 因 CI 不绿永远 skip。
- 回滚：无自动化；备份/恢复：无证据。

---

## 23. P0/P1/P2/P3 Roadmap

P0（一个月内）：
1. 修 CI 到全绿（后端环境测试可重复、Playwright E2E 可跑）→ 恢复 Deploy 自动部署。
2. 修 observability 管道（Jaeger 有 trace、Prometheus target up），或明确下线 OTel 只留 audit spans。
3. query_db 失败恢复：工具失败后 LLM 必须输出说明（禁止空 final_output）；必要时放宽 COUNT 等只读聚合（需用户裁决安全边界）。
4. 明确工具生态策略：接入 3-5 个真实业务工具（CRM/工单/财务类）并完成生产级审批+幂等。
5. 把 benchmark 报告与 Oracle 基线入库版本化（解除 gitignore），避免证据丢失。

P1：语义 RAG（真实 embedding）、租户密钥托管、租户配额/backpressure、备份恢复演练、审批 UX（mismatch 重批流程）、安全渗透一轮。
P2：MCP 接入评估、并行执行、Multi-Agent 结构、SLO/SLA/告警闭环、负载与混沌测试。
P3：合规就绪（数据留存/隐私）、管理员控制台、成本报表。

---

## 24. Final CTO Verdict

**AgentHub 是一个“可靠性层设计优秀、真实执行链路过半、能力层极薄、工程闭环断裂”的 Agent Runtime MVP。**

- 可靠性契约（C-1/C-2/C-4/T24/UNKNOWN/Verify）是真实的，且当前 T24 实现与契约一致——不是“演示代码”。
- 产品叙事（多智能体/MCP/Production Runtime）远超前于实现；当前真实定位是 **Agent Orchestration / Workflow Executor MVP + 3-tool ecosystem**。
- 最严重的不是“代码是假的”，而是“工程闭环是断的”：CI 红、Deploy skip、监控断链、benchmark 证据未入库、真实任务失败后给用户空输出。

---

## 25. Unknown / Unverified

- Kernel runtime 生产路径：RUNTIME_MODE 未启用；kernel 真实效果测试依赖外部 mock 服务（staging 8081），当前环境被 skip。
- Playwright E2E 本地未跑通；CI 失败根因未拉取完整日志。
- 备份/恢复、负载/混沌、安全渗透：无任何证据。
- Phase 1B 报告的模型调用时间与代码版本对应关系：报告 gitignored，无法从 git 追溯生成时刻的代码快照。
- Grafana 是否有可用 dashboard/数据源：未验证（容器在跑）。
- OpenAI 第二供应商回退：默认关闭且密钥未充值，无法验证真实回退成功路径。
- production .env 中 OTEL_SDK_DISABLED=true 的确切生效路径（SDK 初始化未显式读取该变量）：未做运行时抓包验证，仅凭 Jaeger/Prometheus 空数据推断。

---

*本基线由只读审计生成；发现的问题均未修复。下一步需由用户/Pro 裁决的事项见最终汇报。*
