from __future__ import annotations

import asyncio
import statistics
import time

TOTAL_REQUESTS = 50
CONCURRENCY = 5
SERVICE_P95_LIMIT_MS = 20
QUEUE_P95_LIMIT_MS = 150


async def mock_chat_request(
    request_id: int, semaphore: asyncio.Semaphore
) -> tuple[float, float, bool]:
    queued_at = time.perf_counter()
    async with semaphore:
        started_at = time.perf_counter()
        # Deterministic local provider latency; no network or model invocation.
        await asyncio.sleep(0.01 + (request_id % 3) * 0.002)
        output = f"mock-response-{request_id}"
    completed_at = time.perf_counter()
    return (
        (completed_at - started_at) * 1000,
        (completed_at - queued_at) * 1000,
        bool(output),
    )


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * quantile))
    return ordered[index]


def test_bounded_mock_chat_concurrency():
    async def run() -> list[tuple[float, float, bool]]:
        semaphore = asyncio.Semaphore(CONCURRENCY)
        return await asyncio.gather(
            *(mock_chat_request(index, semaphore) for index in range(TOTAL_REQUESTS))
        )

    started = time.perf_counter()
    results = asyncio.run(run())
    elapsed = time.perf_counter() - started
    service_latencies = [service for service, _queue, _ok in results]
    queue_latencies = [queue for _service, queue, _ok in results]
    failures = sum(not ok for _service, _queue, ok in results)
    service_p95 = percentile(service_latencies, 0.95)
    queue_p95 = percentile(queue_latencies, 0.95)
    throughput = TOTAL_REQUESTS / elapsed

    print(
        f"bounded mock chat: requests={TOTAL_REQUESTS} concurrency={CONCURRENCY} "
        f"service_p50={statistics.median(service_latencies):.1f}ms "
        f"service_p95={service_p95:.1f}ms queue_p95={queue_p95:.1f}ms "
        f"errors={failures} throughput={throughput:.1f}req/s"
    )

    assert failures == 0
    assert service_p95 < SERVICE_P95_LIMIT_MS
    assert queue_p95 < QUEUE_P95_LIMIT_MS
    assert throughput > 30
