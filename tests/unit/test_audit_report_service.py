from decimal import Decimal

import pytest

from app.services.audit.audit_report_service import (
    AuditReportService,
    AuditReportValidationError,
)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CapturingSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _RowsResult(self.rows)


def _compiled_statement(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True})).lower()


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


def test_severity_counts_include_defaults_and_unknowns():
    service = AuditReportService()

    counts = service._severity_counts_from_rows(  # noqa: SLF001
        [
            ("HIGH", 2),
            ("medium", 1),
            ("", 3),
            (None, 4),
            ("custom", 5),
        ]
    )

    assert counts == {
        "critical": 0,
        "high": 2,
        "medium": 1,
        "low": 0,
        "unknown": 7,
        "custom": 5,
    }


def test_service_name_normalization_rejects_blank_values():
    service = AuditReportService()

    assert service._normalize_service_name("  payments-api  ") == "payments-api"  # noqa: SLF001
    with pytest.raises(AuditReportValidationError, match="service_name"):
        service._normalize_service_name("   ")  # noqa: SLF001


def test_optional_float_conversion_rounds_numeric_values():
    service = AuditReportService()

    assert service._to_optional_float(None) is None  # noqa: SLF001
    assert service._to_optional_float(Decimal("87.555")) == 87.56  # noqa: SLF001


@pytest.mark.asyncio
async def test_global_alert_count_filters_deleted_docs():
    service = AuditReportService()
    db = _CapturingSession([("medium", 1)])

    counts = await service._count_unresolved_alerts_by_severity(  # noqa: SLF001
        db,
        document_scope=None,
    )

    assert counts["medium"] == 1
    compiled = _compiled_statement(db.statements[0])
    assert "from alerts" in compiled
    assert "left outer join documents" in compiled
    assert "alerts.document_id is null" in compiled
    assert "documents.is_deleted is false" in compiled


@pytest.mark.asyncio
async def test_service_alert_count_filters_to_document_scope():
    service = AuditReportService()
    db = _CapturingSession([("high", 2)])
    document_scope = service._document_scope_select_for_service(  # noqa: SLF001
        service_name="payments-api"
    )

    counts = await service._count_unresolved_alerts_by_severity(  # noqa: SLF001
        db,
        document_scope=document_scope,
    )

    assert counts["high"] == 2
    compiled = _compiled_statement(db.statements[0])
    assert "join documents" in compiled
    assert "alerts.document_id" in compiled
    assert "entities" in compiled
