"""API integration tests for the `/graph/accounts/...` endpoints
(`app/api/routes/graph.py`), against a live database. Skipped when no DB is
reachable (see `tests/conftest.py`), following this project's existing
convention (e.g. `tests/test_accounts_transactions_api.py`).

`analyst+` required since Phase 6 Part A (ingestion is `service`-role) —
every call threads `service_auth_header`/an analyst's `auth_header`
through the helpers below.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction
from tests.conftest import auth_header


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


def _account_id(client: TestClient, external_ref: str, headers: dict) -> str:
    response = client.get(
        "/api/v1/accounts", params={"external_ref": external_ref}, headers=headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    return items[0]["id"]


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_neighborhood_endpoint_returns_nodes_edges_and_disclaimer(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-nbhd-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=1, origin="A", dest="B"),
                _txn_item(prefix, "2", step=2, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        account_id = _account_id(client, f"{prefix}-A", headers)

        response = client.get(
            f"/api/v1/graph/accounts/{account_id}", params={"hops": 2}, headers=headers
        )
        assert response.status_code == 200
        body = response.json()

        assert body["center_account_id"] == account_id
        assert body["hops"] == 2
        assert body["truncated"] is False
        assert "not a fraud determination" in body["disclaimer"]

        node_refs = {node["external_ref"] for node in body["nodes"]}
        assert node_refs == {f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"}
        assert len(body["edges"]) == 2
    finally:
        _cleanup(db_session, prefix)


def test_neighborhood_endpoint_detects_cycle(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-cycle-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=1, origin="A", dest="B"),
                _txn_item(prefix, "2", step=2, origin="B", dest="C"),
                _txn_item(prefix, "3", step=3, origin="C", dest="A"),
            ],
            service_auth_header,
        )
        account_id = _account_id(client, f"{prefix}-A", headers)

        response = client.get(
            f"/api/v1/graph/accounts/{account_id}", params={"hops": 2}, headers=headers
        )
        assert response.status_code == 200
        cycles = response.json()["cycles"]
        assert len(cycles) == 1
        assert set(cycles[0]) == {f"{prefix}-A", f"{prefix}-B", f"{prefix}-C"}
    finally:
        _cleanup(db_session, prefix)


def test_neighborhood_endpoint_404_for_unknown_account(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/graph/accounts/{uuid.uuid4()}", headers=auth_header(user))
    assert response.status_code == 404


def test_neighborhood_endpoint_validates_hops_bounds(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    headers = auth_header(user)
    response = client.get(
        f"/api/v1/graph/accounts/{uuid.uuid4()}", params={"hops": 0}, headers=headers
    )
    assert response.status_code == 422

    response = client.get(
        f"/api/v1/graph/accounts/{uuid.uuid4()}", params={"hops": 5}, headers=headers
    )
    assert response.status_code == 422


def test_metrics_endpoint_reports_fan_in(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-metrics-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        items = [_txn_item(prefix, str(i), step=i, origin=f"S{i}", dest="HUB") for i in range(6)]
        _ingest(client, items, service_auth_header)
        hub_id = _account_id(client, f"{prefix}-HUB", headers)

        response = client.get(f"/api/v1/graph/accounts/{hub_id}/metrics", headers=headers)
        assert response.status_code == 200
        body = response.json()

        assert body["incoming_transaction_count"] == 6
        assert body["outgoing_transaction_count"] == 0
        assert body["unique_senders"] == 6
        assert body["unique_recipients"] == 0
        assert body["fan_in_pattern"] is True
        assert body["fan_out_pattern"] is False
    finally:
        _cleanup(db_session, prefix)


def test_metrics_endpoint_as_of_step_excludes_future_activity(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-metrics-leak-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        _ingest(
            client,
            [
                _txn_item(prefix, "past", step=10, origin="S", dest="HUB"),
                _txn_item(prefix, "future", step=50, origin="S2", dest="HUB"),
            ],
            service_auth_header,
        )
        hub_id = _account_id(client, f"{prefix}-HUB", headers)

        response = client.get(
            f"/api/v1/graph/accounts/{hub_id}/metrics", params={"as_of_step": 50}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["incoming_transaction_count"] == 1
    finally:
        _cleanup(db_session, prefix)


def test_metrics_endpoint_404_for_unknown_account(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(
        f"/api/v1/graph/accounts/{uuid.uuid4()}/metrics", headers=auth_header(user)
    )
    assert response.status_code == 404


def test_transactions_endpoint_labels_direction(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-txns-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        _ingest(
            client,
            [
                _txn_item(prefix, "in", step=1, origin="OTHER", dest="A"),
                _txn_item(prefix, "out", step=2, origin="A", dest="OTHER2"),
            ],
            service_auth_header,
        )
        account_id = _account_id(client, f"{prefix}-A", headers)

        response = client.get(f"/api/v1/graph/accounts/{account_id}/transactions", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2

        by_ref = {item["external_ref"]: item["direction"] for item in body["items"]}
        assert by_ref[f"{prefix}-tx-in"] == "incoming"
        assert by_ref[f"{prefix}-tx-out"] == "outgoing"
    finally:
        _cleanup(db_session, prefix)


def test_fund_flow_endpoint_traces_onward_chain(
    client: TestClient, db_session, make_user, service_auth_header: dict
) -> None:
    prefix = f"test-api-flow-{uuid.uuid4().hex[:8]}"
    try:
        user = make_user(role="analyst")
        headers = auth_header(user)
        _ingest(
            client,
            [
                _txn_item(prefix, "1", step=10, origin="A", dest="B"),
                _txn_item(prefix, "2", step=11, origin="B", dest="C"),
            ],
            service_auth_header,
        )
        account_id = _account_id(client, f"{prefix}-A", headers)

        response = client.get(
            f"/api/v1/graph/accounts/{account_id}/fund-flow",
            params={"max_hops": 2},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()

        assert body["max_hops"] == 2
        assert len(body["paths"]) == 1
        assert len(body["paths"][0]["steps"]) == 2
    finally:
        _cleanup(db_session, prefix)


def test_fund_flow_endpoint_validates_max_branches_bounds(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    headers = auth_header(user)
    response = client.get(
        f"/api/v1/graph/accounts/{uuid.uuid4()}/fund-flow",
        params={"max_branches": 0},
        headers=headers,
    )
    assert response.status_code == 422

    response = client.get(
        f"/api/v1/graph/accounts/{uuid.uuid4()}/fund-flow",
        params={"max_branches": 11},
        headers=headers,
    )
    assert response.status_code == 422


def test_graph_endpoint_rejects_missing_credential(client: TestClient) -> None:
    response = client.get(f"/api/v1/graph/accounts/{uuid.uuid4()}")
    assert response.status_code == 401


def test_graph_endpoint_rejects_service_credential(
    client: TestClient, service_auth_header: dict
) -> None:
    response = client.get(f"/api/v1/graph/accounts/{uuid.uuid4()}", headers=service_auth_header)
    assert response.status_code == 401
