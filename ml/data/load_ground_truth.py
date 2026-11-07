"""One-time/idempotent offline loader for `ground_truth.transaction_labels`.

Runs under the **admin** DB credential (the same one Alembic migrations use,
`ADMIN_DATABASE_URL` — reuses `ALEMBIC_DATABASE_URL` if the former isn't
set), not `ml_trainer`. `ml_trainer` is granted only `SELECT` on
`ground_truth` (docs/database-design.md §3) — on purpose, so the one role
ever allowed near ground truth still can't *write* it from a routine
training run. Seeding labels is a deliberate, separate, admin-level data
operation, exactly like provisioning the schema itself.

Labels are joined to `app.transactions` by `transaction_external_ref`
(`ml.data.identifiers.external_ref_for_row`), matching the same PaySim row
`ml/data/replay.py` ingests — never a foreign key (see
docs/database-design.md §3).
"""

import argparse
import os

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ml.data.identifiers import SOURCE_ROW_ID_COLUMN, attach_source_row_id, external_ref_for_row
from ml.data.loader import clean_and_validate, read_paysim_csv
from ml.data.synthetic import generate_synthetic_paysim

_LABELS_TABLE = sa.table(
    "transaction_labels",
    sa.column("transaction_external_ref"),
    sa.column("is_fraud"),
    sa.column("is_flagged_fraud"),
    schema="ground_truth",
)


def build_label_rows(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "transaction_external_ref": external_ref_for_row(
                int(getattr(row, SOURCE_ROW_ID_COLUMN))
            ),
            "is_fraud": bool(row.isFraud),
            "is_flagged_fraud": bool(row.isFlaggedFraud),
        }
        for row in df.itertuples()
    ]


def load_ground_truth(rows: list[dict], admin_database_url: str, batch_size: int = 1000) -> int:
    engine = sa.create_engine(admin_database_url)
    try:
        with engine.begin() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                stmt = pg_insert(_LABELS_TABLE).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["transaction_external_ref"],
                    set_={
                        "is_fraud": stmt.excluded.is_fraud,
                        "is_flagged_fraud": stmt.excluded.is_flagged_fraud,
                    },
                )
                conn.execute(stmt)
    finally:
        engine.dispose()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="ml/data/paysim.csv")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    admin_url = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not admin_url:
        raise SystemExit(
            "Set ADMIN_DATABASE_URL (or ALEMBIC_DATABASE_URL) before running this script."
        )

    raw = generate_synthetic_paysim(seed=args.seed) if args.synthetic else read_paysim_csv(args.csv)
    raw = attach_source_row_id(raw)
    source_path = args.csv if not args.synthetic else "<synthetic>"
    cleaned, report = clean_and_validate(raw, source_path=source_path)
    print(f"Loaded {report.n_rows_after_cleaning} rows for ground-truth labeling")

    rows = build_label_rows(cleaned)
    n_loaded = load_ground_truth(rows, admin_url, batch_size=args.batch_size)
    print(f"Upserted {n_loaded} ground_truth.transaction_labels rows")


if __name__ == "__main__":
    main()
