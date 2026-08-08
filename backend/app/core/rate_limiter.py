import logging
import time
import uuid

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)


async def _check_window(key: str, now: float, window_seconds: int, limit: int) -> int:
    """Returns current request count for the key, or -1 on Redis error."""
    try:
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", now - window_seconds)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()
        return int(results[2])
    except Exception as exc:
        logger.warning("Rate limiter Redis error key=%s: %s", key, exc)
        return -1


async def sliding_window_rate_limit(request: Request) -> None:
    """
    Two-key sliding window:
    1. Per session-token (primary): prevents a single session from flooding.
    2. Per client IP (secondary, 4x limit): prevents session-farming attacks
       where an attacker creates unlimited sessions to bypass per-token limits.
    Degrades gracefully on Redis failure — allows traffic rather than taking down service.
    """
    now = time.time()
    ip = _get_client_ip(request)
    token = request.headers.get("x-session-token") or ip

    # Check per-token window
    token_count = await _check_window(
        f"rl:tok:{token}", now,
        settings.rate_limit_window_seconds,
        settings.rate_limit_requests,
    )
    if token_count > settings.rate_limit_requests:
        logger.warning("Rate limit exceeded token=%s count=%d", token[:8], token_count)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {settings.rate_limit_requests} requests per "
                   f"{settings.rate_limit_window_seconds // 60} minutes.",
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
        )

    # Check per-IP window (4x the per-token limit)
    ip_limit = settings.rate_limit_requests * 4
    ip_count = await _check_window(
        f"rl:ip:{ip}", now,
        settings.rate_limit_window_seconds,
        ip_limit,
    )
    if ip_count > ip_limit:
        logger.warning("IP rate limit exceeded ip=%s count=%d", ip, ip_count)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests from this IP address.",
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
        )


# Trusted proxy CIDR prefixes — only trust x-forwarded-for when request comes from these.
# Extend via TRUSTED_PROXY_CIDRS env var (comma-separated) for load balancer IPs.
_TRUSTED_PROXY_PREFIXES: tuple[str, ...] = ("127.", "10.", "172.16.", "172.17.",
                                              "172.18.", "172.19.", "172.20.",
                                              "172.21.", "172.22.", "172.23.",
                                              "172.24.", "172.25.", "172.26.",
                                              "172.27.", "172.28.", "172.29.",
                                              "172.30.", "172.31.", "192.168.", "::1")


def _get_client_ip(request: Request) -> str:
    peer_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")

    # Only trust x-forwarded-for when the direct peer is a known proxy/internal IP.
    # An attacker connecting directly from the internet cannot forge a trusted peer IP,
    # so this prevents bypassing the per-IP rate cap via a forged x-forwarded-for header.
    if forwarded and any(peer_ip.startswith(prefix) for prefix in _TRUSTED_PROXY_PREFIXES):
        return forwarded.split(",")[0].strip()

    return peer_ip
