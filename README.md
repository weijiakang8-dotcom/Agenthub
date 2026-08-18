# AgentHub —— 多智能体协作平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-orange.svg)](https://langchain-ai.github.io/langgraph/)

## 项目简介

AgentHub 是一个可部署到云端的多智能体协作平台。用户可以通过对话或可视化工作流，编排多个 AI Agent 完成复杂长任务，并实时查看执行过程、审批敏感操作、审计工具调用。

## 核心能力

- 多智能体编排：固定 `research → analyze → execute` 角色 + 动态任务分类
- 动态 DAG 工作流：条件分支、人工审批节点、自定义 Agent 节点
- Loop 自检：最终输出质量不足时自动重跑
- 断点续跑：LangGraph Checkpoint 持久化到 PostgreSQL
- 人机协同：敏感工具进入 `waiting_for_approval`，可批准 / 修改 / 终止
- Chat 流式对话：多轮上下文、SSE 流式输出、停止生成、执行详情
- 多模型网关：多供应商配置、连接测试、执行引擎自动 fallback
- RAG 知识库：文档上传、向量化、语义检索，Research Agent 自动注入
- 评测闭环：数据集、批量回归、LLM-as-Judge 三维评分
- 用量与成本：Token 估算、模型成本统计
- 通知中心：邮件、Webhook、飞书、钉钉、企微通道
- 企业认证：JWT（access 30 分钟 / refresh 7 天）、登录/注册/找回密码、前端 401 自动刷新
- 企业权限与审计：RBAC（admin/member/viewer）、组织成员管理、动作级审计日志、多租户隔离

## 功能截图

### 工作区 / 对话入口

![AgentHub Dashboard](docs/screenshots/dashboard.png)

### API 文档（Swagger）

![AgentHub Swagger](docs/screenshots/swagger.png)

## 系统架构

```mermaid
flowchart LR
    Web["React + TypeScript + Vite<br/>Chat / Workflow Editor / Execution"]

    subgraph Backend["后端"]
        API["FastAPI<br/>REST /api + WebSocket"]
        Celery["Celery Worker"]
        Graph["LangGraph Engine<br/>multi-agent / DAG / loop"]
        Gateway["Model Gateway<br/>multi-model fallback"]
        RAG["RAG<br/>documents / embeddings"]
        Tools["Tools<br/>search / SQL / email"]
    end

    subgraph Data["数据层"]
        PG[("PostgreSQL<br/>业务模型 + Checkpoint")]
        Redis[("Redis<br/>broker / cache / rate limit")]
    end

    LLM["DeepSeek / OpenAI-compatible models"]

    Web -->|"/api"| API
    API -->|"202 入队"| Redis
    Redis --> Celery
    Celery --> Graph
    Graph --> Gateway
    Gateway --> LLM
    Graph --> RAG
    Graph --> Tools
    Graph <--> PG
    Celery <--> PG
    API <--> PG
```

## 执行流程

```mermaid
sequenceDiagram
    participant User as 用户
    participant Web as React 前端
    participant API as FastAPI
    participant Redis as Redis
    participant Worker as Celery Worker
    participant Graph as LangGraph
    participant LLM as 多模型网关
    participant DB as PostgreSQL

    User->>Web: 输入任务
    Web->>API: POST /api/executions
    API->>DB: 创建 Execution
    API->>Redis: 投递 Celery 任务
    API-->>Web: 202 Accepted
    Redis-->>Worker: 消费任务
    Worker->>Graph: 执行 Agent 工作流
    Graph->>LLM: 调用模型 / 自动 fallback
    Graph->>DB: 写入 Checkpoint / ToolCall
    Graph-->>Web: WebSocket / SSE 状态推送
    Worker->>DB: 更新 Execution 状态
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph + LangChain |
| 异步任务 | Celery + Redis |
| 数据库 | PostgreSQL (asyncpg) |
| ORM / 迁移 | SQLAlchemy 2.0 / Alembic |
| 向量检索 | sentence-transformers + Redis |
| 前端 | React 18 + TypeScript + Vite |
| 可视化 | React Flow |
| UI | Tailwind CSS + shadcn/ui 风格组件 |
| 实时通信 | WebSocket / SSE |
| 可观测性 | OpenTelemetry + Prometheus + Grafana + Jaeger |
| 部署 | Docker Compose + Kubernetes manifests |
| CI/CD | GitHub Actions |

## 快速开始

### 前置条件

- Python 3.11+
- Docker 和 Docker Compose
- Node.js 18+
- DeepSeek 或其他 OpenAI 兼容 API Key

### 1. 克隆项目

```bash
git clone https://github.com/weijiakang8-dotcom/Agenthub.git
cd agenthub
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少填写：

- `OPENAI_API_KEY`
- 生产环境必须设置强随机 `JWT_SECRET_KEY`
- 生产环境应设置 `ENVIRONMENT=production`
- 需要邮件验证码时设置 `RESEND_API_KEY`

### 3. 启动依赖服务

```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

### 4. 启动后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
celery -A app.engine.tasks.celery_app worker --loglevel=info -B
```

