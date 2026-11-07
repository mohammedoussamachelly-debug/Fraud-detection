"""Deterministic synthetic fraud-network scenarios.

Real PaySim data has limited repeated-sender history (see
`docs/implementation-plan.md`'s Phase 3 notes and this phase's mission
brief), so these fixtures exist to exercise structural-pattern detection in
`app.graph.metrics` against known, hand-specified topologies that PaySim
itself rarely contains. Every scenario graph carries
`graph.graph["synthetic"] = True` plus a `scenario`/`description` label.

These are entirely synthetic constructions, not derived from PaySim or any
real transaction, and none of them is, or should be read as, evidence of
real money laundering — see `docs/graph-scenarios.md`. All node/edge
attribute names match `app.graph.build`'s output shape (`external_ref`,
`account_type`, `transaction_id`, `amount`, `step`, `type`) so the same
`app.graph.metrics` functions run against either source unmodified; account
ids and transaction ids here are deterministic strings rather than UUIDs
(there is no real database row behind them).
"""

from collections.abc import Callable

import networkx as nx


def _new_scenario_graph(name: str, description: str) -> nx.MultiDiGraph:
    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    graph.graph["synthetic"] = True
    graph.graph["scenario"] = name
    graph.graph["description"] = description
    return graph


def _add_node(graph: nx.MultiDiGraph, account_ref: str, account_type: str = "customer") -> None:
    if account_ref not in graph:
        graph.add_node(account_ref, external_ref=account_ref, account_type=account_type)


def _add_edge(
    graph: nx.MultiDiGraph,
    tx_ref: str,
    origin: str,
    dest: str,
    amount: float,
    step: int,
    account_type: str = "customer",
) -> None:
    _add_node(graph, origin, account_type)
    _add_node(graph, dest, account_type)
    graph.add_edge(
        origin,
        dest,
        key=tx_ref,
        transaction_id=tx_ref,
        external_ref=tx_ref,
        amount=amount,
        step=step,
        type="TRANSFER",
    )


def many_to_one_concentration(num_senders: int = 8) -> nx.MultiDiGraph:
    """`num_senders` distinct accounts each send one transaction to a single
    hub account — a many-to-one concentration pattern (e.g. "smurfing"-style
    aggregation), without claiming that label proves anything by itself.
    """
    graph = _new_scenario_graph(
        "many_to_one_concentration",
        f"{num_senders} distinct sender accounts each transfer once to a single hub account.",
    )
    for i in range(num_senders):
        sender = f"SYN-M2O-SRC-{i:02d}"
        _add_edge(graph, f"SYN-M2O-TX-{i:02d}", sender, "SYN-M2O-HUB", 500.0 + i * 10, 100 + i)
    return graph


def one_to_many_redistribution(num_recipients: int = 8) -> nx.MultiDiGraph:
    """A single source account distributes funds to `num_recipients` distinct
    recipient accounts — a one-to-many fund-redistribution pattern.
    """
    graph = _new_scenario_graph(
        "one_to_many_redistribution",
        f"A single source account distributes funds to {num_recipients} distinct recipients.",
    )
    for i in range(num_recipients):
        recipient = f"SYN-O2M-DST-{i:02d}"
        _add_edge(graph, f"SYN-O2M-TX-{i:02d}", "SYN-O2M-SRC", recipient, 300.0 + i * 5, 200 + i)
    return graph


def rapid_onward_transfers(chain_length: int = 5) -> nx.MultiDiGraph:
    """A chain of `chain_length` accounts, each forwarding received funds
    onward one simulated step after receiving them, with a small fixed
    skim at each hop (deterministic, not randomized).
    """
    graph = _new_scenario_graph(
        "rapid_onward_transfers",
        f"A chain of {chain_length} accounts, each forwarding funds onward "
        "within one simulated step of receiving them.",
    )
    amount = 10000.0
    for i in range(chain_length):
        origin = f"SYN-CHAIN-{i:02d}"
        dest = f"SYN-CHAIN-{i + 1:02d}"
        amount = round(amount * 0.95, 2)
        _add_edge(graph, f"SYN-CHAIN-TX-{i:02d}", origin, dest, amount, 300 + i)
    return graph


def circular_transfers(cycle_length: int = 4) -> nx.MultiDiGraph:
    """`cycle_length` accounts arranged in a closed loop: funds move through
    every account in the ring and return to the originating account.
    """
    if cycle_length < 3:
        raise ValueError("circular_transfers requires cycle_length >= 3")

    graph = _new_scenario_graph(
        "circular_transfers",
        f"Funds move through a closed loop of {cycle_length} accounts and "
        "return to the originating account.",
    )
    accounts = [f"SYN-RING-{i:02d}" for i in range(cycle_length)]
    for i in range(cycle_length):
        origin = accounts[i]
        dest = accounts[(i + 1) % cycle_length]
        _add_edge(graph, f"SYN-RING-TX-{i:02d}", origin, dest, 1000.0, 400 + i)
    return graph


SCENARIOS: dict[str, Callable[[], nx.MultiDiGraph]] = {
    "many_to_one_concentration": many_to_one_concentration,
    "one_to_many_redistribution": one_to_many_redistribution,
    "rapid_onward_transfers": rapid_onward_transfers,
    "circular_transfers": circular_transfers,
}


def build_scenario(name: str) -> nx.MultiDiGraph:
    if name not in SCENARIOS:
        raise ValueError(f"Unknown synthetic scenario: {name!r}. Known: {sorted(SCENARIOS)}")
    return SCENARIOS[name]()
