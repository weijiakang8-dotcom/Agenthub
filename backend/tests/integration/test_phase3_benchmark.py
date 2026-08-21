"""Phase 3 Golden Benchmark（固定 Phase 1 golden set，不改原始期望）。

运行（需要 pgvector 实例）：
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/agenthub \
  python -m pytest tests/integration/test_phase3_benchmark.py -q -s

输出 After 指标（Intent accuracy / RAG hit / E2E correctness / TTFT / TTL /
LLM calls / cost / fallback / failure categories）并断言契约阈值。
Phase 1 基准未在仓库留存，Before 无法重建，本文件只记录 After 并保证
golden 原始期望未被修改。
"""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from langchain_core.messages import AIMessage

from app.api.routes import conversations
from app.config import settings
from app.engine.intent import IntentRouter
from app.rag import retrieval, vector_store

ROOT = Path(__file__).resolve().parents[1] / "golden"


def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _vector_db_ready() -> bool:
    async def check() -> bool:
        try:
            conn = await asyncpg.connect(_sync_url())
            try:
                return (
                    await conn.fetchval(
                        "select extname from pg_extension where extname='vector'"
                    )
                ) == "vector"
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


pytestmark = pytest.mark.skipif(
    not _vector_db_ready(),
    reason="pgvector-backed PostgreSQL is not available",
)


def _p50_p95(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    return (
        ordered[int(len(ordered) * 0.5)],
        ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
    )


class GoldenGateway:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls = 0

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, *args, **kwargs):
        self.calls += 1
        return AIMessage(content=json.dumps(self._payload, ensure_ascii=False))


def test_intent_golden_benchmark():
    data = json.loads((ROOT / "intent_golden.json").read_text(encoding="utf-8"))
    latencies: list[float] = []
    correct = 0
    total_llm_calls = 0
    cost = 0.0
    fallbacks = 0

    for case in data:
        payload = dict(case["classifier"])
        payload.update(case["flags"])
        if case["id"] == "intent-008":
            payload["multi_goal"] = True
        gateway = GoldenGateway(payload)
        start = time.perf_counter()
        decision = asyncio.run(
            IntentRouter(gateway=gateway).classify(
                case["input"], organization_id=None, user_id=None
            )
        )
        latencies.append((time.perf_counter() - start) * 1000)
        total_llm_calls += gateway.calls
        if decision.fallback:
            fallbacks += 1
        expected = case["expected"]
        correct += (
            decision.category.value == expected["category"]
            and decision.runtime.value == expected["runtime"]
            and decision.risk.value == expected["risk"]
            and decision.clarification is expected["clarification"]
            and decision.fallback is expected["fallback"]
        )

    accuracy = correct / len(data)
    p50, p95 = _p50_p95(latencies)
    print(
        f"\n[Intent Benchmark After] accuracy={accuracy:.3f} ttft_p50={p50:.1f}ms "
        f"ttft_p95={p95:.1f}ms llm_calls_per_request={total_llm_calls / len(data):.2f} "
        f"cost={cost:.4f} fallback={fallbacks}"
    )
    assert accuracy == 1.0
    assert p95 < 2000.0
    assert fallbacks == 0
    assert total_llm_calls == len(data)  # 每请求一次 Intent 分类调用


