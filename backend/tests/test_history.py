"""Integration tests for app/services/history.py against a real DB."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from app.db.models import Account, Transaction
from app.services.history import get_sender_history


def _seed_account(db_session, external_ref: str) -> Account:
    account = Account(
        external_ref=external_ref,
        account_type="customer",
        first_seen_at=datetime.now(UTC),
    )
    db_session.add(account)
    db_session.flush()
    return account


def _seed_transaction(
    db_session, external_ref: str, origin: Account, dest: Account, step: int, amount: float
) -> Transaction:
    txn = Transaction(
        external_ref=external_ref,
        step=step,
        occurred_at=datetime.now(UTC),
        type="TRANSFER",
        amount=amount,
        origin_account_id=origin.id,
        dest_account_id=dest.id,
        origin_balance_before=1000,
        origin_balance_after=1000 - amount,
        dest_balance_before=0,
        dest_balance_after=amount,
    )
    db_session.add(txn)
    return txn


def _cleanup(db_session, prefix: str) -> None:
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_unknown_account_gets_new_account_defaults(db_session) -> None:
    history = get_sender_history(db_session, "no-such-account-ever", as_of_step=100)
    assert history == {
        "num_prev_txns_by_sender": 0,
        "historical_avg_amount": 0.0,
        "num_unique_prev_recipients": 0,
        "recent_txn_frequency": 0,
        "sender_is_new": True,
    }


def test_history_respects_strict_step_boundary(db_session) -> None:
    prefix = f"test-hist-{uuid.uuid4().hex[:8]}"
    try:
        sender = _seed_account(db_session, f"{prefix}-sender")
        dest1 = _seed_account(db_session, f"{prefix}-dest1")
        dest2 = _seed_account(db_session, f"{prefix}-dest2")
        _seed_transaction(db_session, f"{prefix}-tx1", sender, dest1, step=5, amount=100)
        # tx2 is at the same step as tx1 — same-step rows must not see each other.
        _seed_transaction(db_session, f"{prefix}-tx2", sender, dest2, step=5, amount=200)
        _seed_transaction(db_session, f"{prefix}-tx3", sender, dest1, step=10, amount=50)
        db_session.commit()

        # As of step 10 (the tx3 row's own step): only the two step-5 rows
        # qualify — tx3 must never see itself.
        history = get_sender_history(db_session, f"{prefix}-sender", as_of_step=10)
        assert history["num_prev_txns_by_sender"] == 2
        assert history["historical_avg_amount"] == 150.0
        assert history["num_unique_prev_recipients"] == 2
        assert history["sender_is_new"] is False

        # As of step 5 (same step as tx1/tx2): nothing qualifies yet.
        history_at_5 = get_sender_history(db_session, f"{prefix}-sender", as_of_step=5)
        assert history_at_5["num_prev_txns_by_sender"] == 0
        assert history_at_5["sender_is_new"] is True
    finally:
        _cleanup(db_session, prefix)


def test_recent_txn_frequency_window(db_session) -> None:
    prefix = f"test-hist-{uuid.uuid4().hex[:8]}"
    try:
        sender = _seed_account(db_session, f"{prefix}-sender")
        dest = _seed_account(db_session, f"{prefix}-dest")
        _seed_transaction(db_session, f"{prefix}-tx1", sender, dest, step=1, amount=10)
        _seed_transaction(db_session, f"{prefix}-tx2", sender, dest, step=5, amount=20)
        db_session.commit()

        # Window is 24 steps; as of step 30, step 1 and step 5 are both
        # outside [30-24, 30) = [6, 30).
        history = get_sender_history(db_session, f"{prefix}-sender", as_of_step=30)
        assert history["num_prev_txns_by_sender"] == 2
        assert history["recent_txn_frequency"] == 0

        # As of step 10, both are within [10-24, 10) = [-14, 10).
        history_at_10 = get_sender_history(db_session, f"{prefix}-sender", as_of_step=10)
        assert history_at_10["recent_txn_frequency"] == 2
    finally:
        _cleanup(db_session, prefix)
