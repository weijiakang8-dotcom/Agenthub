# 实现 vs Contract 审计 v1

审计日期：2026-08-19。依据：docs/contracts/01–07。

## 01 Intent Contract

- ✅ 类别集合、Runtime 映射、classifier 失败 fail-open 到 CHAT 已实现。
- ❌ `IntentDecision` 缺少 `risk` 字段与内部 flags（requires_tool /
  requires_side_effect / requires_data / needs_knowledge / memory_intent /
  reference_target）。
- ❌ 低置信 + 风险迹象 → CLARIFICATION 未实现（当前一律 CHAT）。
- ❌ reference_target 未解析 → CLARIFICATION 未实现。
- ❌ 分类器输入无上下文（summary/最近轮次）。

## 02 Plan Schema

- ✅ 能力必须来自目录；未知能力被过滤；步数上限 6。
- ❌ step 缺少 step_id/input_refs/output_name/depends_on/condition/
  side_effect/requires_approval；顶层缺 goal/risk。
- ❌ 非法计划当前走 fallback_plan（静默降级），违反 plan_invalid 契约。
- ❌ Capability Registry 未静态声明 side_effect/requires_approval。

## 03 Executor Contract

- ✅ V1 串行；每步 checkpoint；工具幂等键；失败分层基础已存在。
- ❌ 无 PlanValidator / Risk-Budget Validator / plan_invalid 路径。
- ❌ 无 wall-clock/token/cost 预算执行。
- ❌ 只读/副作用预算分级未实现。

## 04 Verify & Replan

- ✅ Verify 有 PASS/FAIL 语义，revision ≤1。
- ❌ Verify 未按风险分级（LOW/MEDIUM 也走 verify）。
- ❌ replan 语义未限制为“只读步骤重排/降级”，且未重过 Validation/Approval 闸门。

## 05 Memory Policy

- ✅ WRITE/RECALL/DELETE、top-k≤3、org+user 隔离、显式写入、无自动候选。
- ❌ UPDATE（显式纠正/合并）未实现为独立动作。
- ❌ 无写入去重/合并。

## 06 Observability Contract

- ✅ 事件名集合、build_event 字段、model_call 结构化日志存在。
- ❌ 固定 span 集未持久化；无跨层 trace 查询；指标未聚合。

## 07 Constitution

- ✅ 文档已定稿；实现未违反已冻结条款。
