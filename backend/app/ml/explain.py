"""Inference-time SHAP explanation: loads the artifact's saved background
sample, builds a `shap.TreeExplainer` against the fitted XGBoost step, and
maps the preprocessed (scaled/one-hot) feature space back to the original
`app/ml/features.FEATURE_COLUMNS` names so the API response is readable.

**SHAP output space** (documented here, not just in prose docs, since this
is exactly the kind of detail that's easy to get subtly wrong): the
explainer is built with `model_output="probability"` and
`feature_perturbation="interventional"`, so `base_value` and each
`shap_contribution` are in **probability units** (0-1), and for a given row:

    base_value + sum(contributions) == model's predicted fraud probability

(up to floating-point rounding). This is why `app/ml/inference.py`'s
`predict_proba` score and this module's contributions are directly
comparable/additive — a caller does not need to apply any further
transformation (e.g. a sigmoid) to interpret them.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from app.ml.features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES


@dataclass
class FeatureContribution:
    feature: str
    value: float | str
    shap_contribution: float
    direction: str  # "increases_risk" | "decreases_risk"


def _feature_group_map(preprocessor) -> dict[str, list[int]]:
    """Maps each original `FEATURE_COLUMNS` name to the list of column
    indices it expands to in the preprocessor's output (1:1 for numeric
    features, 1:many for a one-hot-encoded categorical)."""
    output_names = list(preprocessor.get_feature_names_out())
    groups: dict[str, list[int]] = {name: [] for name in FEATURE_COLUMNS}

    for idx, output_name in enumerate(output_names):
        matched = False
        for cat_feature in CATEGORICAL_FEATURES:
            if output_name == f"cat__{cat_feature}" or output_name.startswith(
                f"cat__{cat_feature}_"
            ):
                groups[cat_feature].append(idx)
                matched = True
                break
        if matched:
            continue
        for num_feature in NUMERIC_FEATURES:
            if output_name == f"num__{num_feature}":
                groups[num_feature].append(idx)
                matched = True
                break
        if not matched:
            raise ValueError(f"Unrecognized preprocessor output column: {output_name}")

    return groups


def build_explainer(
    pipeline: Pipeline, background: pd.DataFrame
) -> tuple[shap.TreeExplainer, np.ndarray]:
    preprocessor = pipeline.named_steps["preprocess"]
    classifier = pipeline.named_steps["classify"]
    background_transformed = preprocessor.transform(background[FEATURE_COLUMNS])

    explainer = shap.TreeExplainer(
        classifier,
        data=background_transformed,
        model_output="probability",
        feature_perturbation="interventional",
    )
    return explainer, background_transformed


def explain_row(
    pipeline: Pipeline,
    explainer: shap.TreeExplainer,
    feature_row: dict,
    top_k: int = 5,
) -> tuple[float, list[FeatureContribution]]:
    """Returns `(base_value, contributions)` for one transaction's already-
    engineered feature row (see `app/ml/features.build_feature_row`),
    sorted by absolute contribution, largest first.
    """
    preprocessor = pipeline.named_steps["preprocess"]
    row_df = pd.DataFrame([feature_row])[FEATURE_COLUMNS]
    transformed = preprocessor.transform(row_df)

    shap_values = explainer.shap_values(transformed)
    if isinstance(shap_values, list):  # some SHAP versions return [class0, class1]
        shap_values = shap_values[1]
    shap_row = np.asarray(shap_values)[0]

    groups = _feature_group_map(preprocessor)
    contributions = []
    for feature in FEATURE_COLUMNS:
        contribution = float(sum(shap_row[idx] for idx in groups[feature]))
        value = feature_row[feature]
        contributions.append(
            FeatureContribution(
                feature=feature,
                value=value,
                shap_contribution=contribution,
                direction="increases_risk" if contribution >= 0 else "decreases_risk",
            )
        )

    contributions.sort(key=lambda c: abs(c.shap_contribution), reverse=True)
    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[-1])
    return base_value, contributions[:top_k]
