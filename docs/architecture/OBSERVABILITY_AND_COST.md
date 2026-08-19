# OBSERVABILITY_AND_COST

## Trace

- 一轮请求 = execution.correlation_id（trace_id）
- 固定 span：intent / memory / rag / plan / step / llm / tool / verify / respond
- 每 span：start/end/latency/tokens/cost/status/model/attempt/error → audit_logs（action=span:*）
- /metrics：agenthub_* gauge（dlq/pending/in_flight/fallback/latency/db/redis），抓取时刷新

## Cost（不伪造）

- 每次 provider call：usage metadata → 按 model_configs rate 计算 cost
- known rate → numeric；unknown → NULL（绝不写 0）
- per-request = 所有 provider call 之和；任一调用 unknown → 请求 cost=NULL
- fallback 每次调用独立计价；多次调用求和
- usage API：cost_unknown_executions 计数
- 历史（预部署）cost 无法准确恢复 → COST_UNKNOWN，不回填猜测值

## Baseline

- 只读 POST_DEPLOY_BASELINE（executions/tool_calls/spans/Redis 聚合）
- 区分 verification traffic / real user traffic
- 无真实用户流量 → REAL_USER_BASELINE_UNAVAILABLE（正确结论，不冒充）
