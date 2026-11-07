"""Integration tests for /transactions/ingest — real DB, skipped (not
faked) when unreachable. Each test uses a unique external_ref prefix and
cleans up its own rows, so repeated runs stay idempotent-safe.

`service`-role only since Phase 6 Part A — every call below passes
`service_auth_header` (tests/conftest.py); the auth-rejection tests at
the bottom check the no-credential / wrong-credential paths.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction


def _item(external_ref: str, **overrides) -> dict:
    item = {
        "external_ref": external_ref,
        "step": 1,
        "type": "TRANSFER",
        "amount": "100.00",
        "origin_external_ref": f"{external_ref}-orig",
        "dest_external_ref": f"{external_ref}-dest",
        "origin_balance_before": "500.00",
        "origin_balance_after": "400.00",
        "dest_balance_before": "0.00",
        "dest_balance_after": "100.00",
    }
    item.update(overrides)
    return item


def _cleanup(db_session, prefix: str, extra_account_refs: list[str] | None = None) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    for ref in extra_account_refs or []:
        db_session.execute(delete(Account).where(Account.external_ref == ref))
    db_session.commit()


def test_ingest_creates_accounts_and_transaction(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-ingest-{uuid.uuid4().hex[:8]}"
    try:
        response = client.post(
            "/api/v1/transactions/ingest",
            json={"transactions": [_item(f"{prefix}-tx1")]},
            headers=service_auth_header,
        )
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "received": 1,
            "inserted": 1,
            "skipped_existing": 0,
            "accounts_created": 2,
        }
    finally:
        _cleanup(db_session, prefix)


def test_ingest_is_idempotent_on_replay(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-ingest-{uuid.uuid4().hex[:8]}"
    try:
        payload = {"transactions": [_item(f"{prefix}-tx1")]}
        first = client.post(
            "/api/v1/transactions/ingest", json=payload, headers=service_auth_header
        )
        second = client.post(
            "/api/v1/transactions/ingest", json=payload, headers=service_auth_header
        )

        assert first.json()["inserted"] == 1
        assert second.json()["inserted"] == 0
        assert second.json()["skipped_existing"] == 1
    finally:
        _cleanup(db_session, prefix)


def test_ingest_reuses_existing_account_across_transactions(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-ingest-{uuid.uuid4().hex[:8]}"
    try:
        shared_origin = f"{prefix}-shared-orig"
        payload = {
            "transactions": [
                _item(f"{prefix}-tx1", origin_external_ref=shared_origin, step=1),
                _item(f"{prefix}-tx2", origin_external_ref=shared_origin, step=2),
            ]
        }
        response = client.post(
            "/api/v1/transactions/ingest", json=payload, headers=service_auth_header
        )
        body = response.json()
        # 2 transactions, but only 3 distinct accounts (shared origin + 2 distinct dests)
        assert body["inserted"] == 2
        assert body["accounts_created"] == 3
    finally:
        _cleanup(db_session, prefix)


def test_ingest_rejects_negative_amount(client: TestClient, service_auth_header: dict) -> None:
    response = client.post(
        "/api/v1/transactions/ingest",
        json={"transactions": [_item("test-ingest-invalid", amount="-5.00")]},
        headers=service_auth_header,
    )
    assert response.status_code == 422


def test_ingest_rejects_invalid_transaction_type(
    client: TestClient, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/transactions/ingest",
        json={"transactions": [_item("test-ingest-invalid", type="NOT_REAL")]},
        headers=service_auth_header,
    )
    assert response.status_code == 422


def test_ingest_rejects_empty_batch(client: TestClient, service_auth_header: dict) -> None:
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": []}, headers=service_auth_header
    )
    assert response.status_code == 422


def test_merchant_accounts_get_merchant_type(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-ingest-{uuid.uuid4().hex[:8]}"
    try:
        dest = f"M{prefix}"
        response = client.post(
            "/api/v1/transactions/ingest",
            json={"transactions": [_item(f"{prefix}-tx1", dest_external_ref=dest)]},
            headers=service_auth_header,
        )
        assert response.status_code == 200

        account = db_session.query(Account).filter(Account.external_ref == dest).one()
        assert account.account_type == "merchant"
    finally:
        _cleanup(db_session, prefix, extra_account_refs=[dest])


def test_ingest_rejects_missing_credential(client: TestClient) -> None:
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": [_item("test-ingest-noauth")]}
    )
    assert response.status_code == 401


def test_ingest_rejects_analyst_token(client: TestClient, make_user) -> None:
    """A human analyst token is not the `service` credential — ingestion
    stays machine-only (docs/api-contracts.md §0)."""
    from tests.conftest import auth_header

    user = make_user(role="admin")
    response = client.post(
        "/api/v1/transactions/ingest",
        json={"transactions": [_item("test-ingest-wrongrole")]},
        headers=auth_header(user),
    )
    assert response.status_code == 401
