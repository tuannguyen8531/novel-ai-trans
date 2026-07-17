import logging
import threading
import time

from src.api.background.models import JobStatus
from src.api.background.registry import JobRegistry
from src.api.background.runner import JobRequest, JobRunner
from src.api.background.streaming import EventBus
from src.api.events import JobEvent
from src.config import Config


def wait_for_terminal(registry: JobRegistry, job_id: str):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = registry.get(job_id)
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not finish")


def test_runner_records_progress_logs_and_completion_without_subscriber() -> None:
    registry = JobRegistry()
    persisted: list[JobStatus] = []
    terminal_persisted = threading.Event()

    def persist(job) -> None:
        persisted.append(job.status)
        if job.status == JobStatus.COMPLETED:
            terminal_persisted.set()

    runner = JobRunner(registry, EventBus(), persist)
    job = registry.create(kind="translate", novel="demo")

    def run(job, emit, cancel_event):
        emit(JobEvent(kind="progress", job_id=job.id, payload={"current": 1, "total": 2}))
        emit(JobEvent(kind="log", job_id=job.id, payload={"message": "explicit log"}))
        logging.getLogger("tests.background.runner").warning("captured log")
        return {"ok": True}

    runner.start(JobRequest(job=job, snapshot=Config(), run=run))
    finished = wait_for_terminal(registry, job.id)

    assert finished.status == JobStatus.COMPLETED
    assert finished.result == {"ok": True}
    assert finished.progress["current"] == 1
    assert "explicit log" in finished.logs
    assert "captured log" in finished.logs
    assert terminal_persisted.wait(timeout=5)
    assert persisted == [JobStatus.RUNNING, JobStatus.COMPLETED]


def test_runner_records_callback_failure_without_subscriber() -> None:
    registry = JobRegistry()
    runner = JobRunner(registry, EventBus(), lambda job: None)
    job = registry.create(kind="translate", novel="demo")

    def fail(job, emit, cancel_event):
        raise RuntimeError("provider failed")

    runner.start(JobRequest(job=job, snapshot=Config(), run=fail))
    finished = wait_for_terminal(registry, job.id)

    assert finished.status == JobStatus.FAILED
    assert finished.error is not None
    assert finished.error.code == "internal_error"
    assert finished.error.message == "provider failed"
