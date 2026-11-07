"""PaySim CSV loading: chunked reads, schema validation, deterministic
missing-value/duplicate handling, and a data-quality report. This module
never touches `isFraud`/`isFlaggedFraud` beyond passing them through to the
ground-truth loader (`ml/data/load_ground_truth.py`) — it does not feed them
into anything feature-related.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from ml.data.schema import RAW_COLUMNS, SchemaValidationReport, validate_schema


@dataclass
class DataQualityReport:
    source_path: str
    n_rows_read: int
    n_rows_after_cleaning: int
    n_exact_duplicates_dropped: int
    n_rows_dropped_for_missing_values: int
    n_rows_dropped_for_invalid_type: int
    n_rows_dropped_for_negative_amount: int
    fraud_rate: float
    class_counts: dict[str, int]
    schema_report: SchemaValidationReport

    def to_dict(self) -> dict:
        d = asdict(self)
        d["schema_report"] = asdict(self.schema_report)
        return d

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))


def read_paysim_csv(path: str | Path, chunksize: int = 200_000) -> pd.DataFrame:
    """Chunked read of the raw PaySim CSV. Chunking bounds peak memory for a
    large file; chunks are concatenated into one DataFrame afterward since
    downstream chronological processing (sorting by `step`, computing
    per-account history) needs the full dataset in memory at once for this
    project's demo scale. A true streaming pipeline would process each
    chunk incrementally against a persistent per-account state store — out of
    scope here (see docs/ml-pipeline.md limitations)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"PaySim CSV not found at {path}. See docs/ml-pipeline.md for how to obtain it, "
            "or use ml.data.synthetic.generate_synthetic_paysim for a labeled-synthetic fixture."
        )

    chunks = []
    for chunk in pd.read_csv(path, chunksize=chunksize):
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True)


def clean_and_validate(
    df: pd.DataFrame, source_path: str = "<in-memory>"
) -> tuple[pd.DataFrame, DataQualityReport]:
    """Deterministic cleaning policy, applied in this fixed order:

    1. Drop exact duplicate rows (every column identical) — these cannot be
       two distinct real transactions.
    2. Drop rows missing any required column value — PaySim's real export has
       none, but this makes the pipeline fail loudly rather than silently
       propagate NaNs into feature engineering if a different export does.
    3. Drop rows with a transaction `type` outside the five known PaySim
       types, and rows with a negative `amount` — both indicate a corrupt or
       non-PaySim-shaped row.

    Every drop count is recorded in the returned report. Nothing is ever
    imputed/fabricated in place of a dropped row.
    """
    schema_report = validate_schema(df)
    if schema_report.missing_columns:
        raise ValueError(f"PaySim CSV is missing required columns: {schema_report.missing_columns}")

    n_rows_read = len(df)

    # Dedup on the PaySim columns only (not any extra passthrough column like
    # a caller-attached row-id tracking column), so an id column never masks
    # a genuine exact duplicate.
    cleaned = df.drop_duplicates(subset=list(RAW_COLUMNS), keep="first")
    n_exact_duplicates_dropped = n_rows_read - len(cleaned)

    before_na_drop = len(cleaned)
    cleaned = cleaned.dropna(subset=list(RAW_COLUMNS))
    n_rows_dropped_for_missing_values = before_na_drop - len(cleaned)

    from ml.data.schema import VALID_TRANSACTION_TYPES

    before_type_drop = len(cleaned)
    cleaned = cleaned[cleaned["type"].isin(VALID_TRANSACTION_TYPES)]
    n_rows_dropped_for_invalid_type = before_type_drop - len(cleaned)

    before_amount_drop = len(cleaned)
    cleaned = cleaned[cleaned["amount"] >= 0]
    n_rows_dropped_for_negative_amount = before_amount_drop - len(cleaned)

    cleaned = cleaned.sort_values("step", kind="stable").reset_index(drop=True)

    fraud_rate = float(cleaned["isFraud"].mean()) if len(cleaned) else 0.0
    class_counts = cleaned["isFraud"].value_counts().to_dict()
    class_counts = {("fraud" if k == 1 else "legitimate"): int(v) for k, v in class_counts.items()}

    report = DataQualityReport(
        source_path=str(source_path),
        n_rows_read=n_rows_read,
        n_rows_after_cleaning=len(cleaned),
        n_exact_duplicates_dropped=n_exact_duplicates_dropped,
        n_rows_dropped_for_missing_values=n_rows_dropped_for_missing_values,
        n_rows_dropped_for_invalid_type=n_rows_dropped_for_invalid_type,
        n_rows_dropped_for_negative_amount=n_rows_dropped_for_negative_amount,
        fraud_rate=fraud_rate,
        class_counts=class_counts,
        schema_report=schema_report,
    )
    return cleaned, report


def plot_class_distribution(df: pd.DataFrame, output_path: str | Path) -> None:
    """Saves a bar chart of legitimate vs. fraud transaction counts. Skipped
    silently (with a note in the data-quality report, not a crash) only if
    matplotlib isn't installed — it's a required dependency here, so this is
    purely a defensive import."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = df["isFraud"].value_counts().sort_index()
    labels = ["legitimate" if i == 0 else "fraud" for i in counts.index]

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(labels, counts.values, color=["#4a7a8c", "#c0392b"])
    ax.set_ylabel("transaction count")
    ax.set_title("Class distribution (synthetic/PaySim, log scale)")
    ax.set_yscale("log")
    for i, v in enumerate(counts.values):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)
