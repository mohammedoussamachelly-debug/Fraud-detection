"""Integration tests for POST /cases/{id}/evidence. Real DB throughout.
Each evidence type (except analyst_note) must resolve from a real source
record — these tests assert that a nonexistent source_id is rejected
(404), not silently accepted, since accepting it would mean the service
fabricated evidence (§7 of the Phase 5 brief / CLAUDE.md "no fabrication").
"""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Alert, Case, CaseAlert, CaseEvidence, RiskScore, Transaction
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


def _make_case(client: TestClient, db_session, tx_id: uuid.UUID, user) -> uuid.UUID:
    alert = Alert(transaction_id=tx_id, alert_type="manual", severity="high")
    db_session.add(alert)
    db_session.commit()
    created = client.post(
        "/api/v1/cases", json={"alert_ids": [str(alert.id)]}, headers=auth_header(user)
    )
    assert created.status_code == 201
    return uuid.UUID(created.json()["id"])


def _cleanup(db_session, prefix: str, case_id: uuid.UUID | None) -> None:
    if case_id is not None:
        db_session.execute(delete(CaseEvidence).where(CaseEvidence.case_id == case_id))
        db_session.execute(delete(CaseAlert).where(CaseAlert.case_id == case_id))
        db_session.execute(delete(Case).where(Case.id == case_id))
    tx_ids = [
        t.id
        for t in db_session.query(Transaction).filter(Transaction.external_ref.like(f"{prefix}%"))
    ]
    for tx_id in tx_ids:
        db_session.execute(delete(RiskScore).where(RiskScore.transaction_id == tx_id))
        db_session.execute(delete(Alert).where(Alert.transaction_id == tx_id))
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_attach_transaction_evidence(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "transaction", "source_id": str(tx.id)},
            headers=auth_header(user),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_reference"] == f"transaction:{tx.id}"
        assert body["evidence_payload"]["id"] == str(tx.id)
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_transaction_evidence_404_for_nonexistent_transaction(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "transaction", "source_id": str(uuid.uuid4())},
            headers=auth_header(user),
        )
        assert response.status_code == 404
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_risk_score_and_shap_evidence(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        risk_score = RiskScore(
            transaction_id=tx.id,
            risk_score=Decimal("0.98000"),
            risk_level="high",
            model_version="test-v1",
            threshold_used=Decimal("0.95000"),
            shap_values={"base_value": 0.1, "contributions": []},
        )
        db_session.add(risk_score)
        db_session.commit()

        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        rs_response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "risk_score", "source_id": str(risk_score.id)},
            headers=auth_header(user),
        )
        assert rs_response.status_code == 201
        assert rs_response.json()["evidence_payload"]["risk_level"] == "high"

        shap_response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "shap_explanation", "source_id": str(risk_score.id)},
            headers=auth_header(user),
        )
        assert shap_response.status_code == 201
        assert shap_response.json()["evidence_payload"] == {"base_value": 0.1, "contributions": []}
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_shap_evidence_422_when_no_explanation_was_computed(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        risk_score = RiskScore(
            transaction_id=tx.id,
            risk_score=Decimal("0.10000"),
            risk_level="low",
            model_version="test-v1",
            threshold_used=Decimal("0.95000"),
            shap_values=None,
        )
        db_session.add(risk_score)
        db_session.commit()

        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "shap_explanation", "source_id": str(risk_score.id)},
            headers=auth_header(user),
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_graph_neighborhood_evidence(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "evidence_type": "graph_neighborhood",
                "source_id": str(tx.origin_account_id),
                "hops": 1,
            },
            headers=auth_header(user),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_reference"] == f"account:{tx.origin_account_id}"
        assert "disclaimer" in body["evidence_payload"]
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_analyst_note_evidence(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "analyst_note", "body": "Sender's balance was fully drained."},
            headers=auth_header(user),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_reference"] == f"user:{user.id}"
        assert body["evidence_payload"]["body"] == "Sender's balance was fully drained."
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_analyst_note_requires_body(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        response = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "analyst_note"},
            headers=auth_header(user),
        )
        assert response.status_code == 422
    finally:
        _cleanup(db_session, prefix, case_id)


def test_attach_evidence_404_for_unknown_case(
    client: TestClient, make_user, service_auth_header: dict
) -> None:
    user = make_user(role="analyst")
    response = client.post(
        f"/api/v1/cases/{uuid.uuid4()}/evidence",
        json={"evidence_type": "analyst_note", "body": "x"},
        headers=auth_header(user),
    )
    assert response.status_code == 404


def test_attach_evidence_requires_auth(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/cases/{uuid.uuid4()}/evidence",
        json={"evidence_type": "analyst_note", "body": "x"},
    )
    assert response.status_code == 401


def test_list_case_evidence_returns_attached_items_newest_last(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-evid-list-{uuid.uuid4().hex[:8]}"
    case_id = None
    try:
        ref = _ingest_one_transaction(client, prefix, service_auth_header)
        tx = db_session.query(Transaction).filter(Transaction.external_ref == ref).one()
        user = make_user(role="analyst")
        case_id = _make_case(client, db_session, tx.id, user)

        first = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "analyst_note", "body": "first note"},
            headers=auth_header(user),
        )
        second = client.post(
            f"/api/v1/cases/{case_id}/evidence",
            json={"evidence_type": "transaction", "source_id": str(tx.id)},
            headers=auth_header(user),
        )
        assert first.status_code == 201
        assert second.status_code == 201

        listed = client.get(f"/api/v1/cases/{case_id}/evidence", headers=auth_header(user))
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] == 2
        assert [item["evidence_type"] for item in body["items"]] == ["analyst_note", "transaction"]
    finally:
        _cleanup(db_session, prefix, case_id)


def test_list_case_evidence_404_for_unknown_case(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}/evidence", headers=auth_header(user))
    assert response.status_code == 404


def test_list_case_evidence_requires_auth(client: TestClient) -> None:
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}/evidence")
    assert response.status_code == 401
