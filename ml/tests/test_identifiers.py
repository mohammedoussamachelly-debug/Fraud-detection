import pandas as pd

from ml.data.identifiers import SOURCE_ROW_ID_COLUMN, attach_source_row_id, external_ref_for_row


def test_attach_source_row_id_is_positional_and_unique() -> None:
    df = pd.DataFrame({"x": ["a", "b", "c"]})
    out = attach_source_row_id(df)
    assert list(out[SOURCE_ROW_ID_COLUMN]) == [0, 1, 2]


def test_attach_source_row_id_survives_filtering() -> None:
    """Dropping rows must not renumber the survivors' ids — the id has to
    stay stable for the ground-truth join to work after cleaning drops some
    rows."""
    df = pd.DataFrame({"x": ["a", "b", "c", "d"]})
    out = attach_source_row_id(df)
    filtered = out[out["x"].isin(["b", "d"])]
    assert list(filtered[SOURCE_ROW_ID_COLUMN]) == [1, 3]


def test_external_ref_is_stable_and_distinct() -> None:
    assert external_ref_for_row(0) == external_ref_for_row(0)
    assert external_ref_for_row(0) != external_ref_for_row(1)
    assert external_ref_for_row(42) == "paysim-42"
