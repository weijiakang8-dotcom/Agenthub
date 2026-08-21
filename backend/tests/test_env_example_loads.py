from __future__ import annotations

from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_settings_load_from_env_example():
    settings = Settings(_env_file=str(ROOT / ".env.example"))
    assert settings.DATABASE_URL
    assert settings.REDIS_URL
    assert hasattr(settings, "TAVILY_API_KEY")
    assert settings.EMBEDDING_PROVIDER == "ollama"
    assert settings.EMBEDDING_DIMENSION == 768
    assert settings.OTEL_SDK_DISABLED is True
    assert settings.TENANT_MONTHLY_TOKEN_BUDGET == 0
    assert settings.TENANT_MONTHLY_COST_BUDGET_CNY == 0.0
    assert settings.TENANT_MAX_CONCURRENT_LLM_CALLS == 0
    assert settings.MEMORY_DEFAULT_TTL_DAYS == 0
