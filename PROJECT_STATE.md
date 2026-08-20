# AgentHub Project State

Last updated: 2026-08-20

## 当前状态

- 三运行时、认证、多租户、审批/幂等/恢复、审计、成本、告警均已生产化并上线。
- 可靠性契约（T24 / C-1 / C-4 / C-2 / Verify Fail-Closed）已实现并通过回归。
- 基准体系：Phase 0（10 事故 Case）、Phase 1A（60 runs）、Phase 1B（416 runs）、
  任务级评测看板与 `GET /api/eval/benchmark/latest` 接口。
- 双供应商回退架构：DeepSeek 主 + OpenAI 备用，可配置开关，未充值自动跳过。
- 运维体系：Staging 预发布（独立 compose 项目 + staging 分支）、生产自动回滚、
  CI 功能/延迟回归门禁、Nginx 与 API 双层安全响应头。

## 测试基线

- 后端：567 passed / 21 skipped（另 2 项为本地环境依赖：Redis、费率种子）。
- 前端：Vitest 20/20，tsc / ESLint / 生产构建通过。

## 已知边界（不做伪装）

- Prompt Injection 防线：设计稿冻结待评审，未实现。
- 真实用户流量 / 市场验证：未开展。
- 真实第二供应商：架构就绪，密钥未充值，开关保持关闭。
- Benchmark 结论为 EXPLORATORY（无 seed、单一 provider 家族、模拟副作用环境）。
