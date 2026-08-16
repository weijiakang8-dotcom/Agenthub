from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.database import async_session_factory
from app.models import Execution

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.OPENAI_API_KEY or "not-configured",
        temperature=0,
    )


async def evaluate_execution(execution_id: str) -> None:
    """LLM-as-Judge：对已完成执行的 final_output 进行三维打分并落库。"""
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None or not execution.final_output:
            return
        user_input = execution.user_input
        final_output = execution.final_output

    prompt = (
        "你是一名严格的评审专家。请根据用户指令和 Agent 最终输出，"
        "从准确性(accuracy)、完整性(completeness)、逻辑性(logic)三个维度打分，"
        "每个维度 1-10 分，并给出简短评语。只输出 JSON：\n"
        '{"accuracy": 8, "completeness": 7, "logic": 9, "comment": "..."}\n\n'
        f"用户指令：{user_input}\nAgent 最终输出：{final_output}"
    )

    llm = _llm()
    result: dict[str, Any] | None = None
    for attempt in range(3):
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            data = _extract_json(str(response.content))
            if {"accuracy", "completeness", "logic"} <= set(data):
                result = data
                break
        except Exception as exc:  # noqa: BLE001
            logger.warning("evaluation attempt %s failed: %s", attempt + 1, exc)

    if result is None:
        logger.warning("evaluation skipped for execution %s", execution_id)
        return

    score = round(
        (
            float(result["accuracy"])
            + float(result["completeness"])
            + float(result["logic"])
        )
        / 3,
        2,
    )
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None:
            return
        execution.eval_score = score
        execution.eval_details = result
        await session.commit()
