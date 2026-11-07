"""Integration tests for `app.graph.fund_flow.trace_fund_flow`: forward-in-time
chains, branching caps, and the `as_of_step` boundary. Skipped when no DB is
reachable (see `tests/conftest.py`).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction
from app.graph.fund_flow import trace_fund_flow


def _ingest(client: TestClient, items: list[dict], service_auth_header: dict) -> None:
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": items}, headers=service_auth_header
    )
    assert response.status_code == 200, response.text


def _txn_item(prefix: str, suffix: str, step: int, origin: str, dest: str) -> dict:
    return {
        "external_ref": f"{prefix}-tx-{suffix}",
        "step": step,
        "type": "TRANSFER",
        "amount": "100.00",
        "origin_external_ref": f"{prefix}-{origin}",
        "dest_external_ref": f"{prefix}-{dest}",
        "origin_balance_before": "1000.00",
        "origin_balance_after": "900.00",
        "dest_balance_before": "0.00",
        "dest_balance_after": "100.00",
    }


def _account_id(db_session, external_ref: str) -> uuid.UUID:
    account = db_session.query(Account).filter(Account.external_ref == external_ref).one()
    return account.id


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_traces_a_forward_chain(client: TestClient, db_session, service_auth_header: dict) -> None:
    prefix = f"test-flow-chain-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=10, origin="A", dest="B"),
                _txn_item(prefix, "2", step=11, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = trace_fund_flow(db_session, a_id, max_hops=2)
        assert result.truncated is False
        assert len(result.paths) == 1
        path = result.paths[0]
        assert len(path) == 2
        assert path[0].to_account_id == path[1].from_account_id
        assert path[0].step < path[1].step
    finally:
        _cleanup(db_session, prefix)


def test_does_not_walk_backward_in_time(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    """An onward transfer that happened *before* the funding transaction must
    not be followed — only strictly later transactions count as "onward."
    """
    prefix = f"test-flow-order-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "earlier", step=5, origin="B", dest="C"),
                _txn_item(prefix, "funding", step=10, origin="A", dest="B"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = trace_fund_flow(db_session, a_id, max_hops=2)
        # Only the funding transaction's own (empty) continuation shows up;
        # B's earlier (step=5) outgoing transfer predates receiving funds at
        # step=10, so it must not appear in any path.
        assert all(len(path) == 1 for path in result.paths)
    finally:
        _cleanup(db_session, prefix)


def test_as_of_step_bounds_the_trace(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-flow-asof-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=10, origin="A", dest="B"),
                _txn_item(prefix, "2", step=20, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = trace_fund_flow(db_session, a_id, as_of_step=20, max_hops=2)
        assert all(len(path) == 1 for path in result.paths)
    finally:
        _cleanup(db_session, prefix)


def test_branching_is_capped(client: TestClient, db_session, service_auth_header: dict) -> None:
    prefix = f"test-flow-branch-{uuid.uuid4().hex[:8]}"
    try:
        items = [_txn_item(prefix, str(i), step=10 + i, origin="A", dest=f"R{i}") for i in range(6)]
        _ingest(client, items, service_auth_header)
        a_id = _account_id(db_session, f"{prefix}-A")

        result = trace_fund_flow(db_session, a_id, max_hops=1, max_branches=2)
        assert len(result.paths) == 2
    finally:
        _cleanup(db_session, prefix)


def test_account_with_no_outgoing_transactions_returns_one_empty_path(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-flow-empty-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [_txn_item(prefix, "1", step=1, origin="A", dest="DEADEND")],
            service_auth_header,
        )
        deadend_id = _account_id(db_session, f"{prefix}-DEADEND")

        result = trace_fund_flow(db_session, deadend_id, max_hops=3)
        assert result.paths == [[]]
        assert result.truncated is False
    finally:
        _cleanup(db_session, prefix)


def test_invalid_parameters_raise() -> None:
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        with pytest.raises(ValueError, match="max_hops"):
            trace_fund_flow(session, uuid.uuid4(), max_hops=0)
        with pytest.raises(ValueError, match="max_branches"):
            trace_fund_flow(session, uuid.uuid4(), max_branches=0)
    finally:
        session.close()
