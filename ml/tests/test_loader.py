import pandas as pd
import pytest

from ml.data.loader import clean_and_validate, read_paysim_csv


def _row(**overrides) -> dict:
    row = {
        "step": 1,
        "type": "TRANSFER",
        "amount": 100.0,
        "nameOrig": "C1",
        "oldbalanceOrg": 500.0,
        "newbalanceOrig": 400.0,
        "nameDest": "C2",
        "oldbalanceDest": 0.0,
        "newbalanceDest": 100.0,
        "isFraud": 0,
        "isFlaggedFraud": 0,
    }
    row.update(overrides)
    return row


def test_exact_duplicates_are_dropped() -> None:
    df = pd.DataFrame([_row(), _row()])
    cleaned, report = clean_and_validate(df)
    assert len(cleaned) == 1
    assert report.n_exact_duplicates_dropped == 1


def test_rows_with_missing_required_values_are_dropped() -> None:
    df = pd.DataFrame([_row(), _row(amount=None, step=2)])
    cleaned, report = clean_and_validate(df)
    assert len(cleaned) == 1
    assert report.n_rows_dropped_for_missing_values == 1


def test_invalid_type_and_negative_amount_rows_are_dropped() -> None:
    df = pd.DataFrame(
        [_row(), _row(type="BOGUS", step=2), _row(amount=-5.0, step=3)]
    )
    cleaned, report = clean_and_validate(df)
    assert len(cleaned) == 1
    assert report.n_rows_dropped_for_invalid_type == 1
    assert report.n_rows_dropped_for_negative_amount == 1


def test_missing_required_column_raises() -> None:
    df = pd.DataFrame([_row()]).drop(columns=["isFraud"])
    with pytest.raises(ValueError):
        clean_and_validate(df)


def test_output_sorted_by_step() -> None:
    df = pd.DataFrame([_row(step=3), _row(step=1), _row(step=2)])
    cleaned, _ = clean_and_validate(df)
    assert list(cleaned["step"]) == [1, 2, 3]


def test_fraud_rate_and_class_counts_reported() -> None:
    df = pd.DataFrame([_row(isFraud=1, step=1), _row(isFraud=0, step=2)])
    _, report = clean_and_validate(df)
    assert report.fraud_rate == 0.5
    assert report.class_counts == {"fraud": 1, "legitimate": 1}


def test_read_paysim_csv_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        read_paysim_csv("/nonexistent/path/does-not-exist.csv")


def test_read_paysim_csv_chunked(tmp_path) -> None:
    df = pd.DataFrame([_row(step=i) for i in range(1, 11)])
    csv_path = tmp_path / "paysim.csv"
    df.to_csv(csv_path, index=False)

    read_back = read_paysim_csv(csv_path, chunksize=3)
    assert len(read_back) == 10
    assert list(read_back["step"]) == list(range(1, 11))


def test_extra_passthrough_column_does_not_mask_duplicates() -> None:
    """An id column (e.g. source_row_id) attached before cleaning must not
    make every row look unique to drop_duplicates."""
    df = pd.DataFrame([_row(), _row()])
    df["source_row_id"] = [0, 1]  # unique per row, but rows are otherwise identical
    cleaned, report = clean_and_validate(df)
    assert len(cleaned) == 1
    assert report.n_exact_duplicates_dropped == 1
