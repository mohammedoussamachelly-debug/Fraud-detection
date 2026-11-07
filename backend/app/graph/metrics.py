"""Pure NetworkX algorithms over an already-bounded graph view (either one
built from the database by `app.graph.build`, or a synthetic scenario from
`app.graph.synthetic`). Nothing here touches the database.

Per the `graph-analytics` skill's mandatory rules: everything returned here
is a *structural* signal, never a fraud determination — see
`GRAPH_DISCLAIMER`, which every API response that surfaces these values
includes verbatim.
"""

from collections.abc import Hashable

import networkx as nx

DEFAULT_VELOCITY_WINDOW_STEPS = 24
DEFAULT_FAN_THRESHOLD = 5
CYCLE_MAX_LENGTH = 6
MAX_CYCLES_RETURNED = 25

GRAPH_DISCLAIMER = (
    "Structural signal derived from transaction connectivity only. "
    "This is not a fraud determination and does not establish money "
    "laundering or any other wrongdoing; it requires human investigation "
    "and corroborating evidence."
)


def incoming_outgoing_counts(graph: nx.MultiDiGraph, node: Hashable) -> dict[str, int]:
    """Transaction counts, not account counts — each parallel edge (repeated
    transaction between the same two accounts) is counted separately, since
    `MultiDiGraph.in_degree`/`out_degree` count edge multiplicity.
    """
    if node not in graph:
        return {"incoming_transaction_count": 0, "outgoing_transaction_count": 0}
    return {
        "incoming_transaction_count": graph.in_degree(node),
        "outgoing_transaction_count": graph.out_degree(node),
    }


def unique_counterparties(graph: nx.MultiDiGraph, node: Hashable) -> dict[str, int]:
    """Distinct sender/recipient accounts — deduplicated even if a
    counterparty sent/received multiple transactions.
    """
    if node not in graph:
        return {"unique_senders": 0, "unique_recipients": 0}
    return {
        "unique_senders": len(set(graph.predecessors(node))),
        "unique_recipients": len(set(graph.successors(node))),
    }


def fan_pattern(
    unique_senders: int,
    unique_recipients: int,
    threshold: int = DEFAULT_FAN_THRESHOLD,
) -> dict[str, bool]:
    """Many-to-one ("fan-in") / one-to-many ("fan-out") concentration flags.

    This is a simple, deterministic, documented heuristic (unique
    counterparty count at or above `threshold`) — not a classifier, and not
    by itself evidence of structuring or money laundering (per the
    graph-analytics skill's rule against classifying an account as
    criminal based solely on connectivity).
    """
    return {
        "fan_in_pattern": unique_senders >= threshold,
        "fan_out_pattern": unique_recipients >= threshold,
    }


def transaction_velocity(
    graph: nx.MultiDiGraph,
    node: Hashable,
    as_of_step: int | None = None,
    window_steps: int = DEFAULT_VELOCITY_WINDOW_STEPS,
) -> int:
    """Count of `node`'s incoming + outgoing transactions in the trailing
    `window_steps` before `as_of_step` (or before the latest step present in
    the graph, if `as_of_step` isn't given). Pure in-memory count over the
    edges already in `graph` — it does not requery the database.
    """
    if node not in graph:
        return 0

    steps = [data["step"] for _, _, data in graph.in_edges(node, data=True)]
    steps += [data["step"] for _, _, data in graph.out_edges(node, data=True)]
    if not steps:
        return 0

    reference_step = as_of_step if as_of_step is not None else max(steps) + 1
    return sum(1 for step in steps if reference_step - window_steps <= step < reference_step)


def connected_components(graph: nx.MultiDiGraph) -> list[list[Hashable]]:
    """Weakly-connected components (direction ignored) of whatever graph
    view is passed in. A single-account neighborhood built by
    `app.graph.build` is connected by construction (it's a BFS from one
    center), so this is most meaningful against a combined view spanning
    multiple accounts/scenarios — see `docs/graph-analytics.md`.
    """
    undirected = graph.to_undirected(as_view=True)
    return [sorted(component, key=str) for component in nx.connected_components(undirected)]


def detect_cycles(
    graph: nx.MultiDiGraph,
    max_length: int = CYCLE_MAX_LENGTH,
    max_cycles: int = MAX_CYCLES_RETURNED,
) -> list[list[Hashable]]:
    """Simple cycles up to `max_length` nodes, capped at `max_cycles` —
    bounded so this stays usable against a dense neighborhood rather than
    risking the combinatorial blow-up `nx.simple_cycles` can have on an
    unbounded graph. Parallel edges (repeated transactions between the same
    pair) are collapsed to one edge first, since cycle *structure* only
    depends on account adjacency, not transaction count.
    """
    simple_graph = nx.DiGraph(graph)
    cycles: list[list[Hashable]] = []
    for cycle in nx.simple_cycles(simple_graph, length_bound=max_length):
        cycles.append(cycle)
        if len(cycles) >= max_cycles:
            break
    return cycles
