# 01 Intent Contract v1

## 1. 输出契约（唯一对外结构）

```text
IntentDecision {
  category: CHAT | KNOWLEDGE | TASK | ACTION | CLARIFICATION
  runtime:  chat | agent          # 仅由 category 映射，禁止其他逻辑决定
  complexity: simple | complex    # 只影响模型策略，永不参与 Runtime 选择
  risk: LOW | MEDIUM | HIGH | SIDE_EFFECT
  confidence: float               # 0..1
  reason: string
  fallback: boolean
  内部属性（不对外成为 Runtime）:
    requires_tool, requires_side_effect, requires_approval,
    requires_data, needs_knowledge, memory_intent, reference_target
}
```

Runtime 映射固定：

```text
CHAT            → chat
KNOWLEDGE       → chat（按需 RAG，检索为空则普通回答）
TASK            → agent
ACTION          → agent（先审批）
CLARIFICATION   → chat（只追问，不创建 Execution）
```

## 2. 判定顺序（命中即停）

```text
1. reference_target 无法解析且意图依赖它      → CLARIFICATION
2. 多目标且其中含副作用                      → 只识别副作用意图，其余下一轮
3. requires_side_effect                     → ACTION
4. requires_tool 或 requires_data           → TASK
5. needs_knowledge 且无工具                  → KNOWLEDGE
6. 其他                                      → CHAT
```

## 3. 硬规则

- 低置信 + (requires_side_effect | requires_tool | requires_data) → CLARIFICATION。
- 分类失败/输出非法/低置信且无风险迹象 → CHAT（fail-open）。
- 有风险迹象时禁止 fail-open 成 CHAT。
- `memory_intent=save/recall` 不改变 Runtime，由 Memory Policy 处理。
- Intent 只产生决策，不执行任何业务动作。
- Risk 由确定性规则计算：副作用→SIDE_EFFECT；多步查询分析→HIGH；
  多步推理→MEDIUM；其余→LOW。

## 4. 验证集覆盖

普通聊天、知识查询、数据库查询、工具调用、副作用、指代、多意图、
隐含意图、记忆、低置信、恶意/异常输入、边界输入。每类 ≥3 条，长期目标 100+。

## 5. 待基准确定的参数

confidence 阈值（默认 0.5），由 golden set 基准在阶段 1 定值。
