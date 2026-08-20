"""CI 基准性能回归门禁：核心接口 p95 延迟阈值（本地 ASGI，无外部依赖）。"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.main import app
from fastapi.testclient import TestClient


def main() -> int:
    limit_ms = float(os.environ.get("CI_P95_LATENCY_MS_LIMIT", "1000"))
    client = TestClient(app)
    latencies: list[float] = []
    statuses: list[int] = []
    for _ in range(20):
        started = time.perf_counter()
        response = client.get("/api/not-a-real-route")
        latencies.append((time.perf_counter() - started) * 1000)
        statuses.append(response.status_code)
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    ok_ratio = sum(1 for s in statuses if s == 404) / len(statuses)
    print(f"ci_gate p95={p95:.1f}ms ok_ratio={ok_ratio}")
    if p95 > limit_ms:
        print(f"CI_GATE_FAIL: p95 {p95:.1f}ms > {limit_ms}ms")
        return 1
    if ok_ratio < 0.99:
        print("CI_GATE_FAIL: functional pass ratio below 0.99")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
