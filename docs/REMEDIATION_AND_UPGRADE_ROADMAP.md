# AgentHub 修复与升级路线图

## 1. 目标与原则

本路线图把当前工作分为三类：

1. **生产风险修复**：先解决越权、SSRF、认证撤销、任务重复执行和部署安全问题；
2. **能力补实**：把 README/简历中的架构能力补成可复现、可评测、可观测的真实能力；
3. **可量化升级**：建立评测集和指标看板，后续所有“提升”都必须有基线、样本和报告。

执行原则：

- P0/P1 修改认证、租户隔离、执行状态机、幂等和部署链路，均属于**核心代码修改**，实施前需单独确认；
- 每个阶段独立分支、独立迁移、独立回滚点，不同时重构安全边界和业务功能；
- 修复必须先有失败测试，再改实现；涉及跨租户访问的接口统一返回 404，避免资源枚举；
- 未通过验收门禁的能力只能标记为实验性，不写入“已上线能力”或简历结果。

## 2. 优先级总览

| 阶段 | 周期建议 | 目标 | 核心交付物 | 发布条件 |
| --- | --- | --- | --- | --- |
| P0 | 1-2 周 | 封堵直接安全风险 | 租户策略、SSRF 防线、认证撤销、上传限制 | 安全回归全绿 |
| P1 | 2-3 周 | 保证 Agent 副作用可靠 | Lease/Heartbeat、状态 CAS、Outbox、显式审批 | 故障注入全绿 |
| P2 | 1-2 周 | 统一生产与交付基线 | Compose 收敛、可信代理、镜像与依赖锁定 | 灰度/回滚演练通过 |
| P3 | 2-4 周 | 补实 RAG 与模型路由价值 | 混合召回、Rerank、路由回放、指标体系 | 离线评测报告通过 |
| P4 | 2-4 周 | 建立 Skill/Agent 数据闭环 | 反馈数据集、候选门禁、版本评测 | 人工采纳后才能上线 |
| P5 | 持续 | 性能、桌面端与开源体验 | WebSocket、拆包、文档、Release | SLO 与发布清单通过 |

---

## 3. P0：生产安全止血

### 3.1 租户隔离与 RBAC

**问题范围**

- `dispatch/decisions`、`dispatch/clarifications` 在传入 `execution_id` 时绕过组织过滤；
- Eval 可引用其他组织的 Workflow；
- Agent、Skill 执行、Workflow rollback、Alert policy 等写接口缺少统一权限门禁；
- `skills/seed-presets` 与 `/metrics` 暴露范围不符合生产边界；
- Conversation 当前按组织而非用户归属控制，同组织成员可读取彼此对话。

**Action**

- 建立 `ResourceScope`/Repository 层，所有资源查询必须同时携带 `organization_id`，用户私有资源再追加 `user_id`；
- 禁止路由中使用“传 ID 时跳过 org filter”的 `if/elif` 模式；
- 为读、写、执行、审批、审计建立权限矩阵，并统一使用 `require_permission()`；
- 将全局预设播种改为受保护的管理命令或启动迁移，不保留匿名写接口；
- `/metrics` 仅在内部网络开放或增加独立监控凭据；
- 增加覆盖所有资源类型的参数化跨租户测试。

**验收标准**

- 两个组织、admin/member/viewer 三种角色完成 API 权限矩阵测试；
- 任意外部资源 UUID 在 GET/UPDATE/DELETE/EXECUTE/APPROVE 下均不可越权；
- 新增路由必须通过 tenant-scope 静态检查或测试辅助器。

### 3.2 SSRF、上传与外部调用边界

**Action**

- 抽取 `SafeOutboundHttpClient`，统一 DNS 解析、公网 IP 校验、重定向复验、超时、响应大小和允许协议；
- 将 Notification webhook、Kernel HTTP effect、模型发现全部迁移到该客户端；
- 文档上传改为流式读取，增加请求体上限、文件大小、页数、解析时限、MIME/魔数校验和异步解析队列；
- 对 webhook 和上传增加组织级速率及并发限制。

**验收标准**

- loopback、RFC1918、link-local、IPv6 private、DNS rebinding 和跨域 redirect 测试全部拒绝；
- 超大 PDF、压缩炸弹、伪扩展名和慢解析均受限且不占满 API worker。

### 3.3 JWT 与凭据生命周期

**Action**

- Access Token 缩短生命周期，Refresh Token 引入 `jti`、哈希存储、单次轮换和 token family；
- 密码重置、登出、账号停用时撤销对应 refresh family，并校验 `password_changed_at`；
- Web 端评估 httpOnly/SameSite Cookie；桌面端使用系统安全存储，不继续将 refresh token 长期放在 localStorage；
- staging 与 production 均启用强 secret 启动检查。

**验收标准**

- 旧 refresh token 在轮换、登出、改密后立即失效；
- 重放已使用 token 可检测并撤销整组会话；
- 浏览器存储和日志中不出现 refresh token。

---

