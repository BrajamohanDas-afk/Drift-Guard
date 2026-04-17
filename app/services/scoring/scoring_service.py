import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.document import Document
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore


@dataclass(frozen=True)
class ScoreInputs:
    document_id: uuid.UUID
    unresolved_alerts: list[Alert]
    latest_entities: list[Entity]


class ScoringService:
    BASE_SCORE = 100.0
    ALERT_WEIGHTS: dict[str, int] = {
        "critical": 30,
        "high": 20,
        "medium": 10,
        "low": 5,
    }
    EXTRACTION_WEIGHTS: dict[str, int] = {
        "missing_owner_entity": 15,
        "missing_service_entity": 10,
        "fewer_than_three_entities": 5,
    }

    async def compute_score_inputs(
        self, db: AsyncSession, *, document_id: uuid.UUID
    ) -> ScoreInputs:
        document = await db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")

        alerts_result = await db.execute(
            select(Alert).where(
                Alert.document_id == document_id,
                Alert.resolved.is_(False),
            )
        )
        unresolved_alerts = list(alerts_result.scalars().all())

        latest_entities: list[Entity] = []
        if document.latest_version_id is not None:
            entities_result = await db.execute(
                select(Entity).where(
                    Entity.document_id == document_id,
                    Entity.document_version_id == document.latest_version_id,
                )
            )
            latest_entities = list(entities_result.scalars().all())

        return ScoreInputs(
            document_id=document_id,
            unresolved_alerts=unresolved_alerts,
            latest_entities=latest_entities,
        )

    def calculate_breakdown(self, inputs: ScoreInputs) -> dict:
        alert_counts = {severity: 0 for severity in self.ALERT_WEIGHTS}
        for alert in inputs.unresolved_alerts:
            severity = (alert.severity or "").lower()
            if severity in alert_counts:
                alert_counts[severity] += 1

        entity_types = {
            (entity.entity_type or "").lower()
            for entity in inputs.latest_entities
            if entity.entity_type
        }
        owner_present = "owner" in entity_types
        service_present = "service" in entity_types
        total_entities = len(inputs.latest_entities)

        deductions: list[dict] = []

        alert_deduction_total = 0.0
        for severity, weight in self.ALERT_WEIGHTS.items():
            count = alert_counts[severity]
            if count <= 0:
                continue
            amount = float(count * weight)
            deductions.append(
                {
                    "category": "alerts",
                    "reason": f"unresolved_{severity}_alerts",
                    "count": count,
                    "weight": weight,
                    "amount": amount,
                }
            )
            alert_deduction_total += amount

        extraction_deduction_total = 0.0
        if not owner_present:
            amount = float(self.EXTRACTION_WEIGHTS["missing_owner_entity"])
            deductions.append(
                {
                    "category": "extraction_quality",
                    "reason": "missing_owner_entity",
                    "count": 1,
                    "weight": self.EXTRACTION_WEIGHTS["missing_owner_entity"],
                    "amount": amount,
                }
            )
            extraction_deduction_total += amount

        if not service_present:
            amount = float(self.EXTRACTION_WEIGHTS["missing_service_entity"])
            deductions.append(
                {
                    "category": "extraction_quality",
                    "reason": "missing_service_entity",
                    "count": 1,
                    "weight": self.EXTRACTION_WEIGHTS["missing_service_entity"],
                    "amount": amount,
                }
            )
            extraction_deduction_total += amount

        if total_entities < 3:
            amount = float(self.EXTRACTION_WEIGHTS["fewer_than_three_entities"])
            deductions.append(
                {
                    "category": "extraction_quality",
                    "reason": "fewer_than_three_entities",
                    "count": 1,
                    "weight": self.EXTRACTION_WEIGHTS["fewer_than_three_entities"],
                    "amount": amount,
                }
            )
            extraction_deduction_total += amount

        total_deductions = alert_deduction_total + extraction_deduction_total
        final_score = max(0.0, min(self.BASE_SCORE, self.BASE_SCORE - total_deductions))
        final_score = round(final_score, 2)

        return {
            "base_score": self.BASE_SCORE,
            "counts": {
                "alerts": alert_counts,
                "entities": {
                    "total": total_entities,
                    "owner_present": owner_present,
                    "service_present": service_present,
                },
            },
            "deductions": deductions,
            "deduction_totals": {
                "alerts": alert_deduction_total,
                "extraction_quality": extraction_deduction_total,
            },
            "total_deductions": total_deductions,
            "final_score": final_score,
        }

    async def persist_score_snapshot(
        self,
        db: AsyncSession,
        *,
        document_id: uuid.UUID,
        score: float,
        breakdown: dict,
    ) -> RunbookScore:
        rounded_score = round(float(score), 2)
        snapshot = RunbookScore(
            document_id=document_id,
            score=rounded_score,
            breakdown=breakdown,
        )
        db.add(snapshot)
        await db.flush()
        await db.commit()
        await db.refresh(snapshot)
        return snapshot

    async def score_document(
        self, db: AsyncSession, *, document_id: uuid.UUID
    ) -> RunbookScore:
        inputs = await self.compute_score_inputs(db, document_id=document_id)
        breakdown = self.calculate_breakdown(inputs)
        score = float(breakdown["final_score"])
        return await self.persist_score_snapshot(
            db,
            document_id=document_id,
            score=score,
            breakdown=breakdown,
        )

    async def get_latest_score(
        self, db: AsyncSession, *, document_id: uuid.UUID
    ) -> RunbookScore | None:
        result = await db.execute(
            select(RunbookScore)
            .where(RunbookScore.document_id == document_id)
            .order_by(
                RunbookScore.scored_at.desc(),
                RunbookScore.id.desc(),
            )
            .limit(1)
        )
        return result.scalars().first()

    async def list_latest_scores_per_document(
        self, db: AsyncSession
    ) -> list[RunbookScore]:
        latest_subquery = self._latest_scores_subquery()

        result = await db.execute(
            select(RunbookScore)
            .join(latest_subquery, latest_subquery.c.score_id == RunbookScore.id)
            .where(latest_subquery.c.rank == 1)
            .order_by(
                RunbookScore.scored_at.desc(),
                RunbookScore.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def list_latest_scores_per_document_paginated(
        self,
        db: AsyncSession,
        *,
        page: int,
        per_page: int,
    ) -> tuple[list[RunbookScore], int]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if per_page < 1 or per_page > 100:
            raise ValueError("per_page must be between 1 and 100")

        latest_subquery = self._latest_scores_subquery()
        total_result = await db.execute(
            select(func.count())
            .select_from(latest_subquery)
            .where(latest_subquery.c.rank == 1)
        )
        total = int(total_result.scalar() or 0)

        result = await db.execute(
            select(RunbookScore)
            .join(latest_subquery, latest_subquery.c.score_id == RunbookScore.id)
            .where(latest_subquery.c.rank == 1)
            .order_by(
                RunbookScore.scored_at.desc(),
                RunbookScore.id.desc(),
            )
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    def _latest_scores_subquery(self):
        latest_rank = func.row_number().over(
            partition_by=RunbookScore.document_id,
            order_by=(RunbookScore.scored_at.desc(), RunbookScore.id.desc()),
        )
        return select(
            RunbookScore.id.label("score_id"),
            latest_rank.label("rank"),
        ).subquery()
