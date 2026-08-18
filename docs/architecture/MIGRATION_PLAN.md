# Migration Plan（旧 Runtime → Kernel）

> 状态：Phase 1 基线。本文档不驱动任何代码改动，只定义"未来如何渐进迁移"。

## What

把现有 `backend/app/engine` 中的**状态与效应语义**逐步迁移到 `backend/app/kernel`，同时保留现有 Application Runtime（LangGraph / LLM / Celery / Redis / PostgreSQL / RAG / API / Workflow）继续运行。

## Why

直接重写会破坏现有可运行系统，且无法证明"新 Kernel 已覆盖旧能力"。必须：Audit → Map → Conflict → Migrate → Test → 删除旧实现，每一步都有证据。

## 迁移边界：哪些进 Kernel，哪些永久留在 App Runtime

### 最终迁移到 Kernel

| 旧实现 | Kernel 目标 |
|---|---|
| `engine/runner.py` 的执行生命周期 | `kernel/transition` 的 TransitionEngine 循环 |
| `engine/graph.py` 的角色节点/loop_check | `kernel/capability`（8 能力）+ `kernel/goal`（GoalEvaluator） |
| `engine/tools.py` 的业务工具 | 能力组合 Task（业务动作不再作为能力原语） |
| `engine/evaluator.py` 的 LLM 打分 | `kernel/goal` 的 Predicate + Evidence 判定 |
| `models/execution.py` / `workflow.py` / `agent.py` | `kernel/state` / `artifact` / `task` / `plan` 模型 |
| `engine/tool_executor.py` 的 ToolCall 审计 | `kernel/effect` 的 Command/Receipt/Observation |

### 永久留在 Application Runtime（不迁入 Kernel）

- HTTP API 路由、认证、RBAC、审计、多租户。
- LLM Gateway、Prompt、模型调用、流式输出。
- Celery / Redis / PostgreSQL、任务队列与持久化。
- RAG / 向量检索 / 文档存储。
- 真实工具（search_web / query_db / send_email）的外部连接。
- 通知、计费、告警、可观测性。
- 前端交互与 SSE/WebSocket。

这些是 Kernel 的**使用者/驱动者**，不是 Kernel 的语义本体。

## Kernel ↔ App Runtime 边界（Adapter）

未来采用一个明确的 Boundary，而不是让 App Runtime 直接读写 Kernel State：

```text
App Runtime (HTTP/LangGraph/Celery)
          |
          |  Adapter: 外部请求/LLM 输出 -> Kernel State 投影
          v
      Kernel (纯 Python + Pydantic，内存态)
          |
          |  Adapter: Kernel Command/Observation -> 真实外部 Effect
          v
     Effectful 外部系统（网络/SMTP/DB）
```

Adapter 的职责：

1. 把 LLM 输出降级为 `KnowledgeState`（L1_INFERRED / L2_SUPPORTED）。
2. 把真实工具执行结果转为 `Observation`（L3_OBSERVED）。
3. 把 Kernel 的 `Command` 翻译为真实外部调用，并回填 `ExecutionReceipt`。
4. 绝不允许 Adapter 把 Prediction 写成 Observation。

## 允许迁移的条件

对每个待迁移能力，必须同时满足：

1. Kernel 中存在对应的 State/Task/Plan/Capability 语义。
2. 对应 TEST（01–08）全部通过。
3. 现有业务测试在不经过该旧实现的情况下仍通过。
4. 迁移行为与旧实现的可观测语义等价（或明确记录了语义变化）。
5. 架构评审批准（涉及 Constitution 的变更需人工确认）。

## 允许删除旧实现的条件

1. 新 Kernel 已连续覆盖该能力 ≥ 一个迁移阶段。
2. 旧实现的调用方已全部切到 Adapter/Kernel。
3. 旧实现的测试已迁移到 Kernel 测试。
4. 生产/演示环境在关闭旧实现后仍通过回归。
5. 删除动作有单次 commit 可回滚。

## 禁止

- 迁移期间用 alias / implicit conversion / hidden compatibility layer 伪造语义等价。
- 为了让旧测试通过而把 Kernel 语义降级。
- 一次性删除旧 `engine`，然后再"希望测试能过"。

