"""Historical feature retrieval for inference: the request-time counterpart
to `ml/training/historical_features.py`'s bulk computation. Both implement
the same aggregate definitions (see app/ml/features.py's docstring); this
module computes them with one SQL query per request, always filtered
`step < as_of_step` — never `<=` — so the transaction being scored can
never see its own effect on its sender's history.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction
from app.ml.features import RECENT_TXN_WINDOW_STEPS, new_account_history_defaults


def get_sender_history(db: Session, sender_external_ref: str, as_of_step: int) -> dict:
    """Returns the `ml.features` history dict for `sender_external_ref` as of
    (strictly before) `as_of_step`. An account with no prior transactions —
    including one never seen in `app.accounts` at all — gets the documented
    new-account defaults, never a fabricated value.
    """
    account = db.scalar(select(Account).where(Account.external_ref == sender_external_ref))
    if account is None:
        return new_account_history_defaults()

    count_and_avg = db.execute(
        select(
            func.count(Transaction.id),
            func.coalesce(func.avg(Transaction.amount), 0),
            func.count(func.distinct(Transaction.dest_account_id)),
        ).where(Transaction.origin_account_id == account.id, Transaction.step < as_of_step)
    ).one()
    n_prev_txns, avg_amount, n_unique_recipients = count_and_avg

    if n_prev_txns == 0:
        return new_account_history_defaults()

    recent_count = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.origin_account_id == account.id,
            Transaction.step < as_of_step,
            Transaction.step >= as_of_step - RECENT_TXN_WINDOW_STEPS,
        )
    )

    return {
        "num_prev_txns_by_sender": int(n_prev_txns),
        "historical_avg_amount": float(avg_amount),
        "num_unique_prev_recipients": int(n_unique_recipients),
        "recent_txn_frequency": int(recent_count or 0),
        "sender_is_new": False,
    }
