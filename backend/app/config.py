from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（backend/ 的上一级），用于定位根目录下的 .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AgentHub"
    DEBUG: bool = False

    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5433/agenthub"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    OPENAI_API_KEY: str = ""
    ADMIN_API_KEY: str = ""
    JWT_SECRET_KEY: str = "change-me-in-production"
    REPLICA_DATABASE_URL: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"
    TAVILY_API_KEY: str = ""
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    RESEND_API_KEY: str = ""
    RESEND_FROM: str = ""
    ALERT_WEBHOOK_URL: str = ""
    FEISHU_WEBHOOK_URL: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
