"""Unit tests for the explicit per-agent tool allow-list
(`app/agents/tools.py::AGENT_TOOL_PERMISSIONS`/`invoke_tool`) — Part C
"explicit tool permissions" and Part H "tool permission boundaries".
No DB rows are needed for most of these: a permission check must reject
*before* any tool function (and therefore any query) runs.
"""

import uuid

import pytest

from app.agents.tools import AGENT_TOOL_PERMISSIONS, ToolPermissionError, invoke_tool


def test_evidence_collector_allow_list_is_exactly_its_tools() -> None:
    assert set(AGENT_TOOL_PERMISSIONS["evidence_collector"]) == {
        "get_transaction",
        "get_account_profile",
        "get_risk_score",
        "get_shap_explanation",
        "get_similar_past_cases",
    }


def test_network_investigator_allow_list_is_exactly_its_tools() -> None:
    assert set(AGENT_TOOL_PERMISSIONS["network_investigator"]) == {
        "get_graph_neighborhood",
        "get_graph_metrics",
        "get_fund_flow",
    }


def test_report_writer_has_no_tool_access() -> None:
    """Agent 3 only ever sees state Agents 1/2 already collected and
    validated (Part E) — it cannot retrieve anything itself.
    """
    assert AGENT_TOOL_PERMISSIONS["report_writer"] == ()


def test_evidence_collector_cannot_call_a_network_investigator_tool(db_session) -> None:
    with pytest.raises(ToolPermissionError):
        invoke_tool("evidence_collector", "get_graph_metrics", db_session, account_id=uuid.uuid4())


def test_network_investigator_cannot_call_an_evidence_collector_tool(db_session) -> None:
    with pytest.raises(ToolPermissionError):
        invoke_tool(
            "network_investigator", "get_transaction", db_session, transaction_id=uuid.uuid4()
        )


def test_report_writer_cannot_call_any_tool(db_session) -> None:
    with pytest.raises(ToolPermissionError):
        invoke_tool("report_writer", "get_transaction", db_session, transaction_id=uuid.uuid4())


def test_unknown_agent_name_has_no_permissions(db_session) -> None:
    with pytest.raises(ToolPermissionError):
        invoke_tool("not_a_real_agent", "get_transaction", db_session, transaction_id=uuid.uuid4())


def test_permitted_tool_call_reaches_the_real_function(db_session) -> None:
    """A permitted call still runs — the allow-list only blocks the
    *wrong* agent, not the tool itself. Validates against a real but
    nonexistent id to confirm it actually executed the query rather than
    short-circuiting silently.
    """
    from app.agents.tools import EvidenceNotFound

    with pytest.raises(EvidenceNotFound):
        invoke_tool(
            "evidence_collector", "get_transaction", db_session, transaction_id=uuid.uuid4()
        )
