from datetime import datetime, timezone
from time import perf_counter
from typing import Optional

import httpx
from pydantic import BaseModel, Field


class HttpProbeResult(BaseModel):
    url: str
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HttpProbeCollector:
    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    async def collect(self, url: str) -> HttpProbeResult:
        checked_at = datetime.now(timezone.utc)
        started = perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)

            elapsed_ms = int((perf_counter() - started) * 1000)
            return HttpProbeResult(
                url=url,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                error=None,
                checked_at=checked_at,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            return HttpProbeResult(
                url=url,
                status_code=None,
                response_time_ms=elapsed_ms,
                error=str(exc),
                checked_at=checked_at,
            )
