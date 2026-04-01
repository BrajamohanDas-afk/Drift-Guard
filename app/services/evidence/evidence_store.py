from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


EvidenceStatus = Literal["found", "not_found", "collection_error"]


class EvidenceRecord(BaseModel):
    collector: str
    target: str
    status: EvidenceStatus
    evidence: dict = Field(default_factory=dict)
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceStore:
    def __init__(self):
        self._records: dict[str, EvidenceRecord] = {}

    def _key(self, collector: str, target: str) -> str:
        return f"{collector}::{target}"

    def upsert(
        self,
        *,
        collector: str,
        target: str,
        status: EvidenceStatus,
        evidence: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> EvidenceRecord:
        record = EvidenceRecord(
            collector=collector,
            target=target,
            status=status,
            evidence=evidence or {},
            error=error,
        )
        self._records[self._key(collector, target)] = record
        return record

    def upsert_from_payload(
        self,
        *,
        collector: str,
        target: str,
        payload: dict,
    ) -> EvidenceRecord:
        error = payload.get("error")
        exists = payload.get("exists")

        if error:
            status: EvidenceStatus = "collection_error"
        elif exists is False:
            status = "not_found"
        else:
            status = "found"

        return self.upsert(
            collector=collector,
            target=target,
            status=status,
            evidence=payload,
            error=error,
        )

    def get(self, *, collector: str, target: str) -> Optional[EvidenceRecord]:
        return self._records.get(self._key(collector, target))

    def list_all(self) -> list[EvidenceRecord]:
        return list(self._records.values())

    def list_by_status(self, status: EvidenceStatus) -> list[EvidenceRecord]:
        return [record for record in self._records.values() if record.status == status]

    def to_alert_evidence(self) -> dict:
        return {
            "records": [record.model_dump(mode="json") for record in self.list_all()],
            "summary": {
                "total": len(self._records),
                "found": len(self.list_by_status("found")),
                "not_found": len(self.list_by_status("not_found")),
                "collection_error": len(self.list_by_status("collection_error")),
            },
        }

    def clear(self) -> None:
        self._records.clear()
