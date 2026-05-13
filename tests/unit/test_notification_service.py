import datetime
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.alerting.notification_service as notification_module
from app.models.alert import Alert
from app.services.alerting.notification_service import (
    NotificationSecurityError,
    NotificationService,
    _idempotency_key,
    _redact_payload,
    _safe_target,
    _validate_webhook_url,
)


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB fixture: these are pure unit tests.
    yield


def test_idempotency_key_is_stable_and_target_is_sanitized():
    audit_job_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    first = _idempotency_key(
        event_type="alert_created",
        audit_job_id=audit_job_id,
        alert_id=alert_id,
        channel="slack",
        target="https://hooks.slack.com/services/TOKEN?secret=value",
    )
    second = _idempotency_key(
        event_type="alert_created",
        audit_job_id=audit_job_id,
        alert_id=alert_id,
        channel="slack",
        target="https://hooks.slack.com/services/TOKEN?secret=other",
    )

    assert first == second
    assert "secret" not in first


def test_redact_payload_removes_sensitive_values_and_url_credentials():
    payload = {
        "authorization": "Bearer secret-token",
        "nested": {
            "api_key": "abc123",
            "url": "https://user:pass@example.com/path?token=abc",
        },
    }

    redacted = _redact_payload(payload)

    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["url"] == "https://example.com/path"
    assert "secret-token" not in str(redacted)
    assert "user:pass" not in str(redacted)
    assert "abc123" not in str(redacted)


def test_safe_target_strips_query_and_credentials():
    assert (
        _safe_target("https://user:pass@example.com:443/path?token=abc")
        == "https://example.com:443/path"
    )


def test_should_notify_alert_respects_minimum_severity():
    service = NotificationService(channels="slack", min_severity="high")

    assert service._should_notify_alert(SimpleNamespace(severity="critical")) is True
    assert service._should_notify_alert(SimpleNamespace(severity="high")) is True
    assert service._should_notify_alert(SimpleNamespace(severity="medium")) is False


@pytest.mark.asyncio
async def test_validate_webhook_url_rejects_unsafe_targets():
    for url in (
        "file:///tmp/payload",
        "https://user:pass@example.com/hook",
        "http://127.0.0.1/hook",
        "http://169.254.169.254/latest/meta-data",
    ):
        with pytest.raises(NotificationSecurityError):
            await _validate_webhook_url(url)


@pytest.mark.asyncio
async def test_validate_webhook_url_rejects_hostname_with_private_dns(monkeypatch):
    def fake_getaddrinfo(host, port, type=None, proto=None):
        return [
            (
                notification_module.socket.AF_INET,
                notification_module.socket.SOCK_STREAM,
                notification_module.socket.IPPROTO_TCP,
                "",
                ("203.0.113.1", port),
            ),
            (
                notification_module.socket.AF_INET,
                notification_module.socket.SOCK_STREAM,
                notification_module.socket.IPPROTO_TCP,
                "",
                ("10.0.0.1", port),
            ),
        ]

    monkeypatch.setattr(notification_module.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(NotificationSecurityError):
        await _validate_webhook_url("https://hooks.example.com/notify")


@pytest.mark.asyncio
async def test_write_email_sink_appends_jsonl():
    sink_path = Path("C:/tmp") / f"drift-guard-notifications-{uuid.uuid4()}.jsonl"
    service = NotificationService(email_sink_path=str(sink_path))

    await service._write_email_sink({"event_type": "alert_created", "value": 1})

    assert sink_path.read_text(encoding="utf-8").strip() == (
        '{"event_type":"alert_created","value":1}'
    )
    sink_path.unlink(missing_ok=True)


def test_alert_payload_is_minimal_and_serializable():
    audit_job = SimpleNamespace(id=uuid.uuid4())
    alert = Alert(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        rule_type="owner_missing",
        severity="high",
        message="Owner is missing",
        evidence={"missing_entity_type": "owner"},
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )

    payload = NotificationService()._alert_payload(
        alert=alert,
        audit_job=audit_job,
    )

    assert payload["event_type"] == "alert_created"
    assert payload["alert"]["rule_type"] == "owner_missing"
    assert "raw_content" not in str(payload)
