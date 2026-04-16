import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.schemas.alert import AlertListResponse, AlertResponse
from app.services.drift.alert_service import AlertService

router = APIRouter(dependencies=[Depends(require_api_key)])
alert_service = AlertService()


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    resolved: bool | None = Query(default=None),
    severity: str | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    document_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    alerts, total = await alert_service.list_alerts(
        db,
        page=page,
        per_page=per_page,
        resolved=resolved,
        severity=severity,
        rule_type=rule_type,
        document_id=document_id,
    )
    return {
        "data": alerts,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    alert = await alert_service.get_alert(db, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    alert = await alert_service.get_alert(db, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    return await alert_service.resolve_alert(db, alert=alert)
