# AgentHub CURRENT REALITY — FINAL（Living Baseline）

> 使命：Agent Production Runtime 产品化交付（自主执行，Evidence over narrative）
> 启动：2026-08-21；由 [CURRENT_REALITY_BASELINE.md](./CURRENT_REALITY_BASELINE.md) 继承并持续更新
> 原则：历史报告仅作起点；一切结论以当前代码、当前测试、当前生产运行证据为准

## 0. 当前真相（每次重大变更后更新）

| 项 | 初始事实（审计 08-21） | 当前状态 | 证据 |
|---|---|---|---|
| 产品定位 | Agent Orchestration / Workflow Executor MVP + 3 tools | 进行中 | — |
| 生产工具 | search_web / query_db / send_email | 进行中 | tool_registry.py |
| CI | 红（backend import path / Playwright 无后端） | 已修配置，待 CI 验证 | ci.yml + pytest.ini |
| Observability | Jaeger 0 服务 / Prometheus target down | 待修 | jaeger/prometheus 查询 |
| query_db 失败闭环 | 失败后空输出 | 待修 | 生产 E2E c20e27ff |
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

## 3. 已知 P0/P1（见基线 §23）

## 4. 最终闸门

CI 绿 → 生产部署 → 真实 E2E → GitHub=生产 → README=现实 → 才允许 COMPLETE。
