# AgentHub 架构决策记录（ADR）

## ADR-001（2026-08-19）最终架构冻结

- 状态：已接受并实施。
- 决策：三 Runtime 定型；Intent→Runtime 统一路由；能力目录取代固定
  research/analyze/execute 主链；Memory 六层定型；RAG 定型为
  Document→Chunk→pgvector；统一 Model Gateway、失败分类、Event Contract。
- 理由：消除 Chat/Agent 混用、多重状态归属、摇摆存储方案与跨层指数重试。

## ADR-002（2026-08-19）pgvector 为唯一向量存储

- 状态：已接受并实施（`document_chunks.embedding vector(768)`，Postgres 镜像
  `pgvector/pgvector:pg16`）。
- 理由：与主库同库保证一致性与租户过滤，避免引入额外服务。

## ADR-003（2026-08-19）移除 sentence-transformers 运行时依赖

- 状态：已接受并实施。
- 理由：该嵌入路径在生产无法下载模型且引入 torch 大镜像；嵌入统一由
  provider 抽象（ollama/hash/pgvector 流程）承担，ST 代码保留惰性降级但不再安装依赖。

## ADR-004（2026-08-19）Provider 超时不触发 Celery 重试

- 状态：已接受并实施。
- 理由：LLM/Tool 瞬态错误在各自层处理；Celery 只重试基础设施故障，
  避免一个 provider 超时引发整图 4 次重复执行。
