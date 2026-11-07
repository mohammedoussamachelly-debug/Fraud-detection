"""Integration tests for case creation, assignment, status transitions,
and the human decision endpoint — the core of Phase 5's human-in-the-loop
guarantee. Real DB throughout.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Alert, Case, CaseAlert, CaseDecision, Transaction
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


def _make_alert(db_session, transaction_id: uuid.UUID) -> Alert:
    alert = Alert(transaction_id=transaction_id, alert_type="manual", severity="high")
    db_session.add(alert)
    db_session.commit()
    return alert


def _cleanup(db_session, prefix: str, case_ids: list[uuid.UUID] | None = None) -> None:
    for case_id in case_ids or []:
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


def test_get_case_decision_404_before_any_decision(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-dec-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        user = make_user(role="analyst")
        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.get(f"/api/v1/cases/{case_id}/decision", headers=auth_header(user))
        assert response.status_code == 404
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_get_case_decision_returns_recorded_decision(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-dec2-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        analyst = make_user(role="analyst")
        senior = make_user(role="senior_analyst")
        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(analyst)
        )
        case_id = uuid.UUID(created.json()["id"])
        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "investigating"},
            headers=auth_header(analyst),
        )
        decided = client.post(
            f"/api/v1/cases/{case_id}/decision",
            json={"decision": "confirmed_fraud", "rationale": "clear balance-draining pattern"},
            headers=auth_header(senior),
        )
        assert decided.status_code == 201

        fetched = client.get(f"/api/v1/cases/{case_id}/decision", headers=auth_header(analyst))
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["decision"] == "confirmed_fraud"
        assert body["rationale"] == "clear balance-draining pattern"
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_get_case_decision_requires_auth(client: TestClient) -> None:
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}/decision")
    assert response.status_code == 401


def test_create_case_from_alert_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/cases", json={"alert_ids": [str(uuid.uuid4())]})
    assert response.status_code == 401


def test_create_case_from_alerts(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)

        user = make_user(role="analyst")
        response = client.post(
            "/api/v1/cases",
            json={"alert_ids": [str(alert.id)], "priority": "high"},
            headers=auth_header(user),
        )
        assert response.status_code == 201
        body = response.json()
        case_id = uuid.UUID(body["id"])
        assert body["status"] == "open"
        assert body["priority"] == "high"
        assert [a["alert_id"] for a in body["alerts"]] == [str(alert.id)]
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_create_case_404_for_unknown_alert(
    client: TestClient, make_user, service_auth_header: dict
) -> None:
    user = make_user(role="analyst")
    response = client.post(
        "/api/v1/cases", json={"alert_ids": [str(uuid.uuid4())]}, headers=auth_header(user)
    )
    assert response.status_code == 404


def test_assign_case_to_real_analyst(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        creator = make_user(role="analyst")
        assignee = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(creator)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.patch(
            f"/api/v1/cases/{case_id}",
            json={"assigned_analyst_id": str(assignee.id)},
            headers=auth_header(creator),
        )
        assert response.status_code == 200
        assert response.json()["assigned_analyst_id"] == str(assignee.id)
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_assign_case_to_nonexistent_user_rejected(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        user = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.patch(
            f"/api/v1/cases/{case_id}",
            json={"assigned_analyst_id": str(uuid.uuid4())},
            headers=auth_header(user),
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_valid_status_transition_open_to_investigating(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        user = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "investigating"}, headers=auth_header(user)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "investigating"
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_invalid_status_transition_open_to_resolved_rejected(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    """`resolved` is reachable only via POST /cases/{id}/decision — PATCH
    must never be able to set it, per CLAUDE.md's human-in-the-loop rule.
    """
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        user = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "resolved"}, headers=auth_header(user)
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_decision_requires_senior_analyst_or_admin(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        analyst = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(analyst)
        )
        case_id = uuid.UUID(created.json()["id"])
        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "investigating"},
            headers=auth_header(analyst),
        )

        response = client.post(
            f"/api/v1/cases/{case_id}/decision",
            json={
                "decision": "confirmed_fraud",
                "rationale": "Clear fan-in pattern with mule chain.",
            },
            headers=auth_header(analyst),
        )
        assert response.status_code == 403
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_decision_by_senior_analyst_resolves_case(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        analyst = make_user(role="analyst")
        senior = make_user(role="senior_analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(analyst)
        )
        case_id = uuid.UUID(created.json()["id"])
        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "investigating"},
            headers=auth_header(analyst),
        )

        response = client.post(
            f"/api/v1/cases/{case_id}/decision",
            json={
                "decision": "confirmed_fraud",
                "rationale": "Clear fan-in pattern with mule chain.",
            },
            headers=auth_header(senior),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["decision"] == "confirmed_fraud"
        assert body["decided_by_user_id"] == str(senior.id)

        case_detail = client.get(f"/api/v1/cases/{case_id}", headers=auth_header(senior))
        assert case_detail.json()["status"] == "resolved"
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_decision_rejects_short_rationale(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        analyst = make_user(role="analyst")
        senior = make_user(role="senior_analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(analyst)
        )
        case_id = uuid.UUID(created.json()["id"])
        client.patch(
            f"/api/v1/cases/{case_id}",
            json={"status": "investigating"},
            headers=auth_header(analyst),
        )

        response = client.post(
            f"/api/v1/cases/{case_id}/decision",
            json={"decision": "dismissed", "rationale": "no"},
            headers=auth_header(senior),
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])


def test_closed_requires_resolved_first(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-cases-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)
        user = make_user(role="analyst")

        created = client.post(
            "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
        )
        case_id = uuid.UUID(created.json()["id"])

        response = client.patch(
            f"/api/v1/cases/{case_id}", json={"status": "closed"}, headers=auth_header(user)
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, [case_id] if case_id else [])
