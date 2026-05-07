from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.entity import Entity
from app.services.drift.alert_service import AlertService
from app.services.drift.rules import (
    CommandDeprecatedRule,
    DashboardDeadRule,
    DependencyUndocumentedRule,
    DriftRuleContext,
    HelmVersionStaleRule,
    OwnerMissingRule,
)
from app.services.drift.rules.base import BaseDriftRule
from app.services.drift.rules_engine import RulesEngine
from app.services.evidence.evidence_store import EvidenceStore
from app.services.evidence.http_collector import HttpProbeCollector
from app.services.scoring.scoring_service import ScoringService


@dataclass(frozen=True)
class AuditScanResult:
    documents_scanned: int
    alerts_created: int
    alerts_resolved: int
    scores_refreshed: int


class AuditScanService:
    def __init__(
        self,
        *,
        rules: list[BaseDriftRule] | None = None,
        http_collector: HttpProbeCollector | None = None,
        alert_service: AlertService | None = None,
        scoring_service: ScoringService | None = None,
    ) -> None:
        self._rules = rules or [
            OwnerMissingRule(),
            DashboardDeadRule(),
            DependencyUndocumentedRule(),
            HelmVersionStaleRule(),
            CommandDeprecatedRule(),
        ]
        self._rules_engine = RulesEngine(self._rules)
        self._http_collector = http_collector or HttpProbeCollector()
        self._alert_service = alert_service or AlertService()
        self._scoring_service = scoring_service or ScoringService()

    async def scan_all_documents(self, db: AsyncSession) -> AuditScanResult:
        documents = await self._list_scannable_documents(db)
        alerts_created = 0
        alerts_resolved = 0
        scores_refreshed = 0
        rule_types = {rule.rule_type for rule in self._rules}

        for document in documents:
            entities = await self._latest_entities_for_document(db, document=document)
            evidence = await self._collect_evidence(entities)
            context = DriftRuleContext(
                document_id=document.id,
                entities=tuple(entities),
                evidence=evidence,
            )
            alerts = self._rules_engine.evaluate(context)
            persistence_result = await self._alert_service.persist_alerts_for_rule_run(
                db,
                alerts,
                document_id=document.id,
                rule_types=rule_types,
            )
            alerts_created += len(persistence_result.created)
            alerts_resolved += len(persistence_result.resolved)

            await self._scoring_service.score_document(db, document_id=document.id)
            scores_refreshed += 1

        return AuditScanResult(
            documents_scanned=len(documents),
            alerts_created=alerts_created,
            alerts_resolved=alerts_resolved,
            scores_refreshed=scores_refreshed,
        )

    async def _list_scannable_documents(self, db: AsyncSession) -> list[Document]:
        result = await db.execute(
            select(Document)
            .where(
                Document.is_deleted.is_(False),
                Document.latest_version_id.is_not(None),
            )
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
        return list(result.scalars().all())

    async def _latest_entities_for_document(
        self, db: AsyncSession, *, document: Document
    ) -> list[dict]:
        if document.latest_version_id is None:
            return []

        result = await db.execute(
            select(Entity)
            .where(
                Entity.document_id == document.id,
                Entity.document_version_id == document.latest_version_id,
            )
            .order_by(Entity.entity_type.asc(), Entity.value.asc(), Entity.id.asc())
        )
        return [
            {
                "entity_type": entity.entity_type,
                "value": entity.value,
                "context": entity.context,
            }
            for entity in result.scalars().all()
        ]

    async def _collect_evidence(self, entities: list[dict]) -> dict:
        store = EvidenceStore()
        for dashboard_url in self._dashboard_urls(entities):
            probe_result = await self._http_collector.collect(dashboard_url)
            store.upsert_from_payload(
                collector="http",
                target=dashboard_url,
                payload=probe_result.model_dump(mode="json"),
            )
        return store.to_alert_evidence()

    def _dashboard_urls(self, entities: list[dict]) -> list[str]:
        seen: set[str] = set()
        dashboard_urls: list[str] = []
        for entity in entities:
            entity_type = str(entity.get("entity_type", "")).strip().lower()
            value = str(entity.get("value", "")).strip()
            if entity_type != "dashboard" or not value or value in seen:
                continue
            if not self._is_http_url(value):
                continue
            seen.add(value)
            dashboard_urls.append(value)
        return dashboard_urls

    def _is_http_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


async def scan_all_documents(db: AsyncSession) -> AuditScanResult:
    return await AuditScanService().scan_all_documents(db)
