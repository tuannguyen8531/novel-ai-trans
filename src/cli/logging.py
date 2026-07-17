"""CLI-owned presentation for LLM activity and verbose output."""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from src.services.logger import set_verbose
from src.utils.display import RESET, YELLOW

_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧"
_JOB_LOGGER_NAME = "novel_ai_trans.job"
_VERBOSE_LOGGER_NAME = "novel_ai_trans.verbose"


class _Spinner:
    def __init__(self) -> None:
        self._message = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, message: str) -> None:
        self.stop()
        self._message = message
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        thread.join()
        self._thread = None
        sys.stdout.write("\r" + " " * (len(self._message) + 4) + "\r")
        sys.stdout.flush()

    def _spin(self) -> None:
        index = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r  {_SPINNER_CHARS[index]} {self._message}")
            sys.stdout.flush()
            index = (index + 1) % len(_SPINNER_CHARS)
            self._stop.wait(0.1)


class _LlmConsoleHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self._spinner = _Spinner()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name == _VERBOSE_LOGGER_NAME:
                self._spinner.stop()
                print(f"{record.getMessage()}\n")
                return

            details = record.__dict__
            event = details.get("presentation_event")
            if event == "llm_call_started":
                self._spinner.start(record.getMessage())
            elif event == "llm_call_completed":
                self._spinner.stop()
            elif event == "llm_retry":
                self._spinner.stop()
                print(
                    f"  {details['provider']} error — waiting {details['delay']}s "
                    f"before retry ({details['attempt']}/{details['max_retries']})..."
                )
            elif event == "llm_fallback_failed":
                self._spinner.stop()
                print(f"  {YELLOW}⚠ {details['provider']} failed: {details['error_message']}{RESET}")
            elif event == "llm_fallback_started":
                print(f"  {YELLOW}  Falling back to {details['provider']}...{RESET}")
            elif event == "cli_message":
                self._spinner.stop()
                print(details["presentation_message"])
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self._spinner.stop()
        super().close()


def enable_verbose() -> None:
    set_verbose(True)


@contextmanager
def llm_console() -> Iterator[None]:
    """Render service LLM events for a terminal command."""
    handler = _LlmConsoleHandler()
    job_logger = logging.getLogger(_JOB_LOGGER_NAME)
    verbose_logger = logging.getLogger(_VERBOSE_LOGGER_NAME)
    previous_verbose_level = verbose_logger.level
    job_logger.addHandler(handler)
    verbose_logger.addHandler(handler)
    verbose_logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        job_logger.removeHandler(handler)
        verbose_logger.removeHandler(handler)
        verbose_logger.setLevel(previous_verbose_level)
        handler.close()


__all__ = ["enable_verbose", "llm_console"]
