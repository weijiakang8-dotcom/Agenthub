# 02 Plan Schema v1

```json
{
  "goal": "string",
  "risk": "LOW | MEDIUM | HIGH | SIDE_EFFECT",
  "steps": [
    {
      "step_id": "string",
      "capability": "CAPABILITIES 目录中的名称",
      "description": "string",
      "input_refs": ["前序 output_name 或原始输入"],
      "output_name": "string",
      "depends_on": ["step_id"],
      "condition": "可选，在 node_outputs 上求值",
      "side_effect": "bool",
      "requires_approval": "bool"
    }
  ]
}
```

## 约束

- capability 只能来自 `app/engine/capabilities.py` 目录。
- side_effect 只能来自能力目录的静态声明，Planner 不得伪造。
- 计划必须无环、依赖必须存在、步数 ≤6。
- 复合任务强制三阶段骨架：Gather（只读）→ Synthesize（analysis）→
  Commit（副作用，串行）→ Verify（按策略）。
- V1 Executor 串行执行；`parallel/condition/depends_on` 字段从第一天
  保留，供未来 Executor 升级，不重新设计 Planner。
- 非法计划输出 `plan_invalid`，不允许静默降级。

## plan_hash 与 approval

- 副作用步骤集合确定后计算 `plan_hash`；审批对象是
  {plan_hash, approved_side_effect_set, approval_id} 的不可变摘要。
- replan 不得增改副作用集合；变化必须重新审批。
