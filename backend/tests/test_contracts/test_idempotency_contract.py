"""Phase 6A Frozen Contract：Idempotency 状态机。

契约来源：Pro FINAL DECISION（覆盖 resume/retry/checkpoint 恢复窗口；
唯一事实源 tool_calls；不支持 external key）。
"""

from __future__ import annotations

import hashlib

from app.engine import canonical
from app.engine.tool_executor import (
    claim_allowed,
    idempotency_decision,
    make_idempotency_key,
)


def test_key_is_stable_for_equivalent_params():
    k1 = make_idempotency_key(
        "exec-1", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    k2 = make_idempotency_key(
        "exec-1",
        "send_email",
        {"to": "a@b.com", "subject": "s", "body": "b", "cc": None},
    )
    assert k1 == k2


def test_key_changes_on_param_change():
    k1 = make_idempotency_key(
        "exec-1", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    k2 = make_idempotency_key(
        "exec-1", "send_email", {"to": "x@y.z", "subject": "s", "body": "b"}
    )
    assert k1 != k2


def test_key_changes_on_execution_or_tool_change():
    base = {"to": "a@b.com", "subject": "s", "body": "b"}
    assert make_idempotency_key("exec-1", "send_email", base) != make_idempotency_key(
        "exec-2", "send_email", base
    )
    assert make_idempotency_key("exec-1", "send_email", base) != make_idempotency_key(
        "exec-1", "query_db", {"sql": "SELECT 1"}
    )


def test_key_uses_global_canonicalization():
    # 与 Approval 共用同一 canonical 实现：等价参数产生相同 key
    from app.engine.approval import params_canonical

    assert params_canonical is canonical.params_canonical
    params = {"to": "a@b.com", "subject": "s", "body": "b"}
    payload = canonical.params_canonical(params, tool_name="send_email")
    expected = hashlib.sha256(f"e\0send_email\0{payload}".encode()).hexdigest()
    assert make_idempotency_key("e", "send_email", params) == expected


def test_decision_table_is_deterministic():
    assert idempotency_decision(None, has_key=True) == "execute_new"
    assert idempotency_decision("pending", has_key=True) == "claim"
    assert idempotency_decision("pending", has_key=False) == "unknown"
    assert idempotency_decision("in_flight", has_key=True) == "unknown"
    assert idempotency_decision("success", has_key=True) == "duplicate"
    assert idempotency_decision("failed", has_key=True) == "failed"
    assert idempotency_decision("rejected", has_key=True) == "rejected"
    assert idempotency_decision("approved", has_key=True) == "unknown"


def test_claim_only_allowed_from_pending_with_key():
    assert claim_allowed("pending", has_key=True)
    assert not claim_allowed("pending", has_key=False)
    assert not claim_allowed("in_flight", has_key=True)
    assert not claim_allowed("success", has_key=True)
    assert not claim_allowed("failed", has_key=True)
    assert not claim_allowed("rejected", has_key=True)
    assert not claim_allowed("approved", has_key=True)


def test_unknown_is_never_auto_replayed():
    # IN_FLIGHT / 无 key 的 PENDING 均不允许再次调用 provider
    assert idempotency_decision("in_flight", has_key=True) == "unknown"
    assert idempotency_decision("pending", has_key=False) == "unknown"
    assert idempotency_decision("approved", has_key=True) == "unknown"
