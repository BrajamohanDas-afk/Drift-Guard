import httpx
import pytest

import app.services.evidence.http_collector as http_collector_module
from app.services.evidence.http_collector import HttpProbeCollector


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeAsyncClient:
    def __init__(self, timeout=None, follow_redirects=None):
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return FakeResponse(status_code=200)


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB reset fixture: these are pure unit tests.
    yield


async def test_collect_success(monkeypatch):
    captured = {}

    class CapturingClient(FakeAsyncClient):
        def __init__(self, timeout=None, follow_redirects=None):
            super().__init__(timeout=timeout, follow_redirects=follow_redirects)
            captured["timeout"] = timeout
            captured["follow_redirects"] = follow_redirects

    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", CapturingClient)

    collector = HttpProbeCollector(timeout_seconds=3.0)
    result = await collector.collect("https://example.com/health")

    assert captured["timeout"] == 3.0
    assert captured["follow_redirects"] is True
    assert result.url == "https://example.com/health"
    assert result.status_code == 200
    assert result.error is None
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0
    assert result.checked_at.tzinfo is not None
    assert result.checked_at.utcoffset() is not None


async def test_collect_non_200_status_is_still_success(monkeypatch):
    class Non200Client(FakeAsyncClient):
        async def get(self, url: str):
            return FakeResponse(status_code=404)

    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", Non200Client)

    collector = HttpProbeCollector()
    result = await collector.collect("https://example.com/missing")

    assert result.status_code == 404
    assert result.error is None
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0


async def test_collect_http_error_returns_error(monkeypatch):
    class ErrorClient(FakeAsyncClient):
        async def get(self, url: str):
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", ErrorClient)

    collector = HttpProbeCollector()
    result = await collector.collect("https://example.com/down")

    assert result.status_code is None
    assert result.error is not None
    assert "connection failed" in result.error
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0
