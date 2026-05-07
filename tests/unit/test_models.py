import datetime
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import CheckConstraint

from app.models.alert import Alert
from app.models.audit_job import AuditJob
from app.models.entity import Entity
from app.models.runbook_score import RunbookScore
from app.schemas.alert import AlertResponse
from app.schemas.audit_job import AuditJobResponse
from app.schemas.document import DocumentCreate, DocumentResponse
from app.schemas.score import ScoreResponse


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
        service_name="payments-api",
    )
    assert doc.doc_type == "runbook"
    assert doc.service_name == "payments-api"


def test_document_response_includes_source_path():
    document = DocumentResponse(
        id=uuid.uuid4(),
        title="runbook.md",
        is_deleted=False,
        deleted_at=None,
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
        path="docs/service/runbook.md",
    )

    assert document.path == "docs/service/runbook.md"


# AlertResponse tests
def test_alert_response_valid():
    alert = AlertResponse(
        id=uuid.uuid4(),
        severity="critical",
        rule_type="owner_missing",
        message="Owner not found",
        created_at=datetime.datetime.now(datetime.timezone.utc),
        resolved=False,
    )
    assert alert.severity == "critical"
    assert alert.evidence is None


# ScoreResponse tests
def test_score_response_valid():
    score = ScoreResponse(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        score=85.50,
        scored_at=datetime.datetime.now(datetime.timezone.utc),
    )
    assert score.score == 85.50
    assert score.breakdown is None


# AuditJobResponse tests
def test_audit_job_response_valid():
    job = AuditJobResponse(
        id=uuid.uuid4(),
        status="completed",
        docs_scanned=14,
        alerts_created=7,
    )
    assert job.status == "completed"
    assert job.docs_scanned == 14


def test_audit_job_response_defaults():
    job = AuditJobResponse(id=uuid.uuid4())
    assert job.status == "pending"
    assert job.docs_scanned is None
    assert job.error is None


def test_audit_job_response_rejects_invalid_status():
    with pytest.raises(ValidationError):
        AuditJobResponse(
            id=uuid.uuid4(),
            status="complete",
        )


def test_audit_job_model_has_status_check_constraint():
    check_constraints = [
        constraint
        for constraint in AuditJob.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert any(
        constraint.name == "ck_audit_jobs_status"
        and "pending" in str(constraint.sqltext)
        and "failed" in str(constraint.sqltext)
        for constraint in check_constraints
    )


def test_hot_query_indexes_are_declared_on_models():
    assert "ix_alerts_resolution_scope_created" in {
        index.name for index in Alert.__table__.indexes
    }
    assert "ix_runbook_scores_document_scored" in {
        index.name for index in RunbookScore.__table__.indexes
    }
    assert "ix_entities_version_type_value" in {
        index.name for index in Entity.__table__.indexes
    }
    assert "ix_audit_jobs_status_started" in {
        index.name for index in AuditJob.__table__.indexes
    }
