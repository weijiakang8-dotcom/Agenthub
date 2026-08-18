# Architecture Gaps

> 状态：Phase 1 基线。每个 Gap 必须满足验收标准，才视为关闭。

## What

列出当前 AgentHub 相对 Kernel 目标架构缺失的能力，并给出可执行的验收标准。

## Why

Gap 清单是迁移的验收地图，避免"实现了一堆但不知道还差什么"。

## Gap 清单与验收标准

| # | Gap | 当前状态 | Kernel 验收标准 |
|---|---|---|---|
| G1 | `State{knowledge,observed,context}` 三层类型 | 缺失（扁平 `AgentState`） | 存在 Pydantic 模型；`observed` 只能由 Observation 写入 |
| G2 | `KnowledgeState` / `ObservedWorldState` 边界 | 缺失 | Pure 写不了 `observed`；有测试 |
| G3 | `EvidenceLevel`（L1–L4） | 缺失 | 类型存在；非法跳级被拒绝 |
| G4 | `Capability`（8 类）+ Registry | 缺失（业务工具硬编码） | Registry 是唯一真相源；8 个能力注册；第 9 个被拒绝 |
| G5 | Pure / Effectful 分类 | 缺失 | 类型分类存在；Pure 无副作用 |
| G6 | `Command/Receipt/Observation` 生命周期 | 缺失（只有 ToolCall 审计） | 不可跳步；有测试 |
| G7 | `idempotency_key` 与 retry | 缺失 | Mutate 必须有 key；retry 复用；有测试 |
| G8 | `Task`（Capability Contract 实例） | 被 `Execution` 顶替 | Task 不绑 Agent/角色；有 Schema 测试 |
| G9 | `Plan`（不绑 Agent 的 Transition Path） | 被 `Workflow` 顶替 | Plan 无 agent_id；拓扑/环检测 |
| G10 | `Goal`（predicate+evidence+constraints） | 缺失（loop_check/LLM 打分） | GoalEvaluator 是唯一 SATISFIED 来源 |
| G11 | 确定性单线程内存 Runtime | 缺失（async/Celery/LLM） | TransitionEngine 确定性；同输入同输出 |
| G12 | `DeterministicWorldSimulator` | 缺失 | 覆盖 5 种结果：SUCCESS / TIMEOUT_BUT_COMMITTED / TIMEOUT_NOT_COMMITTED / DUPLICATE_REQUEST / UNKNOWN_RESULT |
| G13 | Artifact Store 与 State Projection 分离 | 缺失 | State 只存 ArtifactRef；checksum 校验 |
| G14 | Architecture Failure Regression（TEST_08） | 缺失 | 旧架构失败 / 新 Kernel 通过 |

## Forbidden

- 在没有关闭 Gap 的情况下宣称"Kernel Ready"。
- 用"旧 runtime 已有类似功能"来关闭 Gap（旧 runtime 不是 Kernel）。
- 用 mock 结果代替真实 Observation 关闭 G3/G6/G12/G14。

## Runtime Enforcement

- 每个 Gap 的关闭必须由测试证明，测试必须能被 CI 重复执行。

## Failure Cases

- 任一 Gap 未关闭但进入 Phase 3 → 视为流程违规。

## Test Requirements

- Gap 关闭以对应 Kernel 测试为唯一凭证，不以文档措辞为凭证。

