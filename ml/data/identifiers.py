"""The single place that defines how a PaySim CSV row maps to a stable
transaction identifier. Both the replay/ingestion path (writes
`app.transactions.external_ref`) and the ground-truth loader (writes
`ground_truth.transaction_labels.transaction_external_ref`) import this, so
the two schemas join correctly on a value both sides compute the same way.

PaySim has no native per-row transaction id, so the id is derived from the
row's position in the *raw, as-read* CSV (`source_row_id`), attached
immediately after reading and before any cleaning/sorting — cleaning only
ever drops rows, never reorders the surviving ones' `source_row_id` values.
"""

import pandas as pd

SOURCE_ROW_ID_COLUMN = "source_row_id"


def attach_source_row_id(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[SOURCE_ROW_ID_COLUMN] = df.index.astype("int64")
    return df


def external_ref_for_row(source_row_id: int) -> str:
    return f"paysim-{source_row_id}"
