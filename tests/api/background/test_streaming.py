from src.api.background.streaming import EventBus
from src.api.events import JobEvent


class ImmediateLoop:
    def call_soon_threadsafe(self, callback, *args) -> None:
        callback(*args)


def test_event_bus_delivers_and_closes_without_job_persistence() -> None:
    bus = EventBus()
    subscriber = bus.subscribe(ImmediateLoop())
    event = JobEvent(kind="progress", job_id="job-1", payload={"current": 1})

    bus.publish(event)

    assert subscriber.queue.get_nowait() is event
    bus.unsubscribe(subscriber)
    assert subscriber.queue.get_nowait() is None
