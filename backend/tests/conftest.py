import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    Account,
    AgentEvidenceRef,
    AgentRun,
    AgentStep,
    Alert,
    AuditLogEntry,
    Case,
    CaseAlert,
    CaseDecision,
    Transaction,
    User,
)
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _database_reachable() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


@pytest.fixture(scope="session")
def database_reachable() -> bool:
    return _database_reachable()


@pytest.fixture
def db_session(database_reachable: bool):
    """A real DB session (api_service role), for tests that need to read
    back what an endpoint wrote, or seed rows an endpoint should read. Skips
    (doesn't fake a pass) when no DB is reachable — see
    tests/test_health_integration.py's docstring for the rationale.
    """
    if not database_reachable:
        pytest.skip("No reachable Postgres at DATABASE_URL; this test needs a live database.")

    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def make_user(db_session: Session):
    """Factory fixture: `make_user(role="analyst")` inserts a real `User`
    row (bcrypt-hashed password, never plaintext) and returns it, so
    Phase 5 tests authenticate through the same path production does
    rather than mocking `get_current_user`.
    """
    created: list[User] = []

    def _make(role: str = "analyst", *, is_active: bool = True) -> User:
        user = User(
            email=f"test-{uuid.uuid4().hex[:10]}@sentinelai.test",
            password_hash=hash_password("Test-Password-123!"),
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        created.append(user)
        return user

    yield _make

    for user in created:
        # Several tables FK to `users` (audit_log_entries, agent_runs,
        # case_decisions, cases.assigned_analyst_id), and fixture
        # teardown order between independent fixtures (e.g. this one and
        # `make_investigation_case`) isn't something to rely on — a test
        # may create an AgentRun/CaseDecision referencing this user and
        # have this fixture's teardown run *before* that test's own
        # cleanup. So this teardown is unconditionally defensive: it
        # clears every such reference itself rather than assuming some
        # other fixture already did. `agent_steps`/`agent_evidence_refs`
        # cascade from `agent_runs` first since they have their own FK to
        # it. `cases.assigned_analyst_id` is nullable, so it's cleared
        # rather than deleting a case this fixture didn't create.
        run_ids = db_session.scalars(
            select(AgentRun.id).where(AgentRun.started_by_user_id == user.id)
        ).all()
        db_session.execute(
            delete(AgentEvidenceRef).where(AgentEvidenceRef.agent_run_id.in_(run_ids))
        )
        db_session.execute(delete(AgentStep).where(AgentStep.agent_run_id.in_(run_ids)))
        db_session.execute(delete(AgentRun).where(AgentRun.started_by_user_id == user.id))
        db_session.execute(delete(CaseDecision).where(CaseDecision.decided_by_user_id == user.id))
        db_session.execute(
            update(Case).where(Case.assigned_analyst_id == user.id).values(assigned_analyst_id=None)
        )
        db_session.execute(delete(AuditLogEntry).where(AuditLogEntry.user_id == user.id))
        db_session.delete(user)
    db_session.commit()


def auth_header(user: User) -> dict[str, str]:
    token, _ = create_access_token(subject=str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def service_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().service_api_key}"}


@pytest.fixture
def make_investigation_case(client: TestClient, db_session: Session, service_auth_header: dict):
    """Factory fixture for Phase 6 agent tests: `make_investigation_case()`
    ingests one real transaction (a balance-draining TRANSFER by default,
    overridable via kwargs matching the ingest item schema), links it to
    a manual alert and a fresh case, and returns `(case, transaction,
    alert)`. Teardown deletes every agent table row scoped to the case(s)
    it created *before* anything else, so an `AgentRun.started_by_user_id`
    FK to a `make_user`-created analyst never blocks that user's own
    teardown, regardless of fixture teardown order.
    """
    case_ids: list[uuid.UUID] = []
    prefixes: list[str] = []

    def _make(**overrides) -> tuple[Case, Transaction, Alert]:
        prefix = f"test-inv-{uuid.uuid4().hex[:8]}"
        item = {
            "external_ref": f"{prefix}-tx1",
            "step": 10,
            "type": "TRANSFER",
            "amount": "8400.00",
            "origin_external_ref": f"{prefix}-orig",
            "dest_external_ref": f"{prefix}-dest",
            "origin_balance_before": "10000.00",
            "origin_balance_after": "1600.00",
            "dest_balance_before": "500.00",
            "dest_balance_after": "8900.00",
        }
        item.update(overrides)
        response = client.post(
            "/api/v1/transactions/ingest",
            json={"transactions": [item]},
            headers=service_auth_header,
        )
        assert response.status_code == 200, response.text
        prefixes.append(prefix)

        tx = (
            db_session.query(Transaction)
            .filter(Transaction.external_ref == item["external_ref"])
            .one()
        )
        alert = Alert(transaction_id=tx.id, alert_type="manual", severity="high")
        db_session.add(alert)
        db_session.flush()
        case = Case(priority="high")
        db_session.add(case)
        db_session.flush()
        db_session.add(CaseAlert(case_id=case.id, alert_id=alert.id))
        db_session.commit()
        case_ids.append(case.id)
        return case, tx, alert

    yield _make

    for case_id in case_ids:
        run_ids = db_session.scalars(select(AgentRun.id).where(AgentRun.case_id == case_id)).all()
        db_session.execute(
            delete(AgentEvidenceRef).where(AgentEvidenceRef.agent_run_id.in_(run_ids))
        )
        db_session.execute(delete(AgentStep).where(AgentStep.agent_run_id.in_(run_ids)))
        db_session.execute(delete(AgentRun).where(AgentRun.case_id == case_id))
        db_session.execute(delete(CaseAlert).where(CaseAlert.case_id == case_id))
        db_session.execute(delete(Case).where(Case.id == case_id))
    # Two passes, not one per prefix: a test may deliberately make two
    # cases share an account (e.g. to exercise `get_similar_past_cases`),
    # and deleting prefix A's account while prefix B's still-undeleted
    # transaction references it as origin/dest would hit the same FK
    # constraint that makes that sharing meaningful in the first place.
    for prefix in prefixes:
        tx_ids = db_session.scalars(
            select(Transaction.id).where(Transaction.external_ref.like(f"{prefix}%"))
        ).all()
        db_session.execute(delete(Alert).where(Alert.transaction_id.in_(tx_ids)))
        db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    for prefix in prefixes:
        db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def wait_for_run_status(
    run_id: uuid.UUID, statuses: tuple[str, ...], *, timeout: float = 15.0
) -> AgentRun:
    """Polls `agent_runs` (via a fresh session each time, like the real
    background thread uses) until `run.status` is one of `statuses` or
    `timeout` elapses. Investigation runs execute in a background
    `ThreadPoolExecutor` (`app/services/investigations.py`), so tests
    must poll rather than assume completion by the time the HTTP call
    that started the run returns.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = SessionLocal()
        try:
            run = session.get(AgentRun, run_id)
            if run is not None and run.status in statuses:
                session.expunge(run)
                return run
        finally:
            session.close()
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not reach {statuses} within {timeout}s")
