# PHASE7_PRECHECK

生成时间：2026-08-19（部署前，只读事实记录，未修改代码）。

## 本地状态

- HEAD：`b806d40daa47245de0801f775a71e154be986310`（main）
- 前置 commit：`c6cc74d`（6A）、`e9b3756`（production baseline）
- `git status`：clean（无未提交变更）
- 全量测试：`524 passed, 20 skipped, 0 failed`
- ruff：PASS；black --check：PASS；compileall：PASS
- compose config：PASS
- migration 链：0016 / 0017 / 0018 / 0019 存在且顺序正确
- secrets：tracked 文件无 `.env`/私钥；仅 example yaml 与脚本（非 secret 内容）

## Frozen Core / 契约检查

- 三 Runtime、Intent→Runtime 映射、Event Contract、Memory 分层、ModelGateway 路由、Failure/Retry 分层、Checkpoint/Resume、Kernel 边界：未修改
- Approval / Idempotency（6A Pro 冻结契约）：未重新解释

## 部署前基线（远程，稍后重新采集）

- remote commit：`e9b3756`
- migration：`0016`
- 已知历史遗留：DLQ≈11（预部署 SMTP 故障）、PENDING execution 2、PENDING tool_call 1（无 key）

## 风险

- 远程重建镜像需要网络拉取基础镜像（此前偶发 Docker Hub token 超时，重试可解）
- 远程 frontend 上游解析 backend IP 变更：部署后需 force-recreate frontend（既有已知操作）
- 远程 SSL 证书为 ignored 文件，checkout 不触碰；部署后需确认仍有效
