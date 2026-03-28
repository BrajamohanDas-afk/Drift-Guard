import asyncio
import sys

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
async def reset_db_state():
    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    yield

    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    await engine.dispose()