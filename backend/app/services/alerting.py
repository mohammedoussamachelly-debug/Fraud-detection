"""Alert-worthiness and severity rules. No hardcoded score cutoffs: both
functions scale with whatever `threshold` the *active* model artifact
carries (`app/ml/inference.py`'s `ModelArtifact.threshold`), so a retrained
model with a different tuned threshold changes alerting behavior
automatically rather than needing a code change here.
"""

ALERT_TYPE_MODEL_THRESHOLD = "model_threshold"


def should_alert(risk_level: str) -> bool:
    # "configured review conditions" (§3) == the same high/medium/low bands
    # `app/ml/inference.py::risk_level_for_score` already derives from the
    # active threshold; only "high" (score >= threshold) crosses the bar
    # docs/architecture.md §4.2 describes ("above a configured threshold").
    return risk_level == "high"


def severity_for_score(score: float, threshold: float) -> str:
    """ "high" for anything crossing the threshold; "critical" only once the
    score has also crossed the midpoint of the remaining headroom to 1.0 —
    relative to the threshold, never an absolute magic number.
    """
    if threshold >= 1.0:
        return "high"
    midpoint = threshold + (1.0 - threshold) / 2
    return "critical" if score >= midpoint else "high"
