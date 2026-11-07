"""Typed shared state for the investigation LangGraph (Part C). Every
node reads and returns a (partial) `InvestigationState` — LangGraph
merges returned keys into the running state between nodes. Nothing here
is persisted directly; `app/services/investigations.py` writes the
durable record (`AgentRun`/`AgentStep`/`AgentEvidenceRef`) from this
state as each node completes, so the in-memory state only needs to
survive one process's execution of the graph, never a restart (that's
what the database tables are for — see docs/multi-agent-architecture.md
for why this run doesn't rely on LangGraph's own checkpointer).
"""

from typing import Any, TypedDict


class EvidenceItem(TypedDict):
    evidence_type: str
    source_reference: str
    summary: str
    flag: bool  # True if this item looks notable (elevated score, etc.)
    payload: dict[str, Any]


class NetworkFinding(TypedDict):
    evidence_type: str  # always "network_finding" — see AgentEvidenceRef
    source_reference: str
    summary: str
    flag: bool
    payload: dict[str, Any]


class InvestigationState(TypedDict, total=False):
    run_id: str
    case_id: str
    actor_user_id: str
    account_ids: list[str]  # accounts involved, seeded at intake
    transaction_ids: list[str]  # transactions involved, seeded at intake
    evidence: list[EvidenceItem]
    network_findings: list[NetworkFinding]
    feedback: list[str]
    report: dict[str, Any] | None
    status: str
    error: str | None
