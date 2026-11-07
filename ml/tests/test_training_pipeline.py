"""End-to-end smoke test of the real training pipeline (synthetic fixture,
redirected to a tmp_path artifacts dir — never writes into ml/artifacts/).
Not a claim about real-world model performance; see docs/model-card.md for
that. This only asserts the pipeline runs, produces a loadable artifact,
respects chronological integrity, and that SHAP explanations are
mathematically consistent with the model's own predictions.
"""

import json

import joblib
import numpy as np
import pandas as pd
import pytest

from app.ml.explain import build_explainer, explain_row
from app.ml.features import FEATURE_COLUMNS
from ml.training.train import run_training


@pytest.fixture(scope="module")
def trained(tmp_path_factory) -> dict:
    artifacts_dir = tmp_path_factory.mktemp("artifacts")
    result = run_training(
        csv_path="<unused>", synthetic=True, seed=123, artifacts_dir=artifacts_dir
    )
    return {"artifacts_dir": artifacts_dir, **result}


def test_metadata_has_expected_shape(trained: dict) -> None:
    metadata = json.loads(open(trained["metadata_path"]).read())
    assert metadata["served_model"] == "xgboost"
    assert 0.0 < metadata["selected_threshold"] < 1.0
    assert metadata["split"]["train_end_step"] < metadata["split"]["validation_end_step"]
    assert set(metadata["feature_columns"]) == set(FEATURE_COLUMNS)
    assert metadata["shap_additivity_max_error"] < 1e-3
    for model_name in ("dummy_baseline", "logistic_regression", "xgboost"):
        assert model_name in metadata["model_comparison_on_validation_at_threshold_0.5"]


def test_model_artifact_is_loadable_and_predicts(trained: dict) -> None:
    version_dir = trained["artifacts_dir"] / trained["version_label"]
    pipeline = joblib.load(version_dir / "model.joblib")

    row = pd.DataFrame(
        [
            {
                "amount": 1000.0,
                "log_amount": np.log1p(1000.0),
                "hour_of_day": 12.0,
                "sender_prev_balance": 5000.0,
                "recipient_prev_balance": 0.0,
                "num_prev_txns_by_sender": 5,
                "historical_avg_amount": 200.0,
                "num_unique_prev_recipients": 3,
                "recent_txn_frequency": 1,
                "sender_is_new": 0.0,
                "transaction_type": "TRANSFER",
            }
        ]
    )[FEATURE_COLUMNS]

    proba = pipeline.predict_proba(row)[0][1]
    assert 0.0 <= proba <= 1.0


def test_model_predictions_are_deterministic_across_loads(trained: dict) -> None:
    version_dir = trained["artifacts_dir"] / trained["version_label"]
    pipeline_a = joblib.load(version_dir / "model.joblib")
    pipeline_b = joblib.load(version_dir / "model.joblib")

    row = pd.DataFrame(
        [
            {
                "amount": 250.0,
                "log_amount": np.log1p(250.0),
                "hour_of_day": 3.0,
                "sender_prev_balance": 100.0,
                "recipient_prev_balance": 50.0,
                "num_prev_txns_by_sender": 0,
                "historical_avg_amount": 0.0,
                "num_unique_prev_recipients": 0,
                "recent_txn_frequency": 0,
                "sender_is_new": 1.0,
                "transaction_type": "CASH_OUT",
            }
        ]
    )[FEATURE_COLUMNS]

    assert pipeline_a.predict_proba(row)[0][1] == pipeline_b.predict_proba(row)[0][1]


def test_shap_explanation_is_consistent_with_prediction(trained: dict) -> None:
    version_dir = trained["artifacts_dir"] / trained["version_label"]
    pipeline = joblib.load(version_dir / "model.joblib")
    background = joblib.load(version_dir / "shap_background.joblib")

    feature_row = {
        "amount": 5000.0,
        "log_amount": np.log1p(5000.0),
        "hour_of_day": 2.0,
        "sender_prev_balance": 2000.0,
        "recipient_prev_balance": 0.0,
        "num_prev_txns_by_sender": 1,
        "historical_avg_amount": 300.0,
        "num_unique_prev_recipients": 1,
        "recent_txn_frequency": 1,
        "sender_is_new": 0.0,
        "transaction_type": "TRANSFER",
    }

    explainer, _ = build_explainer(pipeline, background)
    base_value, contributions = explain_row(pipeline, explainer, feature_row, top_k=11)

    predicted = pipeline.predict_proba(pd.DataFrame([feature_row])[FEATURE_COLUMNS])[0][1]
    reconstructed = base_value + sum(c.shap_contribution for c in contributions)
    assert reconstructed == pytest.approx(predicted, abs=1e-3)

    # Every contribution must reference a real feature with its real value.
    returned_features = {c.feature for c in contributions}
    assert returned_features == set(FEATURE_COLUMNS)
