"""Replays a cleaned, chronologically-sorted PaySim DataFrame into the
running backend's `POST /transactions/ingest` in `step` order and in
batches — simulating "transactions arriving over time" per
docs/architecture.md §4.1, without a message queue. Writes only
`app.transactions`/`app.accounts` (via the backend's own `api_service`
role) — this script never touches `ground_truth`; see
`ml/data/load_ground_truth.py` for that side.

Since Phase 6 Part A, `/transactions/ingest` requires the `service`
credential (docs/authentication.md) — pass it via `--service-api-key`
or the `SERVICE_API_KEY` environment variable (never hardcoded here).
"""

import argparse
import os

import httpx
import pandas as pd

from ml.data.identifiers import SOURCE_ROW_ID_COLUMN, attach_source_row_id, external_ref_for_row
from ml.data.loader import clean_and_validate, read_paysim_csv
from ml.data.synthetic import generate_synthetic_paysim


def build_ingest_items(df: pd.DataFrame) -> list[dict]:
    """`df` must already have `SOURCE_ROW_ID_COLUMN` attached and be sorted
    by `step` (both done by `ml.data.loader.clean_and_validate` when given
    a frame `attach_source_row_id` has already run on)."""
    items = []
    for row in df.itertuples():
        items.append(
            {
                "external_ref": external_ref_for_row(int(getattr(row, SOURCE_ROW_ID_COLUMN))),
                "step": int(row.step),
                "type": row.type,
                "amount": float(row.amount),
                "origin_external_ref": row.nameOrig,
                "dest_external_ref": row.nameDest,
                "origin_balance_before": float(row.oldbalanceOrg),
                "origin_balance_after": float(row.newbalanceOrig),
                "dest_balance_before": float(row.oldbalanceDest),
                "dest_balance_after": float(row.newbalanceDest),
            }
        )
    return items


def replay_to_api(
    items: list[dict],
    base_url: str,
    service_api_key: str,
    batch_size: int = 500,
    timeout: float = 30.0,
) -> dict[str, int]:
    totals = {"received": 0, "inserted": 0, "skipped_existing": 0, "accounts_created": 0}
    headers = {"Authorization": f"Bearer {service_api_key}"}
    with httpx.Client(base_url=base_url, timeout=timeout, headers=headers) as client:
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            response = client.post("/transactions/ingest", json={"transactions": batch})
            response.raise_for_status()
            data = response.json()
            for key in totals:
                totals[key] += data[key]
    return totals


def _load_dataframe(args: argparse.Namespace) -> pd.DataFrame:
    if args.synthetic:
        raw = generate_synthetic_paysim(seed=args.seed)
    else:
        raw = read_paysim_csv(args.csv)

    raw = attach_source_row_id(raw)
    source_path = args.csv if not args.synthetic else "<synthetic>"
    cleaned, report = clean_and_validate(raw, source_path=source_path)
    print(
        f"Loaded {report.n_rows_read} rows -> {report.n_rows_after_cleaning} after cleaning "
        f"(fraud_rate={report.fraud_rate:.4%})"
    )
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="ml/data/paysim.csv", help="Path to the raw PaySim CSV")
    parser.add_argument(
        "--synthetic", action="store_true", help="Use a generated synthetic dataset instead"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--base-url", default="http://localhost:8001/api/v1")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--service-api-key",
        default=os.environ.get("SERVICE_API_KEY"),
        help="or set SERVICE_API_KEY in the environment instead",
    )
    args = parser.parse_args()
    if not args.service_api_key:
        parser.error("--service-api-key or SERVICE_API_KEY is required")

    cleaned = _load_dataframe(args)
    items = build_ingest_items(cleaned)
    totals = replay_to_api(
        items, args.base_url, args.service_api_key, batch_size=args.batch_size
    )
    print(f"Replay complete: {totals}")


if __name__ == "__main__":
    main()