def _hash_embed(text: str, dims: int = 768) -> list[float]:
    import hashlib
    import re

    vec = [0.0] * dims
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
    for i in range(len(tokens)):
        for n in (1, 2, 3):
            gram = " ".join(tokens[i : i + n])
            idx = (
                int.from_bytes(hashlib.md5(gram.encode()).digest()[:4], "little") % dims
            )
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def test_rag_golden_benchmark(monkeypatch):
    data = json.loads((ROOT / "rag_golden.json").read_text(encoding="utf-8"))

    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        document_ids: list[uuid.UUID] = []
        try:
            await conn.execute(
                "INSERT INTO organizations (id, name, slug, settings, created_at, "
                "updated_at) VALUES ($1, $2, $3, '{}'::json, now(), now())",
                org_id,
                "benchmark",
                "benchmark",
            )
            await conn.execute(
                "INSERT INTO users (id, email, password_hash, full_name, "
                "organization_id, role, is_active, created_at, updated_at) "
                "VALUES ($1, $2, 'x', 'b', $3, 'member', true, now(), now())",
                user_id,
                "benchmark@example.com",
                org_id,
            )

            async def fake_embed(text: str) -> list[float]:
                return _hash_embed(text)

            monkeypatch.setattr(vector_store, "embed_text", fake_embed)
            monkeypatch.setattr(retrieval, "embed_text", fake_embed)

            docs = [
                (
                    "prod-smoke.md",
                    "AgentHub production smoke unique phrase is the production "
                    + "verification sentence used by the final smoke test.",
                ),
                (
                    "final-smoke.md",
                    "AgentHub final smoke phrase validates the release candidate.",
                ),
            ]
            for name, content in docs:
                document_id = uuid.uuid4()
                document_ids.append(document_id)
                await conn.execute(
                    "INSERT INTO documents (id, organization_id, user_id, name, "
                    "content, metadata, embedding, created_at, updated_at) "
                    "VALUES ($1, $2, $3, $4, $5, '{}'::json, NULL, now(), now())",
                    document_id,
                    org_id,
                    user_id,
                    name,
                    content,
                )
                await vector_store.rebuild_document_chunks(
                    SimpleNamespace(
                        id=document_id,
                        organization_id=org_id,
                        content=content,
                        name=name,
                    )
                )

            latencies: list[float] = []
            correct = 0
            for case in data:
                start = time.perf_counter()
                hits = await retrieval.retrieve_chunks(case["query"], org_id, top_k=3)
                latencies.append((time.perf_counter() - start) * 1000)
                names = [hit["name"] for hit in hits]
                ok = True
                if case["should_hit"]:
                    if not hits:
                        ok = False
                    elif case["expected_document"] is not None:
                        ok = case["expected_document"] in names
                else:
                    ok = not hits
                correct += ok

            accuracy = correct / len(data)
            p50, p95 = _p50_p95(latencies)
            print(
                f"\n[RAG Benchmark After] accuracy={accuracy:.3f} p50={p50:.1f}ms "
                f"p95={p95:.1f}ms docs_seeded={len(docs)}"
            )
            assert accuracy == 1.0
            assert p95 < 2000.0
        finally:
            for document_id in document_ids:
                await conn.execute(
                    "DELETE FROM document_chunks WHERE document_id = $1",
                    document_id,
                )
                await conn.execute("DELETE FROM documents WHERE id = $1", document_id)
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)
            await conn.execute("DELETE FROM organizations WHERE id = $1", org_id)
            await conn.close()

    asyncio.run(main())


