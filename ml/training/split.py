"""Chronological train/validation/test split, strictly by `step` — never a
random/shuffled split. Boundaries are computed over the set of *unique*
step values (not row counts), so the split is insensitive to how many
transactions happen to land in a busy step.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SplitBoundaries:
    train_end_step: int  # inclusive
    validation_end_step: int  # inclusive


def compute_split_boundaries(
    df: pd.DataFrame, train_frac: float = 0.70, validation_frac: float = 0.15
) -> SplitBoundaries:
    if not 0 < train_frac < 1 or not 0 < validation_frac < 1 or train_frac + validation_frac >= 1:
        raise ValueError("train_frac and validation_frac must be in (0, 1) and sum to < 1")

    unique_steps = sorted(df["step"].unique())
    n = len(unique_steps)
    if n < 3:
        raise ValueError("Need at least 3 distinct `step` values to split chronologically")

    train_end_idx = max(int(n * train_frac) - 1, 0)
    validation_end_idx = max(int(n * (train_frac + validation_frac)) - 1, train_end_idx + 1)
    validation_end_idx = min(validation_end_idx, n - 2)  # leave at least one step for test

    if validation_end_idx <= train_end_idx:
        # Clamping to leave room for a non-empty test split (above) can, at
        # very small `n`, undercut the earlier floor that guaranteed a
        # non-empty validation split — e.g. n=3 with the default fractions.
        # Silently proceeding would hand `tune_threshold` an empty
        # validation set rather than fail loudly here.
        raise ValueError(
            f"Cannot carve out a non-empty validation split from {n} unique step values "
            f"with train_frac={train_frac}, validation_frac={validation_frac}; use more data "
            "or larger fractions."
        )

    return SplitBoundaries(
        train_end_step=unique_steps[train_end_idx],
        validation_end_step=unique_steps[validation_end_idx],
    )


def apply_split(
    df: pd.DataFrame, boundaries: SplitBoundaries
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = df[df["step"] <= boundaries.train_end_step]
    validation = df[
        (df["step"] > boundaries.train_end_step) & (df["step"] <= boundaries.validation_end_step)
    ]
    test = df[df["step"] > boundaries.validation_end_step]
    return train, validation, test


def assert_no_boundary_violation(
    train: pd.DataFrame, validation: pd.DataFrame, test: pd.DataFrame
) -> None:
    """Fails loudly if any row crossed a split boundary — the exact
    chronological-integrity check CLAUDE.md requires as an automated test,
    not a manual review.
    """
    if len(train) and len(validation):
        assert train["step"].max() <= validation["step"].min(), "train/validation step overlap"
    if len(validation) and len(test):
        assert validation["step"].max() <= test["step"].min(), "validation/test step overlap"
    if len(train) and len(test):
        assert train["step"].max() <= test["step"].min(), "train/test step overlap"
