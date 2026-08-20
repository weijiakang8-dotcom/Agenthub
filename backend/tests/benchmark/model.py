from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CaseSpec:
    """一个 Golden Set Case 的静态定义（输入、预期、Oracle 适用性）。"""

    id: str
    group: str
    name: str
    scenario: str
    risk: str
    user_input: str
    frozen_params: dict[str, Any]
    tampered_params: dict[str, Any] | None = None
    expected_tool: str = "send_email"
    # 成功路径：期望精确调用次数；故障路径：允许上限
    expected_provider_calls: int | None = None
    allowed_max_provider_calls: int | None = None
    expects_refusal: bool = False
    expected_tool_row_status: str = "success"  # success | in_flight | failed | none
    expected_execution_status: str = "completed"  # completed | failed | None
    required_audits: tuple[str, ...] = ()
    oracle_ids: tuple[str, ...] = (
        "O-1",
        "O-2",
        "O-3",
        "O-4",
        "O-5",
        "O-7",
    )
    must_desc: str = ""
    forbid_desc: str = ""
    fault: str = "none"
    notes: str = ""


@dataclass
class Evidence:
    """一次运行采集到的原始证据（供 Oracle 判定）。"""

    case_id: str
    quadrant: str
    reliability_arm: str
    model_arm: str
    model_backend: str
    provider_calls: list[dict[str, Any]] = field(default_factory=list)
    reentry_provider_calls: int = 0
    tool_call_rows: list[dict[str, Any]] = field(default_factory=list)
    execution_status: str | None = None
    audits: list[str] = field(default_factory=list)
    resume_results: list[int] = field(default_factory=list)
    delayed_resumes: int = 0
    returned_rows: list[dict[str, Any]] | None = None
    latency_ms: float = 0.0
    cost_usd: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OracleCheck:
    oracle_id: str
    passed: bool
    detail: str


@dataclass
class RunRecord:
    case_id: str
    case_group: str
    case_name: str
    scenario: str
    risk: str
    quadrant: str
    reliability_arm: str
    model_arm: str
    model_backend: str
    verdict: str
    safety_pass: bool
    semantic_pass: bool
    oracle: list[dict[str, Any]]
    provider_calls: int
    tool_call_states: list[str]
    execution_status: str | None
    audits: list[str]
    latency_ms: float
    cost_usd: float | None
    evidence: dict[str, Any]
    notes: str = ""
