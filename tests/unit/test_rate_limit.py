from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dependencies.rate_limit import (
    require_heavy_endpoint_rate_limit,
    reset_rate_limits_for_tests,
)


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


def _request(path: str = "/v1/documents/upload"):
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        url=path,
    )


@pytest.mark.asyncio
async def test_heavy_endpoint_rate_limit_rejects_excess_requests(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.rate_limit.settings.heavy_endpoint_rate_limit",
        2,
    )
    monkeypatch.setattr(
        "app.dependencies.rate_limit.settings.rate_limit_window_seconds",
        60,
    )

    await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-1")
    await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-1")

    with pytest.raises(HTTPException) as exc_info:
        await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-1")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_heavy_endpoint_rate_limit_is_per_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.rate_limit.settings.heavy_endpoint_rate_limit",
        1,
    )
    monkeypatch.setattr(
        "app.dependencies.rate_limit.settings.rate_limit_window_seconds",
        60,
    )

    await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-1")
    await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-2")


@pytest.mark.asyncio
async def test_heavy_endpoint_rate_limit_can_be_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.dependencies.rate_limit.settings.heavy_endpoint_rate_limit",
        0,
    )

    for _ in range(5):
        await require_heavy_endpoint_rate_limit(_request(), x_api_key="key-1")