> **macOS 注意事项（Celery worker）**
> 在 macOS + Python 3.14 上，Celery 默认的 prefork 池可能因 Objective-C
> `NSCharacterSet initialize` 的 fork 安全问题随机 `SIGABRT`，导致正在执行的
> Execution 卡在 `running`。本地开发请使用 solo 池并关闭 fork 安全检查：
>
> ```bash
> export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
> celery -A app.engine.tasks.celery_app worker --pool=solo --loglevel=info -B
> ```
>
> 生产 Linux 容器不受此问题影响，但建议在部署清单中固定 worker pool 配置；
> 卡死的 `running` Execution 由 beat 的 `mark-stale-executions`（每 120s）自动
> 回收为 `failed`（超时阈值 15 分钟）。

### 5. 启动前端

```bash
cd ../frontend
npm install
npm run dev
```

访问：

- 前端：`http://localhost:5173`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### Docker Compose 一键启动

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

打开：

- 前端：`http://localhost:8080`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

生产 Kubernetes / TLS 部署说明见 [docs/deployment-kubernetes.md](docs/deployment-kubernetes.md)。

## 可观测性

完整 Docker Compose 部署包含以下可观测性服务：

| 服务 | 地址 | 说明 |
|------|------|------|
| Backend Metrics | `http://localhost:8000/metrics` | Prometheus 文本指标 |
| Prometheus | `http://localhost:9090` | 采集 OTel Collector 与 Backend 指标 |
| Grafana | `http://localhost:3000` | 默认账密 `admin/admin` |
| Jaeger | `http://localhost:16686` | Trace 查询 |
| MailHog | `http://localhost:8025` | 本地 SMTP 测试邮件 |

启动完整可观测性组件：

```bash
docker compose -f docker/docker-compose.yml up -d \
  otel-collector prometheus grafana jaeger mailhog
```

从项目根目录执行 Compose 命令时，建议建立 `docker/.env` 软链接，确保 Compose 能读取根目录 `.env`：

```bash
ln -sfn ../.env docker/.env
```

## API 概览

| 模块 | 路径 |
|------|------|
| 认证 | `/api/auth/*` |
| Agent | `/api/agents` |
| Workflow | `/api/workflows` |
| 工作流模板 | `/api/workflow-templates` |
| Execution | `/api/executions` |
| ToolCall | `/api/tool_calls` |
| 对话 | `/api/conversations` |
| 告警 | `/api/alerts` |
| 告警规则 | `/api/alert-rules` |
| 审计日志 | `/api/audit-logs` |
| 模型管理 | `/api/models` |
| 文档 / RAG | `/api/documents` |
| 通知 | `/api/notifications` |
| 评测 | `/api/eval` |
| 用量 | `/api/usage` |
| 任务监控 | `/api/tasks` |
| WebSocket | `/ws/executions/{id}` |
| Metrics | `/metrics` |

## 项目结构

```text
agenthub/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── engine/
│   │   ├── models/
│   │   ├── rag/
│   │   └── schemas/
│   └── tests/
├── frontend/
├── docker/
├── k8s/
├── deploy/
├── docs/
├── .github/workflows/
├── .env.example
└── README.md
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_NAME` | 应用名称 | `AgentHub` |
| `DEBUG` | 调试开关 | `false` |
| `ENVIRONMENT` | 运行环境 | `development` |
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://postgres:postgres@localhost:5433/agenthub` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | LLM API Key | 空 |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 全局默认模型 | `deepseek-chat` |
| `JWT_SECRET_KEY` | JWT 密钥，生产必须强随机 | `change-me-in-production` |
| `CORS_ORIGINS` | 允许跨域的前端地址 | `http://localhost:5173,http://localhost:8080` |
| `ADMIN_API_KEY` | 管理 API Key | 空 |
| `RESEND_API_KEY` | Resend 邮件密钥 | 空 |
| `SMTP_*` | SMTP 邮件配置 | 空 |
| `TAVILY_API_KEY` | Tavily 搜索 Key | 空 |

## 测试

```bash
# 后端
cd backend
pytest -q

# 前端
cd ../frontend
npm run test:run
npm run build
```

## 部署

### Docker Compose

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

### CI/CD

- push 到 `main` 或创建 PR 时运行测试
- CI 通过后自动触发生产部署
- 后端测试、前端测试、前端构建、Docker 构建均为门禁

## 路线图

- [ ] HTTPS / TLS 生产部署
- [ ] 生产环境 Kubernetes 部署验证
- [ ] Prompt 版本管理与 A/B 评测
- [ ] 完整定时任务 / Scheduler
- [ ] 飞书 / 钉钉 / 企微官方 SDK 级通知
- [ ] NPM 包 / 本地 CLI
- [ ] 更多内置工具

## 贡献指南

欢迎提交 Issue 和 Pull Request。

快速参与方式：

```bash
# Fork 仓库并克隆
git clone https://github.com/你的用户名/Agenthub.git
cd agenthub

# 创建功能分支
git checkout -b feat/my-feature

# 后端测试
cd backend
pytest -q

# 前端检查
cd ../frontend
npm run test:run
npm run build
```

提交前请阅读：

- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [AGENTS.md](./AGENTS.md)

Commit 建议遵循 Conventional Commits：

```text
feat: 新增功能
fix: 修复问题
docs: 更新文档
chore: 维护任务
```

## License

[MIT](./LICENSE)
