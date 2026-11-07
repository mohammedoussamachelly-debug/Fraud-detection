"""Time-aware fund-flow tracing: follows onward transfers strictly forward in
simulated time (`step` strictly increasing along the path) to surface
rapid pass-through / mule-chain patterns — money arriving then leaving again
shortly after. Like the rest of `app.graph`, this is a structural trace only
(see `app.graph.metrics.GRAPH_DISCLAIMER`), and every query is bounded.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transaction

DEFAULT_MAX_HOPS = 3
MAX_HOPS = 5
DEFAULT_MAX_BRANCHES = 3
MAX_BRANCHES = 10

# Hard cap on total DB queries issued by one trace_fund_flow call, regardless
# of hops/branches requested — bounds worst-case query volume (max_hops=5,
# max_branches=10 would otherwise branch combinatorially) per this phase's
# "limit query size and traversal depth" requirement.
MAX_TOTAL_EXPANSIONS = 500


@dataclass
class FlowStep:
    transaction_id: UUID
    transaction_external_ref: str
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal
    step: int


@dataclass
class FundFlowResult:
    paths: list[list[FlowStep]] = field(default_factory=list)
    truncated: bool = False


def trace_fund_flow(
    db: Session,
    source_account_id: UUID,
    as_of_step: int | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    max_branches: int = DEFAULT_MAX_BRANCHES,
) -> FundFlowResult:
    """Walks forward from `source_account_id`'s outgoing transactions. At
    each step, only transactions strictly later (`step >` the incoming
    edge's step) than the one that funded the current account are followed,
    so a path never "moves backward in time." `as_of_step`, when given,
    bounds the whole trace the same way as the neighborhood builder: no
    transaction with `step >= as_of_step` is ever visited.

    Branching is capped at `max_branches` per account per hop, and the
    overall walk is capped at `MAX_TOTAL_EXPANSIONS` database queries; once
    hit, `truncated=True` is set on the result rather than continuing
    unbounded.
    """
    if not (1 <= max_hops <= MAX_HOPS):
        raise ValueError(f"max_hops must be between 1 and {MAX_HOPS}, got {max_hops}")
    if not (1 <= max_branches <= MAX_BRANCHES):
        raise ValueError(f"max_branches must be between 1 and {MAX_BRANCHES}, got {max_branches}")

    result = FundFlowResult()
    expansions = 0

    def _extend(current_account_id: UUID, min_step: int, path: list[FlowStep]) -> None:
        nonlocal expansions

        if len(path) >= max_hops:
            result.paths.append(list(path))
            return
        if expansions >= MAX_TOTAL_EXPANSIONS:
            result.truncated = True
            result.paths.append(list(path))
            return

        stmt = select(Transaction).where(
            Transaction.origin_account_id == current_account_id,
            Transaction.step > min_step,
        )
        if as_of_step is not None:
            stmt = stmt.where(Transaction.step < as_of_step)
        stmt = stmt.order_by(Transaction.step.asc()).limit(max_branches)

        rows = list(db.scalars(stmt).all())
        expansions += 1

        if not rows:
            result.paths.append(list(path))
            return

        for row in rows:
            next_step = FlowStep(
                transaction_id=row.id,
                transaction_external_ref=row.external_ref,
                from_account_id=row.origin_account_id,
                to_account_id=row.dest_account_id,
                amount=row.amount,
                step=row.step,
            )
            _extend(row.dest_account_id, row.step, [*path, next_step])

    _extend(source_account_id, min_step=-1, path=[])
    return result
