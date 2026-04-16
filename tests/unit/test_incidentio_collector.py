import httpx
import pytest

import app.services.evidence.incidentio_collector as incidentio_module
from app.services.evidence.incidentio_collector import IncidentIOCollector


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        raise_error: Exception | None = None,
    ):
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

    async def get(
        self,
        url: str,
        headers: dict | None = None,
        params: dict | None = None,
    ):
        return FakeResponse(status_code=200, payload={"catalog_entries": []})


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


async def test_collect_service_missing_token():
    collector = IncidentIOCollector(api_token="")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error == "incident.io API token not configured"


async def test_collect_service_empty_name():
    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("   ")

    assert result.exists is False
    assert result.error == "service_name must not be empty"


async def test_collect_service_success_exact_match(monkeypatch):
    captured = {}

    class SuccessClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            captured["url"] = url
            captured["headers"] = headers
            captured["params"] = params
            return FakeResponse(
                status_code=200,
                payload={
                    "catalog_entries": [
                        {
                            "id": "01HXYZABCDEF",
                            "name": "payments-api",
                            "catalog_type_id": "01HSERVICECAT",
                            "aliases": ["payments"],
                            "permalink": "https://app.incident.io/acme/catalog/services/payments-api",
                        }
                    ]
                },
            )

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", SuccessClient)

    collector = IncidentIOCollector(
        api_token="io-token",
        catalog_type_id="01HSERVICECAT",
        timeout_seconds=4.0,
    )
    result = await collector.collect_service("payments-api")

    assert captured["url"].endswith("/v3/catalog_entries")
    assert captured["headers"]["Authorization"] == "Bearer io-token"
    assert captured["params"]["identifier"] == "payments-api"
    assert captured["params"]["catalog_type_id"] == "01HSERVICECAT"

    assert result.exists is True
    assert result.entry_id == "01HXYZABCDEF"
    assert result.entry_name == "payments-api"
    assert result.catalog_type_id == "01HSERVICECAT"
    assert result.aliases == ["payments"]
    assert result.permalink is not None
    assert result.error is None
    assert result.checked_at.tzinfo is not None


async def test_collect_service_alias_match(monkeypatch):
    class AliasMatchClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            return FakeResponse(
                status_code=200,
                payload={
                    "catalog_entries": [
                        {
                            "id": "01H1",
                            "name": "payments-service",
                            "aliases": ["payments-api"],
                        }
                    ]
                },
            )

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", AliasMatchClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is True
    assert result.error is None


async def test_collect_service_no_match(monkeypatch):
    class NoMatchClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            return FakeResponse(
                status_code=200,
                payload={
                    "catalog_entries": [
                        {"id": "01H2", "name": "checkout-api"},
                    ]
                },
            )

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", NoMatchClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is None


async def test_collect_service_follows_pagination(monkeypatch):
    calls = {"count": 0}

    class PaginatedClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(
                    status_code=200,
                    payload={
                        "catalog_entries": [{"id": "01H0", "name": "checkout-api"}],
                        "pagination_meta": {"after": "cursor-1"},
                    },
                )
            return FakeResponse(
                status_code=200,
                payload={
                    "catalog_entries": [{"id": "01H1", "name": "payments-api"}],
                    "pagination_meta": {},
                },
            )

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", PaginatedClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert calls["count"] == 2
    assert result.exists is True
    assert result.entry_id == "01H1"


async def test_collect_service_unauthorized(monkeypatch):
    class UnauthorizedClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            return FakeResponse(status_code=401, payload={})

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", UnauthorizedClient)

    collector = IncidentIOCollector(api_token="bad-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error == "Unauthorized: invalid incident.io API token"


async def test_collect_service_non_401_http_status(monkeypatch):
    class TooManyRequestsClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            request = httpx.Request("GET", url)
            response = httpx.Response(status_code=429, request=request)
            return FakeResponse(
                status_code=429,
                payload={},
                raise_error=httpx.HTTPStatusError(
                    "429 Too Many Requests",
                    request=request,
                    response=response,
                ),
            )

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", TooManyRequestsClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "429" in result.error


async def test_collect_service_invalid_json(monkeypatch):
    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    class BadJsonClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            return BadJsonResponse(status_code=200)

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", BadJsonClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "Invalid incident.io JSON response" in result.error


async def test_collect_service_invalid_shape(monkeypatch):
    class BadShapeClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            return FakeResponse(status_code=200, payload=["unexpected", "array"])

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", BadShapeClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error == "Invalid incident.io response shape: expected object"


async def test_collect_service_http_error(monkeypatch):
    class ErrorClient(FakeAsyncClient):
        async def get(
            self,
            url: str,
            headers: dict | None = None,
            params: dict | None = None,
        ):
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(incidentio_module.httpx, "AsyncClient", ErrorClient)

    collector = IncidentIOCollector(api_token="io-token")
    result = await collector.collect_service("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "connection failed" in result.error
