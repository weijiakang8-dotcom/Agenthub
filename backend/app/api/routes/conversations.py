from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.database import async_session_factory
from app.models import Conversation, Execution, Workflow
from app.models.enums import ExecutionStatus
from app.engine.tasks import execute_workflow_task


router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = "新对话"


class MessageRequest(BaseModel):
    content: str


def _serialize(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "messages": conversation.messages,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


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
            await session.refresh(workflow)
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

        messages = list(conversation.messages or [])
        messages.append({"role": "user", "content": payload.content})
        conversation.messages = messages
        if conversation.title == "新对话" and payload.content:
            conversation.title = payload.content[:24]
        await session.commit()

    workflow_id = await _get_or_create_chat_workflow(user.organization_id)
    async with async_session_factory() as session:
        execution = Execution(
            workflow_id=workflow_id,
            user_input=payload.content,
            status=ExecutionStatus.PENDING,
            current_step_index=0,
            organization_id=user.organization_id,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)
        execution_id = execution.id

    execute_workflow_task.delay(str(execution_id))

    async def event_stream():
        while True:
            await asyncio.sleep(1)
            async with async_session_factory() as session:
                execution = await session.get(Execution, execution_id)
                if execution is None:
                    yield f"data: {json.dumps({'event': 'error', 'message': 'execution not found'}, ensure_ascii=False)}\n\n"
                    return

                data = {
                    "event": "status",
                    "status": execution.status.value,
                    "final_output": execution.final_output,
                    "error_message": execution.error_message,
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                if execution.status in {
                    ExecutionStatus.COMPLETED,
                    ExecutionStatus.FAILED,
                    ExecutionStatus.ROLLED_BACK,
                }:
                    if execution.final_output:
                        messages = list(conversation.messages or [])
                        messages.append({"role": "assistant", "content": execution.final_output})
                        conversation.messages = messages
                        await session.commit()
                    yield f"data: {json.dumps({'event': 'done', 'status': execution.status.value, 'final_output': execution.final_output}, ensure_ascii=False)}\n\n"
                    return

    return StreamingResponse(event_stream(), media_type="text/event-stream")
