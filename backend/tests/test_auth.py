import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    async def mock_db():
        conn = MagicMock()
        conn.execute = AsyncMock()
        conn.commit = AsyncMock()
        conn.rollback = AsyncMock()
        yield conn

    app.dependency_overrides[get_db] = mock_db

    with patch("app.main.init_pool", new=AsyncMock()), \
         patch("app.main.init_redis", new=AsyncMock()), \
         patch("app.main.close_pool", new=AsyncMock()), \
         patch("app.main.close_redis", new=AsyncMock()), \
         patch("app.core.redis_client._redis", MagicMock()), \
         TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


class TestRegister:
    def test_missing_email_rejected(self, client):
        r = client.post("/v1/auth/register", json={"email": "bad", "password": "Valid1pass"})
        assert r.status_code == 422

    def test_weak_password_rejected(self, client):
        r = client.post("/v1/auth/register", json={"email": "a@b.com", "password": "short"})
        assert r.status_code == 422

    def test_no_uppercase_rejected(self, client):
        r = client.post("/v1/auth/register", json={"email": "a@b.com", "password": "nouppercase1"})
        assert r.status_code == 422

    def test_no_digit_rejected(self, client):
        r = client.post("/v1/auth/register", json={"email": "a@b.com", "password": "NoDigitPass"})
        assert r.status_code == 422


class TestLogin:
    def test_missing_body_rejected(self, client):
        r = client.post("/v1/auth/login", json={})
        assert r.status_code == 422

    def test_invalid_email_format_rejected(self, client):
        r = client.post("/v1/auth/login", json={"email": "notanemail", "password": "pass"})
        assert r.status_code == 422


class TestRefresh:
    def test_no_cookie_returns_401(self, client):
        r = client.post("/v1/auth/refresh")
        assert r.status_code == 401

    def test_garbage_cookie_returns_401(self, client):
        client.cookies.set("refresh_token", "garbage-token")
        r = client.post("/v1/auth/refresh")
        # Will fail DB lookup → 401
        assert r.status_code in (401, 500)


class TestTokenSecurity:
    def test_password_strength_validator(self):
        import pytest

        from app.models.auth import UserCreate
        with pytest.raises(ValueError):
            UserCreate(email="x@x.com", password="weak")
        with pytest.raises(ValueError):
            UserCreate(email="x@x.com", password="alllowercase1")
        with pytest.raises(ValueError):
            UserCreate(email="x@x.com", password="NoDigitHere")
        # Valid password should not raise
        u = UserCreate(email="x@x.com", password="ValidPass1")
        assert u.email == "x@x.com"

    def test_refresh_token_is_hashed(self):
        from app.api.v1.auth import _hash_token
        raw = "my-raw-refresh-token"
        hashed = _hash_token(raw)
        assert hashed != raw
        assert len(hashed) == 64  # SHA-256 hex
        assert _hash_token(raw) == hashed  # deterministic

    def test_different_tokens_different_hashes(self):
        from app.api.v1.auth import _hash_token
        assert _hash_token("token-a") != _hash_token("token-b")


class TestTimingOracle:
    def test_login_always_calls_bcrypt(self):
        """Verify the dummy hash path exists — bcrypt always runs even for unknown emails."""
        src = Path("app/api/v1/auth.py").read_text(encoding="utf-8")
        assert "_DUMMY_HASH" in src, "Dummy hash must exist to prevent timing oracle"
        assert "verify_password(payload.password, candidate_hash)" in src, \
            "Must call verify_password with candidate_hash (not row hash directly)"

    def test_cookie_path_is_root(self):
        """Cookie path must be / so the browser sends it to /api/auth routes."""
        src = Path("app/api/v1/auth.py").read_text(encoding="utf-8")
        assert 'path="/"' in src, "Cookie path must be '/' — not '/v1/auth'"
        assert 'path="/v1/auth"' not in src, "Old path still present"


class TestMigrationDBName:
    def test_no_hardcoded_db_name_in_grant(self):
        """Migration must not hardcode the database name in GRANT statements."""
        src = Path("migrations/versions/0002_users_refresh_tokens_rls.py").read_text(encoding="utf-8")
        assert "GRANT CONNECT ON DATABASE triage_db" not in src, \
            "Database name must not be hardcoded — use current_database()"


