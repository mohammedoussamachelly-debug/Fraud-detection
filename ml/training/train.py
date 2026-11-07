"""Main training entry point. Run with (from the repo root):

    PYTHONPATH=backend python -m ml.training.train [--synthetic] [--csv PATH]

Produces `ml/artifacts/<version_label>/{model.joblib, metadata.json,
shap_background.joblib}` and updates `ml/artifacts/active_version.txt` to
point at it. See docs/ml-pipeline.md for the full walkthrough.

Pipeline: load -> clean/validate -> attach historical features (bulk,
chronological) -> engineer features (the same `app/ml/features.py` function
inference uses) -> chronological split -> fit all 3 candidate models on
train -> compare on validation -> tune threshold for XGBoost on validation
-> evaluate XGBoost once on test -> verify SHAP additivity -> save
artifact. XGBoost is always the served model (see docstring in
`ml/training/pipeline.py` / docs/model-card.md for why), with the dummy and
logistic-regression baselines reported for comparison only.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.ml.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    engineer_features,
)
from ml.data.identifiers import attach_source_row_id
from ml.data.loader import clean_and_validate, plot_class_distribution, read_paysim_csv
from ml.data.synthetic import generate_synthetic_paysim
from ml.explain.shap_explainer import sample_background, verify_additivity
from ml.training.evaluate import compute_metrics, measure_inference_latency_ms, tune_threshold
from ml.training.historical_features import compute_historical_features
from ml.training.pipeline import RANDOM_SEED, build_candidate_models
from ml.training.split import apply_split, assert_no_boundary_violation, compute_split_boundaries

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def _json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _prepare_dataset(csv_path: str, synthetic: bool, seed: int):
    raw = generate_synthetic_paysim(seed=seed) if synthetic else read_paysim_csv(csv_path)
    raw = attach_source_row_id(raw)
    cleaned, quality_report = clean_and_validate(
        raw, source_path=csv_path if not synthetic else "<synthetic>"
    )

    history = compute_historical_features(cleaned)
    combined = cleaned.join(history)
    combined = combined.rename(
        columns={
            "type": "transaction_type",
            "oldbalanceOrg": "sender_prev_balance",
            "oldbalanceDest": "recipient_prev_balance",
        }
    )

    dataset_info = {
        "source": "synthetic" if synthetic else "real_paysim",
        "source_path": csv_path if not synthetic else None,
        "n_rows": int(quality_report.n_rows_after_cleaning),
        "fraud_rate": quality_report.fraud_rate,
    }
    return combined, dataset_info, quality_report


def _xy(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    features = engineer_features(df)
    labels = df["isFraud"].to_numpy()
    return features, labels


def run_training(
    csv_path: str, synthetic: bool, seed: int = RANDOM_SEED, artifacts_dir: Path = ARTIFACTS_DIR
) -> dict:
    combined, dataset_info, quality_report = _prepare_dataset(csv_path, synthetic, seed)

    boundaries = compute_split_boundaries(combined)
    train_df, val_df, test_df = apply_split(combined, boundaries)
    assert_no_boundary_violation(train_df, val_df, test_df)

    x_train, y_train = _xy(train_df)
    x_val, y_val = _xy(val_df)
    x_test, y_test = _xy(test_df)

    n_pos = max(int(y_train.sum()), 1)
    n_neg = len(y_train) - n_pos
    scale_pos_weight = n_neg / n_pos

    candidates = build_candidate_models(scale_pos_weight=scale_pos_weight)

    comparison: dict[str, dict] = {}
    fitted = {}
    for candidate in candidates:
        candidate.pipeline.fit(x_train, y_train)
        fitted[candidate.name] = candidate.pipeline
        val_proba = candidate.pipeline.predict_proba(x_val)[:, 1]
        comparison[candidate.name] = compute_metrics(y_val, val_proba, threshold=0.5).to_dict()

    served_name = "xgboost"
    served_pipeline = fitted[served_name]
    served_hyperparameters = next(c.hyperparameters for c in candidates if c.name == served_name)

    val_proba_served = served_pipeline.predict_proba(x_val)[:, 1]
    selected_threshold, validation_metrics_at_threshold = tune_threshold(y_val, val_proba_served)

    test_proba = served_pipeline.predict_proba(x_test)[:, 1]
    test_metrics = compute_metrics(y_test, test_proba, threshold=selected_threshold)

    latency_ms = measure_inference_latency_ms(served_pipeline, x_test)

    background = sample_background(x_val)
    additivity_error = verify_additivity(served_pipeline, background, x_test.head(10))

    version_label = f"xgb-v1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    version_dir = artifacts_dir / version_label
    version_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(served_pipeline, version_dir / "model.joblib")
    joblib.dump(background, version_dir / "shap_background.joblib")

    metadata = {
        "version_label": version_label,
        "trained_at": datetime.now(UTC).isoformat(),
        "random_seed": seed,
        "dataset": dataset_info,
        "split": {
            "train_rows": len(train_df),
            "validation_rows": len(val_df),
            "test_rows": len(test_df),
            "train_end_step": boundaries.train_end_step,
            "validation_end_step": boundaries.validation_end_step,
        },
        "feature_columns": FEATURE_COLUMNS,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "served_model": served_name,
        "served_model_hyperparameters": served_hyperparameters,
        "model_comparison_on_validation_at_threshold_0.5": comparison,
        "selected_threshold": selected_threshold,
        "selected_threshold_rationale": (
            "Threshold maximizing F1 on the validation split only (never test), "
            "swept over 99 candidate thresholds in (0.01, 0.99)."
        ),
        "validation_metrics_at_selected_threshold": validation_metrics_at_threshold.to_dict(),
        "test_metrics": test_metrics.to_dict(),
        "inference_latency_ms_median": latency_ms,
        "shap_additivity_max_error": additivity_error,
    }
    metadata_json = json.dumps(metadata, indent=2, default=_json_default)
    (version_dir / "metadata.json").write_text(metadata_json)

    quality_report.save(version_dir / "data_quality_report.json")
    plot_class_distribution(combined, version_dir / "class_distribution.png")

    (artifacts_dir / "active_version.txt").write_text(version_label)

    return {"version_label": version_label, "metadata_path": str(version_dir / "metadata.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="ml/data/paysim.csv")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    start = time.time()
    result = run_training(args.csv, args.synthetic, args.seed)
    elapsed = time.time() - start
    print(f"Trained {result['version_label']} in {elapsed:.1f}s")
    print(f"Metadata: {result['metadata_path']}")


if __name__ == "__main__":
    main()
