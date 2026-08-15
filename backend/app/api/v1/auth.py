import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.api.deps import DbConn
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth import LoginRequest, TokenPair, UserCreate, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Module-level — not recreated on every login call
_DUMMY_HASH = "$2b$12$KIXiPBmEFgcSVKCVwBX4AOEe5yEgHjP0i8.JFzGwVwrqX9vRqnxCW"

_REFRESH_TOKEN_EXPIRE_DAYS = 30
_COOKIE_NAME = "refresh_token"


def _hash_token(token: str) -> str:
    """SHA-256 of the raw token — stored in DB, not the raw value."""
    return hashlib.sha256(token.encode()).hexdigest()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,  # HTTPS-only in production
        samesite="lax",
        max_age=_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",  # Must be "/" — BFF is at /api/auth, not /v1/auth
    )


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbConn) -> UserResponse:
    async with await db.execute(
        "SELECT id FROM users WHERE email = %s", (payload.email,)
    ) as cur:
        if await cur.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user_id = uuid.uuid4()
    now = datetime.now(UTC)
    try:
        await db.execute(
            "INSERT INTO users (id, email, hashed_password, created_at) VALUES (%s, %s, %s, %s)",
            (str(user_id), payload.email, hash_password(payload.password), now),
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # UNIQUE constraint violation — concurrent registration with same email
        # psycopg3 wraps this as psycopg.errors.UniqueViolation (subclass of IntegrityError)
        err_str = str(exc).lower()
        if "unique" in err_str or "duplicate" in err_str or "already exists" in err_str:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from exc
        logger.error("Register failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Registration failed") from exc

    logger.info("User registered id=%s email=%s", user_id, payload.email)
    return UserResponse(id=user_id, email=payload.email, is_active=True, created_at=now)


@router.post("/auth/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, response: Response, db: DbConn) -> TokenPair:
    async with await db.execute(
        "SELECT id, hashed_password, is_active FROM users WHERE email = %s", (payload.email,)
    ) as cur:
        row = await cur.fetchone()

    # Timing-safe: always run bcrypt even when user not found.
    # Skipping bcrypt on missing user leaks email existence via response time delta.
    candidate_hash = row["hashed_password"] if row else _DUMMY_HASH  # type: ignore
    password_ok = verify_password(payload.password, candidate_hash)

    if row is None or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not row["is_active"]:  # type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    user_id = uuid.UUID(row["id"])  # type: ignore
    access_token = create_access_token(user_id)

    # Issue refresh token
    raw_refresh = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)
    from app.core.rate_limiter import _get_client_ip
    ip = _get_client_ip(request)

    try:
        await db.execute(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent, ip_address)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (str(user_id), _hash_token(raw_refresh), expires_at,
             request.headers.get("user-agent", "")[:256], ip),
        )
        await db.execute(
            "UPDATE users SET last_login = %s WHERE id = %s",
            (datetime.now(UTC), str(user_id)),
        )
        await db.commit()
    except Exception as exc:
        logger.error("Login token issuance failed: %s", exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Login failed") from exc

    _set_refresh_cookie(response, raw_refresh)
    logger.info("User logged in id=%s", user_id)

    return TokenPair(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh_token(
    response: Response,
    db: DbConn,
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> TokenPair:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    token_hash = _hash_token(refresh_token)
    now = datetime.now(UTC)

    async with await db.execute(
        """
        SELECT rt.id, rt.user_id, u.is_active
        FROM refresh_tokens rt
        JOIN users u ON rt.user_id = u.id
        WHERE rt.token_hash = %s AND rt.revoked = FALSE AND rt.expires_at > %s
        """,
        (token_hash, now),
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        # Invalidate cookie on invalid token — could indicate token theft
        response.delete_cookie(_COOKIE_NAME, path="/")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    if not row["is_active"]:  # type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    user_id = uuid.UUID(row["user_id"])  # type: ignore

    # Rotate: revoke old token, issue new one
    new_raw = secrets.token_urlsafe(48)
    new_expires = now + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)

    try:
        await db.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s", (row["id"],)  # type: ignore
        )
        await db.execute(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (str(user_id), _hash_token(new_raw), new_expires),
        )
        await db.commit()
    except Exception as exc:
        logger.error("Token rotation failed: %s", exc, exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Token refresh failed") from exc

    _set_refresh_cookie(response, new_raw)
    access_token = create_access_token(user_id)

    return TokenPair(
        access_token=access_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: DbConn,
    refresh_token: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> None:
    if refresh_token:
        token_hash = _hash_token(refresh_token)
        try:
            await db.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = %s", (token_hash,)
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Logout revocation failed (non-fatal): %s", exc)
            await db.rollback()
    response.delete_cookie(_COOKIE_NAME, path="/")
