"""Telegram notification helper.

Optional: if ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` are unset in the
environment the notifier is a no-op, so callers can invoke ``send()``
unconditionally without breaking the main flow. All network errors are
swallowed and logged at warning level — notification failures must never
crash a crawl or translation run.
"""

from __future__ import annotations

import html
import time
from datetime import datetime
from typing import Any

import httpx

from src.config import config
from src.utils.logging import get_logger

_logger = get_logger()

_SEND_MESSAGE_PATH = "/bot{token}/sendMessage"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def format_run_footer(started_at: float) -> str:
    """Build the trailing timestamp + runtime block for run notifications.

    Format: ``Time: YYYY-MM-DD HH:MM\\nRuntime: <seconds>s``.
    """
    now = time.time()
    timestamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M")
    runtime = max(0, int(now - started_at))
    return f"Time: {timestamp}\nRuntime: {runtime}s"


class TelegramNotifier:
    """Send plain-text or HTML messages to a single Telegram chat."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        api_base: str = "https://api.telegram.org",
        parse_mode: str = "HTML",
        disable_notification: bool = False,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not bot_token or not chat_id:
            raise ValueError("TelegramNotifier requires both bot_token and chat_id.")
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_base = api_base.rstrip("/")
        self._parse_mode = parse_mode or ""
        self._disable_notification = disable_notification
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def is_configured(self) -> bool:
        return True

    def send(self, message: str, *, silent: bool | None = None) -> bool:
        """Post ``message`` to the configured chat. Returns True on success.

        Never raises: any HTTP, network, or serialisation error is logged
        at warning level and the method returns False.
        """
        if not message:
            return False

        url = f"{self._api_base}{_SEND_MESSAGE_PATH.format(token=self._bot_token)}"
        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        if self._parse_mode:
            payload["parse_mode"] = self._parse_mode
        effective_silent = self._disable_notification if silent is None else silent
        if effective_silent:
            payload["disable_notification"] = True

        try:
            if self._client is not None:
                response = self._client.post(url, json=payload, timeout=self._timeout_seconds)
            else:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            _logger.warning("Telegram notification failed (network error): %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 - defensive: never crash the caller
            _logger.warning("Telegram notification failed (unexpected error): %s", exc)
            return False

        if response.status_code >= 400:
            _logger.warning(
                "Telegram API returned %s: %s",
                response.status_code,
                _safe_truncate(response.text, 200),
            )
            return False
        return True

    @staticmethod
    def escape(text: str) -> str:
        """Escape user text for Telegram's HTML parse mode."""
        return html.escape(text, quote=False)


class _NullNotifier:
    """Stand-in used when Telegram is not configured. All sends are no-ops."""

    @property
    def is_configured(self) -> bool:
        return False

    def send(self, message: str, *, silent: bool | None = None) -> bool:
        return False

    @staticmethod
    def escape(text: str) -> str:
        return text


_NOTIFIER: TelegramNotifier | _NullNotifier | None = None


def get_notifier() -> TelegramNotifier | _NullNotifier:
    """Return a process-wide notifier (real Telegram client or null object)."""
    global _NOTIFIER
    if _NOTIFIER is not None:
        return _NOTIFIER
    if config.telegram_enabled:
        _NOTIFIER = TelegramNotifier(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
            api_base=config.telegram_api_base,
            parse_mode=config.telegram_parse_mode,
            disable_notification=config.telegram_disable_notification,
            timeout_seconds=config.telegram_timeout_seconds,
        )
    else:
        _NOTIFIER = _NullNotifier()
    return _NOTIFIER


def reset_notifier_cache() -> None:
    """Drop the cached notifier (used by tests to pick up env changes)."""
    global _NOTIFIER
    _NOTIFIER = None


def _safe_truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
