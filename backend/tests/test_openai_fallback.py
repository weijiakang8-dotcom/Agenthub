"""第二供应商（OpenAI）跨厂商回退契约测试。"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.core import model_gateway


async def _select(gateway, monkeypatch):
    async def no_models(_org=None):
        return []

    async def no_keys(_user=None):
        return []

    monkeypatch.setattr(model_gateway, "list_active_models", no_models)
    monkeypatch.setattr(model_gateway, "list_user_api_keys", no_keys)
    return await gateway.select(organization_id=None, user_id=None)


def test_disabled_secondary_provider_is_skipped(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_ENABLED", False)
    clients = asyncio.run(_select(model_gateway.ModelGateway(), monkeypatch))
    assert all(getattr(c, "openai_api_base", "").startswith("https://api.deepseek") for c in clients)


def test_enabled_with_key_appends_openai_client(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    clients = asyncio.run(_select(model_gateway.ModelGateway(), monkeypatch))
    last = clients[-1]
    assert getattr(last, "openai_api_base", "").startswith("https://api.openai.com")
    assert getattr(last, "model_name", "") == "gpt-4o-mini"


def test_enabled_without_key_is_skipped_silently(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_FALLBACK_API_KEY", "")
    clients = asyncio.run(_select(model_gateway.ModelGateway(), monkeypatch))
    assert all(getattr(c, "openai_api_base", "").startswith("https://api.deepseek") for c in clients)


def test_primary_failure_falls_back_to_secondary(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage

    class Failing:
        async def ainvoke(self, messages, **kwargs):
            raise TimeoutError("primary provider timeout")

    class Working:
        async def ainvoke(self, messages, **kwargs):
            return AIMessage(content="ok")

    gateway = model_gateway.ModelGateway()

    async def noop_span(*args, **kwargs):
        return None

    async def main():
        monkeypatch.setattr(gateway, "_record", lambda **kw: None)
        monkeypatch.setattr(gateway, "_attach_metadata", lambda *a, **k: None)
        monkeypatch.setattr(model_gateway, "record_span", noop_span)
        response = await gateway.invoke(
            [Failing(), Working()],
            [HumanMessage(content="hi")],
            task_type="fallback",
            organization_id=None,
            correlation_id=None,
        )
        assert str(response.content) == "ok"

    asyncio.run(main())
