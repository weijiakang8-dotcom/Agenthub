"""用户反馈 API 测试：提交落库 + 邮件通知 + 仅站主可见。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.routes import feedback as feedback_module
from app.main import app


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, scalars=None):
        self._scalars = scalars

    def scalars(self):
        return FakeScalarResult(self._scalars or [])


class FakeSession:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.added = []

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("no execute result configured")
        return self.execute_results.pop(0)

    async def commit(self):
        return None

    def add(self, obj):
        self.added.append(obj)


def _client(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)
    return TestClient(app)


def test_submit_feedback_stores_and_emails(monkeypatch):
    sent: list[dict] = []

    async def fake_send_email(to, subject, text):
        sent.append({"to": to, "subject": subject, "text": text})
        return {"ok": True}

    async def fake_commit(_session):
        return None

    monkeypatch.setattr(feedback_module, "send_email", fake_send_email)
    monkeypatch.setattr(
        feedback_module.settings, "FEEDBACK_NOTIFY_EMAIL", "owner@example.com"
    )
    monkeypatch.setattr(FakeSession, "commit", fake_commit)
    # 提交路径使用 async_session_factory（真实 DB），直接真实落库
    client = _client(monkeypatch)
    response = client.post(
        "/api/feedback",
        json={"content": "界面很高级！", "contact": "user@example.com"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["ok"] is True
    assert data["notified"] is True

    assert len(sent) == 1
    assert sent[0]["to"] == "owner@example.com"
    assert "【AgentHub 用户反馈】" in sent[0]["subject"]
    assert "界面很高级！" in sent[0]["text"]
    assert "user@example.com" in sent[0]["text"]


def test_submit_feedback_rejects_empty_content(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/api/feedback", json={"content": "   "})
    assert response.status_code == 422


def test_list_feedback_requires_admin_key(monkeypatch):
    client = _client(monkeypatch)
    response = client.get("/api/feedback")
    assert response.status_code == 401
