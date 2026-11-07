from ml.data.schema import RAW_COLUMNS, validate_schema
from ml.data.synthetic import generate_synthetic_paysim


def test_generated_dataset_matches_schema() -> None:
    df = generate_synthetic_paysim(n_customers=5, n_merchants=2, n_steps=10, txns_per_step=3)
    report = validate_schema(df)
    assert report.is_valid
    assert set(df.columns) == set(RAW_COLUMNS)


def test_generation_is_deterministic_given_same_seed() -> None:
    df1 = generate_synthetic_paysim(seed=7, n_steps=20)
    df2 = generate_synthetic_paysim(seed=7, n_steps=20)
    assert df1.equals(df2)


def test_different_seeds_produce_different_data() -> None:
    df1 = generate_synthetic_paysim(seed=1, n_steps=20)
    df2 = generate_synthetic_paysim(seed=2, n_steps=20)
    assert not df1.equals(df2)


def test_both_classes_present_with_default_fraud_rate() -> None:
    df = generate_synthetic_paysim(n_steps=200, txns_per_step=10, fraud_rate=0.05)
    assert df["isFraud"].sum() > 0
    assert (df["isFraud"] == 0).sum() > 0


def test_amounts_are_non_negative() -> None:
    df = generate_synthetic_paysim(n_steps=50)
    assert (df["amount"] >= 0).all()
