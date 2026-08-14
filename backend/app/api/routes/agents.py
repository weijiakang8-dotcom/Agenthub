import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep, get_current_user
from app.models import Agent
from app.models.enums import AgentStatus
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate


router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
async def list_agents(
    session: SessionDep,
    user: CurrentUserDep,
    status: AgentStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Agent]:
    stmt = select(Agent)
    if user.organization_id is not None:
        stmt = stmt.where(Agent.organization_id == user.organization_id)
    if status is not None:
        stmt = stmt.where(Agent.status == status)
    stmt = stmt.order_by(Agent.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user.organization_id is not None and agent.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post(
    "",
    response_model=AgentRead,
    status_code=201,
    dependencies=[Depends(get_current_user)],
)
async def create_agent(payload: AgentCreate, session: SessionDep, user: CurrentUserDep) -> Agent:
    existing = await session.execute(
        select(Agent).where(
            Agent.name == payload.name,
            Agent.organization_id == user.organization_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Agent name already exists")

    agent = Agent(**payload.model_dump(), organization_id=user.organization_id)
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.put(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(get_current_user)],
)
async def update_agent(
    agent_id: uuid.UUID, payload: AgentUpdate, session: SessionDep, user: CurrentUserDep
) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user.organization_id is not None and agent.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        dup = await session.execute(
            select(Agent).where(
                Agent.name == data["name"],
                Agent.id != agent_id,
                Agent.organization_id == user.organization_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Agent name already exists")

    for key, value in data.items():
        setattr(agent, key, value)

    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete(
    "/{agent_id}",
    status_code=204,
    dependencies=[Depends(get_current_user)],
)
async def delete_agent(agent_id: uuid.UUID, session: SessionDep, user: CurrentUserDep) -> None:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if user.organization_id is not None and agent.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = AgentStatus.INACTIVE
    await session.commit()
    return None
