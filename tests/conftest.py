import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.dependencies.rate_limit import reset_rate_limits_for_tests

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TRUNCATE_SQL = """
TRUNCATE TABLE
    entities,
    document_versions,
    documents,
    sources,
    alerts,
    notification_deliveries,
    runbook_scores,
    audit_jobs
RESTART IDENTITY CASCADE
"""


def assert_safe_test_database(database_url: str) -> None:
    try:
        database_name = make_url(database_url).database or ""
    except ArgumentError as exc:
        raise RuntimeError("Refusing to truncate an invalid DATABASE_URL.") from exc

    if "test" not in database_name.lower():
        raise RuntimeError(
            "Refusing to truncate database because DATABASE_URL must point to a "
            f"database with 'test' in its name. Current database: {database_name!r}."
        )


@pytest.fixture(autouse=True)
async def reset_db_state(request):
    reset_rate_limits_for_tests()

    # Keep pure unit tests runnable without a live DB.
    test_path = Path(str(request.fspath)).as_posix().lower()
    if "/tests/unit/" in f"/{test_path}/":
        yield
        reset_rate_limits_for_tests()
        return

    assert_safe_test_database(settings.database_url)

    await engine.dispose()
    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()

    yield

    async with AsyncSessionLocal() as session:
        await session.execute(text(TRUNCATE_SQL))
        await session.commit()
    await engine.dispose()
    reset_rate_limits_for_tests()
