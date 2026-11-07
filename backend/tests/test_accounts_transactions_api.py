import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction
from tests.conftest import auth_header


def _ingest_one(client: TestClient, prefix: str, service_auth_header: dict) -> dict:
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
    return item


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_list_and_get_account(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-acct-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_one(client, prefix, service_auth_header)
        user = make_user(role="analyst")

        listed = client.get(
            "/api/v1/accounts",
            params={"external_ref": f"{prefix}-orig"},
            headers=auth_header(user),
        )
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] == 1
        account_id = body["items"][0]["id"]

        detail = client.get(f"/api/v1/accounts/{account_id}", headers=auth_header(user))
        assert detail.status_code == 200
        assert detail.json()["external_ref"] == f"{prefix}-orig"
    finally:
        _cleanup(db_session, prefix)


def test_get_account_not_found(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/accounts/{uuid.uuid4()}", headers=auth_header(user))
    assert response.status_code == 404


def test_list_and_get_transaction(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-txn-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_one(client, prefix, service_auth_header)
        user = make_user(role="analyst")

        listed = client.get(
            "/api/v1/transactions",
            params={"type": "TRANSFER", "limit": 5},
            headers=auth_header(user),
        )
        assert listed.status_code == 200
        matches = [t for t in listed.json()["items"] if t["external_ref"] == f"{prefix}-tx1"]
        assert len(matches) == 1
        txn_id = matches[0]["id"]

        detail = client.get(f"/api/v1/transactions/{txn_id}", headers=auth_header(user))
        assert detail.status_code == 200
        assert detail.json()["amount"] == "100.00"
    finally:
        _cleanup(db_session, prefix)


def test_get_transaction_not_found(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/transactions/{uuid.uuid4()}", headers=auth_header(user))
    assert response.status_code == 404


def test_list_transactions_pagination_bounds(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get("/api/v1/transactions", params={"limit": 0}, headers=auth_header(user))
    assert response.status_code == 422

    response = client.get("/api/v1/transactions", params={"limit": 101}, headers=auth_header(user))
    assert response.status_code == 422


def test_accounts_rejects_missing_credential(client: TestClient) -> None:
    response = client.get("/api/v1/accounts")
    assert response.status_code == 401


def test_transactions_rejects_missing_credential(client: TestClient) -> None:
    response = client.get("/api/v1/transactions")
    assert response.status_code == 401


def test_accounts_rejects_service_credential(client: TestClient, service_auth_header: dict) -> None:
    """The `service` principal is a machine credential with no case-
    decision or read-UI rights — reads require a real human role."""
    response = client.get("/api/v1/accounts", headers=service_auth_header)
    assert response.status_code == 401
