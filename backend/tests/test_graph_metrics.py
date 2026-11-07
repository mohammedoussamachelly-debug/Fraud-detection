"""Unit tests for `app.graph.metrics` against small, hand-constructed
NetworkX graphs with predictable expected output — no database involved.
"""

import networkx as nx

from app.graph.metrics import (
    connected_components,
    detect_cycles,
    fan_pattern,
    incoming_outgoing_counts,
    transaction_velocity,
    unique_counterparties,
)


def _edge(
    graph: nx.MultiDiGraph, tx_id: str, origin: str, dest: str, step: int, amount: float = 100.0
) -> None:
    graph.add_edge(
        origin, dest, key=tx_id, transaction_id=tx_id, amount=amount, step=step, type="TRANSFER"
    )


def test_incoming_outgoing_counts_basic() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "C", "B", step=2)
    _edge(graph, "tx3", "B", "D", step=3)

    counts = incoming_outgoing_counts(graph, "B")
    assert counts == {"incoming_transaction_count": 2, "outgoing_transaction_count": 1}


def test_incoming_outgoing_counts_multi_edge_counts_each_transaction() -> None:
    """Two repeated transactions between the same pair of accounts must be
    counted twice, not collapsed into one logical edge.
    """
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "A", "B", step=5)

    counts = incoming_outgoing_counts(graph, "B")
    assert counts["incoming_transaction_count"] == 2

    counterparties = unique_counterparties(graph, "B")
    assert counterparties["unique_senders"] == 1  # still one distinct sender


def test_unique_counterparties_deduplicates() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "HUB", step=1)
    _edge(graph, "tx2", "A", "HUB", step=2)  # repeat sender
    _edge(graph, "tx3", "B", "HUB", step=3)
    _edge(graph, "tx4", "HUB", "C", step=4)
    _edge(graph, "tx5", "HUB", "D", step=5)

    counterparties = unique_counterparties(graph, "HUB")
    assert counterparties == {"unique_senders": 2, "unique_recipients": 2}


def test_isolated_node_returns_zeros() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.add_node("LONELY")

    assert incoming_outgoing_counts(graph, "LONELY") == {
        "incoming_transaction_count": 0,
        "outgoing_transaction_count": 0,
    }
    assert unique_counterparties(graph, "LONELY") == {"unique_senders": 0, "unique_recipients": 0}
    assert transaction_velocity(graph, "LONELY", as_of_step=100) == 0


def test_missing_node_returns_zeros_not_an_error() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    assert incoming_outgoing_counts(graph, "NOPE") == {
        "incoming_transaction_count": 0,
        "outgoing_transaction_count": 0,
    }
    assert unique_counterparties(graph, "NOPE") == {"unique_senders": 0, "unique_recipients": 0}
    assert transaction_velocity(graph, "NOPE", as_of_step=100) == 0


def test_fan_pattern_thresholds() -> None:
    below = fan_pattern(unique_senders=4, unique_recipients=1, threshold=5)
    assert below == {"fan_in_pattern": False, "fan_out_pattern": False}

    at_threshold = fan_pattern(unique_senders=5, unique_recipients=5, threshold=5)
    assert at_threshold == {"fan_in_pattern": True, "fan_out_pattern": True}

    mixed = fan_pattern(unique_senders=1, unique_recipients=9, threshold=5)
    assert mixed == {"fan_in_pattern": False, "fan_out_pattern": True}


def test_transaction_velocity_window() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "HUB", step=10)
    _edge(graph, "tx2", "B", "HUB", step=50)
    _edge(graph, "tx3", "C", "HUB", step=95)

    # as_of_step=100, window=24 -> only step in [76, 100) counts -> tx3 only
    assert transaction_velocity(graph, "HUB", as_of_step=100, window_steps=24) == 1

    # Wider window picks up tx2 and tx3 as well.
    assert transaction_velocity(graph, "HUB", as_of_step=100, window_steps=60) == 2

    # No as_of_step -> reference is max(step) + 1 = 96, window 24 -> [72, 96)
    assert transaction_velocity(graph, "HUB", as_of_step=None, window_steps=24) == 1


def test_connected_components_on_disjoint_graph() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "C", "D", step=2)
    graph.add_node("E")  # isolated, its own component

    components = connected_components(graph)
    component_sets = [set(c) for c in components]

    assert {"A", "B"} in component_sets
    assert {"C", "D"} in component_sets
    assert {"E"} in component_sets
    assert len(components) == 3


def test_connected_components_single_component() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "B", "C", step=2)

    components = connected_components(graph)
    assert len(components) == 1
    assert set(components[0]) == {"A", "B", "C"}


def test_detect_cycles_finds_simple_cycle() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "B", "C", step=2)
    _edge(graph, "tx3", "C", "A", step=3)

    cycles = detect_cycles(graph)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"A", "B", "C"}


def test_detect_cycles_acyclic_graph_returns_empty() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    _edge(graph, "tx1", "A", "B", step=1)
    _edge(graph, "tx2", "B", "C", step=2)
    _edge(graph, "tx3", "C", "D", step=3)

    assert detect_cycles(graph) == []


def test_detect_cycles_respects_length_bound() -> None:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    # A 5-node cycle; with max_length=3 it must not be reported.
    nodes = ["A", "B", "C", "D", "E"]
    for i, node in enumerate(nodes):
        _edge(graph, f"tx{i}", node, nodes[(i + 1) % len(nodes)], step=i)

    assert detect_cycles(graph, max_length=3) == []
    assert len(detect_cycles(graph, max_length=5)) == 1
