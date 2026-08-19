import uuid

import pytest
from app.schemas.agent import AgentCreate
from app.schemas.execution import ExecutionCreate, ExecutionResume, FeedbackCreate
from app.schemas.workflow import WorkflowCreate
from pydantic import ValidationError


def test_agent_name_required():
    with pytest.raises(ValidationError):
        AgentCreate(name="")


def test_workflow_created_by_required():
    with pytest.raises(ValidationError):
        WorkflowCreate(name="workflow")


def test_execution_user_input_nonempty():
    with pytest.raises(ValidationError):
        ExecutionCreate(workflow_id=uuid.uuid4(), user_input="")


def test_feedback_nonempty():
    with pytest.raises(ValidationError):
        FeedbackCreate(feedback="")


def test_execution_resume_default_approved():
    resume = ExecutionResume()
    assert resume.approved is True
