import uuid
import datetime
from pydantic import ValidationError
import pytest
from app.schemas.document import DocumentCreate, DocumentResponse
from app.schemas.alert import AlertResponse
from app.schemas.score import ScoreResponse
from app.schemas.audit_job import AuditJobResponse


# DocumentCreate tests
def test_document_create_valid():
    doc = DocumentCreate(title="payments runbook")
    assert doc.title == "payments runbook"
    assert doc.doc_type is None
    assert doc.service_name is None


def test_document_create_missing_title():
    with pytest.raises(ValidationError):
        DocumentCreate()


def test_document_create_full():
    doc = DocumentCreate(
        title="payments runbook",
        doc_type="runbook",
        service_name="payments-api"
    )
    assert doc.doc_type == "runbook"
    assert doc.service_name == "payments-api"


# AlertResponse tests
def test_alert_response_valid():
    alert = AlertResponse(
        id=uuid.uuid4(),
        severity="critical",
        rule_type="owner_missing",
        message="Owner not found",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        resolved=False
    )
    assert alert.severity == "critical"
    assert alert.evidence is None


# ScoreResponse tests
def test_score_response_valid():
    score = ScoreResponse(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        score=85.50,
        scored_at=datetime.datetime.now(datetime.timezone.utc)
    )
    assert score.score == 85.50
    assert score.breakdown is None


# AuditJobResponse tests
def test_audit_job_response_valid():
    job = AuditJobResponse(
        id=uuid.uuid4(),
        status="complete",
        docs_scanned=14,
        alerts_created=7
    )
    assert job.status == "complete"
    assert job.docs_scanned == 14


def test_audit_job_response_defaults():
    job = AuditJobResponse(id=uuid.uuid4())
    assert job.status is None
    assert job.docs_scanned is None
    assert job.error is None