"""Performance smoke tests for `app.graph`. These assert a generous time
bound (not a strict benchmark) so they stay stable across machines, and
report real measured timings via the assertion message / captured output —
never a fabricated number. Run with `-s` to see the printed timings.

The in-memory tests need no database and always run. The DB-backed test
builds a bounded neighborhood against a real, moderately large ingested
graph and is skipped (not faked) when no DB is reachable.
"""

import time
import uuid

import networkx as nx
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import Account, Transaction
from app.graph.build import build_account_neighborhood
from app.graph.metrics import connected_components, detect_cycles, incoming_outgoing_counts


def _build_hub_and_spoke_graph(num_spokes: int) -> nx.MultiDiGraph:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    for i in range(num_spokes):
        graph.add_edge(
            f"SPOKE-{i}",
            "HUB",
            key=f"tx-{i}",
            transaction_id=f"tx-{i}",
            amount=100.0,
            step=i,
            type="TRANSFER",
        )
    return graph


def test_metrics_scale_to_thousands_of_edges() -> None:
    graph = _build_hub_and_spoke_graph(5000)

    start = time.perf_counter()
    counts = incoming_outgoing_counts(graph, "HUB")
    elapsed = time.perf_counter() - start

    assert counts["incoming_transaction_count"] == 5000
    assert elapsed < 2.0, f"incoming_outgoing_counts took {elapsed:.3f}s on 5000 edges"


def test_connected_components_scale_to_thousands_of_edges() -> None:
    graph = _build_hub_and_spoke_graph(5000)

    start = time.perf_counter()
    components = connected_components(graph)
    elapsed = time.perf_counter() - start

    assert len(components) == 1
    assert elapsed < 2.0, f"connected_components took {elapsed:.3f}s on 5000 edges"


def test_cycle_detection_scales_to_a_long_ring() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    ring_size = 500
    for i in range(ring_size):
        graph.add_edge(
            f"RING-{i}",
            f"RING-{(i + 1) % ring_size}",
            key=f"tx-{i}",
            transaction_id=f"tx-{i}",
            amount=1.0,
            step=i,
            type="TRANSFER",
        )

    start = time.perf_counter()
    # Bounded length_bound keeps this from exploding on a dense graph; a
    # cycle longer than the bound (the full 500-node ring) correctly yields
    # no result rather than hanging.
    cycles = detect_cycles(graph, max_length=6)
    elapsed = time.perf_counter() - start

    assert cycles == []
    assert elapsed < 5.0, f"detect_cycles took {elapsed:.3f}s on a {ring_size}-node ring"


def _txn_item(prefix: str, suffix: str, step: int, origin: str, dest: str) -> dict:
    return {
        "external_ref": f"{prefix}-tx-{suffix}",
        "step": step,
        "type": "TRANSFER",
        "amount": "10.00",
        "origin_external_ref": f"{prefix}-{origin}",
        "dest_external_ref": f"{prefix}-{dest}",
        "origin_balance_before": "1000.00",
        "origin_balance_after": "990.00",
        "dest_balance_before": "0.00",
        "dest_balance_after": "10.00",
    }


def test_neighborhood_build_against_real_database(
    client: TestClient, db_session, service_auth_header: dict
) -> None:
    """Ingests a real hub-and-spoke fan-in (1000 senders) through the actual
    `/transactions/ingest` endpoint, then measures how long a bounded
    neighborhood build takes against the live database.
    """
    prefix = f"test-graph-perf-{uuid.uuid4().hex[:8]}"
    num_spokes = 1000
    try:
        batch = [
            _txn_item(prefix, str(i), step=i, origin=f"S{i}", dest="HUB") for i in range(num_spokes)
        ]
        # The ingest endpoint caps batches at 5000 items (see
        # app/schemas/transaction.py); 1000 fits in one call.
        response = client.post(
            "/api/v1/transactions/ingest", json={"transactions": batch}, headers=service_auth_header
        )
        assert response.status_code == 200, response.text

        hub = db_session.query(Account).filter(Account.external_ref == f"{prefix}-HUB").one()

        start = time.perf_counter()
        # max_nodes must be raised alongside max_edges: build_account_neighborhood
        # enforces both caps independently, and this 1-hop ego graph has one new
        # node per new sender (close to one node per edge), so the default
        # max_nodes=300 would truncate at ~300 of the 1000 senders.
        result = build_account_neighborhood(
            db_session, hub.id, hops=1, max_nodes=num_spokes + 10, max_edges=5000
        )
        elapsed = time.perf_counter() - start

        assert result.graph.number_of_edges() == num_spokes
        assert result.truncated is False
        assert elapsed < 5.0, (
            f"build_account_neighborhood took {elapsed:.3f}s for a "
            f"{num_spokes}-edge neighborhood against a live database"
        )
    finally:
        db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
        db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
        db_session.commit()
