from __future__ import annotations

import asyncio

import pytest
from app.engine import graph, tools


def test_breaker_open_fails_fast_without_fabricating_output(monkeypatch):
    """breaker OPEN 时必须抛错，不能把错误字符串伪装成 final_output。"""

    class FakeLLM:
        model_name = "fake"

        async def ainvoke(self, messages):
            return None

    monkeypatch.setattr(graph.llm_breaker, "allow", lambda: False)

    with pytest.raises(RuntimeError):
        asyncio.run(graph._call_llm_with_fallback([FakeLLM()], []))


def test_send_email_is_idempotent_in_process(monkeypatch):
    sends: list[tuple[str, str, str]] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, message):
            sends.append(
                (message["To"], message["Subject"], str(message.get_payload()))
            )

    monkeypatch.setattr(tools.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(tools.settings, "SMTP_PORT", 587)
    monkeypatch.setattr(tools.settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(tools, "_SENT_EMAIL_HASHES", set())

    first = asyncio.run(
        tools.send_email.ainvoke({"to": "a@b.com", "subject": "S", "body": "B"})
    )
    second = asyncio.run(
        tools.send_email.ainvoke({"to": "a@b.com", "subject": "S", "body": "B"})
    )

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert len(sends) == 1
