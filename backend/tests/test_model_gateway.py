from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core import model_gateway


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
