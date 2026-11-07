"""Bounded NetworkX subgraph construction from `app.accounts`/`app.transactions`.

Per `docs/architecture.md`'s module-boundary rule, this is the only place in
the backend that turns rows from the database into a transaction graph — API
routes and services never issue their own graph-shaped queries and never
import NetworkX directly.

Every query here is bounded, per the graph-analytics skill's and this
phase's mandatory rules:

- A k-hop neighborhood expands hop-by-hop from a single center account,
  never loading `app.transactions` in bulk.
- Each hop's query is capped at `PER_HOP_QUERY_LIMIT` rows; a hop that would
  exceed it truncates rather than growing unbounded.
- Total nodes/edges added to the graph are capped at `max_nodes`/`max_edges`.
- `as_of_step`, when given, is applied as `step < as_of_step` — never
  `<=` — so a neighborhood "as of" a step never includes that step's own
  transaction or anything later (see `docs/database-design.md` §4). This is
  what keeps the neighborhood/metrics endpoints leakage-safe for
  point-in-time investigation.

When a cap is hit, `GraphBuildResult.truncated` is `True` so callers (and API
responses) can say so explicitly rather than silently presenting a partial
view as complete.
"""

from dataclasses import dataclass
from uuid import UUID

import networkx as nx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction

DEFAULT_HOPS = 2
MAX_HOPS = 4
DEFAULT_MAX_NODES = 300
DEFAULT_MAX_EDGES = 1500
PER_HOP_QUERY_LIMIT = 2000


@dataclass
class GraphBuildResult:
    graph: nx.MultiDiGraph
    truncated: bool


def _add_account_node(graph: nx.MultiDiGraph, account: Account) -> None:
    graph.add_node(account.id, external_ref=account.external_ref, account_type=account.account_type)


def _add_transaction_edge(graph: nx.MultiDiGraph, txn: Transaction) -> None:
    graph.add_edge(
        txn.origin_account_id,
        txn.dest_account_id,
        key=txn.id,
        transaction_id=txn.id,
        external_ref=txn.external_ref,
        amount=txn.amount,
        step=txn.step,
        type=txn.type,
    )


def build_account_neighborhood(
    db: Session,
    center_account_id: UUID,
    hops: int = DEFAULT_HOPS,
    as_of_step: int | None = None,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> GraphBuildResult:
    """BFS outward from `center_account_id` for up to `hops` hops. Returns an
    empty graph (not an error) if the center account doesn't exist — callers
    that need a 404 check for that themselves (see
    `app/services/graph_analytics.py`), since "account exists but has no
    transactions" is a distinct, valid case (an isolated account) from
    "account doesn't exist."
    """
    if not (1 <= hops <= MAX_HOPS):
        raise ValueError(f"hops must be between 1 and {MAX_HOPS}, got {hops}")

    graph: nx.MultiDiGraph = nx.MultiDiGraph()
    center_account = db.get(Account, center_account_id)
    if center_account is None:
        return GraphBuildResult(graph=graph, truncated=False)

    _add_account_node(graph, center_account)
    visited_account_ids: set[UUID] = {center_account_id}
    frontier: set[UUID] = {center_account_id}
    seen_transaction_ids: set[UUID] = set()
    truncated = False

    for _hop in range(hops):
        if not frontier:
            break

        stmt = select(Transaction).where(
            or_(
                Transaction.origin_account_id.in_(frontier),
                Transaction.dest_account_id.in_(frontier),
            )
        )
        if as_of_step is not None:
            stmt = stmt.where(Transaction.step < as_of_step)
        stmt = stmt.order_by(Transaction.step.desc()).limit(PER_HOP_QUERY_LIMIT + 1)

        rows = list(db.scalars(stmt).all())
        if len(rows) > PER_HOP_QUERY_LIMIT:
            truncated = True
            rows = rows[:PER_HOP_QUERY_LIMIT]

        candidate_account_ids = {row.origin_account_id for row in rows} | {
            row.dest_account_id for row in rows
        }
        unknown_account_ids = candidate_account_ids - visited_account_ids

        accounts_by_id: dict[UUID, Account] = {}
        if unknown_account_ids:
            accounts_by_id = {
                account.id: account
                for account in db.scalars(
                    select(Account).where(Account.id.in_(unknown_account_ids))
                ).all()
            }

        newly_added_ids: set[UUID] = set()
        for account_id in unknown_account_ids:
            account = accounts_by_id.get(account_id)
            if account is None:
                continue
            if graph.number_of_nodes() >= max_nodes:
                truncated = True
                break
            _add_account_node(graph, account)
            visited_account_ids.add(account_id)
            newly_added_ids.add(account_id)

        for row in rows:
            if row.id in seen_transaction_ids:
                continue
            if row.origin_account_id not in graph or row.dest_account_id not in graph:
                # One endpoint didn't fit within max_nodes this hop.
                truncated = True
                continue
            if graph.number_of_edges() >= max_edges:
                truncated = True
                break
            _add_transaction_edge(graph, row)
            seen_transaction_ids.add(row.id)

        frontier = newly_added_ids
        if truncated:
            break

    return GraphBuildResult(graph=graph, truncated=truncated)
