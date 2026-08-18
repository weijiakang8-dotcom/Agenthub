# Architecture Change Request

> 状态：权威 ACR 已合并到仓库根目录 [ARCHITECTURE_CHANGE_REQUEST.md](../../ARCHITECTURE_CHANGE_REQUEST.md)。
> 当前状态：**APPROVED — PHASE 1 IMPLEMENTED (2026-08-18)**，方案为 Option A（RUNTIME_MODE → 分离 runner）。
> 本文件仅保留模板，避免双份事实源。

## What

任何试图改变 Constitution、State 语义、Evidence 语义、Capability 集合、Effect Lifecycle 的行为，都必须先在此登记，等待人工架构确认。禁止直接实现。

## Why

Kernel 的最小性与确定性依赖"能力集合固定"和"语义不可漂移"。任何新增能力或语义放宽都必须显式、可审查、可回滚。

## Change Request 模板

```text
---
id: ACR-<seq>
status: PROPOSED | APPROVED | REJECTED
---

## 请求类型
（新增 Capability / 修改 State 语义 / 修改 Evidence / 修改 Effect Lifecycle / 其他）

## 为什么现有 8 个能力无法表达

## 为什么不能通过组合已有 Capability 解决

## 会影响哪些 Constitution 条款

## 最小新增/修改方案

## 影响的测试（尤其 TEST_01..TEST_08）

## 迁移与回滚计划
```

## 当前清单

（空）

## Invariants

- 任何未经 APPROVED 的变更请求不得进入代码。
- APPROVED 必须来自人工架构师，不能由 Agent 自行批准。

## Forbidden

- 以"缺能力"为名自行新增第 9 个 Capability。
- 修改本文档后不更新对应 Constitution/测试。

## Test Requirements

- 每个 APPROVED 变更都必须附带新增测试与回归测试。
