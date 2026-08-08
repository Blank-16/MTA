from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RestrictionHit(BaseModel):
    code: str
    reason: str
    layer: str
    ts: datetime


class AuditEntry(BaseModel):
    turn: int
    message_id: UUID
    role: str
    restriction_hits: list[RestrictionHit]
    confidence: str | None
    escalated: bool
    ts: datetime
