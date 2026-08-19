# AgentHub 架构宪法（Frozen Core）

以下为 Frozen Core：后续业务需求不得直接修改，只能通过既定扩展点接入。
确需修改时必须先新增 ADR（见 ARCHITECTURE_DECISIONS.md）说明理由。

1. Runtime 边界：Chat 同步流式、Agent 异步执行、Kernel 确定性内核，三者不得混用。
2. Intent → Runtime 路由：只有 IntentRouter 的决策决定 Runtime；complexity 不路由 Runtime。
3. Execution 生命周期：PENDING → RUNNING → WAITING_FOR_APPROVAL / COMPLETED / FAILED，
   状态由 Execution 唯一持有。
4. Memory 分层与归属：Conversation / Long-term / Knowledge / Execution / Cache 不得互相替代。
5. Event Contract：前端只消费 `app/engine/events.py` 定义的事件名。
6. Model Gateway：业务代码禁止直接构造 ChatOpenAI 或写死模型 ID。
7. Retry/Failure Policy：所有重试必须先经 `app/core/failure.py` 分类；副作用必须幂等。
8. Tenant Isolation：Memory/RAG/Model/Tool/Execution/Cache/Audit 必须 org+user 隔离。
9. Checkpoint/Resume：LangGraph checkpoint 为唯一可恢复状态来源。
10. Kernel 边界：Kernel 只依赖 EffectPort/Constitution 抽象，不得反向依赖 Web/DB。
11. Persistence Ownership：每类数据只有一个写入者（见 ARCHITECTURE.md）。
12. Chat 性能红线：普通 Chat 不得进入 Celery、无条件 RAG、无条件 checkpoint/tool，
    不得等待后台评测；后台任务必须与用户响应解耦。

## 扩展点

- 新意图类别：`app/engine/intent.py` IntentCategory + IntentRouter（需 ADR）。
- 新能力/工具：`app/engine/capabilities.py` CAPABILITIES + `app/engine/tools.py`。
- 新嵌入 Provider：`app/rag/embedder.py`。
- 新模型策略：`app/core/model_gateway.py::ModelGateway`。
- 新事件字段：`app/engine/events.py`（向后兼容添加）。
- 新 Memory 类型：`app/memory/`（不得复用 cache/execution 表）。
