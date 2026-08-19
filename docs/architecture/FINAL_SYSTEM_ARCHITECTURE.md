# FINAL_SYSTEM_ARCHITECTURE

来源：真实代码（backend/app），非理想架构。

## 请求链路

Request → Auth(401/RBAC) → IntentRouter(classify) → decide_runtime(category)

- CHAT / KNOWLEDGE / CLARIFICATION → Chat Runtime（同步 SSE）
- TASK / ACTION → Agent Runtime（Celery + LangGraph + checkpoint）
- Kernel Runtime：`POST /api/skills/{id}/execute`（确定性内核，独立）

Chat：不进 Celery、不 checkpoint、不无条件 RAG；System→Memory→Summary→Recent N→Input 注入。

Agent：execute_workflow_task → run_execution →
Plan（workflow 派生或 Planner）→ Plan Validator（goal/risk/Registry/DAG/≤6）→
Risk/Budget 初始化 →（含副作用）提案生成并冻结 → approval interrupt →
resume → 串行执行 steps（预算闸门/幂等）→ Verify（PASS/FAIL 分级）→ COMPLETED/FAILED。

## 三 Runtime 边界

- Chat：同步流式，性能红线。
- Agent：异步、可恢复（LangGraph checkpoint 唯一可恢复状态源）。
- Kernel：EffectPort/Constitution 抽象，不反向依赖 Web/DB。

## 数据归属

- Conversation：messages + summary
- Execution：intent/plan/steps/final_output/token/cost/checkpoint_data
- tool_calls：副作用唯一事实源（idempotency_key + status）
- audit_logs：HTTP 事实 + 执行闸门审计 + span:*
- checkpoints：LangGraph 状态
- user_memories / document_chunks：Memory/RAG
- Redis：broker + events + semantic cache（可丢弃）

## 关键不变量

- Intent → Runtime 静态映射；complexity 只影响模型策略
- 非法计划 → plan_invalid（不静默降级）
- 副作用预算超限硬终止；只读超限优雅终止
- 所有 LLM 调用经 ModelGateway；所有重试经 failure.py 分层
