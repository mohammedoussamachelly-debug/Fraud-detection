"""Integration tests for POST /risk/score. Needs a real DB (sender-history
lookup always queries it, even for an unseen account) — skipped, not
faked, when unreachable. Uses a tiny model artifact trained on the
synthetic fixture, written to a tmp directory, never the real
ml/artifacts/.

`service`-role only since Phase 6 Part A — every call passes
`service_auth_header` (tests/conftest.py); the auth-rejection tests at
the bottom check the no-credential / wrong-credential paths.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

import app.api.routes.risk as risk_route
from app.core.config import Settings
from app.ml import inference as inference_module


@pytest.fixture(scope="module")
def trained_settings(tmp_path_factory, database_reachable: bool) -> Settings:
    if not database_reachable:
        pytest.skip("No reachable Postgres at DATABASE_URL.")

    from ml.training.train import run_training

    artifacts_dir = tmp_path_factory.mktemp("risk_api_artifacts")
    run_training(csv_path="<unused>", synthetic=True, seed=99, artifacts_dir=artifacts_dir)
    return Settings(ml_artifacts_dir=str(artifacts_dir))


@pytest.fixture
def patched_settings(monkeypatch, trained_settings: Settings):
    monkeypatch.setattr(risk_route, "get_settings", lambda: trained_settings)
    inference_module.clear_cache()
    yield trained_settings
    inference_module.clear_cache()


def _valid_request(**overrides) -> dict:
    request = {
        "transaction_id": f"TX-{uuid.uuid4().hex[:8]}",
        "transaction_type": "TRANSFER",
        "amount": 8400,
        "sender_id": f"unseen-sender-{uuid.uuid4().hex[:8]}",
        "receiver_id": f"unseen-receiver-{uuid.uuid4().hex[:8]}",
        "step": 120,
        "oldbalanceOrg": 10000,
        "oldbalanceDest": 500,
    }
    request.update(overrides)
    return request


def test_score_unseen_account_succeeds_with_new_account_defaults(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post("/api/v1/risk/score", json=_valid_request(), headers=service_auth_header)
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["risk_level"] in {"low", "medium", "high"}
    assert body["model_version"] == trained_version_label(patched_settings)
    assert body["explanation"] is None


def trained_version_label(settings: Settings) -> str:
    from pathlib import Path

    return (Path(settings.ml_artifacts_dir) / "active_version.txt").read_text().strip()


def test_score_with_explanation_returns_shap_contributions(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/risk/score",
        json=_valid_request(include_explanation=True),
        headers=service_auth_header,
    )
    assert response.status_code == 200
    body = response.json()
    explanation = body["explanation"]
    assert explanation is not None
    assert isinstance(explanation["base_value"], float)
    assert 1 <= len(explanation["contributions"]) <= 5

    contributions = explanation["contributions"]
    abs_values = [abs(c["shap_contribution"]) for c in contributions]
    assert abs_values == sorted(abs_values, reverse=True)
    for c in contributions:
        assert c["direction"] in {"increases_risk", "decreases_risk"}
        assert c["feature"]


def test_score_rejects_malformed_request(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/risk/score", json=_valid_request(amount=-5), headers=service_auth_header
    )
    assert response.status_code == 422


def test_score_rejects_invalid_transaction_type(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/risk/score",
        json=_valid_request(transaction_type="BOGUS"),
        headers=service_auth_header,
    )
    assert response.status_code == 422


def test_score_returns_503_when_model_unavailable(
    client: TestClient, tmp_path, monkeypatch, service_auth_header: dict
) -> None:
    empty_settings = Settings(ml_artifacts_dir=str(tmp_path))
    monkeypatch.setattr(risk_route, "get_settings", lambda: empty_settings)
    inference_module.clear_cache()

    response = client.post("/api/v1/risk/score", json=_valid_request(), headers=service_auth_header)
    assert response.status_code == 503
    body = response.json()
    assert body["type"] == "https://sentinelai.dev/errors/model-unavailable"

    inference_module.clear_cache()


def test_response_never_contains_a_ground_truth_field(
    client: TestClient, patched_settings: Settings, service_auth_header: dict
) -> None:
    response = client.post(
        "/api/v1/risk/score",
        json=_valid_request(include_explanation=True),
        headers=service_auth_header,
    )
    body_text = response.text
    assert "isFraud" not in body_text
    assert "isFlaggedFraud" not in body_text


def test_score_rejects_missing_credential(client: TestClient, patched_settings: Settings) -> None:
    response = client.post("/api/v1/risk/score", json=_valid_request())
    assert response.status_code == 401


def test_score_rejects_analyst_token(
    client: TestClient, patched_settings: Settings, make_user
) -> None:
    from tests.conftest import auth_header

    user = make_user(role="admin")
    response = client.post("/api/v1/risk/score", json=_valid_request(), headers=auth_header(user))
    assert response.status_code == 401
