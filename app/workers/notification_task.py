import logging
import uuid
from typing import Any

from app.database import AsyncSessionLocal
from app.services.alerting.notification_service import NotificationService

logger = logging.getLogger(__name__)
notification_service = NotificationService()


async def notification_task(
    _ctx: dict[str, Any],
    *,
    delivery_id: str,
) -> dict[str, Any]:
    delivery_uuid = uuid.UUID(delivery_id)

    async with AsyncSessionLocal() as session:
        delivery = await notification_service.send_delivery(
            session,
            delivery_id=delivery_uuid,
        )

    payload = {
        "status": delivery.status,
        "delivery_id": str(delivery.id),
        "event_type": delivery.event_type,
        "channel": delivery.channel,
        "attempts": delivery.attempts,
    }
    logger.info("notification_task completed", extra=payload)
    return payload
