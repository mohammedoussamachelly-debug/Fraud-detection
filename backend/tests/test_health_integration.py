"""Integration test that exercises /health/ready against a real database
connection, using the api_service role exactly as the running app does. This
is skipped (not faked) when no reachable Postgres is configured, per the
testing-engineer skill's rule against fabricating or silently papering over
results — a skip is reported, not a pass.

In CI (.github/workflows/ci.yml) a real Postgres service container is present
and the baseline migration has been applied, so this test actually runs
there.
"""

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine
from app.main import app

try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    _DATABASE_REACHABLE = True
except OperationalError:
    _DATABASE_REACHABLE = False


def test_readiness_against_a_real_database() -> None:
    if not _DATABASE_REACHABLE:
        import pytest

        pytest.skip(
            "No reachable Postgres at DATABASE_URL; this integration test only "
            "runs with a real database available (see infra/docker-compose.yml "
            "or .github/workflows/ci.yml)."
        )

    client = TestClient(app)
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