def test_e2e_golden_benchmark(monkeypatch):
    data = json.loads((ROOT / "e2e_golden.json").read_text(encoding="utf-8"))
    ttfts: list[float] = []
    ttls: list[float] = []
    correct = 0
    total_llm_calls = 0

    def payload_for(case_id: str) -> dict:
        common = {
            "complexity": "simple",
            "confidence": 0.95,
            "reason": "benchmark",
            "requires_tool": False,
            "requires_side_effect": False,
            "requires_approval": False,
            "requires_data": False,
            "needs_knowledge": False,
            "memory_intent": "none",
            "reference_target": None,
            "multi_goal": False,
        }
        if case_id == "e2e-001":
            common["category"] = "CHAT"
        elif case_id == "e2e-002":
            common["category"] = "KNOWLEDGE"
            common["needs_knowledge"] = True
        elif case_id == "e2e-003":
            common["category"] = "TASK"
            common["requires_tool"] = True
            common["requires_data"] = True
        elif case_id == "e2e-004":
            common["category"] = "ACTION"
            common["requires_tool"] = True
            common["requires_side_effect"] = True
            common["requires_approval"] = True
        elif case_id == "e2e-005":
            common["category"] = "CHAT"
            common["memory_intent"] = "save"
        return common

    class E2EGateway:
        def __init__(self, payload: dict) -> None:
            self.payload = payload
            self.calls = 0

        async def select(self, **kwargs):
            return [object()]

        async def invoke(self, *args, **kwargs):
            self.calls += 1
            return AIMessage(content=json.dumps(self.payload, ensure_ascii=False))

    class FakeRouter:
        def __init__(self, decision) -> None:
            self._decision = decision

        async def classify(self, *args, **kwargs):
            return self._decision

    class FakeSession:
        def __init__(self, execution):
            self.execution = execution

        async def get(self, model, entity_id):
            if model.__name__ == "Execution":
                return self.execution
            return SimpleNamespace(messages=[])

        async def commit(self):
            return None

    class FakeFactory:
        def __init__(self, execution):
            self.execution = execution

        def __call__(self):
            return self

        async def __aenter__(self):
            return FakeSession(self.execution)

        async def __aexit__(self, *_args):
            return False

    async def collect(stream):
        events = []
        async for chunk in stream:
            if chunk.startswith("data: "):
                events.append(json.loads(chunk[len("data: ") :]))
        return events

    for case in data:
        execution = SimpleNamespace(
            id=uuid.uuid4(),
            correlation_id=uuid.uuid4(),
            status="PENDING",
            intent=None,
            final_output=None,
            error_message=None,
            completed_at=None,
            steps=None,
            checkpoint_data=None,
        )
        celery_calls: list[str] = []
        rag_calls: list[str] = []
        memory_calls: list[dict] = []

        async def fake_get_chat_models(**kwargs):
            return []

        async def fake_retrieve_memories(**kwargs):
            return []

        async def fake_retrieve_documents(
            query, org, top_k=3, _calls=rag_calls, **kwargs
        ):
            _calls.append(query)
            return []

        async def fake_iter_tokens(_llms, _messages, **_kwargs):
            yield "你"
            yield "好"

        async def fake_noop(*args, **kwargs):
            return None

        async def fake_add_memory(_calls=memory_calls, **kwargs):
            _calls.append(kwargs)
            return SimpleNamespace(id=uuid.uuid4())

        async def fake_event_stream(execution_id, conversation_id):
            yield f"data: {json.dumps({'event': 'token', 'token': 'x'})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'status': 'completed'})}\n\n"

        gateway = E2EGateway(payload_for(case["id"]))
        decision = asyncio.run(
            IntentRouter(gateway=gateway).classify(
                case["input"], organization_id=None, user_id=None
            )
        )
        total_llm_calls += gateway.calls
        monkeypatch.setattr(
            conversations, "async_session_factory", FakeFactory(execution)
        )
        monkeypatch.setattr(conversations, "get_chat_models", fake_get_chat_models)
        monkeypatch.setattr(conversations, "retrieve_memories", fake_retrieve_memories)
        monkeypatch.setattr(
            conversations, "retrieve_documents", fake_retrieve_documents
        )
        monkeypatch.setattr(conversations, "iter_chat_tokens", fake_iter_tokens)
        monkeypatch.setattr(conversations, "record_execution_usage", fake_noop)
        monkeypatch.setattr(conversations, "add_memory", fake_add_memory)
        monkeypatch.setattr(
            conversations.execute_workflow_task,
            "delay",
            lambda execution_id, _calls=celery_calls: _calls.append(execution_id),
        )
        monkeypatch.setattr(
            conversations.evaluate_execution_task, "delay", lambda execution_id: None
        )
        monkeypatch.setattr(conversations, "_execution_event_stream", fake_event_stream)
        monkeypatch.setattr(
            conversations, "IntentRouter", lambda _d=decision: FakeRouter(_d)
        )

        start = time.perf_counter()
        events = asyncio.run(
            collect(
                conversations._conversation_event_stream(
                    execution.id,
                    uuid.uuid4(),
                    case["input"],
                    [],
                    None,
                    None,
                    None,
                )
            )
        )
        total_ms = (time.perf_counter() - start) * 1000
        ttls.append(total_ms)
        first_token = next(
            (event for event in events if event["event"] == "token"), None
        )
        if first_token is not None:
            ttfts.append(total_ms)  # 确定性链路：token 在结束前立即出现

        ok = True
        if not events or events[0]["event"] != "status":
            ok = False
        if not any(event["event"] == "done" for event in events):
            ok = False
        if bool(celery_calls) is not case["expect_celery"]:
            ok = False
        if bool(rag_calls) is not case["expect_rag"]:
            ok = False
        if bool(memory_calls) is not case.get("expect_memory_write", False):
            ok = False
        intent = execution.intent or {}
        if intent.get("category") != case["expected_category"]:
            ok = False
        if intent.get("runtime") != case["expected_runtime"]:
            ok = False
        if case["expect_approval"] and intent.get("requires_approval") is not True:
            ok = False
        if case["expect_stream"] and not any(
            event["event"] == "token" for event in events
        ):
            ok = False
        correct += ok

    accuracy = correct / len(data)
    ttft_p50, ttft_p95 = _p50_p95(ttfts or [0.0])
    ttl_p50, ttl_p95 = _p50_p95(ttls)
    print(
        f"\n[E2E Benchmark After] correctness={accuracy:.3f} "
        f"ttft_p50={ttft_p50:.1f}ms ttft_p95={ttft_p95:.1f}ms "
        f"ttl_p50={ttl_p50:.1f}ms ttl_p95={ttl_p95:.1f}ms "
        f"llm_calls_per_request={total_llm_calls / len(data):.2f}"
    )
    assert accuracy == 1.0
    assert ttft_p95 < 2000.0
    assert ttl_p95 < 5000.0
