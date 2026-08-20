# Codex 记忆检查点 — AgentHub（对外品牌 synplex）

> 最后更新：2026-08-20 深夜（Asia/Shanghai）
> 用途：如果新会话丢失记忆，先完整读完本文件再动手。本文件是当前唯一权威记忆快照。

## 0. 一句话现状

AgentHub 是一个「带可靠性护栏的企业级 AI Agent 执行运行时」：
能让 AI 聊天、查业务数据、执行写操作（发邮件等），但所有副作用操作必须先经人工审批、
全程审计、可恢复。生产站 synplex.xyz 已上线可用；聊天、知识问答、数据库查询、
「邮件 + 审批 + 实际送达」都已真实验证通过；联网搜索因外部原因暂不可用（见 §10）。

## 1. 用户与沟通约定

- 用户是项目所有者，非纯技术背景也常自称开发者；要求「大白话」讲解、先自我测试再下结论。
- 交流语言：中文。
- 用户偏好：真实证据 + 诚实边界，讨厌被糊弄和夸大；多次强调「不自行下商业结论」。
- 用户常给「全权委托、闭环执行」指令；但涉及契约/Frozen Core 变更必须停下来汇报并等裁决。
- 关键约定：**本地仓库为权威**（local authoritative）；单 main 分支，不搞 cherry-pick 分支。

## 2. 基础设施速查

### 本地（Mac，用户机器）

- 项目路径：`/Users/weijiakang/agenthub`
- 后端 Python 环境：`/Users/weijiakang/agenthub/.venv311`
- Node 版本约 v26；前端依赖已安装（含 playwright/chromium）
- Docker Desktop 存在（平时可能未启动，测试时手动启动）
- Clash 代理：`127.0.0.1:7897`（push GitHub 时需要走这个代理）

### 生产服务器

- 域名：`synplex.xyz` → 公网 IP `193.112.130.181`（腾讯云，Ubuntu）
- SSH：`ssh -i ~/.ssh/agenthub_deploy ubuntu@193.112.130.181`（用户为 ubuntu，root 不通）
- 服务器仓库：`~/agenthub`（main 分支，与 GitHub 保持同步）
- 容器：`agenthub-backend / worker / frontend / postgres(pgvector) / redis / mailhog`
  以及 `grafana / prometheus / jaeger / otel-collector`；另有 `agenthub-staging-*` 预发布栈
- 生产数据库：postgres 容器，库名 `agenthub`，端口 5433
- 后端健康检查：`http://127.0.0.1:8000/health` → 200

### Git

- GitHub：`https://github.com/weijiakang8-dotcom/Agenthub.git`（服务器用 `git@github.com` ssh 只读拉取）
- 本地 push 需：`git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push https://<user-github-token>@github.com/weijiakang8-dotcom/Agenthub.git main`
  （token 是用户之前口头提供、只在命令里使用，**不得写入任何文件或 git**；过期就再向用户要）
- 服务器同步：`git fetch origin main && git reset --hard origin/main` 后重建容器
- 备选部署：`git format-patch` + `scp` + 服务器 `git am`（注意 /tmp 下旧 patch 文件重名坑，必须用唯一文件名）

## 3. 技术栈与架构

- 后端：Python / FastAPI + SQLAlchemy(asyncpg) + LangGraph 执行图 + Celery worker + Redis
- 数据库：PostgreSQL 16（pgvector）+ Alembic（当前 head = 0019，全新库 0001→0019 已验证）
- 前端：React + Vite + TypeScript + Tailwind + Radix（双主题：深色紫色光团 / 浅色蓝色水波）
- 部署：Docker Compose（`docker/docker-compose.yml`）+ Nginx；监控用 Prometheus/Grafana/Jaeger/OTel
- 引擎链路：Intent 分类 → Planner（能力目录 CAPABILITIES）→ 执行图 → Approval（副作用审批）→
  Verify（ADR-005 fail-closed）→ 审计/reconciliation
- 能力目录（`backend/app/engine/capabilities.py`）：answer / research / web_search / knowledge /
  query_db / analysis / execute / send_email；side_effect 与 requires_approval 由目录静态声明，
 模型不得伪造

## 4. 产品定位（GPTLuna 已裁决）

- 产品主线：Agent Production Runtime，不做「多 Agent 平台大而全」
- 技术主线：把概率性 AI 决策收敛为**可验证、可控制、可审计、可恢复**的确定性业务执行
- ICP：已有业务系统、让 Agent 直接改数据的 B2B SaaS / ISV AI 产品团队
- 价值表达：「让 AI 从会回答，走向敢执行」；先卖「敢执行」，不先卖「能聊天」
- Reliability Layer = 产品能力；Small Model = 经济性验证杠杆（不是「小模型稳定器」定位）
- 客户承诺拆成两个指标：安全守住率 + 业务完成率（SAFE_CONTAINED 对安全是成功、对业务未完成）

