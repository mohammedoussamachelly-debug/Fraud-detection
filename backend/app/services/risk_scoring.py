"""Orchestrates one `/risk/score` request: look up sender history
(`app/services/history.py`), build the shared feature row
(`app/ml/features.py`), score it, and optionally explain it
(`app/ml/inference.py`). Pure orchestration — no business rule lives here
beyond "call these in order", per the backend-engineer skill's rule to keep
business logic out of route handlers (it's here, not in `app/api/`, either).
"""

from sqlalchemy.orm import Session

from app.ml.features import build_feature_row
from app.ml.inference import ModelArtifact, explain, predict_proba, risk_level_for_score
from app.schemas.risk import RiskExplanation, RiskScoreRequest, RiskScoreResponse, ShapContribution
from app.services.history import get_sender_history


def score_transaction(
    db: Session, artifact: ModelArtifact, request: RiskScoreRequest
) -> RiskScoreResponse:
    history = get_sender_history(db, request.sender_id, request.step)

    raw = {
        "amount": request.amount,
        "transaction_type": request.transaction_type,
        "step": request.step,
        "sender_prev_balance": request.oldbalanceOrg,
        "recipient_prev_balance": request.oldbalanceDest,
    }
    feature_row = build_feature_row(raw, history)

    score = predict_proba(artifact, feature_row)
    threshold = artifact.threshold
    risk_level = risk_level_for_score(score, threshold)

    explanation = None
    if request.include_explanation:
        base_value, contributions = explain(artifact, feature_row)
        explanation = RiskExplanation(
            base_value=base_value,
            contributions=[
                ShapContribution(
                    feature=c.feature,
                    value=c.value,
                    shap_contribution=c.shap_contribution,
                    direction=c.direction,
                )
                for c in contributions
            ],
        )

    return RiskScoreResponse(
        transaction_id=request.transaction_id,
        risk_score=score,
        risk_level=risk_level,
        model_version=artifact.version_label,
        threshold=threshold,
        explanation=explanation,
    )
