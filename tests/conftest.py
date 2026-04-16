import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal, engine

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TRUNCATE_SQL = """
TRUNCATE TABLE
    entities,
    document_versions,
    documents,
    sources,
    alerts,
    runbook_scores,
    audit_jobs
RESTART IDENTITY CASCADE
"""


@pytest.fixture(autouse=True)
async def reset_db_state(request):
    # Keep pure unit tests runnable without a live DB.
    test_path = Path(str(request.fspath)).as_posix().lower()
    if "/tests/unit/" in f"/{test_path}/":
        yield
        return

    await engine.dispose()
    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    yield

    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()
    await engine.dispose()
