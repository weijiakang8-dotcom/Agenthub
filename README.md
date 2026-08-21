# AgentHub（对外品牌 synplex）

> **模型越多，越不会用。AgentHub 是你的动态调度中枢**：接上你所有的模型 API，发布任务，
> 它分析复杂度、为每一步自动选最便宜的模型，便宜模型失败自动升级强模型——用最少的 token
> 完成最复杂的任务；执行全程可观看、可审计、可澄清、可回滚，最后给你一张省钱账单。
> 一句话：**ChatGPT 是聊天，AgentHub 是调度。**

生产站：https://synplex.xyz

## 当前真实能力

> 本文档只描述有代码、测试或生产运行证据的能力；证据等级见
> [CURRENT_REALITY_BASELINE.md](docs/CURRENT_REALITY_BASELINE.md)。

### 动态调度中枢（核心，全部闭环）

- **复杂度评分器**：规则信号 + 历史统计 + 可选 LLM 法官三层混合，任务级/步骤级两级评分，因子可解释；
- **路由策略引擎**：三档策略（省钱/均衡/质量）× 阈值 × 模型绩效修正 → 每步"便宜 or 强"决策；
  **升级阶梯**（每步 ≤1 次、每任务 ≤4 次）；每次决策落 `routing_decisions` 审计表；
- **澄清中断**：语义歧义/参数缺失 → 暂停弹选项 → 你选择 → 断点继续（全程留痕）；超限显式失败、零副作用；
- **Skill 系统**：8 个预设任务包 + 自动匹配 + **自成长**（同类任务 ≥3 次且成功率达标 → 自动打包候选，你采纳才生效）；
- **多 Agent 体系**：自带 6 Agent（调度/规划/执行/验证/澄清/记账）+ 版本化自更新（候选 → 门禁 → 激活/回滚）；
- **省钱账单**：实际成本 vs "全程最强模型"基线 + 逐模型 token 看板（生产冒烟实测省 90%：¥0.0018 vs ¥0.0182）；
- **MCP 插件**：`POST /api/mcp` 把调度中心暴露为 MCP 工具集，Claude/Codex 等外部助手可直接调用。

### L3 INTEGRATION_VERIFIED（真实运行与测试证据）

- 认证：注册（邮箱验证码）、登录、刷新、找回密码、JWT、登录/全局限流、安全响应头；
- 多租户：`organization_id` 贯穿业务表；`query_db` 强制注入租户谓词；
- Chat：SSE 流式；Agent：Intent → 复杂度评分 → Planner → LangGraph 执行 → Verify；
- 可靠性：Approval Freeze（T24，运行时 mismatch → 零副作用 → 审计 → abort）、幂等 claim
  （副作用恰一次）、IN_FLIGHT/UNKNOWN fail-closed、reconciliation、checkpoint/resume、DLQ、预算闸门；
- 审计/观测：`audit_logs` + `tool_calls` + span 持久化；OTel → Jaeger / Prometheus 生产有数据；
- RAG：文档 → 分块 → Ollama nomic-embed-text（768d）→ pgvector 余弦检索 → top-k；
- 记忆：长期记忆（显式 save/update/delete + 检索），租户隔离；
- 成本：模型价格配置 + 每次调用 usage/cost 记录 + 租户预算（Redis 原子闸门）。

### L2 PARTIAL / L1 DECLARED

- Kernel 确定性内核：代码与单测真实，生产 `RUNTIME_MODE` 未启用；
- 双供应商回退（OpenAI）：代码存在，开关默认关闭且密钥未充值 → 未验证；
- RBAC：admin/member/viewer + 路由依赖，细粒度策略证据有限；
- Workflow/DAG：编辑器与映射存在，执行仍以串行为主。

### 明确的"未实现/不宣称"

- Multi-Agent 是**角色 + 调度分工**（同一执行图内各 Agent 各司其职），不是跨进程 Agent 消息总线；
- `send_sms / create_ticket / refund_order` 等仅存在于 benchmark fixture，不是生产工具；
- Prompt Injection 防线：设计冻结待评审，未实现。

## 快速开始（本地）

