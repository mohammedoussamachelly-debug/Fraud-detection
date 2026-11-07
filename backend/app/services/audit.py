"""Append-only audit trail writer, used by every Phase 5 service that
performs a privileged or consequential action — auth, scoring/alerting,
case mutation, decisions, evidence — per CLAUDE.md's audit-logging rule.
Callers add the row to the current transaction; they do not commit here,
so an audit entry always lands in the same commit as the action it
describes (never logged for an action that then rolled back).
"""

import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLogEntry


def record_event(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    metadata: dict | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        event_metadata=metadata or {},
    )
    db.add(entry)
    db.flush()
    return entry
