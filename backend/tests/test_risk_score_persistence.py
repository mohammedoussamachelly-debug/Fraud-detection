"""Integration tests for POST /risk-scores (service-role persistence) —
real DB + real tiny trained artifact, same pattern as
tests/test_risk_score_api.py. Verifies idempotency, alert creation +
dedup, auth, and the 404/503 failure paths, against the real database.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

import app.api.routes.risk_scores as risk_scores_route
import app.services.scoring_persistence as scoring_persistence_module
from app.core.config import Settings
from app.db.models import Account, Alert, RiskScore, Transaction
from app.ml import inference as inference_module


@pytest.fixture(scope="module")
def trained_settings(tmp_path_factory, database_reachable: bool) -> Settings:
    if not database_reachable:
        pytest.skip("No reachable Postgres at DATABASE_URL.")

    from ml.training.train import run_training

    artifacts_dir = tmp_path_factory.mktemp("risk_persist_artifacts")
    run_training(csv_path="<unused>", synthetic=True, seed=99, artifacts_dir=artifacts_dir)
    return Settings(ml_artifacts_dir=str(artifacts_dir))


@pytest.fixture
def patched_settings(monkeypatch, trained_settings: Settings):
    monkeypatch.setattr(risk_scores_route, "get_settings", lambda: trained_settings)
    inference_module.clear_cache()
    yield trained_settings
    inference_module.clear_cache()


@pytest.fixture
def force_alert_worthy(monkeypatch):
    """The synthetic fixture model (`run_training(synthetic=True)`) is
    trained on near-random fraud labels (`ml/data/synthetic.py`), so it
    has no reliable "this transaction is obviously high risk" case the
    way the real PaySim-trained model does (docs/api-contracts.md §4.1's
    draining example). Alert creation/dedup/idempotency is what these
    tests are about, not the model's classification — so we force
    `should_alert` to always fire and test that logic deterministically.
    """
    monkeypatch.setattr(scoring_persistence_module, "should_alert", lambda risk_level: True)


def _ingest_transaction(
    client: TestClient, prefix: str, service_auth_header: dict, **overrides
) -> dict:
    item = {
        "external_ref": f"{prefix}-tx1",
        "step": 120,
        "type": "TRANSFER",
        "amount": "8400.00",
        "origin_external_ref": f"{prefix}-orig",
        "dest_external_ref": f"{prefix}-dest",
        "origin_balance_before": "10000.00",
        "origin_balance_after": "1600.00",
        "dest_balance_before": "500.00",
        "dest_balance_after": "8900.00",
    }
    item.update(overrides)
    response = client.post(
        "/api/v1/transactions/ingest", json={"transactions": [item]}, headers=service_auth_header
    )
    assert response.status_code == 200
    return item


def _get_transaction_id(db_session, external_ref: str) -> uuid.UUID:
    return db_session.query(Transaction).filter(Transaction.external_ref == external_ref).one().id


def _cleanup(db_session, prefix: str) -> None:
    tx_ids = [
        t.id
        for t in db_session.query(Transaction).filter(Transaction.external_ref.like(f"{prefix}%"))
    ]
    for tx_id in tx_ids:
        db_session.execute(delete(Alert).where(Alert.transaction_id == tx_id))
        db_session.execute(delete(RiskScore).where(RiskScore.transaction_id == tx_id))
    db_session.execute(delete(Transaction).where(Transaction.external_ref.like(f"{prefix}%")))
    db_session.execute(delete(Account).where(Account.external_ref.like(f"{prefix}%")))
    db_session.commit()


def test_persist_creates_risk_score_with_valid_score_and_explanation(
    client: TestClient, db_session, patched_settings: Settings, service_auth_header: dict
) -> None:
    prefix = f"test-persist-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_transaction(client, prefix, service_auth_header)
        tx_id = _get_transaction_id(db_session, f"{prefix}-tx1")

        response = client.post(
            "/api/v1/risk-scores",
            json={"transaction_id": str(tx_id), "include_explanation": True},
            headers=service_auth_header,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["created"] is True
        assert 0.0 <= body["risk_score"]["risk_score"] <= 1.0
        assert body["risk_score"]["risk_level"] in {"low", "medium", "high"}
        assert body["risk_score"]["explanation"] is not None
    finally:
        _cleanup(db_session, prefix)


def test_persist_creates_a_deduplicated_alert_when_alert_worthy(
    client: TestClient,
    db_session,
    patched_settings: Settings,
    service_auth_header: dict,
    force_alert_worthy,
) -> None:
    prefix = f"test-persist-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_transaction(client, prefix, service_auth_header)
        tx_id = _get_transaction_id(db_session, f"{prefix}-tx1")

        response = client.post(
            "/api/v1/risk-scores", json={"transaction_id": str(tx_id)}, headers=service_auth_header
        )
        assert response.status_code == 200
        body = response.json()
        assert body["alert"] is not None
        assert body["alert"]["alert_type"] == "model_threshold"
        assert body["alert"]["severity"] in {"high", "critical"}

        alerts = db_session.query(Alert).filter(Alert.transaction_id == tx_id).all()
        assert len(alerts) == 1
    finally:
        _cleanup(db_session, prefix)


def test_persist_is_idempotent_for_same_transaction_and_model_version(
    client: TestClient,
    db_session,
    patched_settings: Settings,
    service_auth_header: dict,
    force_alert_worthy,
) -> None:
    prefix = f"test-persist-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_transaction(client, prefix, service_auth_header)
        tx_id = _get_transaction_id(db_session, f"{prefix}-tx1")

        first = client.post(
            "/api/v1/risk-scores", json={"transaction_id": str(tx_id)}, headers=service_auth_header
        )
        second = client.post(
            "/api/v1/risk-scores", json={"transaction_id": str(tx_id)}, headers=service_auth_header
        )
        assert first.json()["created"] is True
        assert second.json()["created"] is False
        assert first.json()["risk_score"]["id"] == second.json()["risk_score"]["id"]

        rows = db_session.query(RiskScore).filter(RiskScore.transaction_id == tx_id).all()
        assert len(rows) == 1
        alerts = db_session.query(Alert).filter(Alert.transaction_id == tx_id).all()
        assert len(alerts) == 1
    finally:
        _cleanup(db_session, prefix)


def test_persist_does_not_alert_a_low_risk_transaction(
    client: TestClient, db_session, patched_settings: Settings, service_auth_header: dict
) -> None:
    prefix = f"test-persist-{uuid.uuid4().hex[:8]}"
    try:
        _ingest_transaction(
            client,
            prefix,
            service_auth_header,
            type="PAYMENT",
            amount="10.00",
            origin_balance_before="100000.00",
            origin_balance_after="99990.00",
        )
        tx_id = _get_transaction_id(db_session, f"{prefix}-tx1")

        response = client.post(
            "/api/v1/risk-scores", json={"transaction_id": str(tx_id)}, headers=service_auth_header
        )
        assert response.status_code == 200
        body = response.json()
        assert body["risk_score"]["risk_level"] != "high"
        assert body["alert"] is None
    finally:
        _cleanup(db_session, prefix)


def test_persist_returns_404_for_unknown_transaction(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/risk-scores",
        json={"transaction_id": str(uuid.uuid4())},
        headers=service_auth_header,
    )
    assert response.status_code == 404


def test_persist_rejects_missing_service_credential(
    client: TestClient, patched_settings: Settings
) -> None:
    response = client.post("/api/v1/risk-scores", json={"transaction_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_persist_rejects_wrong_service_credential(
    client: TestClient, patched_settings: Settings
) -> None:
    response = client.post(
        "/api/v1/risk-scores",
        json={"transaction_id": str(uuid.uuid4())},
        headers={"Authorization": "Bearer not-the-service-key"},
    )
    assert response.status_code == 401


def test_persist_returns_503_when_model_unavailable(
    client: TestClient, tmp_path, monkeypatch, service_auth_header: dict
) -> None:
    empty_settings = Settings(ml_artifacts_dir=str(tmp_path))
    monkeypatch.setattr(risk_scores_route, "get_settings", lambda: empty_settings)
    inference_module.clear_cache()

    response = client.post(
        "/api/v1/risk-scores",
        json={"transaction_id": str(uuid.uuid4())},
        headers=service_auth_header,
    )
    assert response.status_code == 503

    inference_module.clear_cache()
