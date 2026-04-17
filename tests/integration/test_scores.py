import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.document import Document
from app.models.runbook_score import RunbookScore

TEST_HEADERS = {"x-api-key": settings.api_key}


async def test_scores_endpoints_require_api_key():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        list_response = await client.get("/v1/scores")
        detail_response = await client.get(f"/v1/scores/{uuid.uuid4()}")

    assert list_response.status_code == 401
    assert detail_response.status_code == 401


async def test_scores_list_returns_latest_per_document_with_pagination_meta():
    now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        document_a = Document(title="runbook-a.md")
        document_b = Document(title="runbook-b.md")
        document_c = Document(title="runbook-c.md")
        session.add_all([document_a, document_b, document_c])
        await session.flush()

        session.add_all(
            [
                RunbookScore(
                    document_id=document_a.id,
                    score=40.0,
                    scored_at=now - timedelta(days=2),
                    breakdown={"alerts": 3},
                ),
                RunbookScore(
                    document_id=document_a.id,
                    score=88.5,
                    scored_at=now - timedelta(days=1),
                    breakdown={"alerts": 1},
                ),
                RunbookScore(
                    document_id=document_b.id,
                    score=76.0,
                    scored_at=now - timedelta(hours=6),
                    breakdown={"alerts": 2},
                ),
                RunbookScore(
                    document_id=document_c.id,
                    score=91.25,
                    scored_at=now - timedelta(hours=1),
                    breakdown={"alerts": 0},
                ),
            ]
        )
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        page_one_response = await client.get(
            "/v1/scores",
            params={"page": 1, "per_page": 2},
            headers=TEST_HEADERS,
        )
        page_two_response = await client.get(
            "/v1/scores",
            params={"page": 2, "per_page": 2},
            headers=TEST_HEADERS,
        )

    assert page_one_response.status_code == 200
    page_one_payload = page_one_response.json()
    assert set(page_one_payload.keys()) == {"data", "meta"}
    assert page_one_payload["meta"] == {"total": 3, "page": 1, "per_page": 2}
    assert len(page_one_payload["data"]) == 2
    page_one_ids = [item["document_id"] for item in page_one_payload["data"]]
    assert page_one_ids == [str(document_c.id), str(document_b.id)]

    assert page_two_response.status_code == 200
    page_two_payload = page_two_response.json()
    assert page_two_payload["meta"] == {"total": 3, "page": 2, "per_page": 2}
    assert len(page_two_payload["data"]) == 1
    assert page_two_payload["data"][0]["document_id"] == str(document_a.id)
    assert page_two_payload["data"][0]["score"] == 88.5
    assert page_two_payload["data"][0]["breakdown"] == {"alerts": 1}


async def test_scores_detail_returns_latest_score_for_document():
    now = datetime(2026, 4, 17, 18, 0, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        document = Document(title="detail-runbook.md")
        session.add(document)
        await session.flush()

        older = RunbookScore(
            document_id=document.id,
            score=51.0,
            scored_at=now - timedelta(hours=3),
            breakdown={"alerts": 4},
        )
        latest = RunbookScore(
            document_id=document.id,
            score=79.75,
            scored_at=now - timedelta(minutes=10),
            breakdown={"alerts": 1},
        )
        session.add_all([older, latest])
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/v1/scores/{document.id}",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(latest.id)
    assert payload["document_id"] == str(document.id)
    assert payload["score"] == 79.75
    assert payload["breakdown"] == {"alerts": 1}


async def test_scores_detail_returns_not_found_when_no_score_exists():
    async with AsyncSessionLocal() as session:
        document = Document(title="missing-score.md")
        session.add(document)
        await session.commit()
        await session.refresh(document)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/v1/scores/{document.id}",
            headers=TEST_HEADERS,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Score not found"
