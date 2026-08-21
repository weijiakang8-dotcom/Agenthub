from __future__ import annotations

import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import SystemMessage
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.config import settings
from app.core.billing import estimate_tokens, record_execution_usage
from app.core.model_gateway import get_chat_models
from app.core.quota import QuotaExceededError
from app.database import async_session_factory
from app.engine import tool_executor
from app.engine.chat import (
    CHAT_SYSTEM_PROMPT,
    build_chat_messages,
    chat_usage_entries,
    iter_chat_tokens,
)
from app.engine.event_bus import CHANNEL_PREFIX
from app.engine.intent import IntentDecision, IntentRouter, RuntimeKind
from app.engine.observability import record_span
from app.engine.runner import build_context_messages
from app.engine.tasks import evaluate_execution_task, execute_workflow_task
from app.engine.tools import build_search_query, format_search_results
from app.memory.service import add_memory, retrieve_memories, summarize_text
from app.models import Conversation, Execution, Workflow, utcnow
from app.models.enums import ExecutionStatus
from app.rag.retrieval import retrieve_documents

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.ROLLED_BACK,
}


class ConversationCreate(BaseModel):
    title: str = "新对话"


class MessageRequest(BaseModel):
    content: str


def _serialize(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "messages": conversation.messages,
        "summary": conversation.summary,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


async def _persist_assistant_message(
    session, conversation_id: uuid.UUID, content: str
) -> None:
    """在当前 session 内持久化 assistant 最终回复，避免 detached 对象丢失写入。"""
    current_conversation = await session.get(Conversation, conversation_id)
    if current_conversation is None:
        return
    messages = list(current_conversation.messages or [])
    messages.append({"role": "assistant", "content": content})
    current_conversation.messages = messages
    await session.commit()


@router.get("")
async def list_conversations(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(200)
    if user.organization_id is not None:
        stmt = stmt.where(Conversation.organization_id == user.organization_id)
    result = await session.execute(stmt)
    return [_serialize(c) for c in result.scalars().all()]


@router.post("", status_code=201)
async def create_conversation(
    payload: ConversationCreate, session: SessionDep, user: CurrentUserDep
) -> dict:
    conversation = Conversation(
        user_id=user.id,
        organization_id=user.organization_id,
        title=payload.title or "新对话",
        messages=[],
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return _serialize(conversation)


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> dict:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or (
        user.organization_id is not None
        and conversation.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _serialize(conversation)


@router.put("/{conversation_id}")
async def append_message(
    conversation_id: uuid.UUID,
    payload: MessageRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or (
        user.organization_id is not None
        and conversation.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = list(conversation.messages or [])
    messages.append({"role": "user", "content": payload.content})
    conversation.messages = messages
    if conversation.title == "新对话" and payload.content:
        conversation.title = payload.content[:24]
    await session.commit()
    await session.refresh(conversation)
    return _serialize(conversation)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or (
        user.organization_id is not None
        and conversation.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    await session.delete(conversation)
    await session.commit()


async def _get_or_create_chat_workflow(org_id: uuid.UUID | None) -> uuid.UUID:
    async with async_session_factory() as session:
        stmt = select(Workflow).where(Workflow.name == "__chat_default__")
        if org_id is not None:
            stmt = stmt.where(Workflow.organization_id == org_id)
        workflow = (await session.execute(stmt)).scalars().first()
        if workflow is None:
            workflow = Workflow(
                name="__chat_default__",
                description="Chat default workflow",
                agent_chain=[],
                dag_definition=None,
                created_by="system",
                organization_id=org_id,
            )
            session.add(workflow)
            await session.commit()
        return workflow.id


@router.post("/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: uuid.UUID,
    payload: MessageRequest,
    user: CurrentUserDep,
) -> StreamingResponse:
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or (
            user.organization_id is not None
            and conversation.organization_id != user.organization_id
        ):
            raise HTTPException(status_code=404, detail="Conversation not found")

        prior_messages = list(conversation.messages or [])
        summary = conversation.summary
        messages = [*prior_messages, {"role": "user", "content": payload.content}]
        conversation.messages = messages
        if conversation.title == "新对话" and payload.content:
            conversation.title = payload.content[:24]
        await session.commit()

    workflow_id = await _get_or_create_chat_workflow(user.organization_id)
    async with async_session_factory() as session:
        execution = Execution(
            workflow_id=workflow_id,
            user_input=payload.content,
            context_messages=build_context_messages(prior_messages),
            status=ExecutionStatus.PENDING,
            current_step_index=0,
            organization_id=user.organization_id,
            user_id=user.id,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        execution_id = execution.id

    return StreamingResponse(
        _conversation_event_stream(
            execution_id,
            conversation_id,
            payload.content,
            prior_messages,
            user.organization_id,
            user.id,
            summary,
        ),
        media_type="text/event-stream",
    )


@router.post("/{conversation_id}/summarize")
async def summarize_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or (
        user.organization_id is not None
        and conversation.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conversation.messages:
        return {"summary": conversation.summary or ""}
    summary = await summarize_text(
        messages=conversation.messages,
        organization_id=(str(user.organization_id) if user.organization_id else None),
        user_id=str(user.id),
    )
    conversation.summary = summary
    await session.commit()
    return {"summary": summary}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _finalize_chat_execution(
    execution_id: uuid.UUID,
    conversation_id: uuid.UUID,
    final_output: str | None,
    *,
    error: str | None = None,
    usage_entries: list | None = None,
) -> None:
    """在一个事务里落库执行结果与 assistant 消息，避免多次往返。"""
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is not None:
            execution.status = (
                ExecutionStatus.FAILED
                if error is not None
                else ExecutionStatus.COMPLETED
            )
            execution.final_output = final_output
            execution.error_message = error
            execution.completed_at = utcnow()
            execution.steps = [{"role": "chat", "name": "chat", "agent_id": None}]
            if usage_entries:
                execution.checkpoint_data = {"llm_usage": usage_entries}

        conversation = await session.get(Conversation, conversation_id)
        if conversation is not None:
            assistant_content = (
                f"请求失败：{error}" if error is not None else (final_output or "")
            )
            if assistant_content:
                messages = list(conversation.messages or [])
                messages.append({"role": "assistant", "content": assistant_content})
                conversation.messages = messages
        await session.commit()

    if error is None and final_output:
        try:
            await record_execution_usage(execution_id)
        except Exception:
            logger.warning("Failed to record chat usage", exc_info=True)
        try:
            evaluate_execution_task.delay(str(execution_id))
        except Exception:
            logger.warning("Failed to enqueue chat evaluation", exc_info=True)

    try:
        await record_span(
            trace_id=(
                str(execution.correlation_id)
                if execution is not None
                else str(execution_id)
            ),
            name="respond",
            status="ok" if error is None else "error",
            error=error,
            details={
                "execution_id": str(execution_id),
                "conversation_id": str(conversation_id),
            },
        )
    except Exception:
        logger.debug("Failed to record respond span", exc_info=True)


async def _execution_event_stream(
    execution_id: uuid.UUID,
    conversation_id: uuid.UUID,
):
    """Agent 路径：订阅 Redis 事件 + 每秒轮询执行状态，直到结束。"""
    redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    channel = f"{CHANNEL_PREFIX}{execution_id}"
    try:
        await pubsub.subscribe(channel)
        counter = 0
        while True:
            counter += 1
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=0.2
            )
            if message is not None and message.get("type") == "message":
                yield f"data: {message['data']}\n\n"

            if counter % 5 != 0:
                continue
            async with async_session_factory() as session:
                execution = await session.get(Execution, execution_id)
                if execution is None:
                    yield _sse({"event": "error", "message": "execution not found"})
                    return
                yield _sse(
                    {
                        "event": "status",
                        "execution_id": str(execution_id),
                        "status": execution.status.value,
                        "final_output": execution.final_output,
                        "error_message": execution.error_message,
                    }
                )
                if execution.status in _TERMINAL_STATUSES:
                    if execution.final_output:
                        await _persist_assistant_message(
                            session, conversation_id, execution.final_output
                        )
                    await record_span(
                        trace_id=(
                            str(execution.correlation_id)
                            if execution.correlation_id
                            else str(execution_id)
                        ),
                        name="respond",
                        status=(
                            "ok"
                            if execution.status == ExecutionStatus.COMPLETED
                            else "error"
                        ),
                        error=execution.error_message,
                        details={
                            "execution_id": str(execution_id),
                            "conversation_id": str(conversation_id),
                        },
                    )
                    yield _sse(
                        {
                            "event": "done",
                            "status": execution.status.value,
                            "final_output": execution.final_output,
                        }
                    )
                    return
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            logger.debug("Failed to unsubscribe from execution channel", exc_info=True)
        await pubsub.aclose()
        await redis.aclose()


async def _conversation_event_stream(
    execution_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_input: str,
    prior_messages: list,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    summary: str | None,
):
    """Chat 主链路：先分类，任务型走 Agent 队列，其余直接流式回答。"""
    execution_id_str = str(execution_id)
    yield _sse(
        {
            "event": "status",
            "execution_id": execution_id_str,
            "status": ExecutionStatus.PENDING.value,
            "final_output": None,
        }
    )

    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        correlation_id = (
            str(execution.correlation_id) if execution is not None else None
        )

    decision: IntentDecision = await IntentRouter().classify(
        user_input,
        organization_id=str(organization_id) if organization_id else None,
        user_id=str(user_id) if user_id else None,
        correlation_id=correlation_id,
    )
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is not None:
            execution.intent = decision.model_dump()
            await session.commit()

    # Memory Policy：仅显式表达（save/update）时写入长期记忆，失败不打断聊天
    if decision.memory_intent in {"save", "update"}:
        try:
            await add_memory(
                user_id=user_id,
                organization_id=organization_id,
                content=user_input,
                source="user",
            )
        except Exception:
            logger.warning(
                "Explicit memory write failed; continuing chat", exc_info=True
            )

    if decision.runtime == RuntimeKind.AGENT:
        try:
            execute_workflow_task.delay(execution_id_str)
        except Exception as exc:
            logger.warning("Task broker unavailable for chat execution", exc_info=True)
            yield _sse(
                {
                    "event": "error",
                    "execution_id": execution_id_str,
                    "message": "任务队列不可用，请稍后重试",
                }
            )
            yield _sse(
                {
                    "event": "done",
                    "execution_id": execution_id_str,
                    "status": ExecutionStatus.FAILED.value,
                    "error_message": str(exc),
                }
            )
            return
        async for event in _execution_event_stream(execution_id, conversation_id):
            yield event
        return

    search_context: str | None = None
    if decision.needs_web_search:
        query = build_search_query(user_input)
        yield _sse(
            {
                "event": "search",
                "execution_id": execution_id_str,
                "status": "started",
                "query": query,
            }
        )
        try:
            search_result = await tool_executor.execute_tool(
                "search_web", {"query": query}, execution_id
            )
        except Exception:
            logger.warning("Chat web search failed; continuing", exc_info=True)
            search_result = {"status": "failed", "error": "search service error"}
        if search_result.get("status") == "success":
            search_context = format_search_results(search_result.get("data") or [])
        else:
            search_context = format_search_results(
                None, error=str(search_result.get("error") or "search failed")
            )
        yield _sse(
            {
                "event": "search",
                "execution_id": execution_id_str,
                "status": "completed",
                "ok": search_result.get("status") == "success",
            }
        )

    llms = await get_chat_models(
        organization_id=str(organization_id) if organization_id else None,
        complexity="simple",
        user_id=str(user_id) if user_id else None,
    )
    model_used = getattr(llms[0], "model_name", None) if llms else None
    try:
        memories = await retrieve_memories(
            user_id=user_id,
            organization_id=organization_id,
            query=user_input,
            top_k=3,
            correlation_id=correlation_id,
        )
    except Exception:
        logger.warning("Memory retrieval failed; continuing", exc_info=True)
        memories = []
    messages = build_chat_messages(
        prior_messages,
        user_input,
        summary=summary,
        memories=memories,
    )

    system_prompt = CHAT_SYSTEM_PROMPT
    if decision.category.value == "KNOWLEDGE":
        try:
            docs = await retrieve_documents(
                user_input,
                organization_id,
                top_k=3,
                correlation_id=correlation_id,
            )
        except Exception:
            logger.warning(
                "Chat RAG retrieval failed; answering without context", exc_info=True
            )
            docs = []
        if docs:
            snippets = "\n---\n".join(doc["content"][:1000] for doc in docs)
            system_prompt += (
                f"\n\n【知识库资料，仅供参考】\n<context>\n{snippets}\n</context>"
            )

    if search_context:
        system_prompt += f"\n\n{search_context}"

    chat_messages = [SystemMessage(content=system_prompt), *messages]
    parts: list[str] = []
    try:
        async for token in iter_chat_tokens(
            llms,
            chat_messages,
            organization_id=str(organization_id) if organization_id else None,
            correlation_id=correlation_id,
        ):
            parts.append(token)
            yield _sse(
                {
                    "event": "token",
                    "execution_id": execution_id_str,
                    "token": token,
                }
            )
        final_output = "".join(parts)
        await _finalize_chat_execution(
            execution_id,
            conversation_id,
            final_output or None,
            usage_entries=chat_usage_entries(
                model_used,
                None,
                input_tokens=estimate_tokens(user_input),
                output_tokens=estimate_tokens(final_output or ""),
            ),
        )
        yield _sse(
            {
                "event": "done",
                "execution_id": execution_id_str,
                "status": ExecutionStatus.COMPLETED.value,
                "final_output": final_output,
            }
        )
    except QuotaExceededError as exc:
        message = str(exc)
        await _finalize_chat_execution(
            execution_id,
            conversation_id,
            None,
            error=message,
        )
        yield _sse(
            {
                "event": "error",
                "execution_id": execution_id_str,
                "message": message,
            }
        )
        yield _sse(
            {
                "event": "done",
                "execution_id": execution_id_str,
                "status": ExecutionStatus.FAILED.value,
                "error_message": message,
            }
        )
    except Exception as exc:
        logger.warning("Chat streaming failed", exc_info=True)
        await _finalize_chat_execution(
            execution_id,
            conversation_id,
            None,
            error=str(exc),
        )
        yield _sse(
            {
                "event": "error",
                "execution_id": execution_id_str,
                "message": str(exc),
            }
        )
        yield _sse(
            {
                "event": "done",
                "execution_id": execution_id_str,
                "status": ExecutionStatus.FAILED.value,
                "error_message": str(exc),
            }
        )
