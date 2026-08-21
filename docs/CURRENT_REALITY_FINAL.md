# AgentHub CURRENT REALITY — FINAL（Living Baseline）

> 使命：Agent Production Runtime 产品化交付（自主执行，Evidence over narrative）
> 启动：2026-08-21；由 [CURRENT_REALITY_BASELINE.md](./CURRENT_REALITY_BASELINE.md) 继承并持续更新
> 原则：历史报告仅作起点；一切结论以当前代码、当前测试、当前生产运行证据为准

## 0. 当前真相（每次重大变更后更新）

| 项 | 初始事实（审计 08-21） | 当前状态 | 证据 |
|---|---|---|---|
| 产品定位 | Agent Orchestration / Workflow Executor MVP + 3 tools | 进行中 | — |
| 生产工具 | search_web / query_db / send_email | 进行中 | tool_registry.py |
| 生产工具 | search_web / query_db / search_knowledge / send_email | ✅ 4 个 + GET /api/tools + 前端工具页 | tool_registry.py + 生产验证 |
| CI | 红（backend import path / Playwright 无后端） | 本地修复完成；GitHub 待 workflow token 推送 | pytest.ini + ci.yml（本地） |
| Observability | Jaeger 0 服务 / Prometheus target down | ✅ Jaeger 有 agenthub-backend；Prometheus target up；collector 689 指标 | 生产验证 08-21 |
| query_db 失败闭环 | 失败后空输出 | ✅ 安全聚合 + 禁止空输出；生产 E2E 成功 | 生产 E2E eff7b8ee |
| RAG | hash embedding | 待升级 | EMBEDDING_PROVIDER=hash |
| Multi-Agent | 角色提示词模拟 | 待评估/补齐 | graph.py |
| T24 | 实现=契约（显式 mismatch→abort） | 保持不动 | 61 tests passed |
| Benchmark | Phase 0/1A/1B 报告存在（gitignored） | 待入库/生成机制 | reports/ |

## 1. 能力矩阵（LIVE）

（与 CURRENT_REALITY_BASELINE §6 一致，随实现逐项翻转；每项必须带测试/生产证据）

## 2. 自愈日志

| 日期 | 问题 | 根因 | 修复 | 回归 |
|---|---|---|---|---|
| 08-21 | CI backend 全红 | pytest 无 pythonpath 配置 | pytest.ini 增加 pythonpath/testpaths | 待 CI |
| 08-21 | CI Playwright 全红 | E2E 无真实后端 | CI 拆分 e2e job + postgres/redis + uvicorn | 待 CI |
| 08-21 | 生产查询失败空输出 | query_db 拒绝 COUNT + 无兜底 | 安全聚合 + fail-visible | 生产 E2E 通过 |
| 08-21 | OTel 空转/不生效 | .env 未声明字段不被 os.getenv 读取 | Settings.OTEL_SDK_DISABLED 字段 | 单测 + 生产验证 |
| 08-21 | 工具不可发现 | 只有后端注册表 | GET /api/tools + 前端工具页 | Playwright 4/4 |
| 08-21 | README 与现状不符 | 历史营销口径 | 重写为证据版 README | 文档审查 |
| 08-21 | 备份/恢复无证据 | 无脚本/演练 | scripts/backup.sh + restore.sh；生产 drill 通过（70 行对账一致） | 生产演练 |

## 3. 已知 P0/P1（见基线 §23）

## 4. 最终闸门

CI 绿 → 生产部署 → 真实 E2E → GitHub=生产 → README=现实 → 才允许 COMPLETE。

## 5. 最终一致性验证（2026-08-21）

- 本地后端全量：592 passed / 20 skipped / 0 failed。
- 本地前端：typecheck / vitest 22 / lint 0 err / build 通过；Playwright E2E 4/4。
- 生产综合 E2E（临时租户，已清理）：
  - 登录 ✅；GET /api/tools 返回 4 个真实工具 ✅；
  - “有多少条执行记录” → query_db COUNT 成功并返回可见结果 ✅（exec a6c53b8a）；
  - “今天上海天气” → search_web 成功、回答带来源 ✅（exec 129b3d56）；
  - “AgentHub 动态整理成邮件” → 搜索预检 → 实时正文提案 → 审批拒绝 → 零发信 ✅（exec 3dbeb5bc）。
- 观测：Jaeger 有 `agenthub-backend`；Prometheus `agenthub_llm_calls_24h` 实时增长。
- 备份/恢复：生产 drill 行数对账一致，临时库已删。
- 遗留 blocker：`.github/workflows/ci.yml` 已修复并本地等价验证，但推送 GitHub 需要
  **workflow scope** 的 token（当前 token 无此权限）。
