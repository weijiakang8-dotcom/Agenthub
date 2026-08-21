from __future__ import annotations

from app.config import Settings


def test_otel_sdk_disabled_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    settings = Settings(_env_file=None)
    assert settings.OTEL_SDK_DISABLED is True


def test_otel_sdk_disabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    settings = Settings(_env_file=None)
    assert settings.OTEL_SDK_DISABLED is False
