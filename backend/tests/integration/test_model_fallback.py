from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from app.config import settings
from app.core import model_gateway
from app.engine.graph import _call_llm_with_fallback
from langchain_core.messages import HumanMessage


def _deepseek_up() -> bool:
    try:
        response = httpx.get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            timeout=10,
        )
        return response.status_code == 200
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _deepseek_up(),
    reason="DeepSeek API unreachable",
)


def test_real_pro_failure_falls_back_to_flash():
    """REAL fallback：Pro 端点真实不可达 → Flash 真实响应。无 mock provider。"""
    pro = SimpleNamespace(
        model="deepseek-v4-pro",
        base_url="http://127.0.0.1:59999/v1",
        api_key="sk-invalid",
        max_tokens=4096,
        timeout=3,
        max_retries=0,
    )
    flash = SimpleNamespace(
        model="deepseek-v4-flash",
        base_url=settings.LLM_BASE_URL,
        api_key=settings.OPENAI_API_KEY,
        max_tokens=4096,
        timeout=60,
        max_retries=2,
    )
    llms = [
        model_gateway.get_chat_model(pro),
        model_gateway.get_chat_model(flash),
    ]

    response = asyncio.run(
        _call_llm_with_fallback(
            llms,
            [HumanMessage(content="请只回复两个字：收到")],
        )
    )

    assert str(response.content).strip()
    metadata = (response.additional_kwargs or {}).get("_agenthub_llm", {})
    assert metadata.get("model_used") == "deepseek-v4-flash"
    assert metadata.get("fallback") is True
