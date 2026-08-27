from types import SimpleNamespace

from app.core.request_utils import get_client_ip


def request(headers=None, peer="10.0.0.2"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=peer))


def test_untrusted_peer_cannot_spoof_forwarded_headers(monkeypatch):
    monkeypatch.setattr("app.core.request_utils.settings.TRUSTED_PROXY_IPS", "10.0.0.1")

    result = get_client_ip(
        request(
            {
                "x-forwarded-for": "203.0.113.7, 10.0.0.1",
                "x-real-ip": "198.51.100.9",
            }
        )
    )

    assert result == "10.0.0.2"


def test_forwarded_for_from_trusted_proxy_has_priority(monkeypatch):
    monkeypatch.setattr("app.core.request_utils.settings.TRUSTED_PROXY_IPS", "10.0.0.2")

    result = get_client_ip(
        request(
            {
                "x-forwarded-for": "203.0.113.7, 10.0.0.1",
                "x-real-ip": "198.51.100.9",
            }
        )
    )

    assert result == "203.0.113.7"


def test_real_ip_from_trusted_proxy_fallback(monkeypatch):
    monkeypatch.setattr("app.core.request_utils.settings.TRUSTED_PROXY_IPS", "10.0.0.2")

    assert get_client_ip(request({"x-real-ip": "198.51.100.9"})) == "198.51.100.9"


def test_trusted_proxy_cidr_supports_cluster_network(monkeypatch):
    monkeypatch.setattr(
        "app.core.request_utils.settings.TRUSTED_PROXY_IPS", "10.42.0.0/16"
    )

    assert (
        get_client_ip(request({"x-forwarded-for": "203.0.113.8"}, peer="10.42.7.9"))
        == "203.0.113.8"
    )


def test_invalid_proxy_entry_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "app.core.request_utils.settings.TRUSTED_PROXY_IPS", "not-a-network"
    )

    assert get_client_ip(request({"x-forwarded-for": "203.0.113.8"})) == "10.0.0.2"


def test_client_host_fallback(monkeypatch):
    monkeypatch.setattr("app.core.request_utils.settings.TRUSTED_PROXY_IPS", "")

    assert get_client_ip(request()) == "10.0.0.2"
