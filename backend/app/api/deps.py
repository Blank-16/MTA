import logging
from typing import Annotated

import psycopg
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.database import get_db
from app.core.security import TokenError, TokenPayload, decode_access_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def _verify_internal_api_key(
    x_internal_key: Annotated[str | None, Header(alias="x-internal-key")] = None,
) -> None:
    if not x_internal_key or x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal API key")


async def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> TokenPayload:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.reason,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def _get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> TokenPayload | None:
    if credentials is None:
        return None
    try:
        return decode_access_token(credentials.credentials)
    except TokenError as exc:
        logger.debug("Optional auth failed — treating as anonymous: %s", exc.reason)
        return None


DbConn = Annotated[psycopg.AsyncConnection, Depends(get_db)]
CurrentUser = Annotated[TokenPayload, Depends(_get_current_user)]
OptionalUser = Annotated[TokenPayload | None, Depends(_get_optional_user)]
InternalRoute = Depends(_verify_internal_api_key)
