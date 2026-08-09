import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestJWT:
    def test_roundtrip(self):
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = decode_access_token(token)
        assert payload.sub == str(uid)
        assert payload.type == "access"

    def test_expired_token_raises(self):
        from jose import jwt

        from app.core.config import settings

        now = datetime.now(UTC)
        raw = {
            "sub": str(uuid.uuid4()),
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(raw, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError) as exc_info:
            decode_access_token(token)
        assert "expired" in exc_info.value.reason.lower()

    def test_tampered_token_raises(self):
        uid = uuid.uuid4()
        token = create_access_token(uid)
        # Replace signature segment entirely with random bytes
        parts = token.split(".")
        import base64
        import os
        bad_sig = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        parts[2] = bad_sig
        bad_token = ".".join(parts)
        with pytest.raises(TokenError):
            decode_access_token(bad_token)

    def test_garbage_token_raises(self):
        with pytest.raises(TokenError):
            decode_access_token("not.a.token")

    def test_extra_claims_preserved(self):
        uid = uuid.uuid4()
        token = create_access_token(uid, extra_claims={"role": "admin"})
        from jose import jwt

        from app.core.config import settings
        raw = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert raw.get("role") == "admin"


class TestPasswordHashing:
    def test_verify_correct_password(self):
        hashed = hash_password("SecurePass123!")
        assert verify_password("SecurePass123!", hashed)

    def test_reject_wrong_password(self):
        hashed = hash_password("SecurePass123!")
        assert not verify_password("WrongPass", hashed)

    def test_hashes_are_unique(self):
        # Same password → different hash (bcrypt uses random salt)
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_verify_against_unique_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert verify_password("same", h1)
        assert verify_password("same", h2)
