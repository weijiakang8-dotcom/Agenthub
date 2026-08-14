# AgentHub —— 企业级多智能体协作平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2+-orange.svg)](https://langchain-ai.github.io/langgraph/)

## 📖 项目简介

AgentHub 是一个**企业级多智能体协作平台**，解决了 AI Agent 在 B 端落地时的三大痛点：
- 🔄 **长任务断点续跑** —— Agent 执行中途中断可从 Checkpoint 恢复
- 🧑‍💼 **人机协同审核** —— 敏感操作（如发邮件）需人工批准，可扩展扣库存等场景
- 📊 **执行轨迹可视化** —— 提供执行轨迹与工具调用审计（React Flow 决策树规划中）

## 🏗️ 系统架构

```mermaid
flowchart LR
    Web["React + TypeScript + Vite<br/>执行列表 / 轨迹"]

    subgraph Backend["后端"]
        API["FastAPI<br/>REST /api"]
        Celery["Celery Worker"]
        Graph["LangGraph Engine<br/>research → analyze → execute"]
        Tools["Tools<br/>Tavily / SQL / SMTP"]
    end

    subgraph Data["数据层"]
        PG[("PostgreSQL<br/>业务模型 + Checkpoint")]
        Redis[("Redis<br/>Broker + 缓存")]
    end

    LLM["DeepSeek<br/>OpenAI 兼容"]

    Web -->|"/api"| API
    API -->|"202 入队"| Redis
    Redis --> Celery
    Celery --> Graph
    Graph --> LLM
    Graph --> Tools
    Graph <--> PG
    Celery <--> PG
    API <--> PG
```

> 详细架构说明见 [docs/architecture.md](./docs/architecture.md)。

### 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph + LangChain |
| 异步任务 | Celery + Redis |
| 数据库 | PostgreSQL (asyncpg) |
| 向量/缓存 | Redis |
| 前端 | React + TypeScript + Vite（React Flow 规划中） |
| 部署 | Docker Compose + Kubernetes（Helm 规划中） |

## 🚀 快速开始

### 前置条件
- Python 3.11+
- Docker & Docker Compose
- Node.js 18+
- DeepSeek API Key（或其他 OpenAI 兼容 API）

### 1. 克隆项目
```bash
git clone https://github.com/你的用户名/agenthub.git
cd agenthub
```

### 2. 配置环境变量
```bash
cp .env.example .env
```

编辑 `.env`，至少填写 `OPENAI_API_KEY`（DeepSeek 或其他 OpenAI 兼容 API 的 Key）。其余变量见下文「环境变量」。

### 3. 启动依赖服务（PostgreSQL + Redis）
```bash
docker compose -f docker/docker-compose.yml up -d postgres redis
```

> 说明：本地 PostgreSQL 宿主机端口映射为 `5433`（容器内为 `5432`），可在 `docker/docker-compose.yml` 中按需调整。

### 4. 启动后端
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

# 终端 1：FastAPI 服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：Celery Worker
celery -A app.engine.tasks worker --loglevel=info
```

### 5. 启动前端
```bash
cd ../frontend
npm install
npm run dev
```

打开以下地址：
- 前端页面：http://localhost:5173
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 🧩 核心功能

- 🤖 **多智能体编排**：`research → analyze → execute` 三个 Agent 节点，由 LangGraph 状态图驱动
- 💾 **断点续跑**：LangGraph `AsyncPostgresSaver` 持久化到 PostgreSQL，支持从 Checkpoint 恢复
- 🧑‍💼 **人机协同**：`send_email` 等敏感工具进入 `waiting_for_approval`，支持 approve/reject 后 resume
- 📈 **执行审计**：每次工具调用记录 `ToolCall` 日志，可查询执行轨迹
- ⚡ **异步任务**：Celery + Redis 解耦 API 请求与实际执行，`POST /api/executions` 立即返回 202

## 🔌 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agents` | 创建 Agent |
| GET | `/api/agents` | Agent 列表（分页 + status 筛选） |
| GET/PUT/DELETE | `/api/agents/{id}` | 详情 / 更新 / 软删除 |
| POST | `/api/workflows` | 创建工作流 |
| GET | `/api/workflows` | 工作流列表 |
| GET/PUT/DELETE | `/api/workflows/{id}` | 详情 / 更新 / 删除（含执行冲突校验） |
| POST | `/api/executions` | 启动执行，返回 202 + execution_id |
| GET | `/api/executions` | 执行列表（workflow_id/status 筛选） |
| GET | `/api/executions/{id}` | 执行详情（含 tool_calls） |
| GET | `/api/executions/{id}/status` | 轮询执行状态 |
| POST | `/api/executions/{id}/cancel` | 取消执行 |
| POST | `/api/executions/{id}/resume` | 从 Checkpoint 恢复执行 |
| GET | `/api/executions/{id}/trace` | 执行轨迹 |
| GET | `/api/tool_calls` | 工具调用列表 |
| POST | `/api/tool_calls/{id}/approve` | 审批通过 |
| POST | `/api/tool_calls/{id}/reject` | 审批拒绝 |

## 📁 项目结构

```text
agenthub/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # 路由与依赖注入
│   │   ├── engine/          # LangGraph 图、工具、Checkpoint、Runner、Celery
│   │   ├── models/          # SQLAlchemy 2.0 异步模型
│   │   ├── schemas/         # Pydantic Schema
│   │   ├── config.py        # Pydantic Settings
│   │   ├── database.py      # 异步引擎与会话
│   │   └── main.py          # FastAPI 入口
│   ├── alembic/             # 数据库迁移
│   └── requirements.txt
├── frontend/                # React + TypeScript + Vite
├── docker/                  # Dockerfile 与 docker-compose.yml
├── k8s/                     # Kubernetes 部署文件（Deployment/Service/Ingress）
├── docs/                    # 项目文档
├── .env.example
└── README.md
```

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `APP_NAME` | 应用名称 | `AgentHub` |
| `DEBUG` | 调试开关 | `false` |
| `DATABASE_URL` | PostgreSQL 连接串（asyncpg） | `postgresql+asyncpg://postgres:postgres@localhost:5433/agenthub` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | DeepSeek / OpenAI 兼容 API Key | 空 |
| `ADMIN_API_KEY` | 管理端 API Key（留空则开发环境不校验） | 空 |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `TAVILY_API_KEY` | Tavily 搜索 Key | 空 |
| `SMTP_HOST` | SMTP 主机 | `localhost` |
| `SMTP_PORT` | SMTP 端口 | `587` |
| `SMTP_USERNAME` | SMTP 用户名 | 空 |
| `SMTP_PASSWORD` | SMTP 密码 | 空 |
| `SMTP_FROM` | 发件人地址 | 空 |

## ✅ 测试

```bash
# 后端
cd backend
pytest

# 前端
cd frontend
npm run test:run
```

## 🐳 部署

- **本地开发**：使用 `docker/docker-compose.yml` 一键启动 PostgreSQL、Redis、backend、frontend。
- **云端生产**：使用 `k8s/` 下的 Deployment、Service、Ingress 部署到阿里云/腾讯云等 Kubernetes 集群，通过公网访问。

## 🗺️ 路线图

- [ ] React Flow 决策树可视化
- [ ] JWT 认证与多租户
- [ ] 更多内置工具（扣库存、HTTP 请求等）
- [ ] Helm Chart 与一键云部署脚本
- [ ] 完整的 pytest / Vitest 测试用例

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。请先阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)，开发规范见 [AGENTS.md](./AGENTS.md)。

## 📄 License

[MIT](./LICENSE)
