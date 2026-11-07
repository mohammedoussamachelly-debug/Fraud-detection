"""The single, shared feature-engineering transformation. Both the offline
training pipeline (`ml/training/`) and the live inference path
(`app/services/risk_scoring.py`) call `engineer_features`/`build_feature_row`
— this is what "identical transformations" (CLAUDE.md, ml-engineer skill)
means in code, not just in intent.

What differs between training and inference is only how the *historical
aggregate* inputs (`num_prev_txns_by_sender`, etc.) are computed: training
computes them in bulk from the full chronological PaySim DataFrame
(`ml/training/historical_features.py`); inference computes the same
aggregates with a single SQL query per request
(`app/services/history.py`), filtered the same way (`step < current_step`).
Both then hand their result to this module, which does the rest identically.

See docs/feature-engineering.md for the full rationale, including the
first-transaction / new-account policy (`sender_is_new`).
"""

import numpy as np
import pandas as pd

NUMERIC_FEATURES: list[str] = [
    "amount",
    "log_amount",
    "hour_of_day",
    "sender_prev_balance",
    "recipient_prev_balance",
    "num_prev_txns_by_sender",
    "historical_avg_amount",
    "num_unique_prev_recipients",
    "recent_txn_frequency",
    "sender_is_new",
]
CATEGORICAL_FEATURES: list[str] = ["transaction_type"]
FEATURE_COLUMNS: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Columns that must never appear anywhere on the path into a feature row.
# Asserted against directly in ml/tests/test_leakage.py.
FORBIDDEN_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {"isFraud", "isFlaggedFraud", "newbalanceOrig", "newbalanceDest"}
)

# "Recent" = within this many steps before the current transaction. PaySim's
# `step` is hours-of-simulation, so 24 steps ~= the trailing day.
RECENT_TXN_WINDOW_STEPS = 24

_RAW_AND_HISTORY_COLUMNS = [
    "amount",
    "transaction_type",
    "step",
    "sender_prev_balance",
    "recipient_prev_balance",
    "num_prev_txns_by_sender",
    "historical_avg_amount",
    "num_unique_prev_recipients",
    "recent_txn_frequency",
    "sender_is_new",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """`df` must already contain `_RAW_AND_HISTORY_COLUMNS` — one row per
    transaction, with historical aggregates already computed by the caller.
    Returns a new DataFrame with exactly `FEATURE_COLUMNS`, in order, ready
    to pass into the fitted sklearn `Pipeline` (preprocessing + classifier)
    saved by training.
    """
    missing = [c for c in _RAW_AND_HISTORY_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"engineer_features: input is missing required columns: {missing}")

    out = pd.DataFrame(index=df.index)
    out["amount"] = df["amount"].astype(float)
    out["log_amount"] = np.log1p(out["amount"])
    out["hour_of_day"] = (df["step"].astype(int) % 24).astype(float)
    out["sender_prev_balance"] = df["sender_prev_balance"].astype(float)
    out["recipient_prev_balance"] = df["recipient_prev_balance"].astype(float)
    out["num_prev_txns_by_sender"] = df["num_prev_txns_by_sender"].astype(float)
    out["historical_avg_amount"] = df["historical_avg_amount"].astype(float)
    out["num_unique_prev_recipients"] = df["num_unique_prev_recipients"].astype(float)
    out["recent_txn_frequency"] = df["recent_txn_frequency"].astype(float)
    out["sender_is_new"] = df["sender_is_new"].astype(float)
    out["transaction_type"] = df["transaction_type"].astype(str)

    assert not any(c in out.columns for c in FORBIDDEN_FEATURE_COLUMNS)
    return out[FEATURE_COLUMNS]


def build_feature_row(raw: dict, history: dict) -> dict:
    """Single-transaction convenience wrapper around `engineer_features`,
    used by inference. Routes through the exact same DataFrame code path
    (a one-row DataFrame) rather than a parallel scalar implementation, so
    there is only ever one transformation to keep in sync.
    """
    combined = {**raw, **history}
    row_df = pd.DataFrame([combined])
    engineered = engineer_features(row_df)
    return engineered.iloc[0].to_dict()


def new_account_history_defaults() -> dict:
    """Deterministic policy for an account's first-ever transaction (as
    sender): zero counts/amounts plus an explicit `sender_is_new` indicator,
    so the model can distinguish "genuinely zero history" from "one prior
    transaction of size zero" rather than silently conflating the two.
    """
    return {
        "num_prev_txns_by_sender": 0,
        "historical_avg_amount": 0.0,
        "num_unique_prev_recipients": 0,
        "recent_txn_frequency": 0,
        "sender_is_new": True,
    }
