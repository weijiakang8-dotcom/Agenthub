"""Phase 0 Golden Set Harness 入口。

运行方式（使用隔离的 benchmark 数据库，migration 0019）：
  DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/agenthub_benchmark_p0 \
  python -m pytest tests/benchmark/test_phase0_benchmark.py -q -s
"""

from __future__ import annotations

import asyncio

import pytest

from .arms import run_layer_off, run_layer_on
from .cases import CASES
from .db import db_ready
from .oracle import build_record, run_oracle, semantic_oracle
from .report import print_summary, write_report

pytestmark = pytest.mark.skipif(
    not asyncio.run(db_ready()),
    reason="requires PostgreSQL at migration 0019 (agenthub_benchmark_p0)",
)


def test_phase0_golden_set_harness(monkeypatch) -> None:
    records = []
    for case in CASES:
        for model_arm in ("small", "large"):
            for reliability_arm in ("on", "off"):
                if reliability_arm == "on":
                    ev = asyncio.run(run_layer_on(case, monkeypatch, model_arm))
                else:
                    ev = asyncio.run(run_layer_off(case, monkeypatch, model_arm))
                checks = run_oracle(case, ev)
                semantic_pass, semantic_detail = semantic_oracle(case, ev)
                records.append(
                    build_record(case, ev, checks, semantic_pass, semantic_detail)
                )

    conflicts = [
        {
            "id": "C-1",
            "severity": "RESOLVED-VERIFIED",
            "title": "Tool 层重试与副作用契约冲突（已修复）",
            "evidence": (
                "Reliability Contract Fix：ToolSpec.side_effect=true 的工具 claim 后 "
                "provider 调用 ≤1；TIMEOUT/TRANSIENT → UNKNOWN → IN_FLIGHT fail-closed；"
                "Case 02B layer-on provider=1（修复前=3）。"
            ),
        },
        {
            "id": "C-2",
            "severity": "INFRA-DEFECT",
            "title": "迁移链 0019 在全新数据库上不可复现",
            "evidence": (
                "0008_full_schema_backfill 已创建 alert_events.organization_id，"
                "0019 再次 add_column 必然 DuplicateColumnError。"
            ),
        },
        {
            "id": "C-3",
            "severity": "SEMANTICS-OBSERVATION",
            "title": "Approval Freeze 的实现语义是按构造冻结",
            "evidence": (
                "graph._execute_frozen_side_effect 始终执行冻结 proposal 的 "
                "tool/params，运行时 step 篡改不会生效（Case 06 验证通过）；"
                "mismatch abort 路径仅覆盖提案级自洽性破坏（Case 07 验证通过）。"
            ),
        },
        {
            "id": "C-4",
            "severity": "RESOLVED-VERIFIED",
            "title": "legacy PENDING 对账审计不幂等（已修复）",
            "evidence": (
                "reconcile 审计按 (resource_id, action, tool_call_id) 确定性去重；"
                "Case 10 second_pass={executions:0, tool_calls:0}（修复前 tool_calls=1）。"
            ),
        },
    ]
    workarounds = [
        {
            "target": "agenthub_benchmark_p0",
            "action": "alembic upgrade 0018 + alembic stamp 0019",
            "reason": "绕过 C-2，未修改任何迁移代码",
        }
    ]
    path = write_report(records, contract_conflicts=conflicts, workarounds=workarounds)
    print_summary(records)
    assert path.exists(), "benchmark report not written"
    assert len(records) == len(CASES) * 4, "missing quadrant records"
