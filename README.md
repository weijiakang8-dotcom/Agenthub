# AgentHub（对外品牌 synplex）

> 目标定位：**Agent Production Runtime** —— 让企业敢于把真实业务任务交给 Agent：
> 在受控边界内可靠地规划、调用工具、执行副作用、审批、审计、恢复、评测与控制成本。
>
> 当前真实定位：**Agent Orchestration / Workflow Executor MVP（产品化进行中）**。
> 本文档只描述有代码、测试或生产运行证据的能力；证据等级定义见
> [CURRENT_REALITY_BASELINE.md](docs/CURRENT_REALITY_BASELINE.md)。

## 当前真实能力（以证据分级）

### L3 INTEGRATION_VERIFIED（有真实运行与测试证据）

- 认证：注册（邮箱验证码）、登录、刷新、找回密码、JWT、登录/全局限流、安全响应头。
- 多租户：`organization_id` 贯穿业务表；`query_db` 强制注入租户谓词。
- Chat：SSE 流式；Agent：Intent → Planner → LangGraph → 执行 → Verify。
- 可靠性：Approval Freeze（T24，运行时 mismatch → 零副作用 → 审计 → abort）、
  幂等 claim（`tool_calls` 唯一事实源）、IN_FLIGHT/UNKNOWN fail-closed、
  副作用不重试、reconciliation 幂等、checkpoint/resume、DLQ、执行预算。
- 工具（真实生产 Tool Registry，4 个）：

| 工具 | Provider | 副作用 | 租户 | 说明 |
|---|---|---|---|---|
| `search_web` | Tavily（DDG 兜底） | 否 | 否 | 已生产 E2E |
| `query_db` | 本库 PostgreSQL | 否 | 是 | 只读单表 + 安全聚合（COUNT/SUM/AVG/MIN/MAX） |
| `search_knowledge` | 本库 RAG（pgvector） | 否 | 是 | 检索当前租户文档 |
| `send_email` | SMTP（Resend 兜底） | 是（需审批） | 否 | 已生产 E2E（审批后执行） |

- 审计/观测：`audit_logs` + `tool_calls` + span 持久化；OTel→Jaeger、Prometheus 已打通
  （2026-08-21 生产验证：Jaeger 可查到 `agenthub-backend`，Prometheus 有业务指标）。
- RAG：文档 → 分块(800/100) → **Ollama nomic-embed-text 语义向量（768d）** →
  pgvector 余弦检索 → top-k → 上下文注入；生产已重嵌入并验证检索命中。
- 记忆：长期记忆（显式 save/update/delete + 检索），租户隔离。
- 成本：模型价格配置 + 每次调用 usage/cost 记录 + 执行预算。
- 测试：后端 590 passed / 20 skipped（本地真实 DB）；前端 vitest 22 + Playwright E2E 3；
  迁移全新库 0019 通过；Kernel 单测 102。

### L2 PARTIAL / L1 DECLARED

- Kernel 确定性内核：代码与单测真实，但生产 `RUNTIME_MODE` 未启用。
- 双供应商回退（OpenAI）：代码存在，开关默认关闭且密钥未充值 → 未验证。
- RBAC：有 `role` 字段与接口依赖，但缺少细粒度策略证据（实际以 admin 为主）。
- Workflow/DAG：有编辑器与 workflow 映射，执行仍为串行；并行/条件执行未实现。
- 观测面板：Grafana/Jaeger/Prometheus 容器与数据管道已通，dashboard 成熟度未审计。
- MCP：未实现（L0）。Prompt Injection 防线：设计冻结，未实现（L0）。

### 明确的“未实现/不宣称”

- Multi-Agent 目前是**角色提示词模拟**（同一串行图 + 不同 system prompt），
  不是 Agent 间通信/并行/聚合/评审。
- `send_sms / create_ticket / refund_order / ticket_assign / list_unpaid_tickets` 等
  仅存在于 benchmark fixture，**不是生产工具**。
- 自动回滚、自动部署、CI 全绿：当前尚未达成（CI workflow 修复已提交本地，待
  workflow 权限 token 推送后验证）。

## 技术栈

