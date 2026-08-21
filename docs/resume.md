# 简历项目描述（可直接复制到简历）

## AgentHub —— 动态模型调度中枢（多 Agent 协作平台）

**项目简介**

AgentHub（对外品牌 synplex，生产 https://synplex.xyz）是一个多 Agent 协作平台：用户接
入自己持有的多模型 API 后发布任务，平台先做复杂度评分与 Skill 匹配，再为执行计划的每
一步**动态选择最划算的模型**（便宜模型失败自动升级强模型），用最少的 token 完成最复杂
的任务；执行全程可观看、可审计、可澄清、可回滚，最后给出省钱账单（真实生产验证节省
90% 成本）。平台自带 6 个 Agent（调度/规划/执行/验证/澄清/记账），并具备自成长能力：
从使用数据自动打包 Skill、对 Agent 提示词做版本化自更新（候选→门禁→灰度→回滚）。

**技术栈**

Python 3.11 / FastAPI / LangGraph（checkpoint + interrupt）/ Celery / Redis / PostgreSQL 16
(pgvector) / SQLAlchemy 2.0 + Alembic / Ollama embedding / React / TypeScript / Vite /
Docker Compose / GitHub Actions / OpenTelemetry（Jaeger + Prometheus）

**个人工作与亮点**

- 设计并实现**复杂度评分器**（规则 + 历史统计 + LLM 法官三层混合）与**路由策略引擎**：
  三档成本策略 × 逐级升级阶梯，每次路由决策落库可审计（routing_decisions）。
- 基于 LangGraph 实现统一执行图：意图路由、计划校验、副作用**审批冻结（T24）**、
  **幂等 claim**（副作用恰执行一次）、UNKNOWN fail-closed、reconciliation、
  checkpoint/resume、DLQ；61+ 契约/集成测试保障可靠性语义。
- 实现**澄清中断**：执行中遇语义歧义弹选项、用户选择后从断点继续，选择全程留痕。
- 构建 **Skill 系统**（8 个预设包 + 触发词/向量匹配 + 自成长打包）与**多 Agent 自更新
  管线**（候选版本 → 结构/指标门禁 → 激活/回滚，全程版本化审计）。
- 实现**成本闭环**：每次 LLM 调用的 token/cost 明细入库，模型绩效档案（时间衰减）反向
  驱动路由"越用越准"，省钱账单按"全 pro 基线 vs 实际"逐期计算。
- 多租户（org 隔离 + query_db 强制租户谓词）、RBAC、JWT 认证、防爆破限流、审计脱敏。
- 前端 React + TS：调度中心 / Skill 库 / Agent 中心 / 省钱账单 / 执行轨迹与审批面板；
  后端 658 测试、前端 vitest 22 + Playwright E2E 7/7；全新库迁移 0001→0020 通过。

**结果**

- 生产（synplex.xyz）真实运行：复杂度评分 → 动态路由 → 执行 → 决策留痕 → 省钱账单全链
  路验证，单任务实测成本为"全程最强模型"基线的 10%；澄清→审批→超限 fail-closed 零副作用。
- 观测闭环：Jaeger/Prometheus 生产有数据；部署/回滚/备份恢复完成真实演练。
