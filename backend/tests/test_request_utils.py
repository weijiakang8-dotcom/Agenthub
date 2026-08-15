from types import SimpleNamespace

from app.core.request_utils import get_client_ip


def test_forwarded_for_has_priority():
    request = SimpleNamespace(
        headers={
            "x-forwarded-for": "203.0.113.7, 10.0.0.1",
            "x-real-ip": "198.51.100.9",
        },
        client=SimpleNamespace(host="10.0.0.2"),
    )

    assert get_client_ip(request) == "203.0.113.7"


def test_real_ip_fallback():
    request = SimpleNamespace(
        headers={"x-real-ip": "198.51.100.9"},
        client=SimpleNamespace(host="10.0.0.2"),
    )

    assert get_client_ip(request) == "198.51.100.9"


def test_client_host_fallback():
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.2"))

    assert get_client_ip(request) == "10.0.0.2"