## 4. P1：Agent 可靠执行内核

### 4.1 Lease、Heartbeat 与取消语义

**问题范围**

- 长任务不更新 `updated_at`，可能被 15 分钟 stale job 误判失败；
- cancel/intervene 只改数据库状态，运行中的图仍可继续产生副作用；
- resume/intervene 在 broker enqueue 失败时可能永久停在 RUNNING。

**Action**

- 为 Execution 增加 `lease_owner`、`lease_expires_at`、`heartbeat_at` 与 `run_attempt`；
- Worker 周期续租，每个节点和工具执行前检查租约与取消令牌；
- stale reconciliation 只回收过期租约，不依据普通 `updated_at`；
- enqueue 采用事务 Outbox：状态变更与任务事件同事务提交，由 dispatcher 可靠投递；
- cancel 定义为“停止调度新步骤”，对已发出的副作用进入 reconciliation，而非虚假宣称已撤销。

### 4.2 状态机 CAS 与副作用幂等

**Action**

- 将 Execution 状态迁移集中到一个 transition service，所有迁移带 expected-status CAS；
- 禁止 FAILED 任务无条件重新进入 RUNNING；重试必须创建 attempt，并继承冻结计划；
- 幂等键以 execution/plan version/step/tool/frozen args 计算并建立数据库唯一约束；
- 将 `PENDING → RUNNING → WAITING → terminal` 转换规则编码为测试矩阵；
- Tool approval 改为显式 `approved is True`，空对象、缺字段和未知决定全部拒绝。

### 4.3 Durable Event 与计费一致性

**Action**

- 用 Outbox/Event Log 替代仅 Redis Pub/Sub 的一次性事件；
- event sequence 在数据库中原子递增，客户端支持按 sequence 补拉；
- 仅当终态 CAS 成功后结算 usage/cost，失败 attempt 单独记录实际消耗；
- resume/evaluate/intervene 任务统一异常收敛、DLQ 和状态回写。

**故障注入验收**

- Worker kill、Redis 断开、DB commit 前后崩溃、LLM 超时、审批中断和重复投递；
- 同一冻结副作用在任意重放下最多提交一次；
- 终态、审计、事件和账单可以从数据库事实重建。

---

## 5. P2：生产部署与供应链收敛

### 5.1 唯一生产 Compose

**Action**

- 明确 `docker-compose.prod.yml` 为唯一生产定义，或删除它并把主 Compose 参数化；禁止两个漂移配置并存；
- 删除生产路径中的默认 `postgres:postgres`、Grafana `admin` 等弱凭据；
- 增加根 `.dockerignore`，排除 `.git`、`node_modules`、缓存、测试产物和本地环境文件；
- 修正 Docker COPY 层，确保 `npm ci` 的容器依赖不会被宿主 `node_modules` 覆盖；
- pin 生产镜像、Python 依赖和 GitHub Actions 到明确版本/摘要。

### 5.2 可信代理与健康门禁

**Action**

- Nginx 覆盖用户传入的 Forwarded headers，后端仅在直连来源属于可信代理时读取；
- 原始 IP Host 的 HTTP 请求统一跳转 HTTPS，不提供明文 API；
- `/live` 只检查进程，`/ready` 检查 DB/Redis，LLM provider 单独作为 dependency 状态；
- 部署回滚不再依赖第三方 LLM 短暂可用性，外部 provider 故障触发降级而非代码回滚。

### 5.3 CI/CD 门禁

**Action**

- CI 强制 Ruff、Black、ESLint、Prettier、unit/integration/e2e、镜像构建与 SBOM；
- 增加 secret scan、依赖漏洞、容器漏洞与许可证扫描；
- README 只引用实际使用的部署脚本，删除或归档旧脚本；
- K8s 若保留则补资源请求/限制、探针、NetworkPolicy、固定镜像和健康路由，否则标记为实验资产。

**验收标准**

- 新机器可按文档从零构建；生产配置无默认密码；
- 灰度发布、失败回滚、数据库恢复和 provider 降级演练均有记录。

---

## 6. P3：补实 RAG 与多模型动态路由

### 6.1 RAG 2.0：混合召回与可验证回答

**Action**

- 建立文档解析规范：标题层级、表格、代码块、页码与来源坐标保留；
- 实现 Dense(pgvector) + BM25 + metadata filter 多路召回，采用 RRF 融合；
- 增加 Query Rewrite、HyDE（按场景开关）、Cross-Encoder Rerank 与上下文压缩；
- 回答必须携带 citation，检索证据不足时拒答，不让模型补齐未知事实；
- 建立离线数据集，覆盖命中、跨段、表格、无答案、冲突文档和 prompt injection。

**指标**

- Retrieval：Recall@K、MRR、nDCG；
- Answer：Faithfulness、Answer Relevance、Citation Precision；
- System：TTFT、P95、Token/请求、Cost/成功回答。

### 6.2 路由策略从“规则”升级为“可评测决策”

**Action**

