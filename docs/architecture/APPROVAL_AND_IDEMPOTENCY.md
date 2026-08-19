# APPROVAL_AND_IDEMPOTENCY（Pro 冻结契约，不可变输入）

## Approval 参数冻结（Decision C）

审批载荷：

{plan_hash, approval_id, side_effect_proposals:[{step_id, capability, tool, params, params_canonical}]}

- params_canonical：全局唯一实现（去 null、key 排序、JSON 稳定序列化、数值语义统一）；Approval 与 Idempotency 共用
- 提案在 Approval 前生成并冻结；Approval 后不得重新生成参数
- 每个 side_effect step 恰好一次 tool call；0 次或多次 → mismatch
- tool 或参数任何不一致 → approval_mismatch → audit → FAILED → 重新审批
- replan 改变任何提案字段 → 新 plan + 新 approval；resume 携带 modified_plan → 拒绝
- resume 校验 plan_hash + approval_id；不匹配 → 拒绝 + audit
- Phase 10：approval_required 事件在 DB waiting 状态 COMMIT 之后发射；resume API 对非 waiting 返回 409 且无副作用

## Idempotency 状态机（Decision B）

key = sha256(execution_id + tool + params_canonical)；不支持 external key。

- PENDING+key → atomic claim → IN_FLIGHT
- SUCCESS → 返回缓存结果，不再执行
- FAILED → 不 retry / 不 replay / 不 replan
- REJECTED → 不执行
- IN_FLIGHT → UNKNOWN → fail-closed
- 工具层 duplicate 视同 SUCCESS 幂等结果（Phase 9 修复）

崩溃后不重复发邮件的原因链：
params_canonical + idempotency_key + atomic claim（provider 调用前提交）+
tool_calls 为唯一事实源 + IN_FLIGHT fail-closed。
