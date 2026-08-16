from __future__ import annotations

from app.core.audit import classify_audit_event


def test_classify_login_register_logout():
    assert classify_audit_event("POST", "/api/auth/login") == ("login", "auth", None)
    assert classify_audit_event("POST", "/api/auth/register") == (
        "register",
        "auth",
        None,
    )
    assert classify_audit_event("POST", "/api/auth/logout") == (
        "logout",
        "auth",
        None,
    )


def test_classify_create_execution():
    assert classify_audit_event("POST", "/api/executions") == (
        "create_execution",
        "execution",
        None,
    )


def test_classify_update_model():
    assert classify_audit_event("PUT", "/api/models/abc-123") == (
        "update_model",
        "model",
        "abc-123",
    )
    assert classify_audit_event("PATCH", "/api/models/abc-123") == (
        "update_model",
        "model",
        "abc-123",
    )


def test_classify_delete_resource():
    assert classify_audit_event("DELETE", "/api/documents/doc-1") == (
        "delete_resource",
        "document",
        "doc-1",
    )


def test_classify_fallback():
    assert classify_audit_event("GET", "/api/models") == (
        "get_models",
        "models",
        None,
    )
