from __future__ import annotations

import asyncio

from app.engine import chat, intent
from app.rag import embedder
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


def test_intent_router_parses_known_decision():
    class FakeGateway:
        async def select(self, **kwargs):
            return [object()]

        async def invoke(self, _llms, _messages, **kwargs):
            return AIMessage(
                content=(
                    '{"category":"ACTION","complexity":"simple",'
                    '"confidence":0.9,"reason":"needs email"}'
                )
            )

    router = intent.IntentRouter(gateway=FakeGateway())
    decision = asyncio.run(
        router.classify("发邮件", organization_id="org", user_id="user")
    )
    assert decision.category == intent.IntentCategory.ACTION
    assert decision.runtime == intent.RuntimeKind.AGENT
    assert decision.fallback is False


def test_intent_router_fails_open_to_chat():
    class FailingGateway:
        async def select(self, **kwargs):
            raise RuntimeError("model down")

        async def invoke(self, _llms, _messages, **kwargs):
            raise RuntimeError("model down")

    router = intent.IntentRouter(gateway=FailingGateway())
    decision = asyncio.run(router.classify("hello", organization_id=None, user_id=None))
    assert decision.category == intent.IntentCategory.CHAT
    assert decision.runtime == intent.RuntimeKind.CHAT
    assert decision.fallback is True


def test_intent_runtime_decision():
    assert intent.decide_runtime(intent.IntentCategory.TASK) == intent.RuntimeKind.AGENT
    assert (
        intent.decide_runtime(intent.IntentCategory.KNOWLEDGE)
        == intent.RuntimeKind.CHAT
    )


class FakeStreamLLM:
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.model_name = "fake-model"

    async def astream(self, _messages):
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield chunk


def test_iter_chat_tokens_streams_and_falls_back():
    class Chunk:
        content = ""

        def __init__(self, content):
            self.content = content

    broken = FakeStreamLLM([], error=RuntimeError("provider down"))
    working = FakeStreamLLM([Chunk("你"), Chunk("好")])

    async def collect():
        return [
            token
            async for token in chat.iter_chat_tokens(
                [broken, working], [HumanMessage(content="hi")]
            )
        ]

    assert asyncio.run(collect()) == ["你", "好"]


def test_hash_embedding_provider_returns_normalized_vector(monkeypatch):
    monkeypatch.setattr(embedder.settings, "EMBEDDING_PROVIDER", "hash")
    monkeypatch.setattr(embedder.settings, "EMBEDDING_DIMENSION", 768)

    vector = asyncio.run(embedder.embed_text("hello world"))

    assert len(vector) == 768
    assert abs(sum(value * value for value in vector) - 1.0) < 1e-6


def test_build_chat_messages_injects_summary_and_memories():
    messages = chat.build_chat_messages(
        [{"role": "assistant", "content": "你好"}],
        "hello",
        summary="之前讨论了天气",
        memories=[{"kind": "fact", "content": "用户喜欢简短回答"}],
    )
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], AIMessage)
    assert isinstance(messages[-1], HumanMessage)


def test_strip_raw_tool_call_text_handles_fullwidth_and_dsml_markers():
    from app.engine.graph import _strip_raw_tool_call_text

    text = (
        "看起来查询失败。\n"
        "<||DSML||tool_calls>\n"
        '<||DSML||invoke name="query_db">\n'
        '<||DSML||parameter name="sql" string="true">SELECT 1</||DSML||parameter>\n'
        "</||DSML||invoke>\n"
        "</||DSML||tool_calls>"
    )
    assert _strip_raw_tool_call_text(text) == "看起来查询失败。"
