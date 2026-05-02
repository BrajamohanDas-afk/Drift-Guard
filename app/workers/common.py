from urllib.parse import unquote, urlparse

from arq.connections import RedisSettings

from app.config import settings

WORKER_QUEUE_NAME = settings.worker_queue_name


def redis_settings_from_url(redis_url: str) -> RedisSettings:
    parsed = urlparse(redis_url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError("REDIS_URL must use redis:// or rediss://")

    host = parsed.hostname or "localhost"
    port = parsed.port or 6379

    database = 0
    if parsed.path and parsed.path != "/":
        db_part = parsed.path.lstrip("/")
        if db_part:
            try:
                database = int(db_part)
            except ValueError as exc:
                raise ValueError("REDIS_URL database index must be an integer") from exc
            if database < 0:
                raise ValueError("REDIS_URL database index must be >= 0")

    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None

    return RedisSettings(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        ssl=parsed.scheme == "rediss",
    )
