import asyncio
import ipaddress
import socket
from datetime import datetime, timezone
from time import perf_counter
from typing import Optional
from urllib.parse import urlparse

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
            await _validate_safe_probe_url(url)

            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
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
        except ValueError as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            return HttpProbeResult(
                url=url,
                status_code=None,
                response_time_ms=elapsed_ms,
                error=str(exc),
                checked_at=checked_at,
            )


async def _validate_safe_probe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("unsafe HTTP probe target: scheme must be http or https")

    if not parsed.hostname:
        raise ValueError("unsafe HTTP probe target: host is required")

    await asyncio.to_thread(_validate_safe_probe_host, parsed.hostname, parsed.port)


def _validate_safe_probe_host(host: str, port: Optional[int]) -> None:
    addresses = _resolve_probe_host(host, port)
    if not addresses:
        raise ValueError("unsafe HTTP probe target: host did not resolve")

    for address in addresses:
        ip_address = ipaddress.ip_address(address)
        if not ip_address.is_global:
            raise ValueError(
                "unsafe HTTP probe target: host resolves to non-public IP space"
            )


def _resolve_probe_host(host: str, port: Optional[int]) -> set[str]:
    try:
        direct_address = ipaddress.ip_address(host)
    except ValueError:
        direct_address = None

    if direct_address is not None:
        return {str(direct_address)}

    try:
        results = socket.getaddrinfo(
            host,
            443 if port is None else port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise ValueError("unsafe HTTP probe target: host did not resolve") from exc

    return {result[4][0] for result in results}
