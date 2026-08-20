"""安全响应头中间件测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present():
    client = TestClient(app)
    response = client.get("/api/not-a-real-route")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
