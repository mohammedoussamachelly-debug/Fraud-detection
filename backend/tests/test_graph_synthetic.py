"""Tests for the deterministic synthetic fraud-network scenarios in
`app.graph.synthetic`, and that `app.graph.metrics` behaves as expected
against each one.
"""

import pytest

from app.graph.metrics import detect_cycles, fan_pattern, unique_counterparties
from app.graph.synthetic import (
    SCENARIOS,
    build_scenario,
    circular_transfers,
    many_to_one_concentration,
    one_to_many_redistribution,
    rapid_onward_transfers,
)


def test_all_registered_scenarios_are_labeled_synthetic() -> None:
    for name in SCENARIOS:
        graph = build_scenario(name)
        assert graph.graph["synthetic"] is True
        assert graph.graph["scenario"] == name
        assert isinstance(graph.graph["description"], str) and graph.graph["description"]


def test_build_scenario_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown synthetic scenario"):
        build_scenario("not-a-real-scenario")


def test_scenarios_are_deterministic() -> None:
    """Calling a generator twice must produce identical graphs — no
    randomness, per this phase's requirement for reproducible fixtures.
    """
    for name, factory in SCENARIOS.items():
        first = factory()
        second = factory()
        assert sorted(first.nodes) == sorted(second.nodes), name
        assert sorted(first.edges(keys=True)) == sorted(second.edges(keys=True)), name


def test_many_to_one_concentration_structure() -> None:
    graph = many_to_one_concentration(num_senders=8)
    assert graph.number_of_nodes() == 9  # 8 senders + 1 hub
    assert graph.number_of_edges() == 8

    counterparties = unique_counterparties(graph, "SYN-M2O-HUB")
    assert counterparties == {"unique_senders": 8, "unique_recipients": 0}

    fan = fan_pattern(counterparties["unique_senders"], counterparties["unique_recipients"])
    assert fan["fan_in_pattern"] is True
    assert fan["fan_out_pattern"] is False


def test_one_to_many_redistribution_structure() -> None:
    graph = one_to_many_redistribution(num_recipients=8)
    assert graph.number_of_nodes() == 9  # 1 source + 8 recipients
    assert graph.number_of_edges() == 8

    counterparties = unique_counterparties(graph, "SYN-O2M-SRC")
    assert counterparties == {"unique_senders": 0, "unique_recipients": 8}

    fan = fan_pattern(counterparties["unique_senders"], counterparties["unique_recipients"])
    assert fan["fan_in_pattern"] is False
    assert fan["fan_out_pattern"] is True


def test_rapid_onward_transfers_is_a_simple_chain_with_no_cycle() -> None:
    graph = rapid_onward_transfers(chain_length=5)
    assert graph.number_of_nodes() == 6  # chain_length + 1
    assert graph.number_of_edges() == 5
    assert detect_cycles(graph) == []

    # Each intermediate account forwards onward: in-degree 1, out-degree 1.
    for i in range(1, 5):
        node = f"SYN-CHAIN-{i:02d}"
        assert graph.in_degree(node) == 1
        assert graph.out_degree(node) == 1

    # Amount decays monotonically hop to hop (a small skim at each step).
    amounts = [
        data["amount"] for _, _, data in sorted(graph.edges(data=True), key=lambda e: e[2]["step"])
    ]
    assert amounts == sorted(amounts, reverse=True)


def test_circular_transfers_forms_exactly_one_cycle() -> None:
    graph = circular_transfers(cycle_length=4)
    assert graph.number_of_nodes() == 4
    assert graph.number_of_edges() == 4

    cycles = detect_cycles(graph)
    assert len(cycles) == 1
    assert set(cycles[0]) == set(graph.nodes)


def test_circular_transfers_rejects_too_short_cycle() -> None:
    with pytest.raises(ValueError, match="cycle_length"):
        circular_transfers(cycle_length=2)
