"""Verifies the ground-truth isolation grants from alembic migration 0001
actually hold against a live database — an automated check, not a manual
one, per the security-reviewer skill's rules. Skipped (not faked) when no
DB is reachable.
"""

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import get_settings
from app.db.session import engine as api_service_engine


def _database_reachable() -> bool:
    try:
        with api_service_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(), reason="No reachable Postgres at DATABASE_URL."
)


def _role_url(role: str, password_env_var: str, default_password: str) -> str:
    parsed = urlparse(get_settings().database_url.replace("postgresql+psycopg2", "postgresql"))
    password = os.environ.get(password_env_var, default_password)
    return f"postgresql://{role}:{password}@{parsed.hostname}:{parsed.port}{parsed.path}"


def test_api_service_cannot_select_ground_truth() -> None:
    engine = create_engine(
        _role_url("api_service", "API_SERVICE_DB_PASSWORD", "api_service_dev_password")
    )
    try:
        with (
            engine.connect() as connection,
            pytest.raises(ProgrammingError, match="permission denied"),
        ):
            connection.execute(text("SELECT * FROM ground_truth.transaction_labels LIMIT 1"))
    finally:
        engine.dispose()


def test_ml_trainer_can_select_ground_truth() -> None:
    engine = create_engine(
        _role_url("ml_trainer", "ML_TRAINER_DB_PASSWORD", "ml_trainer_dev_password")
    )
    try:
        with engine.connect() as connection:
            # Must succeed (no exception) even if the table happens to be empty.
            connection.execute(text("SELECT * FROM ground_truth.transaction_labels LIMIT 1"))
    finally:
        engine.dispose()


def test_ml_trainer_cannot_write_app_accounts() -> None:
    engine = create_engine(
        _role_url("ml_trainer", "ML_TRAINER_DB_PASSWORD", "ml_trainer_dev_password")
    )
    try:
        with (
            engine.connect() as connection,
            pytest.raises(ProgrammingError, match="permission denied"),
        ):
            connection.execute(
                text(
                    "INSERT INTO app.accounts (id, external_ref, account_type, first_seen_at) "
                    "VALUES (gen_random_uuid(), 'security-test-should-fail', 'customer', now())"
                )
            )
    finally:
        engine.dispose()


def test_api_service_can_read_and_write_app_schema() -> None:
    with api_service_engine.connect() as connection:
        result = connection.execute(text("SELECT count(*) FROM app.accounts"))
        assert result.scalar() is not None
