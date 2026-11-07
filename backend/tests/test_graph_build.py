"""Integration tests for `app.graph.build.build_account_neighborhood` against
a live database: hop expansion, temporal (`as_of_step`) leakage boundaries,
multi-edge transactions, truncation on tight caps, and empty/isolated
accounts. Skipped (not faked) when no DB is reachable, matching this
project's existing test convention (see `tests/conftest.py`).
"""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction
from app.graph.build import build_account_neighborhood


def _ingest(client: TestClient, items: list[dict], service_auth_header: dict) -> None:
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": items}, headers=service_auth_header
    )
    assert response.status_code == 200, response.text


def _txn_item(
    prefix: str, suffix: str, step: int, origin: str, dest: str, amount: str = "100.00"
) -> dict:
    return {
        "external_ref": f"{prefix}-tx-{suffix}",
        "step": step,
        "type": "TRANSFER",
        "amount": amount,
        "origin_external_ref": f"{prefix}-{origin}",
        "dest_external_ref": f"{prefix}-{dest}",
        "origin_balance_before": "1000.00",
        "origin_balance_after": "900.00",
        "dest_balance_before": "0.00",
        "dest_balance_after": amount,
    }


def _account_id(db_session, external_ref: str) -> uuid.UUID:
    account = db_session.query(Account).filter(Account.external_ref == external_ref).one()
    return account.id


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_one_hop_neighborhood_contains_only_direct_counterparties(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-graph-1hop-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=1, origin="A", dest="B"),
                _txn_item(prefix, "2", step=2, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = build_account_neighborhood(db_session, a_id, hops=1)
        external_refs = {data["external_ref"] for _, data in result.graph.nodes(data=True)}

        assert external_refs == {f"{prefix}-A", f"{prefix}-B"}
        assert result.graph.number_of_edges() == 1
        assert result.truncated is False
    finally:
        _cleanup(db_session, prefix)


def test_two_hop_neighborhood_reaches_second_degree_accounts(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-graph-2hop-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=1, origin="A", dest="B"),
                _txn_item(prefix, "2", step=2, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = build_account_neighborhood(db_session, a_id, hops=2)
        external_refs = {data["external_ref"] for _, data in result.graph.nodes(data=True)}

        assert external_refs == {f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"}
        assert result.graph.number_of_edges() == 2
    finally:
        _cleanup(db_session, prefix)


def test_as_of_step_excludes_future_transactions(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    """A transaction at or after `as_of_step` must never appear in the
    neighborhood — the temporal-leakage boundary this phase requires.
    """
    prefix = f"test-graph-leak-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "past", step=10, origin="A", dest="B"),
                _txn_item(prefix, "future", step=20, origin="A", dest="C"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = build_account_neighborhood(db_session, a_id, hops=1, as_of_step=20)
        external_refs = {data["external_ref"] for _, data in result.graph.nodes(data=True)}

        assert external_refs == {f"{prefix}-A", f"{prefix}-B"}
        assert f"{prefix}-C" not in external_refs

        # as_of_step equal to the earlier transaction's own step excludes it too.
        result_at_10 = build_account_neighborhood(db_session, a_id, hops=1, as_of_step=10)
        assert result_at_10.graph.number_of_edges() == 0
    finally:
        _cleanup(db_session, prefix)


def test_multi_edge_transactions_are_each_preserved(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-graph-multi-{uuid.uuid4().hex[:8]}"
    try:
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=1, origin="A", dest="B", amount="50.00"),
                _txn_item(prefix, "2", step=2, origin="A", dest="B", amount="75.00"),
                _txn_item(prefix, "3", step=3, origin="A", dest="B", amount="10.00"),
            ],
            service_auth_header,
        )
        a_id = _account_id(db_session, f"{prefix}-A")

        result = build_account_neighborhood(db_session, a_id, hops=1)
        assert result.graph.number_of_edges() == 3
        assert result.graph.number_of_nodes() == 2

        amounts = sorted(data["amount"] for _, _, data in result.graph.edges(data=True))
        assert amounts == [Decimal("10.00"), Decimal("50.00"), Decimal("75.00")]
    finally:
        _cleanup(db_session, prefix)


def test_isolated_account_has_empty_neighborhood(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-graph-iso-{uuid.uuid4().hex[:8]}"
    try:
        # An account that only ever appears as a dest, never transacting again.
        _ingest(
            client,
            [_txn_item(prefix, "1", step=1, origin="A", dest="ISOLATED")],
            service_auth_header,
        )
        isolated_id = _account_id(db_session, f"{prefix}-ISOLATED")

        result = build_account_neighborhood(db_session, isolated_id, hops=2)
        external_refs = {data["external_ref"] for _, data in result.graph.nodes(data=True)}

        assert external_refs == {f"{prefix}-A", f"{prefix}-ISOLATED"}
        assert result.graph.number_of_edges() == 1
    finally:
        _cleanup(db_session, prefix)


def test_unknown_account_returns_empty_graph_not_an_error(db_session) -> None:
    result = build_account_neighborhood(db_session, uuid.uuid4(), hops=1)
    assert result.graph.number_of_nodes() == 0
    assert result.truncated is False


def test_truncation_flag_set_when_max_edges_exceeded(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    prefix = f"test-graph-trunc-{uuid.uuid4().hex[:8]}"
    try:
        items = [_txn_item(prefix, str(i), step=i, origin="HUB", dest=f"R{i}") for i in range(10)]
        _ingest(client, items, service_auth_header)
        hub_id = _account_id(db_session, f"{prefix}-HUB")

        result = build_account_neighborhood(db_session, hub_id, hops=1, max_edges=3)
        assert result.truncated is True
        assert result.graph.number_of_edges() <= 3
    finally:
        _cleanup(db_session, prefix)


def test_invalid_hops_raises() -> None:
    import pytest

    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        with pytest.raises(ValueError, match="hops"):
            build_account_neighborhood(session, uuid.uuid4(), hops=0)
        with pytest.raises(ValueError, match="hops"):
            build_account_neighborhood(session, uuid.uuid4(), hops=5)
    finally:
        session.close()
