from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Execution, ModelConfig


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


async def record_execution_usage(execution_id: uuid.UUID | str) -> None:
    async with async_session_factory() as session:
        execution = await session.get(Execution, uuid.UUID(str(execution_id)))
        if execution is None or execution.input_tokens:
            return

        default_stmt = select(ModelConfig).where(
            ModelConfig.is_active.is_(True),
            ModelConfig.is_default.is_(True),
        )
        if execution.organization_id is not None:
            default_stmt = default_stmt.where(
                ModelConfig.organization_id == execution.organization_id
            )
        default_model = (await session.execute(default_stmt)).scalars().first()
        default_rate = float(default_model.cost_per_1k_tokens if default_model else 0.0)

        usage = (execution.checkpoint_data or {}).get("llm_usage") or []
        if usage:
            model_used: list[str] = []
            token_usage: dict[str, dict[str, int]] = {}
            for entry in usage:
                model = entry.get("model_used")
                if not model:
                    continue
                if model not in model_used:
                    model_used.append(model)
                bucket = token_usage.setdefault(
                    model, {"input_tokens": 0, "output_tokens": 0}
                )
                bucket["input_tokens"] += int(entry.get("input_tokens") or 0)
                bucket["output_tokens"] += int(entry.get("output_tokens") or 0)
            # 按实际响应的模型逐条计价，避免 fallback 后仍按主模型计费。
            model_names = {
                entry.get("model_used") for entry in usage if entry.get("model_used")
            }
            if model_names:
                rate_stmt = select(ModelConfig).where(
                    ModelConfig.model.in_(model_names)
                )
                candidates = list((await session.execute(rate_stmt)).scalars().all())
                org_rates = {
                    model.model: float(model.cost_per_1k_tokens)
                    for model in candidates
                    if model.organization_id == execution.organization_id
                }
                global_rates = {
                    model.model: float(model.cost_per_1k_tokens)
                    for model in candidates
                    if model.organization_id is None
                }
                rates = {**global_rates, **org_rates}
            else:
                rates = {}
            input_tokens = sum(int(entry.get("input_tokens") or 0) for entry in usage)
            output_tokens = sum(int(entry.get("output_tokens") or 0) for entry in usage)
            cost = round(
                sum(
                    (
                        int(entry.get("input_tokens") or 0)
                        + int(entry.get("output_tokens") or 0)
                    )
                    / 1000
                    * rates.get(entry.get("model_used"), default_rate)
                    for entry in usage
                ),
                8,
            )
        else:
            input_tokens = estimate_tokens(execution.user_input or "")
            output_tokens = estimate_tokens(
                execution.final_output or execution.error_message or ""
            )
            cost = round((input_tokens + output_tokens) / 1000 * default_rate, 8)

        execution.input_tokens = input_tokens
        execution.output_tokens = output_tokens
        execution.cost = cost
        if usage:
            execution.model_used = model_used
            execution.token_usage = token_usage
        await session.commit()
