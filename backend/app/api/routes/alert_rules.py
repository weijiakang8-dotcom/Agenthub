import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import SessionDep, get_current_user
from app.models import AlertRule

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    severity: str = "warning"
    condition: dict
    enabled: bool = True
    notification_channels: list = []


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    severity: str | None = None
    condition: dict | None = None
    enabled: bool | None = None
    notification_channels: list | None = None


@router.get("", response_model=None)
async def list_rules(session: SessionDep) -> list[AlertRule]:
    return list((await session.execute(select(AlertRule).order_by(AlertRule.created_at))).scalars().all())


@router.post("", response_model=None, dependencies=[Depends(get_current_user)])
async def create_rule(payload: AlertRuleCreate, session: SessionDep) -> AlertRule:
    rule = AlertRule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=None, dependencies=[Depends(get_current_user)])
async def update_rule(rule_id: uuid.UUID, payload: AlertRuleUpdate, session: SessionDep) -> AlertRule:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204, dependencies=[Depends(get_current_user)])
async def delete_rule(rule_id: uuid.UUID, session: SessionDep) -> None:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    await session.delete(rule)
    await session.commit()


@router.post("/{rule_id}/test", dependencies=[Depends(get_current_user)])
async def test_rule(rule_id: uuid.UUID, session: SessionDep) -> dict:
    rule = await session.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok", "rule": rule.name, "severity": rule.severity}
