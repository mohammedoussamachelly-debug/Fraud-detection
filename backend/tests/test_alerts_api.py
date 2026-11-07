"""Integration tests for GET /alerts, GET /alerts/{id}, PATCH /alerts/{id}.
Real DB: alerts are inserted directly against a real ingested transaction
rather than going through the scoring pipeline (that's covered by
tests/test_risk_score_persistence.py) — this file is about the alert
listing/detail/status-transition API and its auth, not about scoring.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Alert, Transaction
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


def _make_alert(db_session, transaction_id: uuid.UUID, **overrides) -> Alert:
    alert = Alert(
        transaction_id=transaction_id,
        alert_type=overrides.pop("alert_type", "manual"),
        severity=overrides.pop("severity", "high"),
        status=overrides.pop("status", "open"),
    )
    db_session.add(alert)
    db_session.commit()
    return alert


def _cleanup(db_session, prefix: str) -> None:
    tx_ids = [
        t.id
        for t in db_session.query(Transaction).filter(Transaction.external_ref.like(f"{prefix}%"))
    ]
    for tx_id in tx_ids:
        db_session.execute(delete(Alert).where(Alert.transaction_id == tx_id))
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_list_alerts_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/alerts")
    assert response.status_code == 401


def test_list_alerts_filters_by_status(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-alerts-{uuid.uuid4().hex[:8]}"
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        _make_alert(db_session, tx_id, status="open", severity="high")
        _make_alert(db_session, tx_id, alert_type="graph_structural", status="dismissed")

        user = make_user(role="analyst")
        response = client.get(
            "/api/v1/alerts", params={"status": "open"}, headers=auth_header(user)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        assert all(item["status"] == "open" for item in body["items"])
    finally:
        _cleanup(db_session, prefix)


def test_get_alert_detail(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-alerts-{uuid.uuid4().hex[:8]}"
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)

        user = make_user(role="analyst")
        response = client.get(f"/api/v1/alerts/{alert.id}", headers=auth_header(user))
        assert response.status_code == 200
        assert response.json()["id"] == str(alert.id)
    finally:
        _cleanup(db_session, prefix)


def test_get_alert_404_for_unknown_id(
    client: TestClient, make_user, service_auth_header: dict
) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/alerts/{uuid.uuid4()}", headers=auth_header(user))
    assert response.status_code == 404


def test_patch_alert_updates_status(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-alerts-{uuid.uuid4().hex[:8]}"
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id, status="open")

        user = make_user(role="analyst")
        response = client.patch(
            f"/api/v1/alerts/{alert.id}", json={"status": "triaged"}, headers=auth_header(user)
        )
        assert response.status_code == 200
        assert response.json()["status"] == "triaged"
    finally:
        _cleanup(db_session, prefix)


def test_patch_alert_rejects_invalid_status_value(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-alerts-{uuid.uuid4().hex[:8]}"
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx_id = db_session.query(Transaction).filter(Transaction.external_ref == ref).one().id
        alert = _make_alert(db_session, tx_id)

        user = make_user(role="analyst")
        response = client.patch(
            f"/api/v1/alerts/{alert.id}",
            json={"status": "not_a_real_status"},
            headers=auth_header(user),
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix)
