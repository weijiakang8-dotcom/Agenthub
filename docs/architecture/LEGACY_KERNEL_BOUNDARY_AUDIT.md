# Legacy ↔ Kernel Boundary Audit

> Phase 3.0 基线。本文件只描述语义边界，不驱动 Legacy 行为修改。

## A. Legacy Execution 对应 Kernel 中什么

- Legacy `Execution`（[execution.py](/Users/weijiakang/agenthub/backend/app/models/execution.py:28)）是一次"工作流实例运行"，不是 Kernel Task。
- 对应关系：`LegacyExecution` → Adapter → `RuntimeInput`（`initial_state + plan + goal`）。
- `Execution.user_input` → Kernel 输入 Artifact（`L2_SUPPORTED`）。
- `Execution.final_output` → Kernel `Artifact`（`L1_INFERRED`，LLM 输出），**不是 Observation**。
- `Execution.status == COMPLETED` → **不等于** Kernel `GoalStatus.SATISFIED`。

## B. Legacy Workflow 对应 Kernel 中什么

- Legacy `Workflow`（[workflow.py](/Users/weijiakang/agenthub/backend/app/models/workflow.py:16)）= 静态 DAG/agent_chain，绑定 Agent/角色。
- 对应关系：`Workflow` → Adapter → `Plan`（Tasks + Dependencies），**不绑定 Agent**。
- `agent_chain` 中的 Agent 身份是 orchestration metadata，迁移时留在 Adapter/Legacy 层。
- `dag_definition` 的 node 可映射为 `Task`，但 node 的 `research/analyze/execute` 角色不能进入 Task。

## C. Legacy Agent 对应 Kernel 中什么

- Legacy `Agent`（[agent.py](/Users/weijiakang/agenthub/backend/app/models/agent.py:10)）= name/system_prompt/tools，无 Kernel 执行语义。
- Kernel 没有 Agent。Agent 只能决定"谁执行 Task"，不能改变 Task/Capability/Goal/Evidence/Observation。
- 迁移时 `system_prompt`/`name`/`model` 保留在 Adapter/Legacy 层，不得写进 `Task`。

## D. Legacy Tool 对应哪个 Capability

见 `LEGACY_CAPABILITY_MAPPING.md`。核心结论：
- `search_web` → `Retrieve` + `Extract`（Pure，Knowledge）。
- `query_db`（内部库）→ `Retrieve`（Pure，Knowledge）。
- `query_db`（外部状态读取）→ `Observe`（Effectful，L3 Observation）。
- `send_email` → `Mutate`（Effectful，Command + Receipt），**不产生 Observation**。

## E. 哪些旧数据可以直接映射

- `Execution.user_input` → 输入 Artifact（`L2_SUPPORTED`）。
- `Execution.organization_id` → Adapter 上下文（不进入 Kernel 语义）。
- `Workflow.dag_definition` 的节点顺序 → Plan 依赖。
- `ToolCall.input_params` → Task `input_arguments`。
- 纯文本 `final_output` → Artifact（`L1_INFERRED`）。

## F. 哪些旧数据绝对不能映射

- `Agent.system_prompt` / `Agent.tools` → 不能成为 Capability。
- `Agent.role` / DAG node 角色 → 不能成为 Task 字段。
- `Execution.status == COMPLETED` → 不能成为 `SATISFIED`。
- `final_output` / `ToolCall.status == success` / `ExecutionReceipt` → 不能成为 `Observation`。
- `Execution.final_output` 不能进入 `ObservedWorldState`。

## G. 哪些旧语义存在信息损失

- LLM `final_output` 无 evidence/confidence/source，映射到 Kernel 只能降为 `L1_INFERRED`。
- `ToolCall.status` 只表示执行尝试，不表示外部世界事实。
- Legacy `agent_chain` 的 Agent 身份在 Kernel Plan 中丢失（有意为之）。
- Legacy 多轮 `messages` 历史无结构化 Evidence，Adapter 需显式截断/降级。

## H. 哪些 Legacy 输出不能被包装成 Observation

- `final_output`（LLM 文本）。
- `ToolCall.status == success`。
- `search_web` 返回的搜索结果摘要。
- `query_db` 返回的内部库行。
- `send_email` 的 SMTP success。
- 只有真实外部 Observe（如查询发件箱/外部系统状态）才能产生 Observation。

## I. 哪些旧 API 可以通过 Adapter 接入 Kernel

- `POST /conversations/{id}/stream` 的无副作用子流程（可映射为纯 Retrieve/Extract）。
- `POST /executions` 中不涉及 send_email/human_approval 的纯流程。
- 用于评测/对照的只读执行路径。

## J. 哪些 API 暂时不能接入

- `send_email`（需要真实 Observe 回填）。
- `query_db` 的外部世界读取语义未定。
- Celery 异步、human_approval、动态 DAG、WebSocket、billing、notification。

## K. 哪些模块最终应该被迁移

- `engine/runner.py`、`engine/graph.py`、`engine/evaluator.py` 的执行/编排语义 → Kernel。
- `models/execution.py`、`workflow.py`、`agent.py` 的语义模型 → Kernel 模型。

## L. 哪些模块永远属于外围 Infrastructure

- `api/`、`core/auth`、`core/permissions`、`core/audit`、`core/rate_limit`、`core/telemetry`。
- `rag/`、`core/model_gateway`、`core/billing`、`core/notification`、`core/alerting`。
- FastAPI / Celery / Redis / PostgreSQL / LangGraph / LLM SDK / 真实 Tool 连接。

## 语义边界对照

| Legacy | Kernel | 规则 |
|---|---|---|
| final_output | Artifact(L1) | 不是 Observation |
| ToolCall.success | Receipt | 不是 Observation |
| ExecutionStatus.COMPLETED | PlanExecutionStatus | 不是 Goal SATISFIED |
| messages | KnowledgeState entries | 结构化降级，不是 ObservedWorldState |
| tool result | Knowledge / Receipt | 视 Tool 语义而定 |
