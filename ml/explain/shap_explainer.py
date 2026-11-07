"""Training-time SHAP setup: picks the background sample saved alongside
the model artifact, and sanity-checks the explainer actually satisfies
SHAP's additivity property (`base_value + sum(contributions) ≈
predict_proba`) before the artifact is considered valid. This is what
backs the "do not use hardcoded explanations" requirement — if this check
fails, training must fail loudly, not silently ship an artifact whose
explanations don't correspond to its own model.
"""

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from app.ml.explain import build_explainer
from app.ml.features import FEATURE_COLUMNS


def sample_background(x_validation: pd.DataFrame, n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = min(n, len(x_validation))
    idx = rng.choice(x_validation.index, size=n, replace=False)
    return x_validation.loc[idx, FEATURE_COLUMNS].reset_index(drop=True)


def verify_additivity(
    pipeline: Pipeline, background: pd.DataFrame, x_check: pd.DataFrame, atol: float = 1e-3
) -> float:
    """Returns the max absolute additivity error observed over `x_check`
    (a handful of rows is enough — this is a sanity check, not a full
    evaluation). Raises if the error exceeds `atol`.
    """
    explainer, _ = build_explainer(pipeline, background)
    preprocessor = pipeline.named_steps["preprocess"]

    transformed = preprocessor.transform(x_check[FEATURE_COLUMNS])
    shap_values = explainer.shap_values(transformed)
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    shap_values = np.asarray(shap_values)

    predicted = pipeline.predict_proba(x_check[FEATURE_COLUMNS])[:, 1]
    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[-1])
    reconstructed = base_value + shap_values.sum(axis=1)

    max_error = float(np.max(np.abs(reconstructed - predicted)))
    if max_error > atol:
        raise ValueError(
            f"SHAP additivity check failed: max |reconstructed - predicted| = {max_error} > {atol}"
        )
    return max_error
