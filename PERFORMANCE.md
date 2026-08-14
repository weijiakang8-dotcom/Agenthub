# AgentHub 性能压测报告

## 测试目标

验证在 10 / 50 / 100 虚拟用户（VU）并发下，`POST /api/executions` 的可用性、吞吐与延迟，并量化语义缓存带来的降本增效效果。

## 测试环境

- 后端：FastAPI + Uvicorn（异步）
- 数据库：PostgreSQL 16（Docker）
- 消息队列：Celery + Redis
- 压测工具：k6

> 本仓库当前环境的 CPU / 内存规格以实际运行机器为准，建议在报告中补充。

## 运行方式

```bash
cd ~/agenthub

# 10 个虚拟用户
k6 run --summary-export=load_test_summary.json tests/load_test.js \
  -e VUS=10 -e WORKFLOW_ID=<你的工作流ID>

# 50 个虚拟用户
k6 run tests/load_test.js -e VUS=50 -e WORKFLOW_ID=<你的工作流ID>

# 100 个虚拟用户
k6 run tests/load_test.js -e VUS=100 -e WORKFLOW_ID=<你的工作流ID>
```

## 结果（待运行后填充）

| 并发 | 请求成功率 | 平均响应时间 | P95 | P99 | RPS |
|------|-----------|-------------|-----|-----|-----|
| 10   | -         | -           | -   | -   | -   |
| 50   | -         | -           | -   | -   | -   |
| 100  | -         | -           | -   | -   | -   |

## 降本增效结论

开启语义缓存后，重复/相似 Query 将直接命中缓存而不调用 LLM，目标将 `POST /api/executions` 的 P99 延迟降低约 60%，并显著减少 DeepSeek API 调用量与 Token 消耗。

> 说明：以上“P99 降低 60%”为优化目标话术，实际数值需在真实环境执行 k6 压测后填入本表。
