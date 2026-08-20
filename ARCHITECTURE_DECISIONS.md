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

## ADR-005（2026-08-20）Verify Fail-Closed 判定状态机

- 状态：已接受并实施（Pro/GPTLuna 裁决，Frozen Core 变更授权）。
- 决策：verify 判定从 fail-open 改为 fail-closed，状态机为
  PASS / FAIL / UNKNOWN / ERROR：
  - PASS：LLM 输出 trim 后、大小写不敏感的精确 "PASS" → 验证通过，继续 COMPLETED。
  - FAIL：精确 "FAIL" → 触发一次 replan（维持 revision_count==0 才 replan、≤1 的既有语义）。
  - UNKNOWN：输出为空/None/任何非精确 PASS/FAIL 内容（含 "PAS"、"OK"、"满足"）
    → 不算 PASS、不触发 replan、审计 verify_unknown + span error，业务结果保留（未验证）。
  - ERROR：LLM 调用异常/超时/解析异常 → 不算 PASS、不触发 replan、
    审计 verify_error + span error，业务结果保留（未验证）。
- 不变式：UNKNOWN/ERROR 一律不得成为 PASS；不得触发 replan（防基础设施抖动造成
  重规划循环）；verify 预算仍 ≤1；PASS/FAIL 之外的任何状态必须有审计与 span 记录。
- 判定实现为纯函数 classify_verify_output()；代码/规则 oracle 优先的原则由
  Phase 1B Evaluation（P0-2）承接，本 ADR 只冻结生产 verify 判定口径。
- 兼容性声明：本修复不追溯推翻 Phase 1A/1B 已有结论——那些结论使用代码级
  FIELD/JUDGE 语义 oracle，verify 仅为被记录的机制指标。
