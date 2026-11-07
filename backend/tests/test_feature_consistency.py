"""Cross-checks that the two historical-feature computation paths —
`app/services/history.py` (SQL, used by live inference) and
`ml/training/historical_features.py` (bulk pandas, used by training) —
agree on the same scenario. This is the project's "inference consistency"
test: if these ever drift, a model's training-time features would no
longer match what it sees at request time.
"""

import uuid
from datetime import UTC, datetime

import pandas as pd
from ml.data.identifiers import attach_source_row_id
from ml.training.historical_features import compute_historical_features
from sqlalchemy import delete

from app.db.models import Account, Transaction
from app.services.history import get_sender_history


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_sql_and_bulk_pandas_history_agree(db_session) -> None:
    prefix = f"test-consist-{uuid.uuid4().hex[:8]}"
    sender_ref = f"{prefix}-sender"
    dest1_ref, dest2_ref = f"{prefix}-dest1", f"{prefix}-dest2"

    scenario = [
        {"nameOrig": sender_ref, "nameDest": dest1_ref, "amount": 100.0, "step": 1},
        {"nameOrig": sender_ref, "nameDest": dest2_ref, "amount": 200.0, "step": 1},
        {"nameOrig": sender_ref, "nameDest": dest1_ref, "amount": 50.0, "step": 7},
        {"nameOrig": sender_ref, "nameDest": dest2_ref, "amount": 30.0, "step": 20},
    ]

    try:
        accounts = {
            ref: Account(external_ref=ref, account_type="customer", first_seen_at=datetime.now(UTC))
            for ref in {sender_ref, dest1_ref, dest2_ref}
        }
        for account in accounts.values():
            db_session.add(account)
        db_session.flush()

        for i, row in enumerate(scenario):
            db_session.add(
                Transaction(
                    external_ref=f"{prefix}-tx{i}",
                    step=row["step"],
                    occurred_at=datetime.now(UTC),
                    type="TRANSFER",
                    amount=row["amount"],
                    origin_account_id=accounts[row["nameOrig"]].id,
                    dest_account_id=accounts[row["nameDest"]].id,
                    origin_balance_before=1000,
                    origin_balance_after=1000 - row["amount"],
                    dest_balance_before=0,
                    dest_balance_after=row["amount"],
                )
            )
        db_session.commit()

        df = attach_source_row_id(pd.DataFrame(scenario))
        bulk_history = compute_historical_features(df)

        for as_of_step, row_index in [(1, 0), (7, 2), (20, 3)]:
            sql_result = get_sender_history(db_session, sender_ref, as_of_step=as_of_step)
            pandas_result = bulk_history.loc[row_index].to_dict()

            assert sql_result["num_prev_txns_by_sender"] == pandas_result["num_prev_txns_by_sender"]
            assert sql_result["historical_avg_amount"] == pandas_result["historical_avg_amount"]
            assert (
                sql_result["num_unique_prev_recipients"]
                == pandas_result["num_unique_prev_recipients"]
            )
            assert sql_result["recent_txn_frequency"] == pandas_result["recent_txn_frequency"]
            assert bool(sql_result["sender_is_new"]) == bool(pandas_result["sender_is_new"])
    finally:
        _cleanup(db_session, prefix)
