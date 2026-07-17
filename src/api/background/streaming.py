"""Thread-safe background job event streaming."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from typing import Any

from src.api.events import JobEvent


class EventBus:
    """Fan job events out to independent asyncio subscriber queues."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, loop: Any) -> Subscriber:
        subscriber = Subscriber(loop)
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)
        subscriber.close()

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.deliver(event)


class Subscriber:
    def __init__(self, loop: Any) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[JobEvent | None] = asyncio.Queue(maxsize=1024)
        self._closed = False

    def deliver(self, event: JobEvent) -> None:
        if self._closed:
            return

        def put() -> None:
            if self._closed:
                return
            try:
                self.queue.put_nowait(event)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    self.queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    self.queue.put_nowait(event)

        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(put)

    def close(self) -> None:
        self._closed = True

        def close_queue() -> None:
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(None)

        with contextlib.suppress(RuntimeError):
            self.loop.call_soon_threadsafe(close_queue)


__all__ = ["EventBus", "Subscriber"]
