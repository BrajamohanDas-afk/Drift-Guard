import importlib
import uuid
from types import SimpleNamespace

import pytest

notification_task_module = importlib.import_module("app.workers.notification_task")


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


class _FakeSessionContext:
    def __init__(self, session_obj):
        self._session_obj = session_obj

    async def __aenter__(self):
        return self._session_obj

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_notification_task_sends_delivery(monkeypatch):
    delivery_id = uuid.uuid4()
    fake_session = object()
    delivery = SimpleNamespace(
        id=delivery_id,
        status="delivered",
        event_type="alert_created",
        channel="email",
        attempts=1,
    )

    async def fake_send_delivery(session, *, delivery_id):
        assert session is fake_session
        assert delivery_id == delivery.id
        return delivery

    monkeypatch.setattr(
        notification_task_module,
        "AsyncSessionLocal",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        notification_task_module.notification_service,
        "send_delivery",
        fake_send_delivery,
    )

    result = await notification_task_module.notification_task(
        {},
        delivery_id=str(delivery_id),
    )

    assert result == {
        "status": "delivered",
        "delivery_id": str(delivery_id),
        "event_type": "alert_created",
        "channel": "email",
        "attempts": 1,
    }


@pytest.mark.asyncio
async def test_notification_task_rejects_invalid_delivery_id():
    with pytest.raises(ValueError):
        await notification_task_module.notification_task({}, delivery_id="bad-id")
