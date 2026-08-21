from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from app.engine import intent
from app.engine.intent import IntentCategory, IntentRouter, RuntimeKind

GOLDEN = json.loads(
    (Path(__file__).resolve().parents[1] / "golden" / "intent_golden.json").read_text(
        encoding="utf-8"
    )
)

EXPECTED_CATEGORIES = {
    "CHAT",
    "KNOWLEDGE",
    "TASK",
    "ACTION",
    "CLARIFICATION",
}


class GoldenGateway:
    """按 golden 的 classifier + flags 输出结构化决策的假 ModelGateway。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, *args, **kwargs):
        return AIMessage(content=json.dumps(self._payload, ensure_ascii=False))


def _classifier_payload(case: dict) -> dict:
    payload = dict(case["classifier"])
    payload.update(case["flags"])
    if case["id"] == "intent-008":
        # golden 008 是“多目标且含副作用”，内部 multi_goal 标记由分类器给出
        payload["multi_goal"] = True
    return payload


def _classify(case: dict) -> intent.IntentDecision:
    return asyncio.run(
        IntentRouter(gateway=GoldenGateway(_classifier_payload(case))).classify(
            case["input"],
            organization_id=None,
            user_id=None,
        )
    )


def test_golden_schema_is_complete():
    assert GOLDEN
    for case in GOLDEN:
        assert {"id", "input", "classifier", "flags", "expected"} <= set(case)
        assert case["classifier"]["category"] in EXPECTED_CATEGORIES
        assert 0.0 <= case["classifier"]["confidence"] <= 1.0


def test_category_set_is_closed():
    assert {c.value for c in intent.IntentCategory} == EXPECTED_CATEGORIES


def test_runtime_mapping_is_static():
    assert intent.decide_runtime(intent.IntentCategory.CHAT) == intent.RuntimeKind.CHAT
    assert (
        intent.decide_runtime(intent.IntentCategory.KNOWLEDGE)
        == intent.RuntimeKind.CHAT
    )
    assert (
        intent.decide_runtime(intent.IntentCategory.CLARIFICATION)
        == intent.RuntimeKind.CHAT
    )
    assert intent.decide_runtime(intent.IntentCategory.TASK) == intent.RuntimeKind.AGENT
    assert (
        intent.decide_runtime(intent.IntentCategory.ACTION) == intent.RuntimeKind.AGENT
    )


def test_classifier_failure_fails_open_to_chat():
    class FailingGateway:
        async def select(self, **kwargs):
            raise RuntimeError("model down")

        async def invoke(self, *args, **kwargs):
            raise RuntimeError("model down")

    router = intent.IntentRouter(gateway=FailingGateway())
    decision = asyncio.run(router.classify("hello", organization_id=None, user_id=None))
    assert decision.category == intent.IntentCategory.CHAT
    assert decision.runtime == intent.RuntimeKind.CHAT
    assert decision.fallback is True


def test_unparseable_output_fails_open_to_chat():
    class WeirdGateway:
        async def select(self, **kwargs):
            return [object()]

        async def invoke(self, *args, **kwargs):
            return AIMessage(content="not json at all")

    router = intent.IntentRouter(gateway=WeirdGateway())
    decision = asyncio.run(router.classify("hello", organization_id=None, user_id=None))
    assert decision.category == intent.IntentCategory.CHAT
    assert decision.fallback is True


def test_low_confidence_with_risk_flags_becomes_clarification():
    # golden: intent-007 / intent-011
    for case in GOLDEN:
        if case["id"] not in {"intent-007", "intent-011"}:
            continue
        decision = _classify(case)
        assert decision.category == IntentCategory.CLARIFICATION
        assert decision.clarification is True
        assert decision.runtime == RuntimeKind.CHAT
        assert decision.fallback is False
        assert decision.risk.value == case["expected"]["risk"]


def test_unresolved_reference_becomes_clarification():
    # golden: intent-007（低置信 + 未解析指代，最终必须是 CLARIFICATION）
    case = next(item for item in GOLDEN if item["id"] == "intent-007")
    decision = _classify(case)
    assert decision.category == IntentCategory.CLARIFICATION
    assert decision.clarification is True

    # 高置信但指代无法在上下文中解析：同样必须 CLARIFICATION
    payload = {
        "category": "ACTION",
        "complexity": "simple",
        "confidence": 0.95,
        "reason": "unresolved reference",
        "requires_tool": True,
        "requires_side_effect": True,
        "requires_approval": True,
        "requires_data": False,
        "needs_knowledge": False,
        "memory_intent": "none",
        "reference_target": "那个东西",
        "multi_goal": False,
    }
    decision = asyncio.run(
        IntentRouter(gateway=GoldenGateway(payload)).classify(
            "把刚才那个东西发给老板",
            organization_id=None,
            user_id=None,
        )
    )
    assert decision.category == IntentCategory.CLARIFICATION
    assert decision.clarification is True
    assert decision.reference_target == "那个东西"


def test_multi_goal_with_side_effect_requires_confirmation():
    # golden: intent-008（查数据 + 发邮件 + 提醒，只识别副作用意图并确认）
    case = next(item for item in GOLDEN if item["id"] == "intent-008")
    decision = _classify(case)
    assert decision.category == IntentCategory.ACTION
    assert decision.runtime == RuntimeKind.AGENT
    assert decision.risk.value == "SIDE_EFFECT"
    assert decision.clarification is True
    assert decision.requires_side_effect is True


def test_memory_intent_does_not_change_runtime():
    # golden: intent-009（save）/ intent-010（delete）
    for case in GOLDEN:
        if case["id"] not in {"intent-009", "intent-010"}:
            continue
        decision = _classify(case)
        assert decision.category == IntentCategory.CHAT
        assert decision.runtime == RuntimeKind.CHAT
        assert decision.memory_intent == case["flags"]["memory_intent"]


def test_needs_web_search_flag_is_preserved_without_changing_runtime():
    # 简单时效性查询：CHAT 保持 CHAT，仅携带 needs_web_search=True
    case = next(item for item in GOLDEN if item["id"] == "intent-016")
    decision = _classify(case)
    assert decision.category == IntentCategory.CHAT
    assert decision.runtime == RuntimeKind.CHAT
    assert decision.needs_web_search is True

    # 内部业务数据：明确不联网
    case = next(item for item in GOLDEN if item["id"] == "intent-018")
    decision = _classify(case)
    assert decision.category == IntentCategory.TASK
    assert decision.needs_web_search is False


def test_risk_is_computed_deterministically():
    # 遍历全部 golden：最终类别、Runtime、risk、clarification 必须与预期一致
    for case in GOLDEN:
        decision = _classify(case)
        expected = case["expected"]
        assert decision.category.value == expected["category"]
        assert decision.runtime.value == expected["runtime"]
        assert decision.risk.value == expected["risk"]
        assert decision.clarification is expected["clarification"]
        assert decision.fallback is expected["fallback"]
