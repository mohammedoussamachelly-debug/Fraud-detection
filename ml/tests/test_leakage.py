import pandas as pd
import pytest

from app.ml.features import (
    FEATURE_COLUMNS,
    FORBIDDEN_FEATURE_COLUMNS,
    build_feature_row,
    engineer_features,
    new_account_history_defaults,
)


def _row(**overrides) -> dict:
    row = {
        "amount": 100.0,
        "transaction_type": "TRANSFER",
        "step": 10,
        "sender_prev_balance": 500.0,
        "recipient_prev_balance": 0.0,
        "num_prev_txns_by_sender": 3,
        "historical_avg_amount": 50.0,
        "num_unique_prev_recipients": 2,
        "recent_txn_frequency": 1,
        "sender_is_new": False,
    }
    row.update(overrides)
    return row


def test_feature_columns_never_include_forbidden_columns() -> None:
    assert not (set(FEATURE_COLUMNS) & FORBIDDEN_FEATURE_COLUMNS)


def test_engineer_features_output_is_exactly_feature_columns() -> None:
    df = pd.DataFrame([_row(), _row(step=20)])
    out = engineer_features(df)
    assert list(out.columns) == FEATURE_COLUMNS


def test_engineer_features_ignores_a_smuggled_ground_truth_column() -> None:
    """Even if a caller's DataFrame happens to carry isFraud/newbalanceOrig
    alongside the required columns (e.g. because it came straight from a
    PaySim slice), engineer_features must never surface them."""
    df = pd.DataFrame([_row()])
    df["isFraud"] = 1
    df["newbalanceOrig"] = 999.0
    out = engineer_features(df)
    assert "isFraud" not in out.columns
    assert "newbalanceOrig" not in out.columns


def test_engineer_features_raises_on_missing_required_column() -> None:
    df = pd.DataFrame([_row()]).drop(columns=["amount"])
    with pytest.raises(ValueError):
        engineer_features(df)


def test_log_amount_and_hour_of_day_are_derived_correctly() -> None:
    import numpy as np

    df = pd.DataFrame([_row(amount=999.0, step=50)])
    out = engineer_features(df)
    assert out.loc[0, "log_amount"] == pytest.approx(np.log1p(999.0))
    assert out.loc[0, "hour_of_day"] == 50 % 24


def test_build_feature_row_matches_engineer_features() -> None:
    raw = {
        "amount": 42.0,
        "transaction_type": "CASH_OUT",
        "step": 7,
        "sender_prev_balance": 10.0,
        "recipient_prev_balance": 0.0,
    }
    history = new_account_history_defaults()
    row = build_feature_row(raw, history)

    bulk = engineer_features(pd.DataFrame([{**raw, **history}])).iloc[0].to_dict()
    assert row == bulk


def test_new_account_defaults_mark_sender_is_new() -> None:
    defaults = new_account_history_defaults()
    assert defaults["sender_is_new"] is True
    assert defaults["num_prev_txns_by_sender"] == 0
    assert defaults["historical_avg_amount"] == 0.0