- 后端：Python 3.11 / FastAPI / SQLAlchemy(asyncpg) / LangGraph / Celery / Redis。
- 数据：PostgreSQL 16 + pgvector；Alembic 当前 head `0019`；Embedding：Ollama
  （`nomic-embed-text`，内置 `embedding` 服务）。
- 模型：DeepSeek（OpenAI 兼容端点）；Model Gateway 统一路由/重试/回退/成本。
- 前端：React + Vite + TypeScript + Tailwind + Radix（深色/浅色双主题）。
- 部署：Docker Compose（backend/worker/frontend/postgres/redis/mailhog + 监控栈）。

## 架构

```text
Frontend (React) → API (FastAPI, JWT + 限流)
  → Intent → Planner → LangGraph 执行图
      → [search_preflight 按需联网] → Approval(冻结) → Tool Executor
          → Tool Registry（4 个真实工具）→ Provider（Tavily/PostgreSQL/SMTP）
      → Verify(fail-closed) → Audit/Trace → SSE → Frontend
Reliability：Idempotency claim / IN_FLIGHT fail-closed / Reconciliation / Checkpoint-Resume / DLQ
Observability：audit_logs spans + OTel(collector) → Jaeger / Prometheus / Grafana
```

## 快速开始（本地）

前置：Docker Desktop。

```bash
git clone https://github.com/weijiakang8-dotcom/Agenthub.git
cd Agenthub
cp .env.example .env          # 填入 DEEPSEEK_API_KEY / TAVILY_API_KEY 等
docker compose -f docker/docker-compose.yml up -d postgres redis mailhog embedding
cd backend && ../.venv311/bin/python -m uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

本地默认关闭 OTel（`.env` 中 `OTEL_SDK_DISABLED=true`）；
接入监控栈时设为 `false`，并启动 `docker compose up -d otel-collector jaeger prometheus grafana`。

## 测试

```bash
cd backend
../.venv311/bin/python -m pytest -q                    # 590 passed / 20 skipped（本地实测）
../.venv311/bin/python -m pytest -q tests/migration/test_migration_fresh_db.py
cd frontend
npm run typecheck && npm run test:run && npm run lint && npm run build
npm run test:e2e                                        # 需要本地后端已启动
```

Benchmark（真实模型，需显式开启）：

```bash
cd backend
BENCH_REAL_MODELS=1 python -m tests.benchmark.phase1.run_1a
BENCH_REAL_MODELS=1 PHASE1B_MODE=full python -m tests.benchmark.phase1.run_1b
```

历史报告：`backend/tests/benchmark/reports/`（Phase 0）与
`backend/tests/benchmark/phase1/reports/`（Phase 1A/1B，416 runs）当前在本地生成、未入库。

## 生产部署

- 生产站：https://synplex.xyz（腾讯云 Ubuntu，Docker Compose）。
- 当前真实部署路径：本地 commit → patch/scp → 服务器 `git am` → 重建容器 → 健康/E2E 验证。
- 备份/恢复：`scripts/backup.sh`（pg_dump + gzip，保留 7 份）、`scripts/restore.sh`
  （恢复指定目标库）；已在生产完成 dump→restore 演练（行数对账一致）。
- GitHub Actions：`ci.yml`（修复已就绪，待 workflow 权限 token 推送）、`deploy.yml`
  （CI 成功后自动 SSH 部署）、`staging.yml`。
- 可靠性契约、部署细节、生产状态见
  [docs/contracts](docs/contracts) 与
  [CURRENT_REALITY_FINAL.md](docs/CURRENT_REALITY_FINAL.md)。

## P0 路线（当前）

1. CI 全绿并恢复自动部署（workflow 文件已改，待推送验证）。
2. 观测管道（已完成生产验证：Jaeger/Prometheus 有数据）。
3. 失败闭环（已完成：query_db 安全聚合 + 禁止空输出，生产 E2E 通过）。
4. 工具生态（已完成第 4 个生产工具 `search_knowledge`；继续补齐真实业务工具）。
5. RAG 语义化、Memory 分层、复杂编排、前端产品化、治理/配额/备份恢复。

## License

MIT
