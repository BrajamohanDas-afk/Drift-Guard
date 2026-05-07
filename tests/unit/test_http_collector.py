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


@pytest.fixture
def allow_public_dns(monkeypatch):
    def fake_getaddrinfo(host, port, type=None, proto=None):
        return [
            (
                http_collector_module.socket.AF_INET,
                http_collector_module.socket.SOCK_STREAM,
                http_collector_module.socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(http_collector_module.socket, "getaddrinfo", fake_getaddrinfo)


async def test_collect_success(monkeypatch, allow_public_dns):
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
    assert captured["follow_redirects"] is False
    assert result.url == "https://example.com/health"
    assert result.status_code == 200
    assert result.error is None
    assert result.response_time_ms is not None
    assert result.response_time_ms >= 0
    assert result.checked_at.tzinfo is not None
    assert result.checked_at.utcoffset() is not None


async def test_collect_non_200_status_is_still_success(monkeypatch, allow_public_dns):
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


async def test_collect_http_error_returns_error(monkeypatch, allow_public_dns):
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


async def test_collect_rejects_non_http_scheme(monkeypatch):
    class UnexpectedClient(FakeAsyncClient):
        def __init__(self, timeout=None, follow_redirects=None):
            raise AssertionError("HTTP client should not be opened")

    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", UnexpectedClient)

    collector = HttpProbeCollector()
    result = await collector.collect("file:///etc/passwd")

    assert result.status_code is None
    assert result.error == "unsafe HTTP probe target: scheme must be http or https"


async def test_collect_rejects_private_direct_ip(monkeypatch):
    class UnexpectedClient(FakeAsyncClient):
        def __init__(self, timeout=None, follow_redirects=None):
            raise AssertionError("HTTP client should not be opened")

    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", UnexpectedClient)

    collector = HttpProbeCollector()
    result = await collector.collect("http://127.0.0.1:8000/health")

    assert result.status_code is None
    assert (
        result.error
        == "unsafe HTTP probe target: host resolves to non-public IP space"
    )


async def test_collect_rejects_hostname_resolving_to_private_ip(monkeypatch):
    def fake_getaddrinfo(host, port, type=None, proto=None):
        return [
            (
                http_collector_module.socket.AF_INET,
                http_collector_module.socket.SOCK_STREAM,
                http_collector_module.socket.IPPROTO_TCP,
                "",
                ("10.0.0.5", port),
            )
        ]

    class UnexpectedClient(FakeAsyncClient):
        def __init__(self, timeout=None, follow_redirects=None):
            raise AssertionError("HTTP client should not be opened")

    monkeypatch.setattr(http_collector_module.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(http_collector_module.httpx, "AsyncClient", UnexpectedClient)

    collector = HttpProbeCollector()
    result = await collector.collect("https://metadata.internal/health")

    assert result.status_code is None
    assert (
        result.error
        == "unsafe HTTP probe target: host resolves to non-public IP space"
    )
