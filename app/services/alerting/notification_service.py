import asyncio
import datetime
import ipaddress
import json
import logging
import socket
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.alert import Alert
from app.models.audit_job import AuditJob
from app.models.notification_delivery import NotificationDelivery

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
ALERT_CHANNELS = {"slack", "email"}
MAX_ATTEMPTS = 3


class NotificationDeliveryError(RuntimeError):
    pass


class NotificationSecurityError(NotificationDeliveryError):
    pass


class NotificationService:
    def __init__(
        self,
        *,
        channels: str | None = None,
        min_severity: str | None = None,
        slack_webhook_url: str | None = None,
        completion_webhook_url: str | None = None,
        email_sink_path: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.channels = _parse_channels(
            settings.notification_channels if channels is None else channels
        )
        self.min_severity = (
            settings.notification_min_severity
            if min_severity is None
            else min_severity
        ).strip().lower()
        self.slack_webhook_url = (
            settings.slack_webhook_url
            if slack_webhook_url is None
            else slack_webhook_url
        )
        self.completion_webhook_url = (
            settings.completion_webhook_url
            if completion_webhook_url is None
            else completion_webhook_url
        )
        self.email_sink_path = (
            settings.email_sink_path if email_sink_path is None else email_sink_path
        )
        self.timeout_seconds = (
            settings.notification_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )

    async def create_audit_notifications(
        self,
        db: AsyncSession,
        *,
        audit_job: AuditJob,
        created_alerts: list[Alert] | tuple[Alert, ...],
        audit_summary: dict[str, Any],
    ) -> list[NotificationDelivery]:
        deliveries: list[NotificationDelivery] = []
        for alert in created_alerts:
            if not self._should_notify_alert(alert):
                continue

            payload = self._alert_payload(alert=alert, audit_job=audit_job)
            for channel in sorted(self.channels & ALERT_CHANNELS):
                deliveries.append(
                    await self._create_delivery(
                        db,
                        audit_job_id=audit_job.id,
                        alert_id=alert.id,
                        event_type="alert_created",
                        channel=channel,
                        target=self._target_for_channel(channel),
                        payload=payload,
                    )
                )

        if self.completion_webhook_url:
            deliveries.append(
                await self._create_delivery(
                    db,
                    audit_job_id=audit_job.id,
                    alert_id=None,
                    event_type="audit_completed",
                    channel="completion_webhook",
                    target=self.completion_webhook_url,
                    payload=self._completion_payload(
                        audit_job=audit_job,
                        audit_summary=audit_summary,
                    ),
                )
            )

        return deliveries

    async def send_delivery(
        self,
        db: AsyncSession,
        *,
        delivery_id: uuid.UUID,
    ) -> NotificationDelivery:
        delivery = await db.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise NotificationDeliveryError("Notification delivery not found")
        if delivery.status == "delivered":
            return delivery
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
            delivery.error = "maximum delivery attempts reached"
            await db.commit()
            await db.refresh(delivery)
            return delivery

        delivery.status = "sending"
        delivery.attempts += 1
        delivery.error = None
        await db.commit()
        await db.refresh(delivery)

        try:
            await self._deliver(
                channel=delivery.channel,
                target=delivery.target,
                payload=delivery.payload,
            )
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = _safe_error_message(exc)
            await db.commit()
            await db.refresh(delivery)
            logger.warning(
                "Notification delivery failed",
                extra={
                    "delivery_id": str(delivery.id),
                    "audit_job_id": (
                        str(delivery.audit_job_id) if delivery.audit_job_id else None
                    ),
                    "alert_id": str(delivery.alert_id) if delivery.alert_id else None,
                    "channel": delivery.channel,
                    "event_type": delivery.event_type,
                },
                exc_info=True,
            )
            raise

        delivery.status = "delivered"
        delivery.delivered_at = datetime.datetime.now(datetime.timezone.utc)
        delivery.error = None
        await db.commit()
        await db.refresh(delivery)
        return delivery

    def _should_notify_alert(self, alert: Alert) -> bool:
        min_rank = SEVERITY_RANK.get(self.min_severity, SEVERITY_RANK["low"])
        alert_rank = SEVERITY_RANK.get((alert.severity or "").lower(), -1)
        return alert_rank >= min_rank

    async def _create_delivery(
        self,
        db: AsyncSession,
        *,
        audit_job_id: uuid.UUID | None,
        alert_id: uuid.UUID | None,
        event_type: str,
        channel: str,
        target: str | None,
        payload: dict[str, Any],
    ) -> NotificationDelivery:
        idempotency_key = _idempotency_key(
            event_type=event_type,
            audit_job_id=audit_job_id,
            alert_id=alert_id,
            channel=channel,
            target=target,
        )
        existing = await self._get_by_idempotency_key(db, idempotency_key)
        if existing is not None:
            return existing

        delivery = NotificationDelivery(
            audit_job_id=audit_job_id,
            alert_id=alert_id,
            idempotency_key=idempotency_key,
            event_type=event_type,
            channel=channel,
            target=_safe_target(target),
            status="pending",
            attempts=0,
            payload=_redact_payload(payload),
            error=None,
        )
        db.add(delivery)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await self._get_by_idempotency_key(db, idempotency_key)
            if existing is not None:
                return existing
            raise
        await db.refresh(delivery)
        return delivery

    async def _get_by_idempotency_key(
        self, db: AsyncSession, idempotency_key: str
    ) -> NotificationDelivery | None:
        result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.idempotency_key == idempotency_key
            )
        )
        return result.scalars().first()

    async def _deliver(
        self,
        *,
        channel: str,
        target: str | None,
        payload: dict[str, Any],
    ) -> None:
        if channel == "slack":
            if not self.slack_webhook_url:
                raise NotificationDeliveryError("Slack webhook URL is not configured")
            await self._post_webhook(self.slack_webhook_url, _slack_payload(payload))
            return

        if channel == "email":
            if not self.email_sink_path:
                raise NotificationDeliveryError("Email sink path is not configured")
            await self._write_email_sink(payload)
            return

        if channel == "completion_webhook":
            completion_target = self.completion_webhook_url or target
            if not completion_target:
                raise NotificationDeliveryError(
                    "Completion webhook URL is not configured"
                )
            await self._post_webhook(completion_target, payload)
            return

        raise NotificationDeliveryError(f"Unsupported notification channel: {channel}")

    async def _post_webhook(self, url: str, payload: dict[str, Any]) -> None:
        await _validate_webhook_url(url)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.post(url, json=payload)
        response.raise_for_status()

    async def _write_email_sink(self, payload: dict[str, Any]) -> None:
        path = Path(self.email_sink_path or "")
        if not path:
            raise NotificationDeliveryError("Email sink path is not configured")
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        await asyncio.to_thread(_append_line, path, line)

    def _target_for_channel(self, channel: str) -> str | None:
        if channel == "slack":
            return self.slack_webhook_url
        if channel == "email":
            return self.email_sink_path
        return None

    def _alert_payload(self, *, alert: Alert, audit_job: AuditJob) -> dict[str, Any]:
        return {
            "event_type": "alert_created",
            "audit_job_id": str(audit_job.id),
            "alert": {
                "id": str(alert.id),
                "document_id": str(alert.document_id) if alert.document_id else None,
                "rule_type": alert.rule_type,
                "severity": alert.severity,
                "message": alert.message,
                "created_at": alert.created_at.isoformat(),
                "evidence": alert.evidence or {},
            },
        }

    def _completion_payload(
        self, *, audit_job: AuditJob, audit_summary: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "event_type": "audit_completed",
            "audit_job": {
                "id": str(audit_job.id),
                "status": audit_job.status,
                "triggered_by": audit_job.triggered_by,
                "docs_scanned": audit_job.docs_scanned or 0,
                "alerts_created": audit_job.alerts_created or 0,
                "started_at": (
                    audit_job.started_at.isoformat() if audit_job.started_at else None
                ),
                "completed_at": (
                    audit_job.completed_at.isoformat()
                    if audit_job.completed_at
                    else None
                ),
            },
            "summary": audit_summary,
        }


