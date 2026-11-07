"""PaySim raw-CSV schema: the only place that knows the original PaySim column
names. Everything downstream (loader, feature engineering) works off the
validated DataFrame this module produces, never off raw column names directly.

PaySim columns (unchanged from the public dataset):
    step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
    nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud
"""

from dataclasses import dataclass, field

import pandas as pd

RAW_COLUMNS: dict[str, str] = {
    "step": "int64",
    "type": "object",
    "amount": "float64",
    "nameOrig": "object",
    "oldbalanceOrg": "float64",
    "newbalanceOrig": "float64",
    "nameDest": "object",
    "oldbalanceDest": "float64",
    "newbalanceDest": "float64",
    "isFraud": "int64",
    "isFlaggedFraud": "int64",
}

# Ground-truth / post-event columns a loader must never forward into the
# feature-engineering path. `isFraud`/`isFlaggedFraud` go only to
# ground_truth.transaction_labels; `newbalanceOrig`/`newbalanceDest` are
# post-transaction and are used only to compute the *next* transaction's
# pre-transaction balance, never as a feature of the transaction that
# produced them.
GROUND_TRUTH_COLUMNS = ("isFraud", "isFlaggedFraud")
POST_EVENT_COLUMNS = ("newbalanceOrig", "newbalanceDest")

VALID_TRANSACTION_TYPES = frozenset({"CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"})


@dataclass
class SchemaValidationReport:
    n_rows: int
    missing_columns: list[str] = field(default_factory=list)
    unexpected_dtypes: dict[str, str] = field(default_factory=dict)
    n_missing_values_by_column: dict[str, int] = field(default_factory=dict)
    n_exact_duplicate_rows: int = 0
    n_invalid_transaction_type: int = 0
    n_negative_amount: int = 0

    @property
    def is_valid(self) -> bool:
        return (
            not self.missing_columns
            and not self.unexpected_dtypes
            and self.n_invalid_transaction_type == 0
            and self.n_negative_amount == 0
        )


def validate_schema(df: pd.DataFrame) -> SchemaValidationReport:
    """Structural validation only — does not mutate `df`. Callers decide how
    to handle missing values/duplicates (see `ml/data/loader.py`)."""
    report = SchemaValidationReport(n_rows=len(df))

    report.missing_columns = [c for c in RAW_COLUMNS if c not in df.columns]
    if report.missing_columns:
        # Can't check dtypes/values on columns that don't exist.
        return report

    for column, expected_dtype in RAW_COLUMNS.items():
        actual_kind = df[column].dtype.kind
        expected_kind = pd.Series(dtype=expected_dtype).dtype.kind
        if actual_kind != expected_kind and not (actual_kind in "if" and expected_kind in "if"):
            report.unexpected_dtypes[column] = str(df[column].dtype)

    for column in RAW_COLUMNS:
        n_missing = int(df[column].isna().sum())
        if n_missing:
            report.n_missing_values_by_column[column] = n_missing

    report.n_exact_duplicate_rows = int(df.duplicated(keep="first").sum())
    report.n_invalid_transaction_type = int((~df["type"].isin(VALID_TRANSACTION_TYPES)).sum())
    report.n_negative_amount = int((df["amount"] < 0).sum())

    return report
