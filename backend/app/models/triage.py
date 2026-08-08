from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class Citation(BaseModel):
    source: str
    section: str
    similarity: float
    jurisdiction: str


class TriageRequest(BaseModel):
    session_id: UUID
    message: str

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped or len(stripped) > 2000:
            raise ValueError("message must be 1-2000 characters")
        return stripped


class TriageResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    summary: str
    citations: list[Citation]
    escalate: bool
    escalation_reason: str | None
    confidence: Literal["high", "moderate", "low"]
    disclaimer: Literal["consult_gp", "emergency", "pharmacist"]
    restriction_triggered: bool
    restriction_code: str | None


class SessionCreateRequest(BaseModel):
    user_id: UUID | None = None


class SessionResponse(BaseModel):
    session_id: UUID
    session_token: str
