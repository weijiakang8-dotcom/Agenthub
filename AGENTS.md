# AgentHub 开发指南

AgentHub 是一个多智能体协作平台，可部署到云端（阿里云/腾讯云）并通过公网访问。

本文件是项目级的开发约定，供参与本项目的人类开发者与 AI 协作开发时共同遵守。

## 项目结构（Monorepo）

```text
agenthub/
├── backend/          # FastAPI 后端
├── frontend/         # React + TypeScript + Vite 前端
├── docker/           # Dockerfile 与 docker-compose.yml
├── k8s/              # Kubernetes 部署文件（Deployment/Service/Ingress）
└── docs/             # 项目文档
```

## 技术栈

- 后端：Python 3.11+、FastAPI、LangGraph、LangChain、SQLAlchemy（asyncpg）、Celery
- 前端：React、TypeScript、Vite
- 数据与中间件：PostgreSQL（主数据库）、Redis（缓存与会话）
- 容器与编排：Docker、Docker Compose（本地）、Kubernetes（云端）

## 代码风格

### Backend

- 格式化：Black
- Lint：Ruff
- 提交前需保证 `black .` 与 `ruff check .` 通过。

### Frontend

- Lint：ESLint
- 格式化：Prettier
- 提交前需保证 `npm run lint` 与 `npm run format:check` 通过。

## 测试要求

- Backend：pytest，测试文件统一放在 `backend/tests/` 下，命名为 `test_*.py`。
- Frontend：Vitest，测试文件命名为 `*.test.ts` / `*.test.tsx`。
- 新增功能应包含对应测试，合并前需保证全量测试通过。

## 部署目标

- 本地开发与联调：使用 `docker compose` 启动 PostgreSQL、Redis、backend、frontend。
- 云端生产：使用 Kubernetes（Deployment、Service、Ingress），目标云为阿里云/腾讯云，通过公网访问。
