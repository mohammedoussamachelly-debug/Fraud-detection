"""End-to-end integration tests for the investigation API
(`POST /cases/{id}/investigations`, `GET /investigations/{run_id}`,
approve/reject/request-revision) — real DB, real LangGraph execution,
real (mock) LLM. This is the primary demonstration of Part J's "complete
investigation from an existing case through evidence retrieval, graph
analysis, report generation, and human review".
"""

import uuid

from fastapi.testclient import TestClient

from app.db.models import Case
from tests.conftest import auth_header, wait_for_run_status


def test_start_investigation_requires_auth(client: TestClient, make_investigation_case) -> None:
    case, _tx, _alert = make_investigation_case()
    response = client.post(f"/api/v1/cases/{case.id}/investigations")
    assert response.status_code == 401


def test_start_investigation_rejects_service_credential(
    client: TestClient, make_investigation_case, service_auth_header: dict
) -> None:
    case, _tx, _alert = make_investigation_case()
    response = client.post(f"/api/v1/cases/{case.id}/investigations", headers=service_auth_header)
    assert response.status_code == 401


def test_start_investigation_404_for_unknown_case(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.post(
        f"/api/v1/cases/{uuid.uuid4()}/investigations", headers=auth_header(user)
    )
    assert response.status_code == 404


def test_full_investigation_lifecycle_evidence_to_report_to_approval(
    client: TestClient, db_session, make_investigation_case, make_user
) -> None:
    """The Part J demonstration: start -> evidence collected -> network
    analyzed -> report drafted -> human approves. Never auto-finalizes.
    """
    case, tx, _alert = make_investigation_case()
    analyst = make_user(role="analyst")

    started = client.post(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    assert started.status_code == 202
    body = started.json()
    run_id = body["run_id"]
    assert body["status"] == "running"

    # The workflow must halt here — never auto-advance past this status
    # without a human action (CLAUDE.md human-in-the-loop rule).
    wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"))

    detail = client.get(f"/api/v1/investigations/{run_id}", headers=auth_header(analyst))
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "awaiting_approval"
    assert detail_body["final_report"] is None  # not finalized without human approval

    node_names = [s["node_name"] for s in detail_body["steps"]]
    assert node_names == [
        "intake",
        "evidence_collector",
        "network_investigator",
        "report_writer",
        "human_approval_gate",
    ]
    assert all(s["status"] == "succeeded" for s in detail_body["steps"])

    assert len(detail_body["evidence_refs"]) > 0
    ref_sources = {r["source_reference"] for r in detail_body["evidence_refs"]}
    assert f"transaction:{tx.id}" in ref_sources

    report = detail_body["draft_report"]
    assert report["is_mock"] is True
    assert report["model_provider"] == "mock"
    # Every hypothesis must cite only refs that were actually collected.
    valid_refs = {r["source_reference"] for r in detail_body["evidence_refs"]}
    for hypothesis in report["hypotheses"]:
        assert hypothesis["evidence_refs"], "hypothesis must cite at least one evidence_ref"
        for ref in hypothesis["evidence_refs"]:
            assert ref in valid_refs

    approved = client.post(f"/api/v1/investigations/{run_id}/approve", headers=auth_header(analyst))
    assert approved.status_code == 200
    approved_body = approved.json()
    assert approved_body["status"] == "approved"
    assert approved_body["final_report"] == report

    # Approving a report is NOT a case decision — the case itself must be
    # untouched (CLAUDE.md: only `POST /cases/{id}/decision` may resolve
    # a case).
    db_session.expire_all()
    fresh_case = db_session.get(Case, case.id)
    assert fresh_case.status == "open"


def test_approve_is_idempotent(client: TestClient, make_investigation_case, make_user) -> None:
    case, _tx, _alert = make_investigation_case()
    analyst = make_user(role="analyst")
    started = client.post(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    run_id = started.json()["run_id"]
    wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"))

    first = client.post(f"/api/v1/investigations/{run_id}/approve", headers=auth_header(analyst))
    second = client.post(f"/api/v1/investigations/{run_id}/approve", headers=auth_header(analyst))
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "approved"


def test_reject_then_approve_conflicts(
    client: TestClient, make_investigation_case, make_user
) -> None:
    case, _tx, _alert = make_investigation_case()
    analyst = make_user(role="analyst")
    started = client.post(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    run_id = started.json()["run_id"]
    wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"))

    rejected = client.post(f"/api/v1/investigations/{run_id}/reject", headers=auth_header(analyst))
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    conflict = client.post(f"/api/v1/investigations/{run_id}/approve", headers=auth_header(analyst))
    assert conflict.status_code == 409


def test_request_revision_updates_draft_and_is_bounded(
    client: TestClient, make_investigation_case, make_user
) -> None:
    case, _tx, _alert = make_investigation_case()
    analyst = make_user(role="analyst")
    started = client.post(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    run_id = started.json()["run_id"]
    wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"))

    for i in range(3):
        response = client.post(
            f"/api/v1/investigations/{run_id}/request-revision",
            json={"feedback": f"Please double-check the network findings, round {i}."},
            headers=auth_header(analyst),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "awaiting_approval"
        assert body["revision_count"] == i + 1
        assert len(body["review_feedback"]) == i + 1

    # A 4th round exceeds MAX_REVISION_ROUNDS (3) — bounded, not an
    # unbounded loop (Part C).
    fourth = client.post(
        f"/api/v1/investigations/{run_id}/request-revision",
        json={"feedback": "one more look please"},
        headers=auth_header(analyst),
    )
    assert fourth.status_code == 409


def test_get_investigation_404_for_unknown_run(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/investigations/{uuid.uuid4()}", headers=auth_header(user))
    assert response.status_code == 404


def test_get_investigation_requires_auth(client: TestClient) -> None:
    response = client.get(f"/api/v1/investigations/{uuid.uuid4()}")
    assert response.status_code == 401


def test_list_case_investigations_returns_started_run(
    client: TestClient, make_investigation_case, make_user
) -> None:
    case, _tx, _alert = make_investigation_case()
    analyst = make_user(role="analyst")

    started = client.post(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    assert started.status_code == 202
    run_id = started.json()["run_id"]
    wait_for_run_status(uuid.UUID(run_id), ("awaiting_approval", "failed"))

    listed = client.get(f"/api/v1/cases/{case.id}/investigations", headers=auth_header(analyst))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["run_id"] == run_id
    assert body["items"][0]["started_by_user_id"] == str(analyst.id)
    # Summary rows only — full step/evidence/report detail stays on
    # GET /investigations/{run_id}, not duplicated here.
    assert "steps" not in body["items"][0]
    assert "draft_report" not in body["items"][0]


def test_list_case_investigations_404_for_unknown_case(client: TestClient, make_user) -> None:
    user = make_user(role="analyst")
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}/investigations", headers=auth_header(user))
    assert response.status_code == 404


def test_list_case_investigations_requires_auth(client: TestClient) -> None:
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}/investigations")
    assert response.status_code == 401
