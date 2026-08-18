from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.adapters.errors import UnsupportedKernelWorkflowError
from app.api.deps import CurrentUserDep, SessionDep
from app.database import async_session_factory
from app.models import Execution, Skill, Workflow
from app.models.enums import ExecutionStatus, WorkflowStatus

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    goal: dict
    plan_template: dict
    icon: str = "sparkles"


class SkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    goal: dict | None = None
    plan_template: dict | None = None
    icon: str | None = None


class SkillExecute(BaseModel):
    input: str = Field(..., min_length=1)


def _serialize(skill: Skill) -> dict:
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "goal": skill.goal,
        "plan_template": skill.plan_template,
        "icon": skill.icon,
        "organization_id": (
            str(skill.organization_id) if skill.organization_id else None
        ),
        "created_by": str(skill.created_by) if skill.created_by else None,
        "created_at": skill.created_at,
    }


def _resolve_placeholders(value: Any, user_input: str, execution_id: uuid.UUID) -> Any:
    if isinstance(value, str):
        return value.replace("{input}", user_input).replace(
            "{execution_id}", str(execution_id)
        )
    if isinstance(value, list):
        return [_resolve_placeholders(item, user_input, execution_id) for item in value]
    if isinstance(value, dict):
        return {
            key: _resolve_placeholders(item, user_input, execution_id)
            for key, item in value.items()
        }
    return value


@router.get("")
async def list_skills(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    stmt = select(Skill).where(
        or_(
            Skill.organization_id.is_(None),
            Skill.organization_id == user.organization_id,
        )
    )
    result = await session.execute(stmt.order_by(Skill.created_at))
    return [_serialize(skill) for skill in result.scalars().all()]


@router.post("", status_code=201)
async def create_skill(
    payload: SkillCreate, session: SessionDep, user: CurrentUserDep
) -> dict:
    skill = Skill(
        name=payload.name,
        description=payload.description,
        goal=payload.goal,
        plan_template=payload.plan_template,
        icon=payload.icon,
        organization_id=user.organization_id,
        created_by=user.id,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return _serialize(skill)


@router.put("/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    payload: SkillUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.created_by != user.id:
        raise HTTPException(status_code=404, detail="Skill not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, field, value)
    await session.commit()
    await session.refresh(skill)
    return _serialize(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    skill = await session.get(Skill, skill_id)
    if skill is None or skill.created_by != user.id:
        raise HTTPException(status_code=404, detail="Skill not found")
    await session.delete(skill)
    await session.commit()


@router.post("/{skill_id}/execute", status_code=202)
async def execute_skill(
    skill_id: uuid.UUID,
    payload: SkillExecute,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    skill = await session.get(Skill, skill_id)
    if skill is None or (
        skill.organization_id is not None
        and skill.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Skill not found")

    workflow = Workflow(
        name=f"skill:{skill.name}",
        description=skill.description,
        agent_chain=[],
        dag_definition={"kernel_plan": skill.plan_template},
        status=WorkflowStatus.ACTIVE,
        created_by=str(user.id),
        organization_id=user.organization_id,
    )
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)

    execution = Execution(
        workflow_id=workflow.id,
        user_input=payload.input,
        status=ExecutionStatus.PENDING,
        current_step_index=0,
        organization_id=user.organization_id,
        user_id=user.id,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)

    # 用占位符解析后的计划覆写（{input}/{execution_id} 由真实用户输入替换）。
    resolved = _resolve_placeholders(skill.plan_template, payload.input, execution.id)
    workflow.dag_definition = {"kernel_plan": resolved}
    await session.commit()

    from app.adapters.kernel_runner import run_kernel_execution

    try:
        await run_kernel_execution(execution.id)
    except UnsupportedKernelWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with async_session_factory() as read_session:
        refreshed = await read_session.get(Execution, execution.id)
    return {
        "execution_id": str(execution.id),
        "status": refreshed.status.value if refreshed else "pending",
    }
