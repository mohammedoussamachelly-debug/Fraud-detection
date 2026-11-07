"""Loads the frozen model artifact produced by `ml/training/train.py` and
scores transactions. Never trains, never touches `ground_truth`, never
reuses the `ml_trainer` DB role — see docs/architecture.md §5.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from app.ml.explain import FeatureContribution, build_explainer, explain_row
from app.ml.features import FEATURE_COLUMNS


class ModelArtifactUnavailable(RuntimeError):
    """Raised when no active model artifact is configured/loadable. Routes
    catch this and return 503, never a fabricated score."""


@dataclass
class ModelArtifact:
    version_label: str
    pipeline: Pipeline
    metadata: dict
    background: pd.DataFrame
    explainer: shap.TreeExplainer

    @property
    def threshold(self) -> float:
        return float(self.metadata["selected_threshold"])


_CACHE: dict[str, ModelArtifact] = {}


def _resolve_active_version(artifacts_dir: Path) -> str:
    pointer = artifacts_dir / "active_version.txt"
    if not pointer.exists():
        raise ModelArtifactUnavailable(f"No active_version.txt in {artifacts_dir}")
    return pointer.read_text().strip()


def load_active_artifact(artifacts_dir: str | Path) -> ModelArtifact:
    artifacts_dir = Path(artifacts_dir)
    cache_key = str(artifacts_dir.resolve())
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    version_label = _resolve_active_version(artifacts_dir)
    version_dir = artifacts_dir / version_label
    model_path = version_dir / "model.joblib"
    metadata_path = version_dir / "metadata.json"
    background_path = version_dir / "shap_background.joblib"

    for path in (model_path, metadata_path, background_path):
        if not path.exists():
            raise ModelArtifactUnavailable(f"Missing artifact file: {path}")

    pipeline = joblib.load(model_path)
    metadata = json.loads(metadata_path.read_text())
    background = joblib.load(background_path)
    explainer, _ = build_explainer(pipeline, background)

    artifact = ModelArtifact(
        version_label=version_label,
        pipeline=pipeline,
        metadata=metadata,
        background=background,
        explainer=explainer,
    )
    _CACHE[cache_key] = artifact
    return artifact


def clear_cache() -> None:
    """Used by tests so each test can point at its own fixture artifacts
    directory without leaking a previously loaded model across tests."""
    _CACHE.clear()


def predict_proba(artifact: ModelArtifact, feature_row: dict) -> float:
    row_df = pd.DataFrame([feature_row])[FEATURE_COLUMNS]
    proba = artifact.pipeline.predict_proba(row_df)[0][1]
    return float(proba)


def risk_level_for_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return "high"
    if score >= threshold * 0.5:
        return "medium"
    return "low"


def explain(
    artifact: ModelArtifact, feature_row: dict, top_k: int = 5
) -> tuple[float, list[FeatureContribution]]:
    return explain_row(artifact.pipeline, artifact.explainer, feature_row, top_k=top_k)
