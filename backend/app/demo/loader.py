"""Atomic, owned demo batches. All scores come from the active frozen artifact."""

import uuid
from dataclasses import asdict

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, or_, select, text
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    AgentEvidenceRef,
    AgentRun,
    AgentStep,
    Alert,
    Case,
    CaseAlert,
    CaseDecision,
    CaseEvidence,
    DemoBatch,
    DemoRecord,
    RiskScore,
    Transaction,
)
from app.demo.generator import DemoConfig, generate, record_id
from app.ml.explain import _feature_group_map
from app.ml.features import FEATURE_COLUMNS, engineer_features
from app.ml.inference import ModelArtifact, risk_level_for_score
from app.schemas.transaction import TransactionRead
from app.services.alerting import severity_for_score
from app.services.audit import record_event
from app.services.history import get_sender_history


def lock_batch(db: Session, batch: str) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"demo:{batch}"})


def register(db: Session, batch: str, kind: str, ids: list) -> None:
    if ids:
        db.execute(
            insert(DemoRecord), [dict(batch_id=batch, entity_type=kind, entity_id=i) for i in ids]
        )


def load(db: Session, config: DemoConfig, artifact: ModelArtifact) -> dict:
    config.validate()
    lock_batch(db, config.batch)
    existing = db.get(DemoBatch, config.batch)
    if existing:
        if existing.config != asdict(config):
            raise ValueError(
                "Batch already exists with different settings; explicitly reset it first"
            )
        return {"batch": config.batch, "created": False, "scenarios": existing.scenarios}
    accounts, transactions, scenarios = generate(config)
    # IDs/unique references colliding with unrelated data fail atomically; never adopt them.
    db.add(DemoBatch(id=config.batch, seed=config.seed, config=asdict(config), scenarios=[]))
    db.flush()
    db.execute(insert(Account), accounts)
    db.execute(insert(Transaction), transactions)
    register(db, config.batch, "account", [a["id"] for a in accounts])
    register(db, config.batch, "transaction", [t["id"] for t in transactions])
    refs = {a["id"]: a["external_ref"] for a in accounts}
    # Use the production history query, including its strict step < event boundary.
    raw = [
        dict(
            amount=float(t["amount"]),
            transaction_type=t["type"],
            step=t["step"],
            sender_prev_balance=float(t["origin_balance_before"]),
            recipient_prev_balance=float(t["dest_balance_before"]),
            **get_sender_history(db, refs[t["origin_account_id"]], t["step"]),
        )
        for t in transactions
    ]
    features = engineer_features(pd.DataFrame(raw))
    probabilities = artifact.pipeline.predict_proba(features)[:, 1]
    preprocessor = artifact.pipeline.named_steps["preprocess"]
    groups = _feature_group_map(preprocessor)
    base = float(np.asarray(artifact.explainer.expected_value).reshape(-1)[-1])
    scores, alerts = [], []
    for start in range(0, len(transactions), 256):
        frame = features.iloc[start : start + 256]
        values = artifact.explainer.shap_values(preprocessor.transform(frame))
        if isinstance(values, list):
            values = values[1]
        for j, (_, row) in enumerate(frame.iterrows()):
            index = start + j
            tx = transactions[index]
            probability = float(probabilities[index])
            level = risk_level_for_score(probability, artifact.threshold)
            contributions = []
            for feature in FEATURE_COLUMNS:
                contribution = float(np.asarray(values)[j, groups[feature]].sum())
                contributions.append(
                    dict(
                        feature=feature,
                        value=row[feature],
                        shap_contribution=contribution,
                        direction="increases_risk" if contribution >= 0 else "decreases_risk",
                    )
                )
            contributions.sort(key=lambda c: abs(c["shap_contribution"]), reverse=True)
            score_id = record_id(config.batch, "score", tx["id"])
            scores.append(
                dict(
                    id=score_id,
                    transaction_id=tx["id"],
                    risk_score=probability,
                    risk_level=level,
                    model_version=artifact.version_label,
                    threshold_used=artifact.threshold,
                    shap_values=dict(base_value=base, contributions=contributions),
                )
            )
            if level == "high":
                alerts.append(
                    dict(
                        id=record_id(config.batch, "model-alert", tx["id"]),
                        transaction_id=tx["id"],
                        risk_score_id=score_id,
                        alert_type="model_threshold",
                        severity=severity_for_score(probability, artifact.threshold),
                        status="open",
                    )
                )
    db.execute(insert(RiskScore), scores)
    score_map = {str(s["transaction_id"]): s for s in scores}
    for scenario in scenarios:
        score = score_map[scenario["transaction_id"]]
        scenario.update(
            model_score=score["risk_score"],
            model_level=score["risk_level"],
            model_version=artifact.version_label,
        )
        if scenario["key"] != "normal":
            tx_ids = (
                scenario["transaction_ids"]
                if scenario["key"] == "linked"
                else [scenario["transaction_id"]]
            )
            for tx_id in tx_ids:
                alert_id = record_id(config.batch, "rule-alert", tx_id)
                alerts.append(
                    dict(
                        id=alert_id,
                        transaction_id=uuid.UUID(tx_id),
                        risk_score_id=score_map[tx_id]["id"],
                        alert_type=f"demo_rule_{scenario['key']}",
                        severity="high",
                        status="open",
                    )
                )
                scenario["alert_id"] = str(alert_id)
    if alerts:
        db.execute(insert(Alert), alerts)
    register(db, config.batch, "risk_score", [s["id"] for s in scores])
    register(db, config.batch, "alert", [a["id"] for a in alerts])
    linked = next(s for s in scenarios if s["key"] == "linked")
    case_id = record_id(config.batch, "case", "linked")
    db.add(Case(id=case_id, priority="high", status="investigating"))
    db.flush()
    for tx_id in linked["transaction_ids"]:
        db.add(CaseAlert(case_id=case_id, alert_id=record_id(config.batch, "rule-alert", tx_id)))
        linked_tx = db.get(Transaction, uuid.UUID(tx_id))
        assert linked_tx is not None
        db.add(
            CaseEvidence(
                case_id=case_id,
                evidence_type="transaction",
                source_reference=f"transaction:{tx_id}",
                evidence_payload=TransactionRead.model_validate(linked_tx).model_dump(mode="json"),
            )
        )
    register(db, config.batch, "case", [case_id])
    linked["case_id"] = str(case_id)
    batch_record = db.get(DemoBatch, config.batch)
    assert batch_record is not None
    batch_record.scenarios = scenarios
    record_event(
        db,
        user_id=None,
        action="demo_loaded",
        entity_type="demo_batch",
        entity_id=None,
        metadata={
            "batch": config.batch,
            "config": asdict(config),
            "model_version": artifact.version_label,
            "scores": len(scores),
            "alerts": len(alerts),
            "synthetic": True,
        },
    )
    db.commit()
    return dict(
        batch=config.batch,
        created=True,
        accounts=len(accounts),
        transactions=len(transactions),
        scores=len(scores),
        model_alerts=sum(a["alert_type"] == "model_threshold" for a in alerts),
        demo_alerts=sum(a["alert_type"].startswith("demo_rule_") for a in alerts),
        scenarios=scenarios,
    )


