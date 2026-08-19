# 06 Observability Contract v1

## Trace

- 一个用户回合 = 一个 trace_id（execution.correlation_id）。
- span 集固定：intent → memory → rag → plan → step ×n → llm ×n →
  tool ×n → verify → respond。
- 每 span：start/end/latency/tokens/cost/status/model/attempt/error。

## 指标

TTFT/TTL 分位、LLM 调用次数、fallback 率、tool 失败率、审批率、
RAG 命中质量、cache 命中率、cost/请求、重试次数、每类失败计数。

## 三个 Golden Set

Intent / RAG / End-to-End。任何改动必须给出同集、同模型下的
p50/p95、准确率、成本、fallback/重试对比。

## “变好”的判定

TTFT 不升、正确率不降、成本不超阈值、无新增失败类别。
