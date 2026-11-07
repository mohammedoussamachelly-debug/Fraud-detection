"""Unit tests for the health endpoints. The database is mocked here so these
run without a live Postgres connection, per the testing-engineer skill's rule
to keep tests independent of live external services when possible. The real
database path is covered separately in tests/test_health_integration.py.
"""

from fastapi.testclient import TestClient

import app.api.routes.health as health_route


def test_health_liveness_is_always_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_ready_when_database_is_reachable(
    client: TestClient, monkeypatch: object
) -> None:
    monkeypatch.setattr(health_route, "check_database_connection", lambda: True)  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_readiness_reports_503_when_database_is_unreachable(
    client: TestClient, monkeypatch: object
) -> None:
    monkeypatch.setattr(health_route, "check_database_connection", lambda: False)  # type: ignore[attr-defined]

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unreachable"}


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
