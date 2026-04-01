import httpx
import pytest

import app.services.evidence.kubernetes_collector as k8s_module
from app.services.evidence.kubernetes_collector import KubernetesCollector


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
    def __init__(self, timeout=None, verify=None, follow_redirects=None):
        self.timeout = timeout
        self.verify = verify
        self.follow_redirects = follow_redirects

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers: dict | None = None):
        return FakeResponse(status_code=200, payload={})


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB reset fixture: these are pure unit tests.
    yield


async def test_collect_deployment_missing_api_url():
    collector = KubernetesCollector(api_url="", bearer_token="token")
    result = await collector.collect_deployment("payments-api")

    assert result.exists is False
    assert result.error == "Kubernetes API URL is not configured"


async def test_collect_deployment_missing_token():
    collector = KubernetesCollector(api_url="https://k8s.example.com", bearer_token="")
    result = await collector.collect_deployment("payments-api")

    assert result.exists is False
    assert result.error == "Kubernetes bearer token is not configured"


async def test_collect_deployment_empty_deployment():
    collector = KubernetesCollector(
        api_url="https://k8s.example.com",
        bearer_token="token",
    )
    result = await collector.collect_deployment("   ")

    assert result.exists is False
    assert result.error == "deployment must not be empty"


async def test_collect_deployment_success(monkeypatch):
    captured = {}

    class SuccessClient(FakeAsyncClient):
        def __init__(self, timeout=None, verify=None, follow_redirects=None):
            super().__init__(
                timeout=timeout,
                verify=verify,
                follow_redirects=follow_redirects,
            )
            captured["timeout"] = timeout
            captured["verify"] = verify
            captured["follow_redirects"] = follow_redirects

        async def get(self, url: str, headers: dict | None = None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse(
                status_code=200,
                payload={
                    "metadata": {
                        "name": "payments-api",
                        "namespace": "prod",
                        "uid": "deploy-uid-123",
                    },
                    "status": {
                        "replicas": 3,
                        "updatedReplicas": 3,
                        "readyReplicas": 3,
                        "availableReplicas": 3,
                        "unavailableReplicas": 0,
                    },
                },
            )

    monkeypatch.setattr(k8s_module.httpx, "AsyncClient", SuccessClient)

    collector = KubernetesCollector(
        api_url="https://k8s.example.com/",
        bearer_token="token-123",
        timeout_seconds=4.0,
        verify_ssl=False,
    )
    result = await collector.collect_deployment("payments-api", namespace="prod")

    assert captured["timeout"] == 4.0
    assert captured["verify"] is False
    assert captured["follow_redirects"] is True
    assert (
        captured["url"]
        == "https://k8s.example.com/apis/apps/v1/namespaces/prod/deployments/payments-api"
    )
    assert captured["headers"]["Authorization"] == "Bearer token-123"

    assert result.exists is True
    assert result.deployment_uid == "deploy-uid-123"
    assert result.replicas == 3
    assert result.ready_replicas == 3
    assert result.available_replicas == 3
    assert result.error is None
    assert result.checked_at.tzinfo is not None
    assert result.checked_at.utcoffset() is not None


async def test_collect_deployment_not_found(monkeypatch):
    class NotFoundClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None):
            return FakeResponse(status_code=404)

    monkeypatch.setattr(k8s_module.httpx, "AsyncClient", NotFoundClient)

    collector = KubernetesCollector(
        api_url="https://k8s.example.com",
        bearer_token="token",
    )
    result = await collector.collect_deployment("missing-deploy", namespace="prod")

    assert result.exists is False
    assert result.error is None


async def test_collect_deployment_unauthorized(monkeypatch):
    class UnauthorizedClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None):
            return FakeResponse(status_code=401)

    monkeypatch.setattr(k8s_module.httpx, "AsyncClient", UnauthorizedClient)

    collector = KubernetesCollector(
        api_url="https://k8s.example.com",
        bearer_token="bad-token",
    )
    result = await collector.collect_deployment("payments-api")

    assert result.exists is False
    assert result.error == "Unauthorized: invalid Kubernetes bearer token"


async def test_collect_deployment_invalid_json(monkeypatch):
    class BadJsonResponse(FakeResponse):
        def json(self):
            raise ValueError("bad json")

    class BadJsonClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None):
            return BadJsonResponse(status_code=200)

    monkeypatch.setattr(k8s_module.httpx, "AsyncClient", BadJsonClient)

    collector = KubernetesCollector(
        api_url="https://k8s.example.com",
        bearer_token="token",
    )
    result = await collector.collect_deployment("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "Invalid Kubernetes JSON response" in result.error


async def test_collect_deployment_http_error(monkeypatch):
    class ErrorClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict | None = None):
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(k8s_module.httpx, "AsyncClient", ErrorClient)

    collector = KubernetesCollector(
        api_url="https://k8s.example.com",
        bearer_token="token",
    )
    result = await collector.collect_deployment("payments-api")

    assert result.exists is False
    assert result.error is not None
    assert "connection failed" in result.error