- 记录每次候选模型、选择原因、质量、延迟、成本与升级路径；
- 建立离线 replay，对成本优先/均衡/质量策略做 Pareto 对比；
- LLM Judge 采用盲评、多 judge 或规则校验，避免单一模型自评；
- 路由策略版本化并支持 shadow/canary，不直接在线自动改阈值；
- 为 provider 故障建立 circuit breaker、bulkhead 和 fallback 预算。

**验收标准**

- 每次“更省/更准”都能指向固定数据集、基线版本和报告；
- 在质量约束下比较成本，在成本约束下比较质量，不用单一指标吹效果。

---

## 7. P4：Skill 与 Agent 数据闭环

### 7.1 反馈数据产品化

**Action**

- 收集显式评分、重试、人工改写、工具拒绝、最终采纳等信号；
- 将失败样本按规划、检索、模型、工具、权限、基础设施分类；
- 构建去敏、去重、版本化的数据集，保留数据来源与 consent；
- 不直接用在线数据微调，先用于 Prompt/Skill/路由离线评测。

### 7.2 候选生成与发布门禁

**Action**

- Skill/Agent 候选必须包含来源样本、变化 diff、适用范围和回滚版本；
- 依次执行结构校验、安全回归、离线评测、shadow、人工采纳、canary；
- 线上表现下降自动停用候选，不自动覆盖稳定版本；
- 建立 Agent/Prompt/Tool schema/Model policy 四类独立版本，避免一个大版本不可归因。

**验收标准**

- 任一线上 Agent 行为可追溯到版本、数据集、评测报告和审批人；
- “自成长”仅表示自动产生候选，不表示绕过人审自动改生产。

---

## 8. P5：客户端、性能与开源体验

### 8.1 Web 与桌面端

- WebSocket 地址从 API 配置派生，补 Vite `/ws` proxy 与 Tauri 生产连接测试；
- 移除 WebSocket query token，改用短期一次性 ticket 或安全握手；
- 统一 Auth Provider，展示真实用户身份并完成完整路由守卫；
- 对图编辑器、图表、Markdown 高亮做 lazy load，控制首屏 bundle；
- 建立 Markdown XSS、401 refresh、WS reconnect 和桌面 E2E 回归。

### 8.2 开源工程

- README 区分“已验证、实验性、规划中”，附架构图、真实截图和 benchmark 方法；
- 增加 CONTRIBUTING、SECURITY、威胁模型、ADR、版本策略和兼容矩阵；
- Apache-2.0 发布补 NOTICE（仅在存在需归属通知时）、Release notes、SBOM 和镜像签名；
- 用可复现实验报告替代没有数据来源的性能宣传。

---

## 9. 简历亮点与工程证据映射

| 简历表述 | 必须补齐的证据 |
| --- | --- |
| 多模型动态调度降低成本 | 固定评测集、路由版本、质量约束、成本基线与 replay 报告 |
| RAG 缓解幻觉 | Recall/MRR/Faithfulness、无答案拒答与 citation 测试 |
| 副作用恰一次 | 重复投递/崩溃故障注入、唯一约束和 reconciliation 报告 |
| 可中断、可恢复 | Checkpoint、Lease、Outbox 与 resume 故障测试 |
| 自成长 Skill/Agent | 候选来源、离线门禁、人工采纳、canary 和回滚记录 |
| 全链路可观测 | trace/log/metric 关联截图、SLO、告警和故障复盘 |
| 生产级交付 | 可复现镜像、CI 门禁、灰度、回滚和恢复演练 |

在上述证据完成前，简历应使用“设计/实现了某机制”，不要使用没有基线的“显著提升”“生产级恰一次”“自动自优化”等结果性表述。

---

## 10. 建议的首批实施包

### PR-1：Tenant Guard（P0，核心代码，需确认）

- 修复 dispatch/eval 越权；
- 保护 seed-presets/metrics；
- 统一 agents/workflows/skills/alerts 权限；
- 增加跨租户参数化回归测试。

### PR-2：Safe Outbound + Upload Limits（P0，核心代码，需确认）

- Notification/Kernel 统一 SSRF 防线；
- 上传大小、页数、MIME、超时和并发限制；
- 恶意 URL/PDF 测试集。

### PR-3：JWT Session Lifecycle（P0，核心代码 + migration，需确认）

- Refresh family、轮换、撤销与改密失效；
- Web/Tauri token 存储策略；
- 会话管理与重放测试。

### PR-4：Execution Lease + Explicit Approval（P1，核心代码 + migration，需确认）

- Lease/heartbeat/cancel token；
- 状态迁移 CAS；
- 审批 fail-closed；
- 长任务和并发故障注入。

### PR-5：Production Baseline（P2，部署配置，需确认）

- 唯一 Compose、`.dockerignore`、凭据和镜像 pin；
- 可信代理与分层健康检查；
- CI lint/format/security 门禁。

完成 PR-1 至 PR-5 后，再进入 RAG、路由和数据闭环升级，避免在不安全、不可靠的底座上继续堆功能。
