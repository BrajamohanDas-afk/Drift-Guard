from fastapi import FastAPI
from app.api.v1 import documents, sources, alerts, scores, audit

app = FastAPI(
    title="Drift Guard",
    description="Documentation validity engine that detects runbook drift",
    version="0.1.0"
)

app.include_router(documents.router, prefix="/v1/documents", tags=["documents"])
app.include_router(sources.router, prefix="/v1/sources", tags=["sources"])
app.include_router(alerts.router, prefix="/v1/alerts", tags=["alerts"])
app.include_router(scores.router, prefix="/v1/scores", tags=["scores"])
app.include_router(audit.router, prefix="/v1/audit", tags=["audit"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
