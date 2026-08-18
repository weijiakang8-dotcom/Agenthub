# AgentHub Constitution

> 本文件是 AgentHub Kernel 的最高规范。任何 Kernel 代码、数据模型、测试、迁移与文档都不得违反。
> 现有 `backend/app/engine`、`backend/app/api`、`backend/app/models`、`backend/app/core` 属于 **Legacy/Existing Runtime**，在迁移完成前不受本文档直接约束，但不得通过 alias、implicit conversion、hidden compatibility layer 假装满足本文档。

## What

AgentHub 的核心不是 Workflow，不是 Agent，不是 LLM 编排。核心是一条可验证、可终止、确定性的 **State Transition Kernel**：

```text
Goal -> State -> Capability -> State Transition -> Goal Evaluation -> Replan -> State Transition ...
```

最终目标：

```text
AgentHub = State Space Search + Deterministic Validation + Effect Reconciliation
```

## Why

1. 没有严格 State 语义，任何"多 Agent 协作"都会退化为把 LLM 文本互相粘贴，无法证明知识来自现实。
2. 没有 Knowledge/Reality 边界，Prediction 会被当成 Observation，幻觉会在链路上级联传播且无法被检测。
3. 没有 Command/Receipt/Observation 生命周期，副作用无法对账，retry 会制造重复外部效果。
4. 没有 Evidence Level，Goal 只能靠"最后一个节点跑完"来判定，这是虚假完成。

## Formal Model

本 Constitution 由 14 条定律构成。编号在本项目内固定，后续文档和测试引用这些编号。

1. **Kernel Authority**：Kernel 是所有 State Transition 的唯一真相源；Application Runtime 只能通过 Kernel 边界提交 State 与观察结果。
2. **State Transition Model**：一切执行都表达为 `(State, Capability) -> State'` 的有向转换；State Graph 的节点是 State，边是 Capability Transition。
3. **State Projection**：State 是 Artifact 的引用/摘要投影，不是 Artifact 本身；完整产物必须存放在 Artifact Store。
4. **State Model**：State 必须严格分为 `knowledge`、`observed`、`context` 三层。
5. **Evidence Semantics**：Knowledge 中每个条目必须携带 `EvidenceLevel`（L1..L4），只能通过合法 Transition 提升。
6. **Capability Model**：系统只承认 8 个 Capability（Retrieve/Extract/Compute/Validate/Reason/Synthesize/Observe/Mutate）；业务动作是 Capability 的组合，不是 Capability 本身。
7. **Pure/Effectful**：Pure 只能写 `KnowledgeState`；Effectful 必须产生 Command，绝不能直接改写 `ObservedWorldState`。
8. **Effect Lifecycle**：Effectful 操作必须严格走 `Command -> ExecutionReceipt -> Observation -> ObservedWorldState`。
9. **Reality Cannot Be Predicted Into Existence**：模型推理、预测、模拟、Reason、Compute、Synthesize 都不能证明外部世界发生了某事；只有 `Effect + Receipt + Observation` 才能建立现实证据。
10. **Task Model**：Task 是一次 Capability Contract 的可调度实例；Task 不是 DAG Node，也不是 Agent。
11. **Plan Model**：Plan 是 State Transition Path；Plan 描述 Task/Dependency/Precondition/Expected Transition，但不绑定 Agent。Agent 由 Scheduler 在运行时分配。
12. **Goal Evaluator**：Goal 由 `predicate + required_evidence + constraints` 定义；只有 Predicate 满足、Evidence 达标、Hard Constraints 成立、且 ObservedWorldState 支持，Goal 才 SATISFIED。
13. **Determinism**：相同的 `(InitialState, Goal, Plan)` 必须产生相同结果；禁止随机数、时间、LLM 参与决策。
14. **Idempotency**：每个 Mutate 必须携带 `idempotency_key`；retry 必须复用同一 `idempotency_key`，且能证明不会制造重复副作用。

## Invariants

- 不存在"没有 Source 的 ObservedWorldState 更新"。
- 不存在"没有 Receipt 的 Observation"。
- 不存在"没有 Command 的 Receipt"。
- 不存在"没有 `idempotency_key` 的 Mutate"。
- 不存在"没有 `evidence_level` 的 Knowledge 条目"。
- `ObservedWorldState` 只能被 `Observation` 写入。
- 业务代码不能直接提升 `EvidenceLevel`。

## Forbidden

禁止（对 Kernel 而言）：

- 接入 LLM、真实网络、真实数据库、真实文件系统作为 Runtime State。
- 用随机 UUID 参与逻辑决策。
- 用当前时间参与逻辑决策。
- 引入第 9 个 Capability。
- 把业务角色（Researcher/Analyst/Coder/Writer）写进 Kernel。
- 把 DAG Node 当 Task。
- 把 Task 当 Capability。
- 把 Prediction 当 Observation。
- 把 KnowledgeState 当 ObservedWorldState。
- 让 Effectful Capability 直接 mutate State。
- 没有 Observation 就判定现实目标完成。
- 用测试预测结果代替真实观察结果。
- 为了让测试通过而放宽本文档。
- alias / magic fallback / implicit conversion / hidden compatibility layer / prompt workaround 掩盖冲突。

## Runtime Enforcement

- `Capability Registry` 是唯一能力真相源；运行时执行前必须查 Registry。
- `Transition Engine` 在 apply 前检查 Precondition，apply 后检查 Postcondition。
- `GoalEvaluator` 是唯一能返回 `SATISFIED` 的组件。
- `EvidenceLedger` 是唯一能写入 Evidence 的组件。
- `EffectLedger` 是唯一能写入 Command/Receipt/Observation 的组件。

## Failure Cases

1. Precondition 不满足却执行了 Capability → Transition 必须拒绝。
2. Postcondition 不满足却投影新 State → Transition 必须回滚为 invalid。
3. Effectful 操作只产生 Command，没有 Receipt → 不得进入 `observed`。
4. Mutate 返回 `TIMEOUT` 但外部已提交 → `observed` 必须是 UNKNOWN，等待 Observe。
5. Retry 用了新的 `idempotency_key` → 必须视为新 Effect，并触发告警/失败。
6. Goal 要求 L3 但只有 L1/L2 → 必须返回 `NOT_SATISFIED`。

## Test Requirements

- 必须有架构失败回归测试，证明 Prediction ≠ Observation。
- 必须有 Effect Lifecycle 测试，证明 Command→Receipt→Observation 不可跳步。
- 必须有 Idempotency 测试，证明 retry 不产生第二个外部效果。
- 必须有 Determinism 测试，证明同输入同输出。
- 每个 Invariant 至少对应一个失败用例。

