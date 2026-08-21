from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.api.routes import conversations
from app.engine.intent import IntentRouter
from app.rag import retrieval

ROOT = Path(__file__).resolve().parents[1] / "golden"


def test_rag_golden_schema():
    data = json.loads((ROOT / "rag_golden.json").read_text(encoding="utf-8"))
    assert data
    for case in data:
        assert {
            "id",
            "query",
            "expected_document",
            "expected_keywords",
            "should_hit",
        } <= set(case)


def test_e2e_golden_schema():
    data = json.loads((ROOT / "e2e_golden.json").read_text(encoding="utf-8"))
    assert data
    for case in data:
        assert {
            "id",
            "input",
            "expected_category",
            "expected_runtime",
            "expect_celery",
            "expect_approval",
            "expect_rag",
            "expect_stream",
        } <= set(case)


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def test_rag_golden_retrieval_hits(monkeypatch):
    data = json.loads((ROOT / "rag_golden.json").read_text(encoding="utf-8"))
    chunks = [
        {
            "document_id": "doc-prod",
            "name": "prod-smoke.md",
            "content": "AgentHub production smoke unique phrase is the production "
            "verification sentence used by the final smoke test.",
            "embedding": [1.0, 0.0, 0.0],
        },
        {
            "document_id": "doc-final",
            "name": "final-smoke.md",
            "content": "AgentHub final smoke phrase validates the release candidate.",
            "embedding": [0.0, 1.0, 0.0],
        },
    ]

    async def fake_embed(text):
        lowered = text.lower()
        if "production" in lowered and "smoke" in lowered:
            return [1.0, 0.0, 0.0]
        if "final" in lowered and "smoke" in lowered:
            return [0.0, 1.0, 0.0]
        if "smoke" in lowered:
            return [0.5, 0.5, 0.0]
        return [0.0, 0.0, 1.0]

    async def fake_search(query_vector, *, organization_id, top_k):
        scored = sorted(
            ((chunk, _cosine(query_vector, chunk["embedding"])) for chunk in chunks),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            {
                "document_id": chunk["document_id"],
                "name": chunk["name"],
                "content": chunk["content"],
                "score": score,
            }
            for chunk, score in scored
            if score > 0.3
        ][:top_k]

    monkeypatch.setattr(retrieval, "embed_text", fake_embed)
    monkeypatch.setattr(retrieval, "search_chunks", fake_search)

    for case in data:
        hits = asyncio.run(retrieval.retrieve_chunks(case["query"], None, top_k=3))
        names = [hit["name"] for hit in hits]
        if case["should_hit"]:
            assert hits, f"golden {case['id']} should hit"
            if case["expected_document"] is not None:
                assert case["expected_document"] in names, case["id"]
        else:
            assert hits == [], f"golden {case['id']} should not hit"


def _classifier_payload(case_id: str, user_input: str) -> dict:
    common = {
        "complexity": "simple",
        "confidence": 0.95,
        "reason": "e2e golden",
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


class _E2EGateway:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, *args, **kwargs):
        return AIMessage(content=json.dumps(self._payload, ensure_ascii=False))


class _FakeRouter:
    def __init__(self, decision) -> None:
        self._decision = decision

    async def classify(self, *args, **kwargs):
        return self._decision


class _E2ESession:
    def __init__(self, execution):
        self.execution = execution

    async def get(self, model, entity_id):
        if model.__name__ == "Execution":
            return self.execution
        return SimpleNamespace(messages=[])

    async def commit(self):
        return None


class _E2ESessionFactory:
    def __init__(self, execution):
        self.execution = execution

    def __call__(self):
        return self

    async def __aenter__(self):
        return _E2ESession(self.execution)

    async def __aexit__(self, *_args):
        return False


async def _collect_stream(stream):
    events = []
    async for chunk in stream:
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[len("data: ") :]))
    return events


def test_e2e_golden_runtime_behavior(monkeypatch):
    data = json.loads((ROOT / "e2e_golden.json").read_text(encoding="utf-8"))

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
            yield (f"data: {json.dumps({'event': 'token', 'token': 'x'})}\n\n")
            yield (f"data: {json.dumps({'event': 'done', 'status': 'completed'})}\n\n")

        monkeypatch.setattr(
            conversations, "async_session_factory", _E2ESessionFactory(execution)
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
            conversations.evaluate_execution_task,
            "delay",
            lambda execution_id: None,
        )
        monkeypatch.setattr(conversations, "_execution_event_stream", fake_event_stream)
        decision = asyncio.run(
            IntentRouter(
                gateway=_E2EGateway(_classifier_payload(case["id"], case["input"]))
            ).classify(case["input"], organization_id=None, user_id=None)
        )
        monkeypatch.setattr(
            conversations,
            "IntentRouter",
            lambda _decision=decision: _FakeRouter(_decision),
        )

        events = asyncio.run(
            _collect_stream(
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

        assert events, case["id"]
        assert events[0]["event"] == "status"
        assert any(event["event"] == "done" for event in events), case["id"]
        if case["expect_stream"]:
            assert any(event["event"] == "token" for event in events), case["id"]
        assert bool(celery_calls) is case["expect_celery"], case["id"]
        assert bool(rag_calls) is case["expect_rag"], case["id"]
        assert bool(memory_calls) is case.get("expect_memory_write", False), case["id"]
        intent = execution.intent or {}
        assert intent.get("category") == case["expected_category"], case["id"]
        assert intent.get("runtime") == case["expected_runtime"], case["id"]
        if case["expect_approval"]:
            assert intent.get("requires_approval") is True, case["id"]
