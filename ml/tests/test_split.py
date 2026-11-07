import pandas as pd
import pytest

from ml.training.split import apply_split, assert_no_boundary_violation, compute_split_boundaries


def _df_with_steps(steps: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"step": steps, "value": range(len(steps))})


def test_boundaries_follow_unique_step_fractions() -> None:
    df = _df_with_steps(list(range(1, 101)))  # 100 unique steps
    boundaries = compute_split_boundaries(df, train_frac=0.70, validation_frac=0.15)
    assert boundaries.train_end_step == 70
    assert boundaries.validation_end_step == 85


def test_apply_split_partitions_without_overlap() -> None:
    df = _df_with_steps(list(range(1, 101)))
    boundaries = compute_split_boundaries(df)
    train, val, test = apply_split(df, boundaries)

    assert len(train) + len(val) + len(test) == len(df)
    assert_no_boundary_violation(train, val, test)  # must not raise


def test_split_handles_repeated_steps_without_crossing_boundary() -> None:
    # Many rows share each step — the split must still respect step
    # boundaries, not accidentally split rows that share a step.
    steps = [s for s in range(1, 21) for _ in range(5)]
    df = _df_with_steps(steps)
    boundaries = compute_split_boundaries(df, train_frac=0.5, validation_frac=0.25)
    train, val, test = apply_split(df, boundaries)

    assert set(train["step"]).isdisjoint(set(val["step"]))
    assert set(val["step"]).isdisjoint(set(test["step"]))
    assert set(train["step"]).isdisjoint(set(test["step"]))
    assert_no_boundary_violation(train, val, test)


def test_boundary_violation_is_detected() -> None:
    train = _df_with_steps([1, 2, 3, 10])  # a row that leaked past the boundary
    val = _df_with_steps([4, 5])
    test = _df_with_steps([6, 7])
    with pytest.raises(AssertionError):
        assert_no_boundary_violation(train, val, test)


def test_too_few_unique_steps_raises() -> None:
    df = _df_with_steps([1, 1, 2])
    with pytest.raises(ValueError):
        compute_split_boundaries(df)


def test_minimal_three_unique_steps_raises_rather_than_collapsing_validation() -> None:
    """At the smallest n that clears the n<3 guard, the default fractions
    (0.70/0.15) would otherwise carve out zero validation steps — caught
    during a leakage-audit review of this module. This must fail loudly,
    not silently hand back an empty validation split."""
    df = _df_with_steps([1, 2, 3])
    with pytest.raises(ValueError):
        compute_split_boundaries(df)


def test_small_n_with_larger_validation_fraction_succeeds() -> None:
    df = _df_with_steps(list(range(1, 11)))  # 10 unique steps
    boundaries = compute_split_boundaries(df, train_frac=0.5, validation_frac=0.3)
    train, val, test = apply_split(df, boundaries)
    assert len(train) and len(val) and len(test)
    assert_no_boundary_violation(train, val, test)


def test_invalid_fractions_raise() -> None:
    df = _df_with_steps(list(range(1, 11)))
    with pytest.raises(ValueError):
        compute_split_boundaries(df, train_frac=0.9, validation_frac=0.2)
