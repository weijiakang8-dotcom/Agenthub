from __future__ import annotations

import asyncio
import uuid

from app.core import model_gateway


def test_select_returns_distinct_provider_configs(monkeypatch):
    from app.models import ModelConfig

    async def fake_models(organization_id):
        def config(name, provider, base_url, model):
            return ModelConfig(
                id=uuid.uuid4(),
                organization_id=None,
                name=name,
                provider=provider,
                base_url=base_url,
                api_key="sk-test",
                model=model,
                max_tokens=4096,
                cost_per_1k_tokens=0.002,
                priority=100,
                timeout=120,
                max_retries=2,
                enabled=True,
                is_active=True,
                is_default=False,
            )

        return [
            config("provider-a", "provider-a", "https://a.example/v1", "m-a"),
            config("provider-b", "provider-b", "https://b.example/v1", "m-b"),
        ]

    monkeypatch.setattr(model_gateway, "list_active_models", fake_models)

    async def fake_keys(user_id):
        return []

    monkeypatch.setattr(model_gateway, "list_user_api_keys", fake_keys)

    llms = asyncio.run(
        model_gateway.ModelGateway().select(organization_id=None, complexity="simple")
    )
    bases = {getattr(llm, "openai_api_base", None) for llm in llms}
    models = {getattr(llm, "model_name", None) for llm in llms}
    assert bases == {"https://a.example/v1", "https://b.example/v1"}
    assert models == {"m-a", "m-b"}


from types import SimpleNamespace


def test_get_chat_models_orders_by_priority(monkeypatch):
    models = [
        SimpleNamespace(
            name="pro",
            priority=1,
            cost_per_1k_tokens=0.01,
            timeout=120,
            max_retries=2,
        ),
        SimpleNamespace(
            name="flash",
            priority=2,
            cost_per_1k_tokens=0.001,
            timeout=60,
            max_retries=2,
        ),
    ]

    async def fake_list(_organization_id=None):
        return models

    monkeypatch.setattr(model_gateway, "list_active_models", fake_list)
    monkeypatch.setattr(model_gateway, "get_chat_model", lambda model: model.name)

    simple = asyncio.run(model_gateway.get_chat_models("org", complexity="simple"))
    complex_models = asyncio.run(
        model_gateway.get_chat_models("org", complexity="complex")
    )

    assert simple == ["flash", "pro"]
    assert complex_models == ["pro", "flash"]


def test_get_chat_models_falls_back_to_global_settings(monkeypatch):
    async def fake_list(_organization_id=None):
        return []

    monkeypatch.setattr(model_gateway, "list_active_models", fake_list)

    result = asyncio.run(model_gateway.get_chat_models("org"))

    assert len(result) == 1
    assert result[0].model_name == model_gateway.settings.LLM_MODEL
