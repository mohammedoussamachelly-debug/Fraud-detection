"""Transaction ingestion: writes `app.accounts`/`app.transactions` only.
Never touches `ground_truth` — this module has no import, connection, or
knowledge of that schema at all (see docs/database-design.md §3).

Idempotent by `external_ref`: re-ingesting the same PaySim row (e.g. a
replay re-run) inserts nothing new and is reported as skipped, not an
error — this lets the replay script be re-run safely.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Transaction
from app.schemas.transaction import TransactionIngestItem, TransactionIngestResponse

# PaySim's `step` has no real calendar date; this is an arbitrary reference
# epoch used only to give `occurred_at` a timestamptz value. `step` (not
# `occurred_at`) remains the actual ordering key everywhere in this system
# — see docs/database-design.md §4.
PAYSIM_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _occurred_at_for_step(step: int) -> datetime:
    return PAYSIM_EPOCH + timedelta(hours=step)


def _account_type_for_external_ref(external_ref: str) -> str:
    """PaySim's own naming convention (`C...` customer, `M...` merchant) —
    not a fraud signal, purely a prefix lookup."""
    return "merchant" if external_ref.startswith("M") else "customer"


def _get_or_create_account(
    db: Session, external_ref: str, first_seen_at: datetime, cache: dict[str, Account]
) -> tuple[Account, bool]:
    if external_ref in cache:
        return cache[external_ref], False

    existing = db.scalar(select(Account).where(Account.external_ref == external_ref))
    if existing is not None:
        cache[external_ref] = existing
        return existing, False

    account = Account(
        external_ref=external_ref,
        account_type=_account_type_for_external_ref(external_ref),
        first_seen_at=first_seen_at,
    )
    db.add(account)
    db.flush()  # need account.id before the transaction row references it
    cache[external_ref] = account
    return account, True


def ingest_transactions(
    db: Session, items: list[TransactionIngestItem]
) -> TransactionIngestResponse:
    account_cache: dict[str, Account] = {}
    accounts_created = 0
    inserted = 0
    skipped_existing = 0

    for item in items:
        if db.scalar(select(Transaction.id).where(Transaction.external_ref == item.external_ref)):
            skipped_existing += 1
            continue

        occurred_at = _occurred_at_for_step(item.step)

        origin, created = _get_or_create_account(
            db, item.origin_external_ref, occurred_at, account_cache
        )
        accounts_created += int(created)
        dest, created = _get_or_create_account(
            db, item.dest_external_ref, occurred_at, account_cache
        )
        accounts_created += int(created)

        db.add(
            Transaction(
                external_ref=item.external_ref,
                step=item.step,
                occurred_at=occurred_at,
                type=item.type,
                amount=item.amount,
                origin_account_id=origin.id,
                dest_account_id=dest.id,
                origin_balance_before=item.origin_balance_before,
                origin_balance_after=item.origin_balance_after,
                dest_balance_before=item.dest_balance_before,
                dest_balance_after=item.dest_balance_after,
            )
        )
        inserted += 1

    db.commit()
    return TransactionIngestResponse(
        received=len(items),
        inserted=inserted,
        skipped_existing=skipped_existing,
        accounts_created=accounts_created,
    )
