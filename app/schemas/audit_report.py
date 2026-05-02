import datetime
import uuid
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.audit_job import AuditJobResponse


class AuditReportTotals(BaseModel):
    documents: int
    unresolved_alerts: int


class AuditScoreSummary(BaseModel):
    documents_scored: int
    average_score: Optional[float] = None


class AuditDocumentScoreSummary(BaseModel):
    document_id: uuid.UUID
    title: str
    service_name: Optional[str] = None
    score: float
    scored_at: datetime.datetime


class AuditReportResponse(BaseModel):
    generated_at: datetime.datetime
    scope: Literal["global", "service"]
    service_name: Optional[str] = None
    latest_audit_job: Optional[AuditJobResponse] = None
    totals: AuditReportTotals
    alerts_by_severity: dict[str, int]
    score_summary: AuditScoreSummary
    lowest_scoring_documents: list[AuditDocumentScoreSummary]
