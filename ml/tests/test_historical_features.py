import pandas as pd

from ml.data.identifiers import attach_source_row_id
from ml.training.historical_features import compute_historical_features


def test_historical_features_on_hand_constructed_scenario() -> None:
    """Sender C1: two transactions at the *same* step (1), one at step 5,
    one at step 30. RECENT_TXN_WINDOW_STEPS is 24, so the step-30 row's
    "recent" window only reaches back to step 6 — the step-5 transaction
    falls just outside it. Expected values below were computed by hand.
    """
    raw = pd.DataFrame(
        [
            {"nameOrig": "C1", "nameDest": "D1", "amount": 100.0, "step": 1},  # row A
            {"nameOrig": "C1", "nameDest": "D2", "amount": 200.0, "step": 1},  # row B (same step)
            {"nameOrig": "C1", "nameDest": "D1", "amount": 50.0, "step": 5},  # row C
            {"nameOrig": "C1", "nameDest": "D3", "amount": 10.0, "step": 30},  # row D
            {"nameOrig": "C2", "nameDest": "D1", "amount": 999.0, "step": 1},  # unrelated sender
        ]
    )
    df = attach_source_row_id(raw)
    history = compute_historical_features(df)

    row_a, row_b, row_c, row_d, row_e = (history.loc[i] for i in range(5))

    # Row A: C1's very first transaction.
    assert row_a["num_prev_txns_by_sender"] == 0
    assert row_a["historical_avg_amount"] == 0.0
    assert row_a["num_unique_prev_recipients"] == 0
    assert row_a["recent_txn_frequency"] == 0
    assert bool(row_a["sender_is_new"]) is True

    # Row B: same step as A — A must NOT count as prior history.
    assert row_b["num_prev_txns_by_sender"] == 0
    assert bool(row_b["sender_is_new"]) is True

    # Row C (step 5): sees both step-1 rows (A, B).
    assert row_c["num_prev_txns_by_sender"] == 2
    assert row_c["historical_avg_amount"] == 150.0  # (100 + 200) / 2
    assert row_c["num_unique_prev_recipients"] == 2  # D1, D2
    assert row_c["recent_txn_frequency"] == 2  # both within the last 24 steps
    assert bool(row_c["sender_is_new"]) is False

    # Row D (step 30): sees A, B, C — but the "recent" window (step >= 6)
    # excludes all of them (max prior step is 5).
    assert row_d["num_prev_txns_by_sender"] == 3
    assert row_d["historical_avg_amount"] == (100.0 + 200.0 + 50.0) / 3
    assert row_d["num_unique_prev_recipients"] == 2  # D1 (twice), D2
    assert row_d["recent_txn_frequency"] == 0
    assert bool(row_d["sender_is_new"]) is False

    # Row E: a different sender entirely — must be unaffected by C1's history.
    assert row_e["num_prev_txns_by_sender"] == 0
    assert bool(row_e["sender_is_new"]) is True


def test_row_order_in_input_does_not_affect_result() -> None:
    raw = pd.DataFrame(
        [
            {"nameOrig": "C1", "nameDest": "D1", "amount": 100.0, "step": 5},
            {"nameOrig": "C1", "nameDest": "D2", "amount": 200.0, "step": 1},
        ]
    )
    df = attach_source_row_id(raw)
    history = compute_historical_features(df)

    # Row 0 is the step-5 transaction; it must see the step-1 one as history
    # regardless of which order they appeared in the raw input.
    assert history.loc[0, "num_prev_txns_by_sender"] == 1
    assert history.loc[0, "historical_avg_amount"] == 200.0
    # Row 1 is the step-1 transaction; it has no prior history.
    assert history.loc[1, "num_prev_txns_by_sender"] == 0