## 5. 已完成的功能清单（均已上线）

1. 登录注册：注册邮箱验证码 + 确认密码 + 密码显隐；登录只要账号密码
2. 聊天：普通问答 / 知识问答（CHAT 路径），流式输出
3. Agent 任务：规划、只读研究、数据库查询、发邮件（AGENT 路径）
4. 审批流：副作用提案冻结 → 人工批准/修改/拒绝/终止 → 批准后才执行
5. 审计：执行记录、工具调用记录、审计日志、执行详情页
6. 知识库（RAG）、Skill 模板、Workflow、告警中心、质量看板
7. 模型设置：model_configs（多模型路由）、用户自带 API Key、第二供应商 OpenAI 回退开关
   （回退默认关闭，密钥未充值前自动跳过，绝不阻塞主流程）
8. 前端：双主题、全局 tooltip、面包屑 AgentHub/Chat、侧栏品牌 synplex、图标在文字右侧

## 6. 可靠性契约历史（重要！改代码前必须知道）

- **C-1（tool retry）**：side-effect tool claim 后 provider 最多调用 1 次；
  TIMEOUT/TRANSIENT/UNKNOWN 不自动 retry；read-only tool 保留原 retry；UNKNOWN 保持 IN_FLIGHT + fail-closed
- **C-4（reconciliation 幂等）**：多轮 reconcile 不产生重复 audit
- **C-2（migration）**：0008 创建 alert_events.organization_id 后曾有重复创建导致
  DuplicateColumnError；已修复，全新库 0001→0019 一次成功、已有 0019 库 upgrade head 为 no-op；
  禁止 stamp / 手跳 migration / 删 migration / 忽略异常
- **T24（Approval Freeze，Pro 裁决）**：权威语义 = 显式 mismatch detection → abort。
  批准 A、运行时尝试 B（tool 或 params_canonical 任一不一致）→ provider=0 + approval_mismatch
  审计 + FAILED，禁止「把 B 偷偷替换成 A 执行」；实现于 `backend/app/engine/graph.py`
  （`_execute_frozen_side_effect` 运行时显式比对）
- **ADR-005（Verify fail-closed）**：PASS=trim 后精确 PASS；FAIL 触发一次 replan（≤1）；
  UNKNOWN/ERROR 不算 PASS、不触发 replan、有审计 + span error；LLM judge 只准输出 PASS/FAIL
- **提案澄清修复（本次会话）**：side-effect 提案模型返回 0 个 tool call（如缺收件人邮箱）时，
  不再抛晦涩 plan_invalid，而是 audit=proposal_clarification + 发 `clarification` SSE 事件，
  把模型澄清问题原样呈现给用户；仍 zero 副作用、fail-closed、不猜测参数
- **query_db 提示增强（本次会话）**：给工具描述与 capability prompt 加了表/字段速查，
  避免模型瞎猜 sqlite_master/PRAGMA 导致失败；查询仍严格只读、单表、强制租户过滤

## 7. Frozen Core 与绝对不碰清单

以下内容无明确裁决授权不得修改：Approval Freeze 语义、Idempotency 状态机、
UNKNOWN/IN_FLIGHT/reconciliation 语义、Tool Retry 契约、Event Contract、Kernel EffectPort、
planner/intent/model gateway 主流程、alembic migration 历史、benchmark Oracle 与判定标准、
Verify 状态机（ADR-005）。
Prompt Injection 防线：设计稿冻结待评审，**禁止做任何代码实现**。
禁止：为让测试通过放宽 Oracle、改安全阈值、在 harness 伪造生产不存在的机制。

## 8. 凭证位置（只记位置，绝不记明文）

- 有效 DeepSeek Key：`~/.dsh/.credentials.yaml`（`DEEPSEEK_API_KEY`，sk-de68…43cb）。
  生产 `model_configs` 表、生产 `.env` 的 `OPENAI_API_KEY`、本地 `.env` 均已换成此 key。
- 已吊销的旧 key（sk-cdd9…9a4f）：**永远不要再用**。曾导致 401「hello 报错」。
- OpenAI 第二供应商 key（sk-proj-…）：未充值；`OPENAI_FALLBACK_ENABLED=false`，不要开启。
- Resend：`RESEND_API_KEY` 在生产 `.env`；发件地址 `no-reply@synplex.xyz`，已验证可用。
- GitHub token：只在用户口头提供时用于本次 push 命令，不落盘、不写文档。
- 生产 `.env` 有备份 `.env.bak`；`.env` 均已 gitignore，禁止提交。

