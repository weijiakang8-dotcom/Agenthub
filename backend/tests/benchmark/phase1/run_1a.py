"""Phase 1A 入口：5 tasks × 4 arms × 3 trials = 60 runs（真实 DeepSeek 调用）。

运行：BENCH_REAL_MODELS=1 python -m tests.benchmark.phase1.run_1a
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

from tests.benchmark.phase1.model_matrix import ARMS
from tests.benchmark.phase1.oracle1 import REPRESENTATIVE_1A_TASKS
from tests.benchmark.phase1.runner1 import run_trial

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def _arm_metrics(records: list[dict]) -> dict:
    n = len(records)
    safe = sum(1 for r in records if r["safe_success"])
    serious = sum(len(r["serious_unsafe_event"]) for r in records)
    latencies = [r["latency_ms"] for r in records]
    costs = [r["cost_cny"] for r in records if r["cost_cny"] is not None]
    safe_costs = [r["cost_cny"] for r in records if r["safe_success"] and r["cost_cny"] is not None]
    return {
        "runs": n,
        "safe_success": safe,
        "safe_success_rate": round(safe / n * 100, 1) if n else 0.0,
        "serious_unsafe_events": serious,
        "serious_unsafe_events_per_100": round(serious / n * 100, 1) if n else 0.0,
        "mean_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 1) if latencies else None,
        "total_cost_cny": round(sum(costs), 6) if costs else None,
        "cost_per_safe_success_cny": round(sum(safe_costs) / len(safe_costs), 6) if safe_costs else None,
        "total_input_tokens": sum(r["input_tokens"] for r in records),
        "total_output_tokens": sum(r["output_tokens"] for r in records),
    }


def _compare(label: str, left: dict, right: dict) -> dict:
    def delta(key: str):
        l, r = left.get(key), right.get(key)
        if l is None or r is None:
            return None
        return round(r - l, 3)

    return {
        "comparison": label,
        "safe_success_rate_delta": delta("safe_success_rate"),
        "serious_unsafe_events_per_100_delta": delta("serious_unsafe_events_per_100"),
        "cost_per_safe_success_delta_cny": delta("cost_per_safe_success_cny"),
        "mean_latency_delta_ms": delta("mean_latency_ms"),
        "total_tokens_delta": (
            (right.get("total_input_tokens", 0) + right.get("total_output_tokens", 0))
            - (left.get("total_input_tokens", 0) + left.get("total_output_tokens", 0))
        ),
    }


def _write_report(records: list[dict]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    by_arm = {arm: [r for r in records if r["arm"] == arm] for arm in ARMS}
    metrics = {arm: _arm_metrics(by_arm[arm]) for arm in ARMS}
    comparisons = [
        _compare("A→B (small + Layer)", metrics["A"], metrics["B"]),
        _compare("C→D (large + Layer)", metrics["C"], metrics["D"]),
        _compare("A→C (bare small vs bare large)", metrics["A"], metrics["C"]),
        _compare("B→D (layered small vs layered large)", metrics["B"], metrics["D"]),
    ]
    payload = {
        "experiment": "PHASE_1A_REAL_MODEL_BENCHMARK",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": "EXPLORATORY (n=5 tasks, 3 trials, no seed, single provider family, simulated side effects)",
        "metrics_per_arm": metrics,
        "comparisons": comparisons,
        "records": records,
    }
    json_path = REPORT_DIR / "phase1a_report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, metrics, comparisons, records)
    return json_path


def _write_markdown(payload: dict, metrics: dict, comparisons: list[dict], records: list[dict]) -> None:
    lines: list[str] = []
    add = lines.append
    add("# PHASE1A_REPORT — 真实模型四象限 Benchmark")
    add("")
    add(f"- 生成时间：{payload['generated_at']}")
    add("- 状态：EXPLORATORY")
    add("")
    add("## 1. Experiment Status")
    completed = sum(1 for r in records if r["success"])
    failed = sum(1 for r in records if not r["success"])
    add(f"- 60 runs 要求：{len(records)} runs；completed={completed}；failed={failed}；blocked=0")
    add("")
    add("## 2. 四象限结果")
    for arm in ("A", "B", "C", "D"):
        m = metrics[arm]
        add(
            f"- **Arm {arm}**（{ARMS[arm]['model']} + {ARMS[arm]['reliability']}）："
            f"SSR={m['safe_success_rate']}% ({m['safe_success']}/{m['runs']})；"
            f"SUE/100={m['serious_unsafe_events_per_100']}；mean={m['mean_latency_ms']}ms；"
            f"p95={m['p95_latency_ms']}ms；total_cost={m['total_cost_cny']} CNY；"
            f"cost/SS={m['cost_per_safe_success_cny']} CNY"
        )
    add("")
    add("## 3. 每 arm 指标")
    add("| arm | model | SSR | SUE/100 | recovery | mean ms | p95 ms | total cost CNY | cost/SS CNY |")
    add("|---|---|---|---|---|---|---|---|---|")
    for arm in ("A", "B", "C", "D"):
        m = metrics[arm]
        add(
            f"| {arm} | {ARMS[arm]['model']} | {m['safe_success_rate']}% | "
            f"{m['serious_unsafe_events_per_100']} | N/A(1A) | {m['mean_latency_ms']} | "
            f"{m['p95_latency_ms']} | {m['total_cost_cny']} | {m['cost_per_safe_success_cny']} |"
        )
    add("")
    add("## 4. 每 task 结果")
    for task_id in REPRESENTATIVE_1A_TASKS:
        task_records = [r for r in records if r["task_id"] == task_id]
        safe = sum(1 for r in task_records if r["safe_success"])
        reasons = [f"{r['arm']}:{r['failure_reason']}" for r in task_records if not r["safe_success"]]
        add(f"- {task_id}: {safe}/{len(task_records)} safe success；unsafe={reasons}")
    add("")
    add("## 5. 每 trial 结果")
    add("| task | arm | trial | safe | safety | semantic | tool | terminal | in tok | out tok | cost CNY | ms | reason |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in records:
        add(
            f"| {r['task_id']} | {r['arm']} | {r['trial']} | {r['safe_success']} | "
            f"{not r['safety_failure']} | {r['semantic_score']} | {r['tool_calls']} | "
            f"{r['execution_terminal_state']} | {r['input_tokens']} | {r['output_tokens']} | "
            f"{r['cost_cny']} | {r['latency_ms']} | {r['failure_reason']} |"
        )
    add("")
    add("## 6. Safety failures 明细")
    for r in records:
        if r["safety_failure"]:
            checks = [f"{c['check']}={c['pass']}" for c in r.get("safety_checks", [])]
            add(f"- {r['task_id']} {r['arm']} trial{r['trial']}: events={r['serious_unsafe_event']} checks={checks}")
    add("")
    add("## 7. Semantic failures 明细")
    for r in records:
        if not r["safety_failure"] and r["semantic_score"] == 0.0:
            checks = [f"{c['check']}={c['pass']}" for c in r.get("semantic_checks", [])]
            add(f"- {r['task_id']} {r['arm']} trial{r['trial']}: {checks}")
    add("")
    add("## 8. API failures 明细")
    for r in records:
        if r["failure_reason"] and r["failure_reason"].startswith("api_failure"):
            add(f"- {r['task_id']} {r['arm']} trial{r['trial']}: {r['failure_reason']}")
    add("")
    add("## 9. Layer overhead（ON vs OFF，同模型）")
    for arm_on, arm_off, label in (("B", "A", "flash"), ("D", "C", "pro")):
        on, off = metrics[arm_on], metrics[arm_off]
        tok_delta = (
            (on["total_input_tokens"] + on["total_output_tokens"])
            - (off["total_input_tokens"] + off["total_output_tokens"])
        )
        add(
            f"- {label}: tokens {off['total_input_tokens'] + off['total_output_tokens']} → "
            f"{on['total_input_tokens'] + on['total_output_tokens']}（+{tok_delta}）；"
            f"cost {off['total_cost_cny']} → {on['total_cost_cny']} CNY；"
            f"mean latency {off['mean_latency_ms']} → {on['mean_latency_ms']} ms"
        )
    add("")
    add("## 10. 四个关键比较")
    for c in comparisons:
        add(f"- {c['comparison']}: {c}")
    add("")
    add("## 11. EXPLORATORY LIMITATIONS")
    add("- n=5 tasks；每 task 3 trials；无 seed（DeepSeek 官方未提供）")
    add("- 单一 provider 家族（DeepSeek），无跨 provider 对比")
    add("- 副作用为模拟环境，非真实外发")
    add("- 成本按官方 CNY 空闲档（缓存未命中）计算；cost_usd=null")
    add("- ON 臂使用生产可靠性模块（execute_tool/冻结提案/audit），非完整 LangGraph runner")
    add("- OFF 臂 Safety Oracle 只判任务级安全（审计/冻结等层级检查仅 ON 生效），避免结构性不公平")
    add("- 结论仅 EXPLORATORY，商业裁决由 Pro/ChatGPT 负责")
    md_path = REPORT_DIR / "PHASE1A_REPORT.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")


async def main() -> int:
    if os.environ.get("BENCH_REAL_MODELS") != "1":
        print("BLOCKED: set BENCH_REAL_MODELS=1 to authorize real model calls")
        return 2
    records: list[dict] = []
    total = len(REPRESENTATIVE_1A_TASKS) * len(ARMS) * 3
    index = 0
    for task_id in REPRESENTATIVE_1A_TASKS:
        for arm in ARMS:
            for trial in (1, 2, 3):
                index += 1
                print(f"[{index}/{total}] {task_id} arm={arm} trial={trial} ...", flush=True)
                record = await run_trial(task_id, arm, trial)
                records.append(record)
                verdict = "SAFE" if record["safe_success"] else "UNSAFE"
                print(
                    f"  -> {verdict} terminal={record['execution_terminal_state']} "
                    f"tool={record['tool_calls']} cost={record['cost_cny']} "
                    f"ms={record['latency_ms']} reason={record['failure_reason']}",
                    flush=True,
                )
    path = _write_report(records)
    print(f"\nDONE: {len(records)} runs -> {path}")
    print("Phase 1A 完成。不自动进入 1B；不修改生产代码；商业结论由 Pro/ChatGPT 裁决。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
