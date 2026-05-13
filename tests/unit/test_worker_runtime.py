import datetime

import pytest
from arq.connections import RedisSettings

from app.workers.audit_run_task import audit_run_task
from app.workers.ingest_task import ingest_task
from app.workers.nightly_scan import nightly_scan
from app.workers.notification_task import notification_task
from app.workers.runtime import (
    WorkerSettings,
    build_cron_jobs,
    on_shutdown,
    on_startup,
    redis_settings_from_url,
)
from app.workers.score_task import score_task


@pytest.fixture(autouse=True)
def reset_db_state():
    # Override global DB fixture for pure unit tests.
    yield


def test_redis_settings_from_url_parses_standard_url():
    redis_settings = redis_settings_from_url("redis://localhost:6380/5")

    assert isinstance(redis_settings, RedisSettings)
    assert redis_settings.host == "localhost"
    assert redis_settings.port == 6380
    assert redis_settings.database == 5
    assert redis_settings.ssl is False


def test_redis_settings_from_url_parses_rediss_and_credentials():
    redis_settings = redis_settings_from_url("rediss://user:pa%24%24@cache.local:6379/2")

    assert redis_settings.host == "cache.local"
    assert redis_settings.port == 6379
    assert redis_settings.database == 2
    assert redis_settings.username == "user"
    assert redis_settings.password == "pa$$"
    assert redis_settings.ssl is True


def test_redis_settings_from_url_rejects_invalid_scheme():
    with pytest.raises(ValueError, match="REDIS_URL must use redis:// or rediss://"):
        redis_settings_from_url("http://localhost:6379")


def test_redis_settings_from_url_rejects_non_integer_database():
    with pytest.raises(ValueError, match="database index must be an integer"):
        redis_settings_from_url("redis://localhost:6379/not-an-int")


def test_redis_settings_from_url_rejects_negative_database():
    with pytest.raises(ValueError, match="database index must be >= 0"):
        redis_settings_from_url("redis://localhost:6379/-1")


def test_worker_settings_registers_phase7_functions():
    assert WorkerSettings.functions == [
        audit_run_task,
        ingest_task,
        score_task,
        notification_task,
        nightly_scan,
    ]
    assert WorkerSettings.queue_name == "drift-guard"
    assert WorkerSettings.timezone == datetime.timezone.utc
    assert WorkerSettings.max_jobs == 10


def test_build_cron_jobs_uses_configured_nightly_scan_schedule(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_enabled",
        True,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_hour_utc",
        3,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_minute",
        15,
    )

    cron_jobs = build_cron_jobs()

    assert len(cron_jobs) == 1
    cron_job = cron_jobs[0]
    assert cron_job.name == "nightly_scan"
    assert cron_job.hour == 3
    assert cron_job.minute == 15
    assert cron_job.second == 0
    assert cron_job.microsecond == 0
    assert cron_job.unique is True
    assert cron_job.run_at_startup is False


def test_build_cron_jobs_returns_empty_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_enabled",
        False,
    )

    assert build_cron_jobs() == []


def test_build_cron_jobs_validates_hour_and_minute(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_enabled",
        True,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_hour_utc",
        25,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_minute",
        0,
    )

    with pytest.raises(ValueError, match="NIGHTLY_SCAN_CRON_HOUR_UTC"):
        build_cron_jobs()

    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_hour_utc",
        2,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_minute",
        60,
    )

    with pytest.raises(ValueError, match="NIGHTLY_SCAN_CRON_MINUTE"):
        build_cron_jobs()

    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_hour_utc",
        -1,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_minute",
        0,
    )

    with pytest.raises(ValueError, match="NIGHTLY_SCAN_CRON_HOUR_UTC"):
        build_cron_jobs()

    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_hour_utc",
        2,
    )
    monkeypatch.setattr(
        "app.workers.runtime.settings.nightly_scan_cron_minute",
        -1,
    )

    with pytest.raises(ValueError, match="NIGHTLY_SCAN_CRON_MINUTE"):
        build_cron_jobs()


@pytest.mark.asyncio
async def test_worker_startup_and_shutdown_hooks_store_start_time():
    ctx: dict[str, object] = {}

    await on_startup(ctx)

    started_at = ctx.get("started_at")
    assert isinstance(started_at, datetime.datetime)
    assert started_at.tzinfo == datetime.timezone.utc

    await on_shutdown(ctx)


@pytest.mark.asyncio
async def test_score_task_rejects_invalid_document_id():
    with pytest.raises(ValueError):
        await score_task({}, document_id="doc-1")
