"""Real PostgreSQL, frozen XGBoost, ownership and workflow regression checks."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.db.models import (
    Account,
    Alert,
    Case,
    CaseAlert,
    CaseEvidence,
    DemoBatch,
    DemoRecord,
    RiskScore,
    Transaction,
)
from app.db.session import SessionLocal
from app.demo.generator import DemoConfig, generate
from app.demo.loader import load, register, reset
from app.ml.inference import load_active_artifact
from app.schemas.risk import RiskScoreRequest
from app.services import workspace
from app.services.risk_scoring import score_transaction
from tests.conftest import auth_header, wait_for_run_status


def test_generator_consistency():
    config = DemoConfig(accounts=50, transactions=300, days=60)
    accounts, transactions, scenarios = generate(config)
    assert generate(config) == (accounts, transactions, scenarios)
    assert len({t["id"] for t in transactions}) == 300
    assert len(accounts) == 50 and len(scenarios) == 5
    assert transactions[-1]["step"] - transactions[0]["step"] >= 59 * 24
    balances = {a["id"]: Decimal("2000000") for a in accounts}
    for tx in transactions:
        origin, dest = tx["origin_account_id"], tx["dest_account_id"]
        assert origin != dest
        assert tx["origin_balance_before"] == balances[origin]
        assert tx["dest_balance_before"] == balances[dest]
        assert tx["amount"] >= 0
        balances[origin] -= tx["amount"]
        balances[dest] += tx["amount"]
        assert tx["origin_balance_after"] == balances[origin] >= 0
        assert tx["dest_balance_after"] == balances[dest]
    assert sum(balances.values()) == Decimal("100000000")


@pytest.fixture
def demo(db_session):
    config = DemoConfig(batch="qa-" + uuid.uuid4().hex[:10], accounts=50, transactions=300, days=60)
    artifact = load_active_artifact(get_settings().ml_artifacts_dir)
    result = load(db_session, config, artifact)
    yield config, artifact, result
    db_session.rollback()
    reset(db_session, config.batch, f"DELETE DEMO {config.batch}")


def test_real_model_parity_idempotency_and_thresholds(db_session, demo):
    config, artifact, result = demo
    assert result["created"] and result["scores"] == 300
    assert load(db_session, config, artifact)["created"] is False
    with pytest.raises(ValueError, match="different settings"):
        load(db_session, replace(config, seed=42), artifact)
    db_session.rollback()
    for scenario in result["scenarios"]:
        tx = db_session.get(Transaction, uuid.UUID(scenario["transaction_id"]))
        origin = db_session.get(Account, tx.origin_account_id)
        dest = db_session.get(Account, tx.dest_account_id)
        score = score_transaction(
            db_session,
            artifact,
            RiskScoreRequest(
                transaction_id=str(tx.id),
                transaction_type=tx.type,
                amount=float(tx.amount),
                sender_id=origin.external_ref,
                receiver_id=dest.external_ref,
                step=tx.step,
                oldbalanceOrg=float(tx.origin_balance_before),
                oldbalanceDest=float(tx.dest_balance_before),
                include_explanation=True,
            ),
        )
        stored = db_session.scalar(select(RiskScore).where(RiskScore.transaction_id == tx.id))
        assert float(stored.risk_score) == pytest.approx(score.risk_score, abs=1e-6)
        actual = {c.feature: c.shap_contribution for c in score.explanation.contributions}
        saved = {c["feature"]: c["shap_contribution"] for c in stored.shap_values["contributions"]}
        for key, value in actual.items():
            assert saved[key] == pytest.approx(value, abs=1e-7)
        assert stored.shap_values["base_value"] + sum(saved.values()) == pytest.approx(
            score.risk_score, abs=1e-5
        )
    scores = db_session.scalars(
        select(RiskScore)
        .join(DemoRecord, DemoRecord.entity_id == RiskScore.id)
        .where(DemoRecord.batch_id == config.batch, DemoRecord.entity_type == "risk_score")
    ).all()
    model_alerts = db_session.scalars(
        select(Alert)
        .join(DemoRecord, DemoRecord.entity_id == Alert.id)
        .where(DemoRecord.batch_id == config.batch, Alert.alert_type == "model_threshold")
    ).all()
    assert {a.transaction_id for a in model_alerts} == {
        s.transaction_id for s in scores if float(s.risk_score) >= artifact.threshold
    }


def test_reset_confirmation_and_unrelated_records(db_session, demo):
    config, _, result = demo
    unrelated = Account(
        external_ref="qa-unrelated-" + uuid.uuid4().hex,
        account_type="customer",
        first_seen_at=datetime.now(UTC),
    )
    db_session.add(unrelated)
    db_session.commit()
    try:
        with pytest.raises(ValueError, match="exact confirmation"):
            reset(db_session, config.batch, config.batch)
        assert db_session.get(DemoBatch, config.batch)
        reset(db_session, config.batch, f"DELETE DEMO {config.batch}")
        assert db_session.get(Account, unrelated.id)
        assert not db_session.scalar(
            select(DemoRecord.entity_id).where(DemoRecord.batch_id == config.batch)
        )
        assert not db_session.get(Transaction, uuid.UUID(result["scenarios"][0]["transaction_id"]))
    finally:
        db_session.delete(unrelated)
        db_session.commit()


def test_reset_refuses_external_case_reference(db_session, demo):
    config, _, result = demo
    external = Case(priority="low")
    db_session.add(external)
    db_session.flush()
    db_session.add(
        CaseAlert(case_id=external.id, alert_id=uuid.UUID(result["scenarios"][1]["alert_id"]))
    )
    db_session.commit()
    try:
        with pytest.raises(ValueError, match="external references"):
            reset(db_session, config.batch, f"DELETE DEMO {config.batch}")
        db_session.rollback()
        assert db_session.get(Case, external.id)
    finally:
        db_session.execute(delete(CaseAlert).where(CaseAlert.case_id == external.id))
        db_session.delete(external)
        db_session.commit()


def test_workspace_rbac_dedup_and_human_decisions(
    client, db_session, demo, make_user, service_auth_header
):
    _, _, result = demo
    analyst = make_user()
    senior = make_user("senior_analyst")
    headers = auth_header(analyst)
    assert client.get("/api/v1/workspace/dashboard").status_code == 401
    assert client.get("/api/v1/demo/scenarios", headers=service_auth_header).status_code == 401
    alert_id = result["scenarios"][1]["alert_id"]

    def open_case(_):
        with SessionLocal() as session:
            return workspace.investigate(
                session, session.get(Alert, uuid.UUID(alert_id)), analyst.id
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        opened = list(pool.map(open_case, range(2)))
    assert opened[0]["case_id"] == opened[1]["case_id"]
    assert sum(item["created"] for item in opened) == 1
    case_id = opened[0]["case_id"]
    assert (
        db_session.scalar(
            select(func.count()).select_from(CaseEvidence).where(CaseEvidence.case_id == case_id)
        )
        == 3
    )
    context = client.get(f"/api/v1/workspace/cases/{case_id}", headers=headers)
    assert context.status_code == 200, context.text
    assert context.json()["activities"][0]["sender"] == "Growing business"
    report_url = f"/api/v1/workspace/cases/{case_id}/report"

    def open_report(_):
        with SessionLocal() as session:
            return workspace.report(session, session.get(Case, case_id), analyst.id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(open_report, range(2)))
    assert reports[0]["run_id"] == reports[1]["run_id"]
    first = client.post(report_url, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(report_url, headers=headers)
    assert first.json()["run_id"] == second.json()["run_id"]
    run_id = first.json()["run_id"]
    run = wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"), timeout=45)
    assert run.status == "awaiting_approval"
    assert run.model_provider == "mock"
    assert (
        client.post(f"/api/v1/investigations/{run_id}/approve", headers=headers).status_code == 200
    )
    db_session.expire_all()
    assert db_session.get(Case, case_id).status == "investigating"
    body = {
        "decision": "dismissed",
        "rationale": "Synthetic scenario reviewed; no crime is asserted.",
    }
    assert (
        client.post(f"/api/v1/cases/{case_id}/decision", json=body, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/cases/{case_id}/decision", json=body, headers=auth_header(senior)
        ).status_code
        == 201
    )
    db_session.expire_all()
    assert db_session.get(Case, case_id).status == "resolved"
    dashboard = client.get("/api/v1/workspace/dashboard", headers=headers).json()
    assert dashboard["transactions"] == db_session.scalar(
        select(func.count()).select_from(Transaction)
    )
    inbox = client.get(
        "/api/v1/workspace/alerts", params={"search": "Growing business"}, headers=headers
    ).json()
    assert any(i["source"] == "Demonstration rule" for i in inbox["items"])


def test_scenario_graphs_include_event_hour(db_session, demo):
    from app.services.graph_analytics import get_account_metrics, get_account_neighborhood

    _, _, result = demo
    incoming = result["scenarios"][2]
    tx = db_session.get(Transaction, uuid.UUID(incoming["transaction_id"]))
    account_id = uuid.UUID(incoming["account_id"])
    before = get_account_neighborhood(db_session, account_id, hops=2, as_of_step=tx.step)
    through_event = get_account_neighborhood(db_session, account_id, hops=2, as_of_step=tx.step + 1)
    assert len(before.edges) == 0
    assert len(through_event.edges) == 10
    metrics = get_account_metrics(db_session, account_id, as_of_step=tx.step + 1)
    assert metrics.unique_senders == 10 and metrics.fan_in_pattern
    outgoing = result["scenarios"][3]
    tx = db_session.get(Transaction, uuid.UUID(outgoing["transaction_id"]))
    metrics = get_account_metrics(db_session, account_id, as_of_step=tx.step + 1)
    assert metrics.unique_recipients == 6 and metrics.fan_out_pattern


def test_different_alerts_for_same_payment_reuse_case(db_session, demo, make_user):
    config, _, result = demo
    analyst = make_user()
    original = db_session.get(Alert, uuid.UUID(result["scenarios"][1]["alert_id"]))
    second = Alert(
        transaction_id=original.transaction_id,
        risk_score_id=original.risk_score_id,
        alert_type="manual",
        severity="medium",
    )
    db_session.add(second)
    db_session.flush()
    register(db_session, config.batch, "alert", [second.id])
    db_session.commit()

    def open_case(alert_id):
        with SessionLocal() as session:
            return workspace.investigate(session, session.get(Alert, alert_id), analyst.id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        opened = list(pool.map(open_case, [original.id, second.id]))
    assert opened[0]["case_id"] == opened[1]["case_id"]
    assert sum(item["created"] for item in opened) == 1
    case_id = opened[0]["case_id"]
    assert set(
        db_session.scalars(select(CaseAlert.alert_id).where(CaseAlert.case_id == case_id))
    ) == {original.id, second.id}
    assert (
        db_session.scalar(
            select(func.count()).select_from(CaseEvidence).where(CaseEvidence.case_id == case_id)
        )
        == 3
    )


def test_reset_refuses_external_evidence_and_active_report(db_session, demo, make_user):
    from app.db.models import AgentRun

    config, _, result = demo
    external = Case(priority="low")
    db_session.add(external)
    db_session.flush()
    evidence = CaseEvidence(
        case_id=external.id,
        evidence_type="historical_stats",
        source_reference=f"account:{result['scenarios'][0]['account_id']}",
        evidence_payload={},
    )
    db_session.add(evidence)
    db_session.commit()
    try:
        with pytest.raises(ValueError, match="external references"):
            reset(db_session, config.batch, f"DELETE DEMO {config.batch}")
        db_session.rollback()
        assert db_session.get(DemoBatch, config.batch)
    finally:
        db_session.delete(evidence)
        db_session.flush()
        db_session.delete(external)
        db_session.commit()

    analyst = make_user()
    active = AgentRun(
        case_id=uuid.UUID(result["scenarios"][4]["case_id"]),
        started_by_user_id=analyst.id,
        status="running",
        model_provider="mock",
        model_name="reset-safety-test",
        prompt_version="test",
        tool_versions={},
    )
    db_session.add(active)
    db_session.commit()
    try:
        with pytest.raises(ValueError, match="active investigations"):
            reset(db_session, config.batch, f"DELETE DEMO {config.batch}")
        db_session.rollback()
        assert db_session.get(AgentRun, active.id)
    finally:
        db_session.delete(active)
        db_session.commit()
