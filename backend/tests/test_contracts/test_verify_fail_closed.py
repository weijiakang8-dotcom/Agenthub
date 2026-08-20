"""ADR-005 Verify Fail-Closed 契约测试。

覆盖 TEST-1..TEST-6：PASS 变体 / FAIL replan 守卫 / ERROR / 空输出 UNKNOWN /
非法内容 UNKNOWN / verify 预算 ≤1。
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage

from app.engine import graph as graph_module


def _state(**overrides: Any) -> dict[str, Any]:
    state = {
        "final_output": "ok",
        "user_input": "用户输入",
        "execution_id": "exec-1",
        "organization_id": "org-1",
        "user_id": "user-1",
        "revision_count": 0,
        "llm_usage": [],
        "budget_used": {"verifies": 0, "max_verifies": 1},
    }
    state.update(overrides)
    return state


def _install(monkeypatch, *, content: Any = None, raise_error: bool = False):
    invoked: list[Any] = []
    audits: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []

    async def fake_get_llms(organization_id, complexity=None, user_id=None):
        return [object()]

    async def fake_invoke(llms, messages, **kwargs):
        invoked.append(messages)
        if raise_error:
            raise TimeoutError("verifier timeout")
        return AIMessage(content=content)

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    async def fake_span(**kwargs):
        spans.append(kwargs)

    monkeypatch.setattr(graph_module, "_get_llms", fake_get_llms)
    monkeypatch.setattr(graph_module._gateway, "invoke", fake_invoke)
    monkeypatch.setattr(graph_module, "audit_execution_event", fake_audit)
    monkeypatch.setattr(graph_module, "record_span", fake_span)
    return invoked, audits, spans


def _run_node(state: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(graph_module._verify_node(state))


def test_pass_variants_do_not_replan(monkeypatch):
    for text in ("PASS", " pass ", "Pass"):
        invoked, audits, spans = _install(monkeypatch, content=text)
        result = _run_node(_state())
        assert result["revision_requested"] is False
        assert len(invoked) == 1
        assert audits == []
        assert spans[-1]["status"] == "ok"
        assert spans[-1]["details"]["result"] == "PASS"
        assert result["budget_used"]["verifies"] == 1


def test_fail_replans_once_then_guard(monkeypatch):
    _, _, _ = _install(monkeypatch, content="FAIL")
    first = _run_node(_state(revision_count=0))
    assert first["revision_requested"] is True
    assert first["revision_count"] == 1
    assert first["final_output"] is None

    second = _run_node(_state(revision_count=1))
    assert second["revision_requested"] is False
    assert second["budget_used"]["verifies"] == 1


def test_error_no_replan_audit_and_span(monkeypatch):
    invoked, audits, spans = _install(monkeypatch, raise_error=True)
    result = _run_node(_state())
    assert result["revision_requested"] is False
    assert len(invoked) == 1
    assert any(a["action"] == "verify_error" for a in audits)
    assert spans[-1]["status"] == "error"
    assert spans[-1]["details"]["result"] == "ERROR"
    assert result["final_output"] == "ok"


def test_empty_output_unknown_without_llm_call(monkeypatch):
    invoked, audits, spans = _install(monkeypatch)
    result = _run_node(_state(final_output=""))
    assert result["revision_requested"] is False
    assert len(invoked) == 0
    assert any(a["action"] == "verify_unknown" for a in audits)
    assert spans[-1]["status"] == "error"
    assert spans[-1]["details"]["result"] == "UNKNOWN"
    assert result["budget_used"]["verifies"] == 0


def test_malformed_output_unknown(monkeypatch):
    for text in ("PAS", "OK", "满足", ""):
        _, audits, spans = _install(monkeypatch, content=text)
        result = _run_node(_state())
        assert result["revision_requested"] is False
        assert any(a["action"] == "verify_unknown" for a in audits)
        assert spans[-1]["details"]["result"] == "UNKNOWN"
        assert result["final_output"] == "ok"


def test_verify_budget_respected(monkeypatch):
    invoked, _, _ = _install(monkeypatch, content="PASS")
    result = _run_node(_state(budget_used={"verifies": 1, "max_verifies": 1}))
    assert result["revision_requested"] is False
    assert len(invoked) == 0
    assert result["budget_used"]["verifies"] == 1


def test_classify_verify_output_pure():
    assert graph_module.classify_verify_output("PASS") == "PASS"
    assert graph_module.classify_verify_output(" pass ") == "PASS"
    assert graph_module.classify_verify_output("FAIL") == "FAIL"
    assert graph_module.classify_verify_output(" fail ") == "FAIL"
    assert graph_module.classify_verify_output(None) == "UNKNOWN"
    assert graph_module.classify_verify_output("") == "UNKNOWN"
    assert graph_module.classify_verify_output("PAS") == "UNKNOWN"
    assert graph_module.classify_verify_output("满足") == "UNKNOWN"
