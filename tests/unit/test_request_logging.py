import logging

from fastapi.testclient import TestClient

from app.main import app


def test_request_logging_adds_request_id_and_logs_path_without_query(caplog):
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/health?token=secret-value")

    assert response.status_code == 200
    assert response.headers["x-request-id"]

    records = [
        record for record in caplog.records if record.name == "app.request"
    ]
    assert records
    record = records[-1]
    assert record.request_id == response.headers["x-request-id"]
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0
    assert "secret-value" not in record.getMessage()


def test_request_logging_preserves_caller_request_id():
    client = TestClient(app)

    response = client.get("/health", headers={"x-request-id": "request-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "request-123"
