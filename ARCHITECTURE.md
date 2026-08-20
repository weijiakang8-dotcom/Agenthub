# AgentHub 最终架构

## Runtime 边界（唯一主架构）

| Runtime | 职责 | 入口 | 是否进 Celery | 关键代码 |
| --- | --- | --- | --- | --- |
| Chat Runtime | 聊天/问答/澄清/知识问答：同步流式 | `POST /api/conversations/{id}/stream` | 否 | `app/engine/chat.py`, `app/api/routes/conversations.py` |
| Agent Execution Runtime | 任务/动作：Planner→Capability→Verify，异步事件 | 同上（Intent=TASK/ACTION）或 `POST /api/executions` | 是 | `app/engine/graph.py`, `app/engine/runner.py`, `app/engine/tasks.py` |
| Kernel Runtime | 确定性执行内核（Skill 与未来接入点） | `POST /api/skills/{id}/execute` | 否（进程内） | `app/kernel/*`, `app/adapters/kernel_runner.py` |

Intent → Execution Decision → Runtime Selection 由 `app/engine/intent.py` 统一决定；
`complexity` 只影响模型策略，不决定 Runtime。

## 请求链路

```text
Browser → Nginx → FastAPI
  Chat:   IntentRouter → Chat Runtime（LLM streaming → SSE token → done）
  Agent:  IntentRouter → Celery → LangGraph(plan → capability steps → verify) → Redis events → SSE/WS
  Kernel: Skill 执行 → KernelRuntime（plan validation → transition/effect → goal evaluator）→ DB/audit
```

## 状态与持久化归属

- Conversation = 对话事实（`conversations.messages/summary`）
- Execution = 一次执行事实（`executions`：intent/plan/steps/final_output/token_usage/cost）
- Runtime State = LangGraph 内存状态（`checkpoints/checkpoint_blobs/checkpoint_writes`）
- Audit = `audit_logs`、`tool_calls`、`intervention_logs`、`shadow_audits`
- Cache = Redis（semantic cache / broker / events），可丢弃

## Memory 分层

1. Working Memory：当前请求与图状态
2. Conversation Memory：`conversations.messages` + 可选 `summary`
3. Long-term User Memory：`user_memories`（org+user 隔离、importance、过期）
4. Knowledge Memory：`documents` + `document_chunks`（pgvector）
5. Execution Memory：executions/checkpoints/tool/audit
6. Semantic Cache：Redis，永远不是 Memory

## RAG

Document → Chunk（`app/rag/chunking.py`）→ Embedding（`app/rag/embedder.py`）→
pgvector（`document_chunks.embedding`）→ Retrieval（`app/rag/vector_store.py`）→
Context Builder → LLM。检索与 LLM 解耦，故障 fail-open。

## Model Gateway

`app/core/model_gateway.py::ModelGateway`：select/invoke/stream + 统一重试回退 + 结构化观测。
优先级：用户 Key > 租户模型 > 全局模型 > 系统默认。

### 双供应商跨厂商回退

- 主供应商：DeepSeek（OpenAI 兼容端点）。
- 备用供应商：OpenAI，通过 `OPENAI_FALLBACK_ENABLED` 开关控制；
  未启用或未配置密钥时自动跳过，绝不阻塞主流程。
- 主供应商故障/超时后，Gateway 按候选列表顺序自动切换到备用客户端。

## 失败与重试

`app/core/failure.py`：错误分类（transient/timeout/provider/infrastructure/permanent/business/approval）
与分层重试职责；副作用工具幂等（`tool_calls.idempotency_key`）且 claim 后禁止自动 retry
（TIMEOUT/UNKNOWN → IN_FLIGHT fail-closed）。

## Event Contract

`app/engine/events.py`：status/token/step/tool_call/tool_result/approval_required/error/
execution_completed/execution_failed/waiting_for_approval/done。前端只消费本协议。

## Observability

execution.correlation_id 为统一 trace id；ModelGateway 输出结构化 `model_call` 日志；
audit_logs 记录 HTTP 事实；事件携带 correlation_id/sequence。

## 运维与部署

- 生产：`deploy/production-deploy.sh` 记录稳定点 → 构建 → 健康门禁 → 失败自动回滚。
- 预发布：`staging` 分支 + `docker/docker-compose.staging.yml`
  （独立项目，内部端口 8001/8081/5434/6380）。
- 回滚：`deploy/rollback.sh`（默认回退 `deploy/.last-good-commit`）。
- CI 门禁：全量测试 + 核心接口 p95 延迟与功能通过率（`scripts/ci_latency_gate.py`）。
- 安全头：Nginx 前端静态层（`docker/nginx.conf`）与 FastAPI API 层双层统一。
