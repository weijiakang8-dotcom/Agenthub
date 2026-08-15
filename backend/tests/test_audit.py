from types import SimpleNamespace

from app.core.audit import build_audit_details, sanitize_audit_data


def test_sanitize_audit_data_redacts_sensitive_keys():
    payload = {
        "email": "user@example.com",
        "password": "secret-pass",
        "api_key": "sk-123",
        "nested": {"code": "654321", "safe": "ok"},
    }

    result = sanitize_audit_data(payload)

    assert result["password"] == "***"
    assert result["api_key"] == "***"
    assert result["nested"]["code"] == "***"
    assert result["nested"]["safe"] == "ok"


def test_build_audit_details_parses_json_body():
    request = SimpleNamespace(
        headers={"content-type": "application/json"},
        query_params={"page": "1", "token": "abc"},
        client=SimpleNamespace(host="10.0.0.2"),
    )

    details = build_audit_details(
        request,
        b'{"name": "test", "password": "secret"}',
    )

    assert details["ip"] == "10.0.0.2"
    assert details["query_params"]["token"] == "***"
    assert details["body"]["name"] == "test"
    assert details["body"]["password"] == "***"
