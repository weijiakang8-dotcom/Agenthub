"""复杂度评分器 + 路由策略引擎单元测试。"""

from __future__ import annotations

from app.core.complexity import (
    ComplexityScore,
    explain,
    in_gray_zone,
    score_step,
    score_task,
)
from app.core.routing import (
    DEFAULT_TIER,
    RouteChoice,
    allow_escalation,
    build_route,
    choose_complexity,
    normalize_tier,
)


class TestScoreTask:
    def test_plain_chat_scores_low(self):
        score = score_task("你好", intent={"category": "CHAT"})
        assert score.level == "simple"
        assert 0.0 < score.score < 0.5
        assert score.source == "rules"

    def test_side_effect_task_scores_high(self):
        score = score_task(
            "把报告发给老板",
            intent={"category": "ACTION", "requires_side_effect": True},
        )
        assert score.score >= 0.3

    def test_multi_step_plan_raises_score(self):
        simple = score_task("算一下 1+1", intent={"category": "TASK"})
        complex_task = score_task(
            "调研行业趋势并写报告",
            intent={
                "category": "TASK",
                "requires_tool": True,
                "needs_web_search": True,
            },
            plan={
                "steps": [
                    {"step_id": "s1", "capability": "research"},
                    {"step_id": "s2", "capability": "analysis"},
                    {"step_id": "s3", "capability": "answer"},
                    {"step_id": "s4", "capability": "analysis"},
                ]
            },
        )
        assert complex_task.score > simple.score

    def test_judge_blends_and_is_explainable(self):
        score = score_task(
            "帮我查点东西",
            intent={"category": "TASK", "requires_tool": True},
            judge_result={"score": 0.9, "confidence": 0.9, "reason": "需要深度推理"},
        )
        assert score.source == "rules+judge"
        assert "深度推理" in explain(score)

    def test_weak_history_bumps_score(self):
        base = score_task("查一下数据", intent={"category": "TASK"})
        bumped = score_task(
            "查一下数据",
            intent={"category": "TASK"},
            stats={"attempts": 10, "success_rate": 0.3},
        )
        assert bumped.score >= base.score
        assert bumped.source == "rules+stats"

    def test_score_bounded(self):
        for _ in range(20):
            score = score_task(
                "x" * 1000,
                intent={
                    "category": "ACTION",
                    "requires_tool": True,
                    "requires_data": True,
                    "requires_side_effect": True,
                    "multi_goal": True,
                },
            )
            assert 0.0 <= score.score <= 1.0


class TestScoreStep:
    def test_analysis_step_scores_higher_than_search(self):
        analysis = score_step({"capability": "analysis"}, 0.4)
        search = score_step({"capability": "web_search"}, 0.4)
        assert analysis.score > search.score

    def test_step_bounded(self):
        assert 0.0 <= score_step({"capability": "analysis"}, 0.95).score <= 1.0


class TestGrayZone:
    def test_gray_zone(self):
        assert in_gray_zone(0.5)
        assert not in_gray_zone(0.1)
        assert not in_gray_zone(0.9)


class TestRouting:
    def test_normalize_tier(self):
        assert normalize_tier("economy") == "economy"
        assert normalize_tier("QUALITY") == "quality"
        assert normalize_tier(None) == DEFAULT_TIER
        assert normalize_tier("bogus") == DEFAULT_TIER

    def test_threshold_choice(self):
        score = ComplexityScore(
            score=0.2, level="simple", source="rules", confidence=0.9, factors=[]
        )
        complexity, reason = choose_complexity(score, tier="balanced")
        assert complexity == "simple"
        assert "0.20" in reason

        high = ComplexityScore(
            score=0.8, level="complex", source="rules", confidence=0.9, factors=[]
        )
        complexity, _ = choose_complexity(high, tier="balanced")
        assert complexity == "complex"

    def test_quality_tier_is_conservative(self):
        score = ComplexityScore(
            score=0.4, level="simple", source="rules", confidence=0.9, factors=[]
        )
        assert choose_complexity(score, tier="quality")[0] == "complex"
        assert choose_complexity(score, tier="balanced")[0] == "simple"
        assert choose_complexity(score, tier="economy")[0] == "simple"

    def test_weak_history_forces_strong_model(self):
        score = ComplexityScore(
            score=0.2, level="simple", source="rules", confidence=0.9, factors=[]
        )
        complexity, reason = choose_complexity(
            score, tier="economy", stats={"attempts": 10, "success_rate": 0.2}
        )
        assert complexity == "complex"
        assert "历史修正" in reason

    def test_strong_history_allows_cheap(self):
        score = ComplexityScore(
            score=0.6, level="complex", source="rules", confidence=0.9, factors=[]
        )
        complexity, reason = choose_complexity(
            score, tier="balanced", stats={"attempts": 10, "success_rate": 0.95}
        )
        assert complexity == "simple"
        assert "历史修正" in reason

    def test_build_route_is_explainable(self):
        step = {"step_id": "step_2", "capability": "analysis"}
        step_score = score_step(step, 0.6)
        choice = build_route(step, step_score, tier="balanced", candidates=["a", "b"])
        assert isinstance(choice, RouteChoice)
        assert choice.step_id == "step_2"
        assert choice.candidates == ["a", "b"]
        assert choice.complexity in {"simple", "complex"}
        assert choice.reason

    def test_escalation_gates(self):
        assert allow_escalation({}, step_id="s1") is True
        assert allow_escalation({"s1": 1}, step_id="s1") is False
        assert allow_escalation({"s2": 1}, step_id="s1") is True
        assert allow_escalation({}, step_id="s1", task_escalations=4) is False
