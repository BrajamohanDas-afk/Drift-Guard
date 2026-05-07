import importlib
import sys

from fastapi.testclient import TestClient


def _reload_main_with_docs_setting(monkeypatch, enabled: bool):
    monkeypatch.setattr("app.config.settings.public_api_docs_enabled", enabled)
    sys.modules.pop("app.main", None)
    return importlib.import_module("app.main")


def test_public_api_docs_can_be_disabled(monkeypatch):
    main = _reload_main_with_docs_setting(monkeypatch, enabled=False)
    client = TestClient(main.app)

    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_public_api_docs_can_be_enabled(monkeypatch):
    main = _reload_main_with_docs_setting(monkeypatch, enabled=True)
    client = TestClient(main.app)

    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200

    sys.modules.pop("app.main", None)
    importlib.import_module("app.main")
