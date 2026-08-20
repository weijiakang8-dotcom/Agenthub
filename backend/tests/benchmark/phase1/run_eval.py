"""P0-2 Evaluation 入口。

离线（默认，零模型调用）：
  python -m tests.benchmark.phase1.run_eval --offline
Live（需显式授权 + BENCH_REAL_MODELS=1）：
  BENCH_REAL_MODELS=1 PHASE1B_MODE=full python -m tests.benchmark.phase1.run_eval --live
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from tests.benchmark.phase1.evaluation import build_payload, write_reports

REPORT_DIR = Path(__file__).resolve().parent / "reports"
DEFAULT_OFFLINE = REPORT_DIR / "phase1b_report.json"


async def run_live() -> Path:
    from tests.benchmark.phase1.golden1b import R2_HARD_IDS, TASKS_1B
    from tests.benchmark.phase1.model_matrix import ARMS
    from tests.benchmark.phase1.runner1b import run_trial_1b

    records: list[dict] = []
    task_ids = list(TASKS_1B.keys())
    for task_id in task_ids:
        trials = 5 if task_id in R2_HARD_IDS else 3
        for arm in ARMS:
            for trial in range(1, trials + 1):
                records.append(await run_trial_1b(task_id, arm, trial))
    payload = build_payload(records, source="live-run")
    json_path, _ = write_reports(payload)
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.live:
        if os.environ.get("BENCH_REAL_MODELS") != "1":
            print("BLOCKED: set BENCH_REAL_MODELS=1 to authorize live model calls")
            return 2
        asyncio.run(run_live())
        return 0
    source = DEFAULT_OFFLINE
    if not source.exists():
        print(f"offline source not found: {source}")
        return 2
    with open(source, encoding="utf-8") as fh:
        records = json.load(fh)["records"]
    payload = build_payload(records, source=str(source))
    json_path, md_path = write_reports(payload)
    print(f"offline evaluation done: {json_path} / {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
