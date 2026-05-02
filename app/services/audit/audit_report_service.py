import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.alert import Alert
from app.models.audit_job import AuditJob
from app.models.document import Document
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore
from app.schemas.audit_report import (
    AuditDocumentScoreSummary,
    AuditReportResponse,
    AuditReportTotals,
    AuditScoreSummary,
)


class AuditReportError(RuntimeError):
    pass


class AuditReportValidationError(AuditReportError):
    pass


class AuditServiceNotFoundError(AuditReportError):
    pass


class AuditReportService:
    DEFAULT_SEVERITIES = ("critical", "high", "medium", "low")
    LOWEST_SCORE_LIMIT = 5

    def _utcnow(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    def _normalize_service_name(self, service_name: str) -> str:
        normalized = service_name.strip()
        if not normalized:
            raise AuditReportValidationError("service_name must not be empty")
        return normalized

    def _severity_counts_from_rows(
        self, rows: list[tuple[str | None, int]]
    ) -> dict[str, int]:
        counts = {severity: 0 for severity in self.DEFAULT_SEVERITIES}
        for severity, count in rows:
            key = (severity or "unknown").strip().lower() or "unknown"
            counts[key] = counts.get(key, 0) + int(count or 0)
        return counts

    def _latest_scores_subquery(self):
        latest_rank = func.row_number().over(
            partition_by=RunbookScore.document_id,
            order_by=(RunbookScore.scored_at.desc(), RunbookScore.id.desc()),
        )
        return select(
            RunbookScore.id.label("score_id"),
            RunbookScore.document_id.label("document_id"),
            RunbookScore.score.label("score"),
            RunbookScore.scored_at.label("scored_at"),
            latest_rank.label("rank"),
        ).subquery()

    def _document_scope_select_for_service(self, *, service_name: str) -> Select:
        normalized = service_name.lower()
        latest_service_entity_exists = (
            select(Entity.id)
            .where(
                Entity.document_id == Document.id,
                Entity.document_version_id == Document.latest_version_id,
                Entity.entity_type == "service",
                func.lower(func.trim(Entity.value)) == normalized,
            )
            .exists()
        )
        return select(Document.id).where(
            Document.is_deleted.is_(False),
            or_(
                func.lower(func.trim(Document.service_name)) == normalized,
                latest_service_entity_exists,
            ),
        )

    async def _document_scope_exists(
        self, db: AsyncSession, *, document_scope: Select
    ) -> bool:
        result = await db.execute(select(document_scope.exists()))
        return bool(result.scalar())

    def _apply_document_scope(self, query, *, document_scope: Select | None):
        if document_scope is None:
            return query
        return query.where(Document.id.in_(document_scope))

    async def get_global_report(self, db: AsyncSession) -> AuditReportResponse:
        return await self._build_report(db, scope="global", document_scope=None)

    async def get_service_report(
        self, db: AsyncSession, *, service_name: str
    ) -> AuditReportResponse:
        normalized_service_name = self._normalize_service_name(service_name)
        document_scope = self._document_scope_select_for_service(
            service_name=normalized_service_name
        )
        if not await self._document_scope_exists(db, document_scope=document_scope):
            raise AuditServiceNotFoundError("Service not found")

        return await self._build_report(
            db,
            scope="service",
            service_name=normalized_service_name,
            document_scope=document_scope,
        )

    async def _build_report(
        self,
        db: AsyncSession,
        *,
        scope: Literal["global", "service"],
        document_scope: Select | None,
        service_name: str | None = None,
    ) -> AuditReportResponse:
        latest_job = await self._get_latest_audit_job(db)
        total_documents = await self._count_documents(db, document_scope=document_scope)
        alerts_by_severity = await self._count_unresolved_alerts_by_severity(
            db, document_scope=document_scope
        )
        unresolved_alerts = sum(alerts_by_severity.values())
        score_summary = await self._get_score_summary(
            db, document_scope=document_scope
        )
        lowest_scores = await self._list_lowest_scoring_documents(
            db, document_scope=document_scope
        )

        return AuditReportResponse(
            generated_at=self._utcnow(),
            scope=scope,
            service_name=service_name,
            latest_audit_job=latest_job,
            totals=AuditReportTotals(
                documents=total_documents,
                unresolved_alerts=unresolved_alerts,
            ),
            alerts_by_severity=alerts_by_severity,
            score_summary=score_summary,
            lowest_scoring_documents=lowest_scores,
        )

    async def _get_latest_audit_job(self, db: AsyncSession) -> AuditJob | None:
        result = await db.execute(
            select(AuditJob)
            .order_by(
                AuditJob.started_at.desc().nullsfirst(),
                AuditJob.completed_at.desc().nullsfirst(),
                AuditJob.id.desc(),
            )
            .limit(1)
        )
        return result.scalars().first()

    async def _count_documents(
        self, db: AsyncSession, *, document_scope: Select | None
    ) -> int:
        query = select(func.count()).select_from(Document).where(
            Document.is_deleted.is_(False)
        )
        query = self._apply_document_scope(query, document_scope=document_scope)

        result = await db.execute(query)
        return int(result.scalar() or 0)

    async def _count_unresolved_alerts_by_severity(
        self, db: AsyncSession, *, document_scope: Select | None
    ) -> dict[str, int]:
        query = (
            select(Alert.severity, func.count())
            .select_from(Alert)
            .where(Alert.resolved.is_(False))
            .group_by(Alert.severity)
        )

        if document_scope is not None:
            query = query.join(Document, Document.id == Alert.document_id).where(
                Document.is_deleted.is_(False)
            )
            query = self._apply_document_scope(query, document_scope=document_scope)
        else:
            query = query.outerjoin(Document, Document.id == Alert.document_id).where(
                or_(
                    Alert.document_id.is_(None),
                    Document.is_deleted.is_(False),
                )
            )

        result = await db.execute(query)
        rows = [(severity, count) for severity, count in result.all()]
        return self._severity_counts_from_rows(rows)

    async def _get_score_summary(
        self, db: AsyncSession, *, document_scope: Select | None
    ) -> AuditScoreSummary:
        latest_scores = self._latest_scores_subquery()
        query = (
            select(
                func.count(latest_scores.c.score_id),
                func.avg(latest_scores.c.score),
            )
            .select_from(latest_scores)
            .join(Document, Document.id == latest_scores.c.document_id)
            .where(
                latest_scores.c.rank == 1,
                Document.is_deleted.is_(False),
            )
        )
        query = self._apply_document_scope(query, document_scope=document_scope)

        result = await db.execute(query)
        documents_scored, average_score = result.one()
        return AuditScoreSummary(
            documents_scored=int(documents_scored or 0),
            average_score=self._to_optional_float(average_score),
        )

    async def _list_lowest_scoring_documents(
        self, db: AsyncSession, *, document_scope: Select | None
    ) -> list[AuditDocumentScoreSummary]:
        latest_scores = self._latest_scores_subquery()
        query = (
            select(
                Document.id,
                Document.title,
                Document.service_name,
                latest_scores.c.score,
                latest_scores.c.scored_at,
            )
            .select_from(latest_scores)
            .join(Document, Document.id == latest_scores.c.document_id)
            .where(
                latest_scores.c.rank == 1,
                Document.is_deleted.is_(False),
            )
            .order_by(
                latest_scores.c.score.asc(),
                latest_scores.c.scored_at.desc(),
                Document.id.desc(),
            )
            .limit(self.LOWEST_SCORE_LIMIT)
        )
        query = self._apply_document_scope(query, document_scope=document_scope)

        result = await db.execute(query)
        return [
            AuditDocumentScoreSummary(
                document_id=document_id,
                title=title,
                service_name=service_name,
                score=float(score),
                scored_at=scored_at,
            )
            for document_id, title, service_name, score, scored_at in result.all()
        ]

    def _to_optional_float(self, value: Decimal | float | int | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)
