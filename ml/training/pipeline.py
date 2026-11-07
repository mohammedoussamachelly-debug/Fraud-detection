"""Builds the preprocessing + classifier `Pipeline` for each candidate
model. The fitted pipeline (preprocessing included) is exactly what gets
saved to `model.joblib` and loaded by `app/ml/inference.py` — inference
never rebuilds a preprocessor itself, it only ever unpickles the one
training fit.

Transformer names `num`/`cat` are load-bearing: `app/ml/explain.py` parses
`ColumnTransformer.get_feature_names_out()` output (`num__<feature>`,
`cat__<feature>_<category>`) to map one-hot SHAP contributions back to
original feature names.
"""

from dataclasses import dataclass

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from app.ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

RANDOM_SEED = 42


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )


@dataclass
class CandidateModel:
    name: str
    pipeline: Pipeline
    hyperparameters: dict


def build_candidate_models(scale_pos_weight: float) -> list[CandidateModel]:
    """`scale_pos_weight` (negatives/positives ratio in the *training* split
    only) is the sole class-imbalance handling mechanism used here —
    documented in docs/model-evaluation.md rather than resampling the data,
    which would risk subtly interacting with the chronological split.
    """
    dummy_params = {"strategy": "most_frequent"}
    dummy = Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("classify", DummyClassifier(**dummy_params)),
        ]
    )

    logreg_params = {
        "class_weight": "balanced",
        "max_iter": 1000,
        "random_state": RANDOM_SEED,
    }
    logreg = Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("classify", LogisticRegression(**logreg_params)),
        ]
    )

    xgb_params = {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.1,
        "scale_pos_weight": scale_pos_weight,
        "eval_metric": "aucpr",
        "random_state": RANDOM_SEED,
        "n_jobs": -1,  # use all available cores — real PaySim scale (millions of rows)
    }
    xgb = Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("classify", XGBClassifier(**xgb_params)),
        ]
    )

    return [
        CandidateModel("dummy_baseline", dummy, dummy_params),
        CandidateModel("logistic_regression", logreg, logreg_params),
        CandidateModel("xgboost", xgb, xgb_params),
    ]
