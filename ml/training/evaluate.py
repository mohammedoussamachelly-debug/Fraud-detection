"""Evaluation metrics and validation-only threshold tuning. Every number
this module returns is computed from actual predictions on the data it's
given — nothing here is a stand-in or estimated value.
"""

import time
from dataclasses import asdict, dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline


@dataclass
class ClassificationMetrics:
    threshold: float
    precision: float
    recall: float
    f1: float
    average_precision: float
    roc_auc: float
    false_positive_rate: float
    false_alerts_per_1000_legit: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(
    y_true: np.ndarray, y_proba: np.ndarray, threshold: float
) -> ClassificationMetrics:
    y_pred = (y_proba >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    n_legit = tn + fp

    fpr = fp / n_legit if n_legit else 0.0
    false_alerts_per_1000 = fpr * 1000

    # average_precision/roc_auc need both classes present and don't depend
    # on `threshold` — computed once per (y_true, y_proba) pair regardless.
    avg_precision = average_precision_score(y_true, y_proba) if y_true.sum() > 0 else float("nan")
    roc_auc = roc_auc_score(y_true, y_proba) if 0 < y_true.sum() < len(y_true) else float("nan")

    return ClassificationMetrics(
        threshold=threshold,
        precision=precision_score(y_true, y_pred, zero_division=0),
        recall=recall_score(y_true, y_pred, zero_division=0),
        f1=f1_score(y_true, y_pred, zero_division=0),
        average_precision=avg_precision,
        roc_auc=roc_auc,
        false_positive_rate=fpr,
        false_alerts_per_1000_legit=false_alerts_per_1000,
        true_positives=int(tp),
        false_positives=int(fp),
        true_negatives=int(tn),
        false_negatives=int(fn),
    )


def tune_threshold(
    y_true: np.ndarray, y_proba: np.ndarray, candidate_thresholds: np.ndarray | None = None
) -> tuple[float, ClassificationMetrics]:
    """Selects the threshold maximizing F1 **on the data passed in** — this
    must only ever be called with validation-set predictions; the caller
    (ml/training/train.py) is responsible for never calling it with test
    data. Returns the chosen threshold and its validation-set metrics.
    """
    if candidate_thresholds is None:
        candidate_thresholds = np.linspace(0.01, 0.99, 99)

    best_threshold = 0.5
    best_metrics: ClassificationMetrics | None = None
    best_f1 = -1.0

    for threshold in candidate_thresholds:
        metrics = compute_metrics(y_true, y_proba, float(threshold))
        if metrics.f1 > best_f1:
            best_f1 = metrics.f1
            best_threshold = float(threshold)
            best_metrics = metrics

    assert best_metrics is not None
    return best_threshold, best_metrics


def measure_inference_latency_ms(pipeline: Pipeline, x_sample, n_repeats: int = 100) -> float:
    """Median single-row `predict_proba` latency in milliseconds, measured
    against the already-fitted pipeline — this is what `app/ml/inference.py`
    actually calls per request."""
    one_row = x_sample.iloc[[0]]
    durations = []
    for _ in range(n_repeats):
        start = time.perf_counter()
        pipeline.predict_proba(one_row)
        durations.append((time.perf_counter() - start) * 1000)
    return float(np.median(durations))