def reset(db: Session, batch: str, confirmation: str) -> dict:
    if confirmation != f"DELETE DEMO {batch}":
        raise ValueError(f"Reset requires exact confirmation: DELETE DEMO {batch}")
    lock_batch(db, batch)
    # Block concurrent writes while checking even non-FK evidence references.
    # Read-only requests remain available. Never clear tables; deletes below use owned IDs.
    db.execute(
        text(
            "LOCK TABLE app.accounts, app.transactions, app.risk_scores, app.alerts, "
            "app.cases, app.case_alerts, app.case_evidence, app.case_decisions, "
            "app.agent_runs, app.agent_steps, app.agent_evidence_refs, app.demo_records "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    if not db.get(DemoBatch, batch):
        return {"batch": batch, "removed": False}
    owned: dict[str, list] = {}
    for row in db.scalars(select(DemoRecord).where(DemoRecord.batch_id == batch)):
        owned.setdefault(row.entity_type, []).append(row.entity_id)
    accounts, txs, scores, alerts, cases = [
        owned.get(k, []) for k in ("account", "transaction", "risk_score", "alert", "case")
    ]
    # Refuse mixed ownership, including references without database foreign keys.
    checks = [
        select(Transaction.id).where(
            or_(
                Transaction.origin_account_id.in_(accounts),
                Transaction.dest_account_id.in_(accounts),
            ),
            Transaction.id.not_in(txs),
        ),
        select(RiskScore.id).where(RiskScore.transaction_id.in_(txs), RiskScore.id.not_in(scores)),
        select(Alert.id).where(
            or_(Alert.transaction_id.in_(txs), Alert.risk_score_id.in_(scores)),
            Alert.id.not_in(alerts),
        ),
        select(CaseAlert.case_id).where(
            or_(
                CaseAlert.alert_id.in_(alerts) & CaseAlert.case_id.not_in(cases),
                CaseAlert.case_id.in_(cases) & CaseAlert.alert_id.not_in(alerts),
            )
        ),
    ]
    references = [
        f"{kind}:{i}"
        for kind, ids in (
            ("account", accounts),
            ("transaction", txs),
            ("risk_score", scores),
            ("case", cases),
            ("alert", alerts),
        )
        for i in ids
    ]
    checks.append(
        select(CaseEvidence.id).where(
            CaseEvidence.case_id.not_in(cases), CaseEvidence.source_reference.in_(references)
        )
    )
    run_ids = list(db.scalars(select(AgentRun.id).where(AgentRun.case_id.in_(cases))))
    checks.append(
        select(AgentEvidenceRef.id).where(
            AgentEvidenceRef.agent_run_id.not_in(run_ids),
            AgentEvidenceRef.source_reference.in_(references),
        )
    )
    checks.append(
        select(AgentRun.id).where(
            AgentRun.case_id.in_(cases), AgentRun.status.in_(["running", "revision_requested"])
        )
    )
    if any(db.scalar(query.limit(1)) is not None for query in checks):
        raise ValueError(
            "Reset refused: external references or active investigations exist; preserve this batch"
        )
    for model, condition in [
        (AgentEvidenceRef, AgentEvidenceRef.agent_run_id.in_(run_ids)),
        (AgentStep, AgentStep.agent_run_id.in_(run_ids)),
        (AgentRun, AgentRun.id.in_(run_ids)),
        (CaseDecision, CaseDecision.case_id.in_(cases)),
        (CaseEvidence, CaseEvidence.case_id.in_(cases)),
        (CaseAlert, CaseAlert.case_id.in_(cases)),
        (Case, Case.id.in_(cases)),
        (Alert, Alert.id.in_(alerts)),
        (RiskScore, RiskScore.id.in_(scores)),
        (Transaction, Transaction.id.in_(txs)),
        (Account, Account.id.in_(accounts)),
        (DemoRecord, DemoRecord.batch_id == batch),
        (DemoBatch, DemoBatch.id == batch),
    ]:
        db.execute(delete(model).where(condition))
    record_event(
        db,
        user_id=None,
        action="demo_reset",
        entity_type="demo_batch",
        entity_id=None,
        metadata={"batch": batch, "counts": {k: len(v) for k, v in owned.items()}},
    )
    db.commit()
    return {"batch": batch, "removed": True}
