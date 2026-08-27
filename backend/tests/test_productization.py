from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import executions, skills, user_api_keys
from app.core import model_gateway, security
from app.models import UserApiKey


def _user(organization_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=(
            organization_id if organization_id is not None else uuid.uuid4()
        ),
        role="member",
    )


class FakeSession:
    def __init__(self, get_results=None):
        self.get_results = list(get_results or [])
        self.added = []
        self.deleted = []
        self.commits = 0

    async def get(self, _model, _obj_id):
        if not self.get_results:
            return None
        return self.get_results.pop(0)

    async def execute(self, _stmt):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=list, first=lambda: None)
        )

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        if hasattr(obj, "created_at"):
            obj.created_at = obj.created_at or "2026-08-18T00:00:00Z"


def test_encrypt_decrypt_roundtrip_and_mask():
    secret = "sk-live-abcdef123456"
    ciphertext = security.encrypt_secret(secret)

    assert ciphertext != secret
    assert security.decrypt_secret(ciphertext) == secret
    assert security.decrypt_secret("not-a-token") is None
    assert security.mask_secret(secret).startswith("sk-liv")
    assert security.mask_secret(secret).endswith("*")


def test_user_api_key_create_lists_masked_only(monkeypatch):
    async def allow_public_url(_url: str):
        return None

    monkeypatch.setattr(user_api_keys, "_validate_public_url", allow_public_url)
    user = _user()
    session = FakeSession()

    result = asyncio.run(
        user_api_keys.create_key(
            user_api_keys.UserApiKeyCreate(
                provider="deepseek",
                model="deepseek-v4-flash",
                base_url="https://api.deepseek.com/v1",
                api_key="sk-live-abcdef123456",
            ),
            session=session,
            user=user,
        )
    )

    assert result["api_key_masked"] == "****3456"
    assert result["api_mode"] == "chat_completions"
    assert "api_key" not in result
    stored = session.added[0]
    assert isinstance(stored, UserApiKey)
    assert stored.api_key_encrypted != "sk-live-abcdef123456"
    assert security.decrypt_secret(stored.api_key_encrypted) == "sk-live-abcdef123456"


def test_user_api_key_persists_responses_mode_without_schema_change(monkeypatch):
    async def allow_public_url(_url: str):
        return None

    monkeypatch.setattr(user_api_keys, "_validate_public_url", allow_public_url)
    session = FakeSession()
    result = asyncio.run(
        user_api_keys.create_key(
            user_api_keys.UserApiKeyCreate(
                provider="openai",
                model="gpt-5",
                base_url="https://api.openai.com/v1",
                api_key="sk-openai-1234",
                api_mode="responses",
            ),
            session=session,
            user=_user(),
        )
    )

    assert session.added[0].provider == "openai:responses"
    assert result["provider"] == "openai"
    assert result["api_mode"] == "responses"


def test_user_api_key_delete_scoped_to_owner():
    user = _user()
    other_key = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    session = FakeSession(get_results=[other_key])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(user_api_keys.delete_key(other_key.id, session=session, user=user))

    assert exc.value.status_code == 404


def test_feedback_upsert_and_tenant_isolation():
    user = _user(organization_id=uuid.uuid4())
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=user.organization_id,
    )
    session = FakeSession(get_results=[execution])

    result = asyncio.run(
        executions.submit_feedback(
            execution.id,
            executions.FeedbackCreate(feedback="like", rating=5, comment="很好"),
            session=session,
            user=user,
        )
    )

    assert result.feedback == "like"
    feedback_row = session.added[0]
    assert feedback_row.execution_id == execution.id
    assert feedback_row.user_id == user.id
    assert feedback_row.rating == 5

    foreign = _user(organization_id=uuid.uuid4())
    foreign_session = FakeSession(get_results=[execution])
    with pytest.raises(HTTPException):
        asyncio.run(
            executions.submit_feedback(
                execution.id,
                executions.FeedbackCreate(feedback="dislike", rating=1),
                session=foreign_session,
                user=foreign,
            )
        )


def test_skill_execute_builds_kernel_plan_and_runs(monkeypatch):
    user = _user()
    skill_row = SimpleNamespace(
        id=uuid.uuid4(),
        name="web-observe",
        description="观察外部数据",
        goal={"predicate": "observation_exists", "required_evidence": "L3_OBSERVED"},
        plan_template={
            "goal": {
                "predicate": "observation_exists",
                "required_evidence": "L3_OBSERVED",
            },
            "tasks": [
                {
                    "task_id": "t-observe",
                    "capability_id": "observe",
                    "idempotency_key": "skill-{execution_id}",
                    "payload": {"url": "{input}"},
                }
            ],
        },
        icon="eye",
        organization_id=user.organization_id,
        created_by=user.id,
        created_at="2026-08-18T00:00:00Z",
    )
    completed = SimpleNamespace(
        id=uuid.uuid4(), status=SimpleNamespace(value="completed")
    )
    session = FakeSession(get_results=[skill_row, completed])
    runs = []

    async def fake_run(execution_id):
        runs.append(execution_id)

    monkeypatch.setattr("app.adapters.kernel_runner.run_kernel_execution", fake_run)

    class FakeReadSession:
        async def get(self, _model, _obj_id):
            return completed

    class FakeReadFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return FakeReadSession()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(skills, "async_session_factory", FakeReadFactory())

    result = asyncio.run(
        skills.execute_skill(
            skill_row.id,
            skills.SkillExecute(input="https://example.com/data"),
            session=session,
            user=user,
        )
    )

    assert result["status"] == "completed"
    assert len(runs) == 1
    workflow = session.added[0]
    assert workflow.dag_definition["kernel_plan"]["tasks"][0]["payload"]["url"] == (
        "https://example.com/data"
    )


