from fastapi import APIRouter

from app.api.routes import (
    accounts,
    alerts,
    audit,
    auth,
    cases,
    graph,
    health,
    investigations,
    risk,
    risk_scores,
    transactions,
    workspace,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(risk.router)
api_router.include_router(risk_scores.router)
api_router.include_router(graph.router)
api_router.include_router(alerts.router)
api_router.include_router(cases.router)
api_router.include_router(audit.router)
api_router.include_router(investigations.router)

api_router.include_router(workspace.router)
