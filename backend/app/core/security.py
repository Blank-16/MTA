import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator

from app.core.config import settings

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    sub: str
    exp: datetime
    iat: datetime
    type: str = "access"

    @field_validator("type")
    @classmethod
    def must_be_access(cls, v: str) -> str:
        if v != "access":
            raise ValueError("Only 'access' tokens are accepted here")
        return v


class TokenError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: UUID, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        # nbf 5s in the past: handles clock skew on distributed nodes
        "nbf": now - timedelta(seconds=5),
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Raises TokenError on any failure — never returns None."""
    try:
        raw = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError:
        logger.debug("JWT expired")
        raise TokenError("Token has expired") from None
    except JWTError as exc:
        logger.warning("JWT decode error: %s", exc)
        raise TokenError("Invalid token") from exc
    try:
        return TokenPayload(**raw)
    except Exception as exc:
        logger.warning("JWT payload validation failed: %s", exc)
        raise TokenError("Malformed token payload") from exc
