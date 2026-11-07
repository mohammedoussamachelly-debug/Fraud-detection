import pandas as pd

from ml.data.schema import RAW_COLUMNS, validate_schema


def _valid_row() -> dict:
    return {
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


def test_valid_dataframe_passes() -> None:
    df = pd.DataFrame([_valid_row(), _valid_row()])
    report = validate_schema(df)
    assert report.is_valid
    assert report.n_rows == 2


def test_missing_column_detected() -> None:
    df = pd.DataFrame([_valid_row()]).drop(columns=["amount"])
    report = validate_schema(df)
    assert "amount" in report.missing_columns
    assert not report.is_valid


def test_invalid_transaction_type_detected() -> None:
    row = _valid_row()
    row["type"] = "NOT_A_REAL_TYPE"
    df = pd.DataFrame([row])
    report = validate_schema(df)
    assert report.n_invalid_transaction_type == 1
    assert not report.is_valid


def test_negative_amount_detected() -> None:
    row = _valid_row()
    row["amount"] = -50.0
    df = pd.DataFrame([row])
    report = validate_schema(df)
    assert report.n_negative_amount == 1
    assert not report.is_valid


def test_missing_values_counted() -> None:
    row = _valid_row()
    row["amount"] = None
    df = pd.DataFrame([row, _valid_row()])
    report = validate_schema(df)
    assert report.n_missing_values_by_column.get("amount") == 1


def test_all_raw_columns_present_in_fixture() -> None:
    assert set(_valid_row().keys()) == set(RAW_COLUMNS)
