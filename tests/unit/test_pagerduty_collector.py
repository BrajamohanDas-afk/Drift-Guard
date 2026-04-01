import httpx
import pytest

import app.services.evidence.pagerduty_collector as pd_module
from app.services.evidence.pagerduty_collector import PagerDutyCollector


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, raise_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_error = raise_error

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error


class FakeAsyncClient:
    def __init__(self, timeout=None, follow_redirects=None):
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
        return FakeResponse(status_code=200, payload={"services": []})


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB fixture for pure unit tests
    yield


async def test_collect_service_missing_token():
    collector = PagerDutyCollector(api_token="")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error == "PagerDuty API token not configured"


async def test_collect_service_empty_name():
    collector = PagerDutyCollector(api_token="pd-token")
    result = await collector.collect_service("   ")

    assert result.exists is False
    assert result.error == "service_name must not be empty"


async def test_collect_service_success_exact_match(monkeypatch):
    captured = {}

    class SuccessClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            return FakeResponse(
                status_code=200,
                payload={
                    "services": [
                        {
                            "id": "P12345",
                            "name": "payments-api",
                            "html_url": "https://acme.pagerduty.com/service-directory/P12345",
                            "escalation_policy": {"id": "PEP123"},
                        }
                    ]
                },
            )

    monkeypatch.setattr(pd_module.httpx, "AsyncClient", SuccessClient)

    collector = PagerDutyCollector(api_token="pd-token", timeout_seconds=4.0)
    result = await collector.collect_service("payments-api")

    assert captured["url"].endswith("/services")
    assert captured["headers"]["Authorization"] == "Token token=pd-token"
    assert "version=2" in captured["headers"]["Accept"]
    assert captured["params"]["query"] == "payments-api"

    assert result.exists is True
    assert result.service_id == "P12345"
    assert result.service_name == "payments-api"
    assert result.escalation_policy_id == "PEP123"
    assert result.error is None
    assert result.checked_at.tzinfo is not None


async def test_collect_service_no_exact_match(monkeypatch):
    class NoMatchClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            return FakeResponse(
                status_code=200,
                payload={
                    "services": [
                        {"id": "P1", "name": "payments-worker"},
                        {"id": "P2", "name": "checkout-api"},
                    ]
                },
            )

    monkeypatch.setattr(pd_module.httpx, "AsyncClient", NoMatchClient)

    collector = PagerDutyCollector(api_token="pd-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is None


async def test_collect_service_unauthorized(monkeypatch):
    class UnauthorizedClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            return FakeResponse(status_code=401, payload={})

    monkeypatch.setattr(pd_module.httpx, "AsyncClient", UnauthorizedClient)

    collector = PagerDutyCollector(api_token="bad-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error == "Unauthorized: invalid PagerDuty API token"


async def test_collect_service_invalid_json(monkeypatch):
    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    class BadJsonClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            return BadJsonResponse(status_code=200)

    monkeypatch.setattr(pd_module.httpx, "AsyncClient", BadJsonClient)

    collector = PagerDutyCollector(api_token="pd-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "Invalid PagerDuty JSON response" in result.error


async def test_collect_service_http_error(monkeypatch):
    class ErrorClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None, params: dict | None = None):
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(pd_module.httpx, "AsyncClient", ErrorClient)

    collector = PagerDutyCollector(api_token="pd-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "connection failed" in result.error
