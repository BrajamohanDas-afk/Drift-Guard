import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Header, HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

_hits_by_subject: dict[str, Deque[float]] = defaultdict(deque)


def _rate_limit_subject(request: Request, api_key: str | None) -> str:
    if api_key:
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        return f"api-key:{key_hash}"

    client = getattr(request, "client", None)
    host = getattr(client, "host", None) or "unknown"
    return f"ip:{host}"


def reset_rate_limits_for_tests() -> None:
    _hits_by_subject.clear()


async def require_heavy_endpoint_rate_limit(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    limit = settings.heavy_endpoint_rate_limit
    window_seconds = settings.rate_limit_window_seconds
    if limit <= 0 or window_seconds <= 0:
        return

    now = time.monotonic()
    cutoff = now - window_seconds
    subject = _rate_limit_subject(request, x_api_key)
    hits = _hits_by_subject[subject]

    while hits and hits[0] <= cutoff:
        hits.popleft()

    if len(hits) >= limit:
        logger.warning(
            "Heavy endpoint rate limit exceeded",
            extra={
                "rate_limit_subject": subject,
                "path": str(getattr(request, "url", "")),
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    hits.append(now)
