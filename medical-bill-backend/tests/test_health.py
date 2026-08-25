"""Unit test for the backend /health endpoint.

Regression: health.py previously referenced ``settings.AUTH_ENABLED`` which does
not exist in app.config, so /health raised AttributeError on every call. The
endpoint must now report a truthful auth status without crashing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok_and_truthful_auth():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    # The auth field is truthful and does not depend on a phantom setting.
    assert data["auth"] == "enforced"
    assert "auth_enabled" not in data