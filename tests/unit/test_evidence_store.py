import pytest

from app.services.evidence.evidence_store import EvidenceStore


@pytest.fixture(autouse=True)
async def reset_db_state():
    # Override global DB reset fixture: these are pure unit tests.
    yield


def test_upsert_and_get_record():
    store = EvidenceStore()

    record = store.upsert(
        collector="http",
        target="https://example.com/health",
        status="found",
        evidence={"status_code": 200},
    )

    fetched = store.get(
        collector="http",
        target="https://example.com/health",
    )

    assert fetched is not None
    assert fetched.collector == "http"
    assert fetched.target == "https://example.com/health"
    assert fetched.status == "found"
    assert fetched.evidence["status_code"] == 200
    assert record.checked_at.tzinfo is not None
    assert record.checked_at.utcoffset() is not None


def test_upsert_from_payload_infers_found():
    store = EvidenceStore()

    record = store.upsert_from_payload(
        collector="kubernetes",
        target="prod/payments-api",
        payload={"exists": True, "ready_replicas": 3},
    )

    assert record.status == "found"
    assert record.error is None


def test_upsert_from_payload_infers_not_found():
    store = EvidenceStore()

    record = store.upsert_from_payload(
        collector="github",
        target="acme/runbooks::missing.md",
        payload={"exists": False, "error": None},
    )

    assert record.status == "not_found"
    assert record.error is None


def test_upsert_from_payload_infers_collection_error():
    store = EvidenceStore()

    record = store.upsert_from_payload(
        collector="pagerduty",
        target="payments-api",
        payload={"exists": False, "error": "Unauthorized"},
    )

    assert record.status == "collection_error"
    assert record.error == "Unauthorized"


def test_list_by_status_and_summary():
    store = EvidenceStore()
    store.upsert(collector="a", target="x", status="found", evidence={"exists": True})
    store.upsert(
        collector="b",
        target="y",
        status="not_found",
        evidence={"exists": False},
    )
    store.upsert(
        collector="c",
        target="z",
        status="collection_error",
        evidence={"exists": False, "error": "boom"},
        error="boom",
    )

    found = store.list_by_status("found")
    not_found = store.list_by_status("not_found")
    errors = store.list_by_status("collection_error")
    evidence_payload = store.to_alert_evidence()

    assert len(found) == 1
    assert len(not_found) == 1
    assert len(errors) == 1
    assert evidence_payload["summary"]["total"] == 3
    assert evidence_payload["summary"]["found"] == 1
    assert evidence_payload["summary"]["not_found"] == 1
    assert evidence_payload["summary"]["collection_error"] == 1
    assert len(evidence_payload["records"]) == 3


def test_clear_removes_all_records():
    store = EvidenceStore()
    store.upsert(collector="http", target="url", status="found")
    assert len(store.list_all()) == 1

    store.clear()

    assert store.list_all() == []
