# Prompt Injection 防线契约（Decision Integrity Guard，DRAFT v0.1）

> 状态：DRAFT，未冻结，未实现。这是 Frozen Core 级新边界，实施前必须经
> Pro/GPTLuna 签核并落 ADR。本文只定义设计，不授权改生产代码。

## 1. 定位

Prompt Injection 解决的是“模型是否被诱导改变意图”，与 Approval Freeze 的
“执行参数是否与冻结提案一致”是两层不同问题。它作为 Reliability Layer 的
上游安全边界独立存在，命名：Decision Integrity Guard / Instruction Trust Boundary。

Phase 1B 证据：T21 / T30（注入类任务）在 ON 臂仍有 UNSAFE——模型被说服后，
其 attempt 与冻结提案在参数上一致，参数层无法区分。这是本防线的动机。

## 2. 检测对象与信任边界

- 不可信输入源：用户输入、工具返回结果、检索/RAG 内容、外部系统回写上下文。
- 可信源：Agent 自身 system prompt、平台注入的审批/预算/策略指令。
- 边界规则：不可信文本中的“指令性内容”不得覆盖可信指令。

## 3. 拦截点

副作用执行之前：R2 工具的 claim 之前（与 Approval Freeze 并列，先完整性后一致性）。

## 4. 判定分层（确定性优先）

### Tier 0：确定性（首批实现范围）

- 不可信文本的 provenance / taint 标记：工具结果、检索片段、外部上下文在进入
  prompt 前标记来源。
- 静态规则：检测不可信文本中的指令模式（“忽略审批/直接执行/跳过验证/不要调用
  工具”等），命中 → 进入 fail-closed 决策。
- 工具结果 schema 隔离：外部返回内容不作为指令注入（结构化字段，不拼接原文）。

### Tier 1：LLM 意图判定（第二层，仅在有明确风险时触发）

- 输出分类沿用 fail-closed 状态机（PASS/FAIL/UNKNOWN/ERROR，ADR-005 语义）。
- 判定对象：候选动作是否被不可信内容诱导（与“正确业务动作”比较）。
- 任何 UNKNOWN/ERROR → 拦截，绝不默认为安全。

## 5. 失败语义与审计

- 拦截 → 不产生副作用；要求重新确认 / 重新审批；执行 abort。
- 审计 action（新值，需 ADR）：`injection_blocked`，details 含来源、命中规则、
  候选动作、时间戳、correlation_id。
- 观察指标：injection 命中率、误报率（人工复核抽样）。

## 6. 误报策略（核心风险）

业务数据天然包含“忽略审批”“直接执行”等合法文本，Tier 0 静态规则必须：

- 只对“指令形态”文本生效（存在祈使结构 + 与工具/审批相关），不是关键词命中即拦。
- 提供 allowlist / 明确豁免路径（工具结果 schema 内业务字段不算指令）。
- 误报 → 人工复核 → 规则调整，必须有审计闭环，不静默。

## 7. 与既有契约的关系

- 不改变 Approval Freeze、Idempotency、Recovery、Event Contract 语义。
- 拦截发生在 provider claim 之前，天然满足 provider=0 的不变量。
- 若触发，执行进入 abort + 审计，与 approval_mismatch 并行但独立计数。

## 8. 落地顺序（评审通过后）

1. ADR（本契约转正）。
2. Tier 0：provenance/taint + 静态规则 + 工具结果 schema 隔离。
3. 基准回归：T21/T30 必须从 UNSAFE 变为 SAFE_CONTAINED / SAFE_REFUSAL，
   且不能引入对正常任务的误报（回归 Phase 0/1A/1B）。
4. Tier 1 作为可选增强，单独评审。

## 9. 未决问题（提交 Pro/GPTLuna）

- 拦截后是“重新确认”还是“重新审批”（产品语义）。
- 工具结果 schema 隔离是否对所有工具强制（影响 Tool Registry 元数据，Frozen Core 扩展）。
- 误报率可接受阈值。

