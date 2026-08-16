from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from app.models.tool_call import ToolCall
    from app.models.workflow import Workflow


class Execution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution（工作流实例/运行记录）。"""

    __tablename__ = "executions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(
            ExecutionStatus,
            name="execution_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=ExecutionStatus.PENDING,
    )
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # LangGraph 的 Checkpoint 状态快照，开始运行前可为空
    checkpoint_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    final_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    eval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    workflow: Mapped[Workflow] = relationship(
        back_populates="executions", lazy="selectin"
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="execution", cascade="all, delete-orphan", lazy="selectin"
    )