def test_get_chat_models_prefers_user_keys_then_system(monkeypatch):
    user_id = uuid.uuid4()

    async def fake_user_keys(_uid):
        return [
            SimpleNamespace(
                provider="user-provider",
                model="user-model",
                base_url="https://user.example.com/v1",
                api_key_encrypted=security.encrypt_secret("sk-user"),
            )
        ]

    async def fake_system_models(_org):
        return [
            SimpleNamespace(
                model="deepseek-v4-pro",
                base_url="https://api.deepseek.com/v1",
                api_key="sk-system",
                max_tokens=4096,
                timeout=120,
                max_retries=2,
                cost_per_1k_tokens=0.02,
                priority=1,
            )
        ]

    monkeypatch.setattr(model_gateway, "list_user_api_keys", fake_user_keys)
    monkeypatch.setattr(model_gateway, "list_active_models", fake_system_models)

    llms = asyncio.run(
        model_gateway.get_chat_models("org", complexity="complex", user_id=user_id)
    )

    assert [llm.model_name for llm in llms] == ["user-model", "deepseek-v4-pro"]
    assert llms[0].use_responses_api is False


def test_get_chat_models_uses_responses_for_openai_user_key(monkeypatch):
    async def fake_user_keys(_uid):
        return [
            SimpleNamespace(
                provider="openai:responses",
                model="gpt-5",
                base_url="https://api.openai.com/v1",
                api_key_encrypted=security.encrypt_secret("sk-openai"),
            )
        ]

    async def fake_system_models(_org):
        return []

    monkeypatch.setattr(model_gateway, "list_user_api_keys", fake_user_keys)
    monkeypatch.setattr(model_gateway, "list_active_models", fake_system_models)

    llms = asyncio.run(
        model_gateway.get_chat_models("org", complexity="complex", user_id=uuid.uuid4())
    )

    assert llms[0].model_name == "gpt-5"
    assert llms[0].use_responses_api is True
    assert llms[0].metadata["provider"] == "openai"
    assert llms[0].metadata["api_mode"] == "responses"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/api",
        "http://10.0.0.1/api",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/api",
        "file:///etc/passwd",
    ],
)
def test_real_effect_executor_rejects_unsafe_observe_urls(url):
    from app.adapters.real_effect_executor import RealEffectExecutor
    from app.kernel.effects.command import Command

    result = RealEffectExecutor().execute_effect(
        Command(
            command_id="unsafe-observe",
            idempotency_key="unsafe-observe",
            capability_id="observe",
            payload={"url": url},
        )
    )

    assert result.status == "error"
    assert result.committed is None
    assert "public HTTP" in result.error


def test_real_effect_executor_keeps_url_query_string(monkeypatch):
    from app.adapters.real_effect_executor import RealEffectExecutor
    from app.kernel.effects.command import Command

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def __init__(self):
            self.headers: dict[str, str] = {}

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    async def fake_request_public(client, method, url, **kwargs):
        assert method == "GET"
        return await client.get(url, params=kwargs.get("params"))

    monkeypatch.setattr(
        "app.adapters.real_effect_executor.httpx.AsyncClient", FakeClient
    )
    monkeypatch.setattr(
        "app.adapters.real_effect_executor.request_public", fake_request_public
    )

    result = RealEffectExecutor().execute_effect(
        Command(
            command_id="c1",
            idempotency_key="k1",
            capability_id="observe",
            payload={"url": "http://example.test/api?query=abc"},
        )
    )

    assert captured["url"] == "http://example.test/api?query=abc"
    assert captured["params"] is None
    assert result.status == "success"
    assert result.committed is True


def test_prompt_optimize_returns_optimized_text(monkeypatch):
    from app.api.routes import prompts

    class FakeResponse:
        content = "优化后的提示词"

    class FakeGateway:
        async def select(self, **kwargs):
            return [object()]

        async def invoke(self, _llms, _messages, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(prompts, "ModelGateway", FakeGateway)

    result = asyncio.run(
        prompts.optimize_prompt(
            prompts.PromptOptimizeRequest(content="帮我查一下天气"),
            _user(),
        )
    )

    assert result == {"optimized": "优化后的提示词"}