def _parse_channels(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        channel.strip().lower()
        for channel in value.split(",")
        if channel.strip()
    }


def _idempotency_key(
    *,
    event_type: str,
    audit_job_id: uuid.UUID | None,
    alert_id: uuid.UUID | None,
    channel: str,
    target: str | None,
) -> str:
    return "||".join(
        [
            event_type,
            str(audit_job_id) if audit_job_id else "",
            str(alert_id) if alert_id else "",
            channel,
            _safe_target(target) or "",
        ]
    )


def _slack_payload(payload: dict[str, Any]) -> dict[str, Any]:
    alert = payload.get("alert") or {}
    severity = str(alert.get("severity") or "unknown").upper()
    message = str(alert.get("message") or "Drift alert")
    return {
        "text": f"[{severity}] {message}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*[{severity}] Drift Guard alert*\n{message}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Rule: `{alert.get('rule_type')}` | "
                            f"Audit: `{payload.get('audit_job_id')}`"
                        ),
                    }
                ],
            },
        ],
    }


async def _validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise NotificationSecurityError("Webhook URL must use http or https")
    if not parsed.hostname:
        raise NotificationSecurityError("Webhook URL host is required")
    if parsed.username or parsed.password:
        raise NotificationSecurityError("Webhook URL must not include credentials")

    await asyncio.to_thread(_reject_private_ip_hostname, parsed.hostname, parsed.port)


def _reject_private_ip_hostname(hostname: str, port: int | None) -> None:
    try:
        direct_address = ipaddress.ip_address(hostname)
    except ValueError:
        direct_address = None

    if direct_address is not None:
        _reject_private_ip(direct_address)
        return

    try:
        results = socket.getaddrinfo(
            hostname,
            443 if port is None else port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise NotificationSecurityError("Webhook URL host did not resolve") from exc

    for result in results:
        _reject_private_ip(ipaddress.ip_address(result[4][0]))


def _reject_private_ip(
    ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    if not ip_address.is_global:
        raise NotificationSecurityError(
            "Webhook URL resolves to non-public IP space"
        )


def _safe_target(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme and parsed.hostname:
        host = parsed.hostname.lower()
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme.lower()}://{host}{parsed.path}"
    return target


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_url(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(
        part in normalized
        for part in (
            "access_token",
            "authorization",
            "credential",
            "key",
            "password",
            "secret",
            "signature",
            "token",
        )
    )


def _redact_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return value
    host = parsed.hostname.lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme.lower()}://{host}{parsed.path}"


def _safe_error_message(exc: Exception) -> str:
    return str(exc).replace("\r", " ").replace("\n", " ")[:500]


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as sink:
        sink.write(f"{line}\n")
