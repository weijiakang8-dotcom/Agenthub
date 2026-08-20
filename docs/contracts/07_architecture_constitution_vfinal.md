# AgentHub Architecture Constitution vFinal

状态：定稿。本文档为六份 Contract 的汇总与最高裁决依据。

## Frozen Core（不得直接修改）

1. 三 Runtime 边界：Chat 同步流式 / Agent 异步执行 / Kernel 确定性内核。
2. Intent 是决策层：只决定 WHAT/WHERE，不执行业务；Runtime 唯一入口。
3. Runtime ≠ Complexity：complexity 只影响模型策略。
4. 单轮单主目标；含副作用的多目标必须先确认，不得擅自执行。
5. Approval 授权的是不可变副作用集合（plan_hash/approval_id），
   不是授权 Agent 自由发挥；验证必须先于审批。
6. 非法计划 → plan_invalid，禁止静默降级。
7. 预算按副作用区分强制等级；副作用预算超限禁止自动 replan。
8. Verify 只有 PASS/FAIL 职权；replan 必须重过全部验证与审批闸门。
   （ADR-005 补充：UNKNOWN/ERROR 不算 PASS、不触发 replan；判定 fail-closed。）
9. Memory 分层与归属；Cache 永不视为 Memory；V1 显式写入。
10. 所有模型调用必须经 Model Gateway；业务代码禁止写死模型。
11. Failure/Retry 分层；副作用必须幂等；Provider 超时不触发 Celery 重试。
12. Event Contract、Tenant Isolation、Checkpoint/Resume、
    Persistence Ownership 保持现有定义。
13. Chat 性能红线：不进 Celery、不无条件 RAG/checkpoint/tool、不等评测。

## 扩展点（允许扩展）

意图能力、能力目录、Plan 字段、Executor 并行度、Memory 动作、
RAG 检索策略、Model 策略、Event 字段（向后兼容）、观测指标。

## 重新打开架构的条件

仅当出现：Contract 冲突 / Frozen Core 冲突 / 跨 Runtime 问题 /
无法解释的系统级失败 / 重大性能与正确性权衡。
必须先写 ADR，并由 Pro 复审，禁止在 Flash 实现期自行重开。

## 实施门禁

Contract 定稿 → Golden Tests → Implementation → Benchmark → Production。
