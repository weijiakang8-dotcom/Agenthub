from __future__ import annotations

import uuid

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Execution, ModelConfig


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001
        return max(1, len(text) // 4)


async def record_execution_usage(execution_id: uuid.UUID | str) -> None:
    async with async_session_factory() as session:
        execution = await session.get(Execution, uuid.UUID(str(execution_id)))
        if execution is None or execution.input_tokens:
            return

        input_tokens = estimate_tokens(execution.user_input or "")
        output_tokens = estimate_tokens(execution.final_output or execution.error_message or "")

        stmt = select(ModelConfig).where(
            ModelConfig.is_active.is_(True),
            ModelConfig.is_default.is_(True),
        )
        if execution.organization_id is not None:
            stmt = stmt.where(ModelConfig.organization_id == execution.organization_id)
        model = (await session.execute(stmt)).scalars().first()

        cost_per_1k = float(model.cost_per_1k_tokens if model else 0.0)
        cost = round((input_tokens + output_tokens) / 1000 * cost_per_1k, 8)

        execution.input_tokens = input_tokens
        execution.output_tokens = output_tokens
        execution.cost = cost
        await session.commit()