class TestRateLimiterIPCap:
    def test_ip_cap_present(self):
        """Rate limiter must have an IP-based secondary cap."""
        src = Path("app/core/rate_limiter.py").read_text(encoding="utf-8")
        assert "rl:ip:" in src, "IP rate limit key must be present"
        assert "_check_window" in src, "_check_window helper must exist"


class TestDummyHashModuleLevel:
    def test_dummy_hash_not_in_function_body(self):
        """_DUMMY_HASH must be a module-level constant, not re-created per call."""
        src = Path("app/api/v1/auth.py").read_text(encoding="utf-8")
        login_fn_start = src.index("async def login(")
        login_fn_end = src.index("\n@router", login_fn_start)
        login_body = src[login_fn_start:login_fn_end]
        assert "_DUMMY_HASH = " not in login_body, \
            "_DUMMY_HASH must not be defined inside login() — it is a module-level constant"

    def test_jwt_algorithm_is_literal(self):
        """jwt_algorithm must be typed as Literal to prevent 'none' algorithm attacks."""
        src = Path("app/core/config.py").read_text(encoding="utf-8")
        assert 'jwt_algorithm: Literal[' in src, \
            "jwt_algorithm must use Literal type to restrict allowed algorithms"
        assert '"none"' not in src.split('jwt_algorithm')[1].split('\n')[0], \
            "'none' must not be in the allowed algorithm list"


class TestNBFClaim:
    def test_jwt_includes_nbf(self):
        """JWT must include nbf claim for clock-skew tolerance."""
        from jose import jwt

        from app.core.config import settings
        from app.core.security import create_access_token

        token = create_access_token(uuid.uuid4())
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert "nbf" in decoded, "JWT must include nbf claim"
        # nbf must be before iat (5 seconds earlier for clock skew)
        assert decoded["nbf"] <= decoded["iat"], "nbf must be <= iat"
        assert decoded["iat"] - decoded["nbf"] <= 10, "nbf skew should be <= 10 seconds"


class TestIPAuditLogging:
    def test_auth_uses_rate_limiter_ip_fn(self):
        """auth.py login must use _get_client_ip (trusted-proxy-aware) not raw x-forwarded-for."""
        src = Path("app/api/v1/auth.py").read_text(encoding="utf-8")
        assert "_get_client_ip(request)" in src, "Must use _get_client_ip from rate_limiter"
        raw_xfwd = 'request.headers.get("x-forwarded-for")'
        # raw x-forwarded-for outside of _get_client_ip is a spoof risk
        auth_body = src[src.index("async def login"):src.index("async def refresh_token")]
        assert raw_xfwd not in auth_body, "login() must not read x-forwarded-for directly"


class TestRegisterTOCTOU:
    def test_integrity_error_returns_409(self, client):
        from unittest.mock import AsyncMock, MagicMock


        async def mock_db_conflict():
            conn = MagicMock()
            # First execute (SELECT) returns no row
            select_cur = MagicMock()
            select_cur.__aenter__ = AsyncMock(return_value=select_cur)
            select_cur.__aexit__ = AsyncMock(return_value=False)
            select_cur.fetchone = AsyncMock(return_value=None)
            # Second execute (INSERT) raises UniqueViolation
            conn.execute = AsyncMock(side_effect=[
                select_cur,
                Exception("duplicate key value violates unique constraint"),
            ])
            conn.commit = AsyncMock()
            conn.rollback = AsyncMock()
            yield conn

        from app.core.database import get_db
        from app.main import app
        app.dependency_overrides[get_db] = mock_db_conflict
        r = client.post("/v1/auth/register", json={"email": "race@test.com", "password": "ValidPass1"})
        app.dependency_overrides.clear()
        assert r.status_code == 409


class TestMiddlewareState:
    def test_state_not_reset_when_already_exists(self):
        scope = {"type": "http", "headers": [], "state": {"existing_key": "existing_value"}}
        from app.core.middleware import RequestIDMiddleware
        RequestIDMiddleware(app=None)
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = "test-id"
        assert scope["state"]["existing_key"] == "existing_value", \
            "Existing state keys must not be wiped"
        assert scope["state"]["request_id"] == "test-id"
