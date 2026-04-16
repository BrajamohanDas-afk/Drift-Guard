import datetime
import hashlib
import json
import uuid
from datetime import date, time

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.services.drift.rules.base import DriftAlertDraft


class AlertService:
    def _normalize_evidence_value(self, value: object) -> object:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, (datetime.datetime, date, time)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): self._normalize_evidence_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        if isinstance(value, (list, tuple)):
            return [self._normalize_evidence_value(item) for item in value]
        if isinstance(value, (set, frozenset)):
            normalized_items = [self._normalize_evidence_value(item) for item in value]
            return sorted(
                normalized_items,
                key=lambda item: json.dumps(
                    item, sort_keys=True, separators=(",", ":")
                ),
            )
        return {"__python_repr__": repr(value), "__python_type__": type(value).__name__}

    def _evidence_fingerprint(self, evidence: dict | None) -> str:
        normalized_evidence = self._normalize_evidence_value(evidence or {})
        return json.dumps(normalized_evidence, sort_keys=True, separators=(",", ":"))

    def _stable_lock_id(self, *parts: str) -> int:
        raw = "||".join(parts).encode("utf-8")
        digest = hashlib.sha256(raw).digest()[:8]
        unsigned = int.from_bytes(digest, byteorder="big", signed=False)
        if unsigned >= 2**63:
            return unsigned - 2**64
        return unsigned

    def _dedup_key(self, draft: DriftAlertDraft) -> tuple[str, str, str, str, str]:
        return (
            draft.rule_type,
            draft.severity,
            str(draft.document_id),
            draft.message,
            self._evidence_fingerprint(draft.evidence),
        )

    async def _acquire_dedup_lock(
        self, db: AsyncSession, *, dedup_key: tuple[str, str, str, str, str]
    ) -> None:
        lock_id = self._stable_lock_id(*dedup_key)
        await db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    async def _get_matching_unresolved_alert(
        self,
        db: AsyncSession,
        *,
        draft: DriftAlertDraft,
        normalized_evidence: dict,
    ) -> Alert | None:
        query: Select[tuple[Alert]] = select(Alert).where(
            Alert.resolved.is_(False),
            Alert.rule_type == draft.rule_type,
            Alert.severity == draft.severity,
            Alert.message == draft.message,
            Alert.evidence == normalized_evidence,
        )
        if draft.document_id is None:
            query = query.where(Alert.document_id.is_(None))
        else:
            query = query.where(Alert.document_id == draft.document_id)

        result = await db.execute(query.limit(1))
        return result.scalars().first()

    async def persist_alerts(
        self, db: AsyncSession, alerts: list[DriftAlertDraft]
    ) -> list[Alert]:
        if not alerts:
            return []

        created: list[Alert] = []
        seen_in_batch: set[tuple[str, str, str, str, str]] = set()
        for draft in alerts:
            dedup_key = self._dedup_key(draft)
            if dedup_key in seen_in_batch:
                continue

            await self._acquire_dedup_lock(db, dedup_key=dedup_key)
            normalized_evidence = self._normalize_evidence_value(draft.evidence or {})
            if not isinstance(normalized_evidence, dict):
                normalized_evidence = {"value": normalized_evidence}

            existing = await self._get_matching_unresolved_alert(
                db,
                draft=draft,
                normalized_evidence=normalized_evidence,
            )
            if existing is not None:
                seen_in_batch.add(dedup_key)
                continue

            created_alert = Alert(
                document_id=draft.document_id,
                rule_type=draft.rule_type,
                severity=draft.severity,
                message=draft.message,
                evidence=normalized_evidence,
                resolved=False,
                resolved_at=None,
            )
            db.add(created_alert)
            created.append(created_alert)
            seen_in_batch.add(dedup_key)

        if not created:
            return []

        await db.commit()
        for alert in created:
            await db.refresh(alert)
        return created

    async def list_alerts(
        self,
        db: AsyncSession,
        *,
        page: int,
        per_page: int,
        resolved: bool | None = None,
        severity: str | None = None,
        rule_type: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> tuple[list[Alert], int]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if per_page < 1 or per_page > 100:
            raise ValueError("per_page must be between 1 and 100")

        query: Select[tuple[Alert]] = select(Alert)
        count_query = select(func.count()).select_from(Alert)

        if resolved is not None:
            query = query.where(Alert.resolved == resolved)
            count_query = count_query.where(Alert.resolved == resolved)
        if severity:
            query = query.where(Alert.severity == severity)
            count_query = count_query.where(Alert.severity == severity)
        if rule_type:
            query = query.where(Alert.rule_type == rule_type)
            count_query = count_query.where(Alert.rule_type == rule_type)
        if document_id is not None:
            query = query.where(Alert.document_id == document_id)
            count_query = count_query.where(Alert.document_id == document_id)

        total_result = await db.execute(count_query)
        total = int(total_result.scalar() or 0)

        result = await db.execute(
            query.order_by(Alert.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        alerts = list(result.scalars().all())
        return alerts, total

    async def get_alert(self, db: AsyncSession, *, alert_id: uuid.UUID) -> Alert | None:
        return await db.get(Alert, alert_id)

    async def resolve_alert(self, db: AsyncSession, *, alert: Alert) -> Alert:
        if alert.resolved:
            return alert

        resolved_at = datetime.datetime.now(datetime.timezone.utc)
        update_result = await db.execute(
            update(Alert)
            .where(
                Alert.id == alert.id,
                Alert.resolved.is_(False),
            )
            .values(
                resolved=True,
                resolved_at=resolved_at,
            )
        )
        if update_result.rowcount:
            await db.commit()
            await db.refresh(alert)
            return alert

        await db.refresh(alert)
        return alert
