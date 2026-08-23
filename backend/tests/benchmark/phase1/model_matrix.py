"""四臂模型矩阵与成本费率（DeepSeek 官方 CNY 价格，2026-08-20 抓取）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_openai import ChatOpenAI

from app.config import settings

SMALL_MODEL = "deepseek-v4-flash"
LARGE_MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1"

# 官方价格：CNY / 百万 tokens（缓存未命中 input；off-peak / peak）。
# 来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing
RATES_CNY = {
    SMALL_MODEL: {
        "input_offpeak": 1.5,
        "input_peak": 3.0,
        "output_offpeak": 4.5,
        "output_peak": 9.0,
    },
    LARGE_MODEL: {
        "input_offpeak": 4.5,
        "input_peak": 9.0,
        "output_offpeak": 13.5,
        "output_peak": 27.0,
    },
}

ARMS = {
    "A": {"model": SMALL_MODEL, "reliability": "OFF"},
    "B": {"model": SMALL_MODEL, "reliability": "ON"},
    "C": {"model": LARGE_MODEL, "reliability": "OFF"},
    "D": {"model": LARGE_MODEL, "reliability": "ON"},
}


def build_llm(model: str) -> ChatOpenAI:
    """harness 内显式构造臂模型；不读取生产 LLM_MODEL 默认值。"""
    return ChatOpenAI(
        model=model,
        base_url=BASE_URL,
        api_key=settings.OPENAI_API_KEY or "",
        temperature=0,
        request_timeout=120,
        max_retries=0,
    )


def is_peak_hour(now: datetime | None = None) -> bool:
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    hour = now.hour
    return (9 <= hour < 12) or (14 <= hour < 18)


def cost_cny(
    model: str, input_tokens: int, output_tokens: int, peak: bool
) -> float | None:
    rates = RATES_CNY.get(model)
    if rates is None:
        return None
    input_rate = rates["input_peak" if peak else "input_offpeak"]
    output_rate = rates["output_peak" if peak else "output_offpeak"]
    if input_tokens is None or output_tokens is None:
        return None
    return round(
        input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate,
        6,
    )