## 9. 生产运行状态（2026-08-20 深夜）

- 聊天 hello、知识问答、查数据库、发邮件全链路实测通过
- 邮件自测：已真实送达 `weijiakang8@gmail.com`（Resend last_event=delivered，主题「AgentHub 平台自测」）
- 查询库自测：模型现在能生成合法查询（如 `SELECT status, created_at FROM executions LIMIT 20`），
  结果严格限定当前租户数据
- 历史遗留：15 条 401 时期的失败 hello 执行记录（用户真实数据，勿动）；
  早期 smoke/e2e 测试账号（smoke-*、model-*、fallback-*、e2e-fb-* 等）仍在库中，清理需用户点头

## 10. 已知问题与待办

1. **联网搜索不可用**：生产服务器在中国大陆，DuckDuckGo 被墙；TAVILY_API_KEY 未配置。
   表现为优雅降级（明确说搜不了 + 用已有知识）。**等用户提供 Tavily key 即可打通**（上次已承诺）。
2. **邮件正文冻结时机**：提案在 plan 阶段生成并冻结，早于 research 步骤执行，
   所以「先搜索再整理发邮件」的正文基于模型知识而非实时抓取。改「先搜后提案再审批」会动
   Approval Freeze 冻结时机语义，需用户拍板，不要擅自改。
3. **query_db 限制**：只读、单表、白名单、自动租户过滤；禁止 COUNT(*)/函数括号/ORDER BY/JOIN
   等，是安全设计不是 bug。
4. **Phase 1A** 已完成（60 runs，exploratory）；**Phase 1B** spec 已设计，但完整 416-run
   的执行在本会话证据中未确认落地，新会话如要继续需先核查 benchmark 目录与既有报告。
5. 无 seed、单 provider family，所有 benchmark 结论必须标记 EXPLORATORY，禁止包装成产品结论。

## 11. 测试与验证命令速查

- 后端（先启动本地 docker 依赖）：
  `docker compose -f docker/docker-compose.yml up -d postgres redis mailhog`
  `cd backend && ../.venv311/bin/python -m pytest -q`
  基线：577 passed / 20 skipped / 0 failed（20 跳过均为需外部服务的既有集成测试）
- 迁移：`AGENTHUB_MIGRATION_TEST_DB_URL=... pytest tests/migration/test_migration_fresh_db.py`
- 前端：`cd frontend && npm run typecheck && npm run test:run && npm run lint && npm run build`
- 静态检查：`../.venv311/bin/python -m ruff check <files> && ruff format --check <files>`
- 生产 E2E：SSH 到服务器后，用「插入临时 org/user → login → conversations/stream」方式自测，
  测完按 audit_logs→tool_calls→executions→conversations→users→organizations 顺序清理临时数据

## 12. 部署流程速查

1. 本地改码 → 自测（§11）
2. `git commit` → 走代理 + token push 到 GitHub（§2）
3. 服务器：`git fetch origin main && git reset --hard origin/main`，
   然后 `docker compose -f docker/docker-compose.yml up -d --build backend worker frontend`
4. 验证：容器日志、`/health`、必要时真实 E2E

## 13. 明天醒来后的建议动作

1. 读完全文 → `cd ~/agenthub && git status && git log --oneline -5` 确认与 GitHub/服务器一致
2. 检查生产健康（`/health`、容器状态）
3. 若用户给了 Tavily key：配到生产 `.env` + 重启 backend，真实测一次联网搜索，更新本文件
4. 若用户选择改「先搜索后提案」：先写影响分析给用户裁决，不要直接改 Approval Freeze
5. 其余按用户当天的指令执行；涉及 §7 的改动先汇报

## 14. 关键文件索引

- `backend/app/engine/graph.py`：执行图 / Approval Freeze / 提案澄清（最常改动的核心文件）
- `backend/app/engine/capabilities.py`：能力目录（扩展点）
- `backend/app/engine/tools.py`：search_web / query_db / send_email
- `backend/app/engine/planner.py`：计划生成与校验
- `backend/app/core/model_gateway.py`：模型选择 / 回退
- `frontend/src/pages/Chat.tsx`：聊天 SSE 与审批按钮
- `docs/` 与根目录 ADR/ARCHITECTURE 文档：契约原文
- 上一轮的完整自测结论（功能清单/短板/使用教程）就在会话历史里，可对照本文件 §9/§10
