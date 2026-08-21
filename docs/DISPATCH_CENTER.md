# 动态调度中枢（Dispatch Center）架构

> 二次装修（2026-08-21）核心交付。目标：**用户接入所有模型后，发布任务，
> 平台分析复杂度、动态为每一步选最划算的模型，用最少 token 做最复杂的事，
> 全程可观看、可审计、可澄清、可回滚，最后给一张省钱账单。**

## 1. 三个闭环（"动态"的实体）

```text
闭环①（执行中）  每步路由决策 → 便宜模型先试 → 工具失败自动升级强模型（阶梯 ≤1/步）
闭环②（跨任务）  用量明细 + 成败回写 → 模型绩效档案（时间衰减）→ 路由越用越准
闭环③（跨时间）  使用数据 → 自成长 Skill 提议 / Agent 候选版本 → 门禁 → 灰度激活 → 可回滚
```

三个闭环的共同底线：**每次变化都有版本、有记录、可回滚**。

## 2. 组件与数据流

```text
用户输入 → Intent（category/flags）
  → 任务级复杂度评分 score_task（规则 + 历史统计 + 可选 LLM 法官）
  → Skill 匹配（触发词 + 文本相似）
  → Planner 产出计划 → 每步 score_step → build_route（档位 × 阈值 × 绩效）
  → 执行：ModelGateway(complexity=simple|complex) 选便宜/强模型
  → 便宜失败 → 升级阶梯重跑该步（routing_decisions 记 escalated）
  → 歧义/缺参 → 澄清中断（interrupt → 弹选项 → 用户选择 → 继续规划）
  → 副作用 → 审批冻结（T24）→ 幂等执行
  → 验证（跨模型 verifier，fail-closed）→ 完成
  → usage_events / model_performance 回写 → 省钱账单（全 pro 基线 vs 实际）
```

## 3. 新增数据模型（alembic 0020）

| 表 | 作用 |
|---|---|
| `routing_decisions` | 每步"为什么选这个模型"的审计事实（score/tier/reason/outcome/model/cost）|
| `model_performance` | 模型 × 任务类型 × 档位的成功率/成本（时间衰减，越用越准）|
| `usage_events` | 每次 LLM 调用明细（token 看板 / 省钱账单 / 自成长原料）|
| `clarifications` | 澄清问题/选项/回答/状态（pending→answered）|
| `savings_reports` | 逐期省钱账单（基线 vs 实际 vs 节省率）|
| `agent_versions` | Agent 提示词版本（candidate/active/retired，可回滚）|
| `skills`（扩展列） | source(preset/user/auto)/version/status/runtime/trigger/model_tier_hints/times_used |

## 4. 关键语义（继承 Frozen Core，未放宽）

- 副作用步骤一律强模型 + 审批冻结 + 幂等（T24 语义不变）；
- 澄清超限（≥2 次）→ 显式失败 + 零副作用（fail-closed，不猜测参数）；
- 升级阶梯硬上限：每步 1 次、每任务 4 次；触发即审计；
- 省钱不造假：unknown 价格不计入节省，基线按最贵可用单价假设；
- 自成长绝不擅自生效：候选 Skill 必须用户采纳；Agent 候选版本必须过门禁。

## 5. API 面

- `POST /api/dispatch/analyze`：发布前预览（复杂度 + Skill 匹配 + 路由方案，零 LLM 成本）
- `GET  /api/dispatch/decisions?execution_id=`：路由决策审计
- `GET  /api/dispatch/clarifications` / `POST /api/dispatch/clarifications/{id}/answer`
- `GET  /api/skills/match?input=` / `POST /api/skills/seed-presets` /
  `POST /api/skills/{id}/adopt` / `POST /api/skills/growth/run` / accept / reject / use
- `GET  /api/agent-center` / `POST /{name}/update` / `POST /versions/{id}/activate` /
  `POST /{name}/rollback`
- `GET  /api/usage/tokens?days=` / `GET /api/usage/savings`

## 6. 事件契约新增

`complexity`（评分报告）/ `routing`（预览与每步决策+结果）/ `clarification_required`（澄清中断）。

## 7. 生产证据（2026-08-21 冒烟）

- 任务"查数据库执行记录数"：复杂度 0.30 → query_db 步选便宜模型（0.33 < 0.5 阈值）→
  执行成功 → routing_decisions 1 行（outcome=success, model=deepseek-v4-flash）→
  省钱账单：实际 ¥0.0018 vs 基线 ¥0.0182，**节省 90%**。
- 澄清链：歧义 → 澄清中断落库 → 用户回答 → 重新规划 → 副作用提案 → 审批暂停 →
  批准继续 → 二次缺参 → 澄清超限 → 显式失败，**零副作用（无任何邮件发出）**。
