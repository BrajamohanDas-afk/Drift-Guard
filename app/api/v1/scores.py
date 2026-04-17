import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_api_key
from app.schemas.score import ScoreListResponse, ScoreResponse
from app.services.scoring.scoring_service import ScoringService

router = APIRouter(dependencies=[Depends(require_api_key)])
score_service = ScoringService()


@router.get("", response_model=ScoreListResponse)
async def list_scores(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    try:
        latest_scores, total = (
            await score_service.list_latest_scores_per_document_paginated(
                db,
                page=page,
                per_page=per_page,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "data": latest_scores,
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/{document_id}", response_model=ScoreResponse)
async def get_score(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    score = await score_service.get_latest_score(db, document_id=document_id)

    if score is None:
        raise HTTPException(status_code=404, detail="Score not found")
    return score
