from fastapi import FastAPI

from app.api.v1 import alerts, audit, documents, scores, sources
from app.config import settings
from app.middleware.request_logging import request_logging_middleware

app = FastAPI(
    title="Drift Guard",
    description="Documentation validity engine that detects runbook drift",
    version="0.1.0",
    docs_url="/docs" if settings.public_api_docs_enabled else None,
    redoc_url="/redoc" if settings.public_api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.public_api_docs_enabled else None,
)

app.middleware("http")(request_logging_middleware)

app.include_router(documents.router, prefix="/v1/documents", tags=["documents"])
app.include_router(sources.router, prefix="/v1/sources", tags=["sources"])
app.include_router(alerts.router, prefix="/v1/alerts", tags=["alerts"])
app.include_router(scores.router, prefix="/v1/scores", tags=["scores"])
app.include_router(audit.router, prefix="/v1/audit", tags=["audit"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
