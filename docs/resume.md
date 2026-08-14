# 简历项目描述（可直接复制到简历）

## AgentHub —— 企业级多智能体协作平台

**项目简介**

AgentHub 是一个可部署到云端的多智能体协作平台，用于编排多个 AI Agent 完成复杂长任务，支持断点续跑、人机协同审核和执行轨迹审计。

**技术栈**

Python 3.11+ / FastAPI / LangGraph / LangChain / Celery / Redis / PostgreSQL(asyncpg) / SQLAlchemy 2.0 / Alembic / React / TypeScript / Vite / Docker / Kubernetes

**个人工作与亮点**

- 设计并实现 FastAPI 后端，完成 Agent、Workflow、Execution、ToolCall 四个核心数据模型的 SQLAlchemy 2.0 异步建模与 Alembic 迁移。
- 基于 LangGraph 构建多智能体编排图，实现 `research → analyze → execute` 条件路由，集成 DeepSeek（OpenAI 兼容接口）完成真实 LLM 调用。
- 使用 Celery + Redis 解耦 API 与执行链路，将 `POST /api/executions` 异步化为 202 Accepted，支持状态轮询与取消。
- 实现基于 `AsyncPostgresSaver` 的 Checkpoint 断点续跑，敏感工具触发 `waiting_for_approval` 人工审核，支持 approve/reject 后从断点恢复。
- 提供工具调用审计与执行轨迹 API，前端（React + TS + Vite）展示执行列表与轨迹。
- 通过 Docker Compose 完成本地一键部署，并编写 Kubernetes（Deployment / Service / Ingress）云部署清单。

**结果**

端到端验证通过：创建 Agent → Workflow → Execution，状态从 `pending` 流转到 `completed`，Celery 日志确认成功调用 DeepSeek LLM 并返回结构化结果。
