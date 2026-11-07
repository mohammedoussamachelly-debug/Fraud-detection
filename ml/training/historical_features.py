"""Bulk, chronologically-correct computation of the historical aggregates
`app/ml/features.py` needs (`num_prev_txns_by_sender`, etc.) across an
entire PaySim-shaped DataFrame. This is training's side of the "identical
transformations" requirement — `app/services/history.py` computes the same
aggregates one request at a time via SQL; both must agree on the exact
definition, verified by `ml/tests/test_feature_consistency.py`.

**Chronological-ordering assumption** (documented once, applies everywhere):
multiple rows can share the same `step` (PaySim's `step` is an hour-wide
bucket). There is no reliable sub-step ordering in the source data, so rows
sharing a step are treated as simultaneous — a row's history includes only
rows with a *strictly earlier* step, never same-step rows, regardless of
their position in the CSV. This is what prevents row-order artifacts from
leaking information.

**Why this is fully vectorized, not a per-sender Python loop**: real PaySim
has ~6.35M unique senders for ~6.36M transactions (most senders transact
exactly once). An earlier version of this function iterated
`for _, group in df.groupby("nameOrig"): ...`, building one small DataFrame
per sender — fine at the small scale of `ml/tests` fixtures, but at real
PaySim's cardinality it allocates millions of Python-level DataFrame
objects, which drove memory past 28GB and was killed before finishing (see
the incident note in docs/ml-pipeline.md §6). Every step below instead
uses pandas' C-level grouped operations (`groupby(...).cumsum()`,
`merge`, `merge_asof(..., by=...)`), which scale to millions of groups
without per-group Python overhead.
"""

import numpy as np
import pandas as pd

from app.ml.features import RECENT_TXN_WINDOW_STEPS
from ml.data.identifiers import SOURCE_ROW_ID_COLUMN


def compute_historical_features(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must have `nameOrig`, `nameDest`, `amount`, `step`, and
    `SOURCE_ROW_ID_COLUMN` (see `ml.data.identifiers`). Returns a DataFrame
    aligned to `df.index` with exactly the history columns
    `app/ml/features.py` expects — ready to concatenate with the raw columns
    before calling `engineer_features`.
    """
    required = {"nameOrig", "nameDest", "amount", "step", SOURCE_ROW_ID_COLUMN}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_historical_features: missing columns {missing}")

    # --- Per-(sender, step) block aggregates -----------------------------
    # Every row sharing a (nameOrig, step) pair gets identical history —
    # they're simultaneous by the assumption above — so all per-row work
    # below is actually done once per block, then broadcast back to rows.
    block = (
        df.groupby(["nameOrig", "step"], sort=False, as_index=False)
        .agg(block_count=("amount", "size"), block_sum=("amount", "sum"))
        .sort_values(["nameOrig", "step"], kind="stable")
        .reset_index(drop=True)
    )

    by_sender = block.groupby("nameOrig", sort=False)
    block["cum_count_incl"] = by_sender["block_count"].cumsum()
    block["cum_sum_incl"] = by_sender["block_sum"].cumsum()
    block["cum_count_before"] = block["cum_count_incl"] - block["block_count"]
    block["cum_sum_before"] = block["cum_sum_incl"] - block["block_sum"]

    # --- Unique recipients, via each (sender, recipient) pair's first use ---
    # A recipient only ever newly contributes to "unique recipients" at the
    # step of the sender's *first* transaction with them.
    first_use = (
        df.groupby(["nameOrig", "nameDest"], sort=False)["step"].min().reset_index(name="step")
    )
    new_recipients_per_block = (
        first_use.groupby(["nameOrig", "step"], sort=False)
        .size()
        .reset_index(name="new_recipients_count")
    )
    block = block.merge(new_recipients_per_block, on=["nameOrig", "step"], how="left")
    block["new_recipients_count"] = block["new_recipients_count"].fillna(0).astype(np.int64)
    block = block.sort_values(["nameOrig", "step"], kind="stable").reset_index(drop=True)

    by_sender = block.groupby("nameOrig", sort=False)  # order changed above; regroup
    block["cum_unique_recipients_incl"] = by_sender["new_recipients_count"].cumsum()
    block["cum_unique_recipients_before"] = (
        block["cum_unique_recipients_incl"] - block["new_recipients_count"]
    )

    # --- Recent-window count, via an as-of lookup per sender -------------
    # recent_txn_frequency(step) = (count strictly before `step`)
    #                             - (count strictly before `step - WINDOW`)
    # The first term is `cum_count_before` above. The second term is looked
    # up by finding, per sender, the latest block at or before
    # `step - WINDOW - 1` and taking its *inclusive* cumulative count — a
    # grouped as-of search (`merge_asof(..., by="nameOrig")`), vectorized
    # in pandas rather than a Python loop per sender. `merge_asof` requires
    # global ascending order on `on` ("step"); `by` is applied as an
    # equality filter during the search, not as a sort key, so sorting by
    # `step` alone (not `(nameOrig, step)`) is correct here.
    lookup = block[["nameOrig", "step"]].copy()
    lookup["asof_step"] = lookup["step"] - RECENT_TXN_WINDOW_STEPS - 1
    lookup = lookup.sort_values("asof_step", kind="stable").reset_index(drop=True)

    asof_source = block[["nameOrig", "step", "cum_count_incl"]].sort_values(
        "step", kind="stable"
    )
    matched = pd.merge_asof(
        lookup,
        asof_source,
        left_on="asof_step",
        right_on="step",
        by="nameOrig",
        direction="backward",
        suffixes=("", "_asof"),
    )
    matched["cum_count_incl"] = matched["cum_count_incl"].fillna(0).astype(np.int64)
    matched = matched.set_index(["nameOrig", "step"])["cum_count_incl"]

    block = block.set_index(["nameOrig", "step"])
    block["count_before_window"] = matched
    block["recent_txn_frequency"] = block["cum_count_before"] - block["count_before_window"]
    block = block.reset_index()

    # --- Assemble, then broadcast block-level results back to every row --
    block["historical_avg_amount"] = np.divide(
        block["cum_sum_before"],
        block["cum_count_before"],
        out=np.zeros(len(block), dtype="float64"),
        where=block["cum_count_before"] > 0,
    )
    block["sender_is_new"] = block["cum_count_before"] == 0

    history_by_block = block.set_index(["nameOrig", "step"])[
        [
            "cum_count_before",
            "historical_avg_amount",
            "cum_unique_recipients_before",
            "recent_txn_frequency",
            "sender_is_new",
        ]
    ].rename(
        columns={
            "cum_count_before": "num_prev_txns_by_sender",
            "cum_unique_recipients_before": "num_unique_prev_recipients",
        }
    )

    result = df[["nameOrig", "step"]].join(history_by_block, on=["nameOrig", "step"])
    result = result.drop(columns=["nameOrig", "step"])
    result["num_prev_txns_by_sender"] = result["num_prev_txns_by_sender"].astype(np.int64)
    result["num_unique_prev_recipients"] = result["num_unique_prev_recipients"].astype(np.int64)
    result["recent_txn_frequency"] = result["recent_txn_frequency"].astype(np.int64)
    return result
