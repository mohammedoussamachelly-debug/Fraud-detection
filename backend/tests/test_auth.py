"""Integration tests for POST /auth/login and GET /auth/me. `make_user`
(tests/conftest.py) depends on the real `db_session` fixture, so any test
using it is automatically skipped (not faked) when no DB is reachable —
same pattern as the rest of this test suite.
"""

from fastapi.testclient import TestClient

from tests.conftest import auth_header


def test_login_succeeds_with_correct_password(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")

    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Test-Password-123!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert len(body["access_token"]) > 0


def test_login_rejects_wrong_password(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")

    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong"})
    assert response.status_code == 401


def test_login_rejects_unknown_email(client: TestClient, db_session) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@sentinelai.test", "password": "whatever"}
    )
    assert response.status_code == 401


def test_login_rejects_deactivated_user(client: TestClient, make_user) -> None:
    user = make_user(role="analyst", is_active=False)

    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "Test-Password-123!"}
    )
    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient, make_user) -> None:
    user = make_user(role="senior_analyst")

    response = client.get("/api/v1/auth/me", headers=auth_header(user))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["role"] == "senior_analyst"


def test_me_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
