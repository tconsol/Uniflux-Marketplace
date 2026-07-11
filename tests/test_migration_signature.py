import inspect
from app.services.jobs_service import migrate_jobs_to_global


def test_migration_is_async_zero_arg():
    assert inspect.iscoroutinefunction(migrate_jobs_to_global)
    assert list(inspect.signature(migrate_jobs_to_global).parameters) == []
