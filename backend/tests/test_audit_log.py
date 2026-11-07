"""Integration tests for GET /audit-log and the audit rows Phase 5
services write as a side effect of login/case actions. Real DB
throughout — CLAUDE.md requires audit logging for authentication events
and case decisions, and these tests verify the row actually lands, not
just that the action itself succeeded.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Alert, AuditLogEntry, Case, CaseAlert, CaseDecision, Transaction
from tests.conftest import auth_header


def _ingest_one_transaction(client: TestClient, prefix: str, service_auth_header: dict) -> str:
    item = {
        "external_ref": f"{prefix}-tx1",
        "step": 1,
        "type": "TRANSFER",
        "amount": "100.00",
        "origin_external_ref": f"{prefix}-orig",
        "dest_external_ref": f"{prefix}-dest",
        "origin_balance_before": "500.00",
        "origin_balance_after": "400.00",
        "dest_balance_before": "0.00",
        "dest_balance_after": "100.00",
    }
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": [item]}, headers=service_auth_header
    )
    assert response.status_code == 200
    return f"{prefix}-tx1"


def _cleanup(db_session, prefix: str, case_id: uuid.UUID | None, user_ids: list[uuid.UUID]) -> None:
    for uid in user_ids:
        db_session.execute(delete(AuditLogEntry).where(AuditLogEntry.user_id == uid))
    if case_id is not None:
        db_session.execute(delete(AuditLogEntry).where(AuditLogEntry.entity_id == case_id))
        db_session.execute(delete(CaseDecision).where(CaseDecision.case_id == case_id))
        db_session.execute(delete(CaseAlert).where(CaseAlert.case_id == case_id))
        db_session.execute(delete(Case).where(Case.id == case_id))
    tx_ids = [
        t.id
        for t in db_session.query(Transaction).filter(Transaction.external_ref.like(f"{prefix}%"))
    ]
    for tx_id in tx_ids:
        db_session.execute(delete(Alert).where(Alert.transaction_id == tx_id))
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_audit_log_requires_admin(client: TestClient, make_user, service_auth_header: dict) -> None:
    analyst = make_user(role="analyst")
    response = client.get("/api/v1/audit-log", headers=auth_header(analyst))
    assert response.status_code == 403


def test_audit_log_rejects_unauthenticated(client: TestClient) -> None:
    response = client.get("/api/v1/audit-log")
    assert response.status_code == 401


def test_login_writes_audit_entry(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    user = make_user(role="analyst")
    admin = make_user(role="admin")
    try:
        login_response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "Test-Password-123!"}
        )
        assert login_response.status_code == 200

        response = client.get(
            "/api/v1/audit-log",
            params={"user_id": str(user.id), "action": "login"},
            headers=auth_header(admin),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert body["items"][0]["action"] == "login"
        assert body["items"][0]["user_id"] == str(user.id)
    finally:
        _cleanup(db_session, "unused", None, [user.id, admin.id])


def test_case_decision_writes_audit_entry(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-audit-{uuid.uuid4().hex[:8]}"
    case_id = None
    analyst = make_user(role="analyst")
    senior = make_user(role="senior_analyst")
    admin = make_user(role="admin")
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        alert = Alert(transaction_id=tx.id, alert_type="manual", severity="high")
        db_session.add(alert)
        db_session.commit()

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(analyst)
        )
        case_id = uuid.UUID(created.json()["id"])
        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "investigating"},
            headers=auth_header(analyst),
        )
        decision = client.post(
            f"/api/v1/cases/{case_id}/decision",
            json={"decision": "confirmed_fraud", "rationale": "Clear mule-chain pattern observed."},
            headers=auth_header(senior),
        )
        assert decision.status_code == 201

        response = client.get(
            "/api/v1/audit-log",
            params={"action": "case_decision_recorded"},
            headers=auth_header(admin),
        )
        assert response.status_code == 200
        matching = [item for item in response.json()["items"] if item["entity_id"] == str(case_id)]
        assert len(matching) == 1
        assert matching[0]["user_id"] == str(senior.id)
        assert matching[0]["event_metadata"]["decision"] == "confirmed_fraud"
    finally:
        _cleanup(db_session, prefix, case_id, [analyst.id, senior.id, admin.id])
