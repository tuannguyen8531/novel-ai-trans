import pytest

from src.api.background.models import JobStatus
from src.api.background.registry import JobConflictError, JobRegistry


def test_same_novel_jobs_conflict_without_threads() -> None:
    registry = JobRegistry()
    active = registry.create(kind="crawl", novel="a")

    with pytest.raises(JobConflictError) as error:
        registry.create(kind="translate", novel="a")

    assert error.value.args[0] == active.id


def test_different_novel_jobs_can_be_active_without_threads() -> None:
    registry = JobRegistry()
    first = registry.create(kind="crawl", novel="a")
    second = registry.create(kind="translate", novel="b")

    assert {job.id for job in registry.list_active()} == {first.id, second.id}


def test_global_job_conflicts_in_both_directions_without_threads() -> None:
    registry = JobRegistry()
    novel_job = registry.create(kind="crawl", novel="a")

    with pytest.raises(JobConflictError) as error:
        registry.create(kind="system", novel=None)
    assert error.value.args[0] == novel_job.id

    novel_job.status = JobStatus.COMPLETED
    registry.finish(novel_job)
    global_job = registry.create(kind="system", novel=None)
    with pytest.raises(JobConflictError) as error:
        registry.create(kind="translate", novel="b")
    assert error.value.args[0] == global_job.id
