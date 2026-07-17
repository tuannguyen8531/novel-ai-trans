from __future__ import annotations

import logging
from unittest.mock import patch

from src.cli.logging import llm_console
from src.services import logger as logger_service


def test_llm_console_starts_and_stops_spinner_from_service_events() -> None:
    job_logger = logging.getLogger("novel_ai_trans.job")
    with (
        patch("src.cli.logging._Spinner.start") as start,
        patch("src.cli.logging._Spinner.stop") as stop,
        llm_console(),
    ):
        job_logger.info(
            "Calling ollama (translate)...",
            extra={"presentation_event": "llm_call_started"},
        )
        job_logger.info(
            "Done ollama (translate) in 1.0s",
            extra={"presentation_event": "llm_call_completed"},
        )

    start.assert_called_once_with("Calling ollama (translate)...")
    assert stop.call_count >= 1


def test_llm_console_preserves_retry_and_fallback_messages(capsys) -> None:
    job_logger = logging.getLogger("novel_ai_trans.job")
    with patch("src.cli.logging._Spinner.stop"), llm_console():
        job_logger.info(
            "retry",
            extra={
                "presentation_event": "llm_retry",
                "provider": "ollama",
                "delay": 5,
                "attempt": 1,
                "max_retries": 3,
            },
        )
        job_logger.info(
            "failed",
            extra={
                "presentation_event": "llm_fallback_failed",
                "provider": "gemini",
                "error_message": "timed out",
            },
        )
        job_logger.info(
            "fallback",
            extra={"presentation_event": "llm_fallback_started", "provider": "ollama"},
        )
        job_logger.info(
            "Language: chinese",
            extra={
                "presentation_event": "cli_message",
                "presentation_message": "  📝 Language: chinese",
            },
        )

    output = capsys.readouterr().out
    assert "ollama error — waiting 5s before retry (1/3)..." in output
    assert "⚠ gemini failed: timed out" in output
    assert "Falling back to ollama..." in output
    assert "  📝 Language: chinese" in output


def test_llm_console_preserves_verbose_ai_output(capsys) -> None:
    logger_service.set_verbose(True)
    try:
        with patch("src.cli.logging._Spinner.stop"), llm_console():
            logger_service.log_ai_call(
                "translate",
                system_prompt="system prompt",
                user_prompt="user prompt",
                response="translated response",
            )
    finally:
        logger_service.set_verbose(False)

    output = capsys.readouterr().out
    assert "--- SYSTEM (13 chars) ---" in output
    assert "system prompt" in output
    assert "--- RESPONSE (19 chars) ---" in output
    assert "translated response" in output
