import asyncio
import sys
import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import engine

@pytest.fixture(autouse=True)
async def reset_db_connections():
    yield
    await engine.dispose()