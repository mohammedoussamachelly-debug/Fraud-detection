"""Business-logic layer for the graph-analytics API routes
(`app/api/routes/graph.py`): looks up the account, calls the pure
construction/algorithm functions in `app/graph/`, and shapes the result into
the Pydantic response schemas (`app/schemas/graph.py`). Per
`docs/architecture.md`, API routes never import NetworkX or query
`app.transactions` directly — everything graph-shaped goes through here.
"""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction
from app.graph.build import DEFAULT_MAX_EDGES, DEFAULT_MAX_NODES, build_account_neighborhood
from app.graph.fund_flow import (
    DEFAULT_MAX_BRANCHES,
    trace_fund_flow,
)
from app.graph.fund_flow import (
    DEFAULT_MAX_HOPS as FUND_FLOW_DEFAULT_MAX_HOPS,
)
from app.graph.metrics import (
    DEFAULT_FAN_THRESHOLD,
    DEFAULT_VELOCITY_WINDOW_STEPS,
    GRAPH_DISCLAIMER,
    detect_cycles,
    fan_pattern,
    incoming_outgoing_counts,
    transaction_velocity,
    unique_counterparties,
)
from app.schemas.graph import (
    AccountGraphMetricsResponse,
    AccountGraphTransactionsResponse,
    AccountNeighborhoodResponse,
    FundFlowPath,
    FundFlowResponse,
    FundFlowStep,
    GraphEdge,
    GraphNode,
    GraphTransactionRead,
)
from app.schemas.transaction import TransactionRead

# Metrics only ever build a 1-hop (ego) neighborhood, so its own
# incoming/outgoing counts are accurate up to a much larger cap than the
# multi-hop investigation neighborhood needs by default. max_nodes must be
# overridden alongside max_edges — build_account_neighborhood enforces both
# caps independently, and a 1-hop ego graph can have close to one node per
# edge (each new counterparty contributes one edge), so leaving max_nodes
# at its default (300) would silently cut off counts well before
# METRICS_MAX_EDGES is reached, defeating the point of raising it.
METRICS_MAX_EDGES = 5000
METRICS_MAX_NODES = METRICS_MAX_EDGES + 1


class AccountNotFound(Exception):
    pass


def _require_account(db: Session, account_id: UUID) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise AccountNotFound(str(account_id))
    return account


def get_account_neighborhood(
    db: Session,
    account_id: UUID,
    hops: int,
    as_of_step: int | None,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> AccountNeighborhoodResponse:
    _require_account(db, account_id)

    result = build_account_neighborhood(
        db, account_id, hops=hops, as_of_step=as_of_step, max_nodes=max_nodes, max_edges=max_edges
    )
    graph = result.graph

    nodes = [
        GraphNode(id=node_id, external_ref=data["external_ref"], account_type=data["account_type"])
        for node_id, data in graph.nodes(data=True)
    ]
    edges = [
        GraphEdge(
            source=source,
            target=target,
            transaction_id=data["transaction_id"],
            external_ref=data["external_ref"],
            amount=data["amount"],
            step=data["step"],
            type=data["type"],
        )
        for source, target, data in graph.edges(data=True)
    ]
    cycles = [
        [graph.nodes[node_id]["external_ref"] for node_id in cycle]
        for cycle in detect_cycles(graph)
    ]

    return AccountNeighborhoodResponse(
        center_account_id=account_id,
        hops=hops,
        as_of_step=as_of_step,
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        truncated=result.truncated,
        disclaimer=GRAPH_DISCLAIMER,
    )


def get_account_metrics(
    db: Session,
    account_id: UUID,
    as_of_step: int | None = None,
    fan_threshold: int = DEFAULT_FAN_THRESHOLD,
    velocity_window_steps: int = DEFAULT_VELOCITY_WINDOW_STEPS,
) -> AccountGraphMetricsResponse:
    _require_account(db, account_id)

    result = build_account_neighborhood(
        db,
        account_id,
        hops=1,
        as_of_step=as_of_step,
        max_nodes=METRICS_MAX_NODES,
        max_edges=METRICS_MAX_EDGES,
    )
    graph = result.graph

    counts = incoming_outgoing_counts(graph, account_id)
    counterparties = unique_counterparties(graph, account_id)
    fan = fan_pattern(
        counterparties["unique_senders"],
        counterparties["unique_recipients"],
        threshold=fan_threshold,
    )
    velocity_count = transaction_velocity(
        graph, account_id, as_of_step=as_of_step, window_steps=velocity_window_steps
    )

    return AccountGraphMetricsResponse(
        account_id=account_id,
        as_of_step=as_of_step,
        incoming_transaction_count=counts["incoming_transaction_count"],
        outgoing_transaction_count=counts["outgoing_transaction_count"],
        unique_senders=counterparties["unique_senders"],
        unique_recipients=counterparties["unique_recipients"],
        fan_in_pattern=fan["fan_in_pattern"],
        fan_out_pattern=fan["fan_out_pattern"],
        velocity_window_steps=velocity_window_steps,
        velocity_count=velocity_count,
        truncated=result.truncated,
        disclaimer=GRAPH_DISCLAIMER,
    )


def get_account_transactions(
    db: Session,
    account_id: UUID,
    as_of_step: int | None = None,
    limit: int = 25,
    offset: int = 0,
) -> AccountGraphTransactionsResponse:
    _require_account(db, account_id)

    stmt = select(Transaction).where(
        or_(Transaction.origin_account_id == account_id, Transaction.dest_account_id == account_id)
    )
    if as_of_step is not None:
        stmt = stmt.where(Transaction.step < as_of_step)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Transaction.step.desc()).limit(limit).offset(offset)).all()

    items = [
        GraphTransactionRead(
            **TransactionRead.model_validate(row).model_dump(),
            direction="outgoing" if row.origin_account_id == account_id else "incoming",
        )
        for row in rows
    ]

    return AccountGraphTransactionsResponse(
        items=items, total=total, limit=limit, offset=offset, as_of_step=as_of_step
    )


def get_account_fund_flow(
    db: Session,
    account_id: UUID,
    as_of_step: int | None = None,
    max_hops: int = FUND_FLOW_DEFAULT_MAX_HOPS,
    max_branches: int = DEFAULT_MAX_BRANCHES,
) -> FundFlowResponse:
    _require_account(db, account_id)

    result = trace_fund_flow(
        db, account_id, as_of_step=as_of_step, max_hops=max_hops, max_branches=max_branches
    )

    paths = [
        FundFlowPath(
            steps=[
                FundFlowStep(
                    transaction_id=step.transaction_id,
                    transaction_external_ref=step.transaction_external_ref,
                    from_account_id=step.from_account_id,
                    to_account_id=step.to_account_id,
                    amount=step.amount,
                    step=step.step,
                )
                for step in path
            ]
        )
        for path in result.paths
    ]

    return FundFlowResponse(
        source_account_id=account_id,
        as_of_step=as_of_step,
        max_hops=max_hops,
        max_branches=max_branches,
        paths=paths,
        truncated=result.truncated,
        disclaimer=GRAPH_DISCLAIMER,
    )
