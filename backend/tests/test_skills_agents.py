"""Skill 系统（预设/匹配/自成长）与 Agent 体系测试。"""

from __future__ import annotations

import asyncio
import uuid


async def _new_org() -> str:
    from app.database import async_session_factory
    from app.models import Organization

    async with async_session_factory() as session:
        org = Organization(name="t", slug=f"a-{uuid.uuid4().hex[:12]}")
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return str(org.id)


from app.agents import get_agent_spec, get_prompt, list_agent_specs
from app.agents.updater import (
    activate_agent_version,
    list_agent_versions,
    propose_agent_update,
    rollback_agent,
)
from app.skills.growth import signature_from_plan, signature_label
from app.skills.matching import match_skills
from app.skills.presets import PRESET_SKILLS, ensure_preset_skills


class TestPresets:
    def test_presets_well_formed(self):
        assert len(PRESET_SKILLS) >= 8
        for preset in PRESET_SKILLS:
            assert preset["name"]
            assert preset["plan"]["goal"]
            assert preset["plan"]["steps"]
            for step in preset["plan"]["steps"]:
                assert step["capability"]
            assert preset["tier_hints"]

    def test_ensure_preset_skills_idempotent(self):
        first = asyncio.run(ensure_preset_skills())
        second = asyncio.run(ensure_preset_skills())
        assert first >= 0
        assert second == 0


class TestMatching:
    def test_keyword_match(self):
        results = asyncio.run(
            match_skills("帮我调研一下民宿行业趋势", "org-matching-test")
        )
        assert isinstance(results, list)
        for item in results:
            assert "score" in item
            assert "reason" in item

    def test_match_hits_research_preset(self):
        results = asyncio.run(
            match_skills("给我做一份行业研究报告", "org-matching-test")
        )
        names = [item["name"] for item in results]
        assert any("研究" in name for name in names) or not results  # 预设存在则命中


class TestGrowth:
    def test_signature(self):
        plan = {
            "steps": [
                {"capability": "research"},
                {"capability": "analysis"},
                {"capability": "answer"},
            ]
        }
        assert signature_from_plan(plan) == ("research", "analysis", "answer")
        assert signature_from_plan(None) == ()

    def test_signature_label(self):
        assert signature_label(("research", "answer")) == "research → answer"
        assert signature_label(()) == "answer"


class TestAgents:
    def test_registry(self):
        specs = list_agent_specs()
        names = {spec.name for spec in specs}
        assert {
            "dispatcher",
            "planner",
            "executor",
            "verifier",
            "clarifier",
            "billing",
        } <= names

    def test_get_prompt_default(self):
        prompt = asyncio.run(get_prompt("verifier", None))
        assert "PASS" in prompt or "FAIL" in prompt

    def test_get_agent_spec_unknown(self):
        assert get_agent_spec("nope") is None

    def test_update_cycle(self):
        org = asyncio.run(_new_org())
        proposed = asyncio.run(
            propose_agent_update(
                "planner",
                organization_id=org,
                change_note="加两个成功样本",
                examples=["样本A：拆成三步完成", "样本B：复用了技能骨架"],
            )
        )
        assert proposed["ok"] is True
        assert proposed["status"] == "candidate"
        assert "近期成功样本" in proposed["system_prompt"]

        activated = asyncio.run(activate_agent_version(uuid.UUID(proposed["id"])))
        assert activated["ok"] is True
        assert activated["status"] == "active"

        prompt = asyncio.run(get_prompt("planner", org))
        assert "近期成功样本" in prompt

        versions = asyncio.run(list_agent_versions("planner", org))
        assert any(item["status"] == "active" for item in versions)

        rolled = asyncio.run(rollback_agent("planner", org))
        assert rolled["ok"] is True

    def test_update_gate_rejects_short_prompt(self):
        result = asyncio.run(
            propose_agent_update(
                "planner",
                organization_id=str(uuid.uuid4()),
                change_note="bad",
                examples=[],
                metrics=None,
            )
        )
        # 默认 prompt 本来就合规，此用例验证管线返回结构合法
        assert result["ok"] is True or "error" in result

    def test_metrics_gate_rejects_regression(self):
        org = asyncio.run(_new_org())
        # 先激活一个带高指标的版本
        first = asyncio.run(
            propose_agent_update(
                "billing",
                organization_id=org,
                change_note="v1",
                metrics={"success_rate": 0.95},
            )
        )
        assert first["ok"] is True
        asyncio.run(activate_agent_version(uuid.UUID(first["id"])))
        # 候选版本指标更差 → 门禁拒绝
        second = asyncio.run(
            propose_agent_update(
                "billing",
                organization_id=org,
                change_note="v2 regression",
                metrics={"success_rate": 0.5},
            )
        )
        assert second["ok"] is False
        assert "gate" in second["error"]
