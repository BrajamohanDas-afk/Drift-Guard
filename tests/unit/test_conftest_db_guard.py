import pytest

from tests.conftest import assert_safe_test_database


def test_safe_test_database_guard_allows_test_database():
    assert_safe_test_database(
        "postgresql+asyncpg://drift:drift@localhost:5433/driftguard_test"
    )


def test_safe_test_database_guard_rejects_non_test_database():
    with pytest.raises(RuntimeError, match="Refusing to truncate database"):
        assert_safe_test_database(
            "postgresql+asyncpg://drift:drift@localhost:5433/driftguard"
        )


def test_safe_test_database_guard_rejects_invalid_url():
    with pytest.raises(RuntimeError, match="invalid DATABASE_URL"):
        assert_safe_test_database("not a database url")