前置：Docker Desktop。

```bash
git clone https://github.com/weijiakang8-dotcom/Agenthub.git
cd Agenthub
cp .env.example .env          # 填入 OPENAI_API_KEY（DeepSeek 兼容）/ TAVILY_API_KEY 等
docker compose -f docker/docker-compose.yml up -d postgres redis mailhog embedding
cd backend && ../.venv311/bin/python -m alembic upgrade head
../.venv311/bin/python -m uvicorn app.main:app --port 8000   # 后端
# 另开 worker（macOS 用 --pool=solo 避免 fork 崩溃；Linux 无需）：
../.venv311/bin/python -m celery -A app.engine.tasks.celery_app worker --loglevel=warning --pool=solo
cd ../frontend && npm install && npm run dev               # 前端 http://localhost:5173
```

登录后：左侧「调度中心」先分析任务 →「新建对话」发布 → 执行全程直播 →「省钱账单」看账。

## 技术栈

- 后端：Python 3.11 / FastAPI / SQLAlchemy(asyncpg) / LangGraph / Celery / Redis；
- 数据：PostgreSQL 16 + pgvector；Alembic head `0020`；Embedding：Ollama `nomic-embed-text`；
- 模型：DeepSeek（OpenAI 兼容端点）；Model Gateway 统一路由/重试/回退/成本；
- 前端：React + Vite + TypeScript + Tailwind + Radix（深色/浅色双主题）；
- 部署：Docker Compose（backend/worker/frontend/postgres/redis/mailhog/embedding + 监控栈）。

## 架构

```text
Frontend (React) → API (FastAPI, JWT + 限流)
  → Intent → 复杂度评分 → Skill 匹配 → Planner → LangGraph 执行图
      → 每步路由决策（便宜/强 × 三档策略，失败自动升级）→ 澄清中断（歧义弹选项）
      → 副作用审批冻结（T24）→ 幂等执行（恰一次）→ Verify(fail-closed)
      → 审计/Trace → SSE → Frontend
闭环：usage_events/model_performance 回写 → 路由越用越准 → 省钱账单（全 pro 基线对比）
自成长：成功样本 → Skill 候选（采纳制）/ Agent 候选版本（门禁 + 回滚）
```

真实生产工具（6 个）：`search_web / query_db / search_knowledge / recall_memory /
recall_executions / send_email`。能力目录：`backend/app/engine/capabilities.py`。
可靠性层：Idempotency claim / IN_FLIGHT fail-closed / Reconciliation / Checkpoint-Resume / DLQ。
观测：audit_logs spans + OTel(collector) → Jaeger / Prometheus / Grafana。
详见 [docs/DISPATCH_CENTER.md](docs/DISPATCH_CENTER.md) 与 [docs/contracts](docs/contracts)。

## 测试

```bash
cd backend
../.venv311/bin/python -m pytest -q                 # 658 passed / 20 skipped
../.venv311/bin/python -m pytest -q tests/migration/test_migration_fresh_db.py
cd ../frontend
npm run typecheck && npm run test:run && npm run lint && npm run build
npm run test:e2e                                     # 需要本地后端已启动
```

Benchmark（真实模型，需显式开启）：

```bash
cd backend
BENCH_REAL_MODELS=1 python -m tests.benchmark.phase1.run_1a
BENCH_REAL_MODELS=1 PHASE1B_MODE=full python -m tests.benchmark.phase1.run_1b
```

## 生产部署

- 生产站：https://synplex.xyz（腾讯云 Ubuntu，Docker Compose）；
- 部署/回滚：`deploy/production-deploy.sh`（fetch+reset → 构建 → 健康门禁 → 失败自动回滚）；
  `deploy/rollback.sh`（回上一稳定 commit）；生产已完成 deploy → rollback → redeploy 真实演练；
- 备份/恢复：`scripts/backup.sh`（pg_dump + gzip，保留 7 份）、`scripts/restore.sh`；
- GitHub Actions：`ci.yml`（测试/迁移/Playwright）、`deploy.yml`（CI 成功后自动 SSH 部署）、`staging.yml`。

## License

MIT
