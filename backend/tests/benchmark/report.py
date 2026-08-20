"""结构化 Benchmark 报告：JSON 落盘 + 文本摘要。"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model import RunRecord

REPORT_DIR = Path(__file__).resolve().parent / "reports"


def summarize(records: list[RunRecord]) -> dict[str, Any]:
    per_case: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = per_case.setdefault(
            record.case_group,
            {
                "SAFE_SUCCESS": 0,
                "SAFE_ABORT": 0,
                "SAFE_FAILURE": 0,
                "UNSAFE_FAILURE": 0,
            },
        )
        bucket[record.verdict] += 1
    total = len(records)
    safe = sum(
        1
        for record in records
        if record.verdict in ("SAFE_SUCCESS", "SAFE_ABORT", "SAFE_FAILURE")
    )
    return {
        "total_runs": total,
        "safe_runs": safe,
        "unsafe_runs": total - safe,
        "safety_pass_rate": round(safe / total * 100, 1) if total else 0.0,
        "per_case": per_case,
    }


def write_report(
    records: list[RunRecord],
    *,
    contract_conflicts: list[dict[str, Any]],
    workarounds: list[dict[str, Any]],
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "phase0-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_backend": "stub",
        "notes": (
            "Phase 0 只验证 Reliability Layer 与 Harness 本身；模型维度使用确定性 stub，"
            "不调用真实 LLM。四象限 = model_arm(small/large) x reliability(on/off)。"
        ),
        "contract_conflicts": contract_conflicts,
        "workarounds": workarounds,
        "summary": summarize(records),
        "records": [asdict(record) for record in records],
    }
    path = REPORT_DIR / "phase0_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_summary(records: list[RunRecord]) -> None:
    summary = summarize(records)
    print("\n===== Phase 0 Benchmark Summary =====")
    print(
        f"runs={summary['total_runs']} safe={summary['safe_runs']} "
        f"unsafe={summary['unsafe_runs']} safety_pass_rate={summary['safety_pass_rate']}%"
    )
    for case_group, counts in summary["per_case"].items():
        print(f"  case {case_group}: {counts}")
    print("----- UNSAFE details -----")
    for record in records:
        if record.verdict == "UNSAFE_FAILURE":
            failed = [c["oracle_id"] for c in record.oracle if not c["passed"]]
            err = record.evidence.get("error")
            print(
                f"  {record.case_id} [{record.quadrant}] "
                f"failed={failed} error={err} calls={record.provider_calls}"
            )
