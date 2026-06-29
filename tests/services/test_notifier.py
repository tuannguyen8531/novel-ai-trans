"""Tests for the Telegram notifier and its CLI wiring."""

from __future__ import annotations

import importlib
import unittest
import unittest.mock
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx2 as httpx

from src.services import notifier as notifier_module
from src.services.notifier import (
    TelegramNotifier,
    _NullNotifier,
    format_run_footer,
    get_notifier,
    reset_notifier_cache,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text


class _CaptureClient:
    def __init__(self, response: _FakeResponse | None = None, exc: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._response = response or _FakeResponse()
        self._exc = exc

    def post(self, url: str, json: dict[str, Any], timeout: float | None = None) -> Any:
        self.calls.append({"url": url, "json": dict(json), "timeout": timeout})
        if self._exc is not None:
            raise self._exc
        return self._response


class TelegramNotifierTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_notifier_cache()

    def test_requires_token_and_chat_id(self) -> None:
        with self.assertRaises(ValueError):
            TelegramNotifier(bot_token="", chat_id="abc")
        with self.assertRaises(ValueError):
            TelegramNotifier(bot_token="token", chat_id="")

    def test_send_posts_to_telegram_url(self) -> None:
        client = _CaptureClient(_FakeResponse(200, '{"ok":true}'))
        n = TelegramNotifier(
            bot_token="TOKEN",
            chat_id="123",
            api_base="https://api.telegram.org",
            parse_mode="HTML",
            client=client,  # type: ignore[arg-type]
        )
        self.assertTrue(n.send("<b>hello</b>"))
        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["url"], "https://api.telegram.org/botTOKEN/sendMessage")
        self.assertEqual(call["json"]["chat_id"], "123")
        self.assertEqual(call["json"]["text"], "<b>hello</b>")
        self.assertEqual(call["json"]["parse_mode"], "HTML")
        self.assertTrue(call["json"]["disable_web_page_preview"])

    def test_send_omits_parse_mode_when_unset(self) -> None:
        client = _CaptureClient(_FakeResponse())
        n = TelegramNotifier(bot_token="T", chat_id="1", parse_mode="", client=client)  # type: ignore[arg-type]
        n.send("hi")
        self.assertNotIn("parse_mode", client.calls[0]["json"])

    def test_send_respects_silent_override(self) -> None:
        client = _CaptureClient(_FakeResponse())
        n = TelegramNotifier(
            bot_token="T",
            chat_id="1",
            disable_notification=True,
            client=client,  # type: ignore[arg-type]
        )
        n.send("hi", silent=False)
        self.assertNotIn("disable_notification", client.calls[0]["json"])
        n.send("hi", silent=True)
        self.assertTrue(client.calls[1]["json"]["disable_notification"])

    def test_send_returns_false_on_http_error(self) -> None:
        client = _CaptureClient(_FakeResponse(400, "Bad Request: chat not found"))
        n = TelegramNotifier(bot_token="T", chat_id="1", client=client)  # type: ignore[arg-type]
        self.assertFalse(n.send("hi"))

    def test_send_swallows_network_errors(self) -> None:
        client = _CaptureClient(exc=httpx.ConnectError("dns"))
        n = TelegramNotifier(bot_token="T", chat_id="1", client=client)  # type: ignore[arg-type]
        self.assertFalse(n.send("hi"))

    def test_send_swallows_unexpected_exceptions(self) -> None:
        client = _CaptureClient(exc=RuntimeError("boom"))
        n = TelegramNotifier(bot_token="T", chat_id="1", client=client)  # type: ignore[arg-type]
        self.assertFalse(n.send("hi"))

    def test_send_returns_false_for_empty_message(self) -> None:
        client = _CaptureClient(_FakeResponse())
        n = TelegramNotifier(bot_token="T", chat_id="1", client=client)  # type: ignore[arg-type]
        self.assertFalse(n.send(""))
        self.assertEqual(client.calls, [])

    def test_escape_handles_html_chars(self) -> None:
        n = TelegramNotifier(bot_token="T", chat_id="1", client=_CaptureClient())  # type: ignore[arg-type]
        self.assertEqual(n.escape("<b>Tom & Jerry</b>"), "&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;")
        self.assertEqual(n.escape("a < b > c"), "a &lt; b &gt; c")

    def test_strips_trailing_slash_from_api_base(self) -> None:
        client = _CaptureClient(_FakeResponse())
        n = TelegramNotifier(
            bot_token="T",
            chat_id="1",
            api_base="https://proxy.example.com/",
            client=client,  # type: ignore[arg-type]
        )
        n.send("hi")
        self.assertEqual(client.calls[0]["url"], "https://proxy.example.com/botT/sendMessage")


class GetNotifierTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_notifier_cache()

    def _fake_config(self, **overrides: Any) -> Any:
        defaults: dict[str, Any] = dict(
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_chat_id="1",
            telegram_api_base="https://api.telegram.org",
            telegram_parse_mode="HTML",
            telegram_disable_notification=False,
            telegram_timeout_seconds=5.0,
        )
        defaults.update(overrides)
        return unittest.mock.MagicMock(**defaults)

    def test_returns_null_notifier_when_unconfigured(self) -> None:
        fake = self._fake_config(telegram_enabled=False)
        with patch.object(notifier_module, "config", fake):
            n = get_notifier()
        self.assertIsInstance(n, _NullNotifier)
        self.assertFalse(n.is_configured)
        self.assertFalse(n.send("anything"))

    def test_returns_real_notifier_when_configured(self) -> None:
        fake = self._fake_config(telegram_enabled=True, telegram_bot_token="T")
        with patch.object(notifier_module, "config", fake):
            n = get_notifier()
        self.assertIsInstance(n, TelegramNotifier)
        self.assertTrue(n.is_configured)

    def test_singleton_is_cached(self) -> None:
        fake = self._fake_config(telegram_enabled=False)
        with patch.object(notifier_module, "config", fake):
            first = get_notifier()
            second = get_notifier()
        self.assertIs(first, second)

    def test_reset_clears_cache(self) -> None:
        fake_off = self._fake_config(telegram_enabled=False)
        with patch.object(notifier_module, "config", fake_off):
            first = get_notifier()
        reset_notifier_cache()
        fake_on = self._fake_config(telegram_enabled=True, telegram_bot_token="T")
        with patch.object(notifier_module, "config", fake_on):
            second = get_notifier()
        self.assertIsNot(first, second)
        self.assertIsInstance(second, TelegramNotifier)


class NullNotifierTest(unittest.TestCase):
    def test_send_is_noop(self) -> None:
        n = _NullNotifier()
        self.assertFalse(n.is_configured)
        self.assertFalse(n.send("hi"))

    def test_escape_passthrough(self) -> None:
        self.assertEqual(_NullNotifier.escape("<x>"), "<x>")


class ConfigTelegramFieldsTest(unittest.TestCase):
    def test_telegram_disabled_by_default(self) -> None:
        from src.config import Config

        cfg = Config()
        self.assertFalse(cfg.telegram_enabled)
        self.assertEqual(cfg.telegram_bot_token, "")
        self.assertEqual(cfg.telegram_chat_id, "")
        self.assertEqual(cfg.telegram_api_base, "https://api.telegram.org")
        self.assertEqual(cfg.telegram_parse_mode, "HTML")

    def test_telegram_enabled_when_both_set(self) -> None:
        from src.config import Config

        cfg = Config(telegram_bot_token="abc", telegram_chat_id="42")
        self.assertTrue(cfg.telegram_enabled)

    def test_invalid_parse_mode_rejected(self) -> None:
        from src.config import Config

        with self.assertRaises(ValueError):
            Config(telegram_parse_mode="Bogus")

    def test_markdown_parse_mode_rejected_until_formatter_supports_it(self) -> None:
        from src.config import Config

        with self.assertRaises(ValueError):
            Config(telegram_parse_mode="MarkdownV2")

    def test_invalid_timeout_rejected(self) -> None:
        from src.config import Config

        with self.assertRaises(ValueError):
            Config(telegram_timeout_seconds=0)


class CliNotificationWiringTest(unittest.TestCase):
    """The CLI modules should call get_notifier().send() on key events."""

    def test_crawl_cli_sends_on_consecutive_failure(self) -> None:
        from src.cli import crawl as crawl_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with (
            patch.object(crawl_module, "get_notifier", return_value=_Stub()),
            patch.object(crawl_module, "format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 0s"),
            patch.object(crawl_module, "_resolve_config_path", return_value=Path("/tmp/demo.json")),
            patch.object(crawl_module, "SiteConfig") as mock_site_config,
            patch.object(crawl_module, "NovelCrawler") as mock_crawler_cls,
        ):
            instance = mock_crawler_cls.return_value
            instance.config = type("Cfg", (), {"name": "demo"})()
            instance.crawl.side_effect = crawl_module.ConsecutiveFailureError("Stopped after 5 consecutive chapter failures.")
            mock_site_config.from_file.return_value = type("Cfg", (), {"name": "demo"})()

            import argparse

            args = argparse.Namespace(
                target="demo",
                browser=False,
                workers=1,
                max_chapters=None,
                translated_output=None,
                ignore_robots=False,
                fail_fast=False,
                overwrite=False,
                dry_run=False,
            )
            rc = crawl_module._crawl(args)

        self.assertEqual(rc, 1)
        self.assertEqual(len(sent), 1)
        self.assertIn("Status: Failed", sent[0])
        self.assertIn("Task: Crawl", sent[0])
        self.assertIn("Detail:", sent[0])
        self.assertIn("5 consecutive chapter failures", sent[0])

    def test_translate_cli_sends_on_success(self) -> None:
        from src.cli import translate as translate_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with (
            patch.object(translate_module, "get_notifier", return_value=_Stub()),
            patch.object(translate_module, "format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 0s"),
        ):
            translate_module._notify_translation(
                translate_module.get_notifier(),
                "demo-novel",
                "success",
                "",
                {"total": 3, "success": 3, "failed": 0},
            )

        self.assertEqual(len(sent), 1)
        self.assertEqual(
            sent[0],
            "\n".join(
                [
                    "Status: Success",
                    "Task: Translation",
                    "Novel: demo-novel",
                    "Detail: Translation finished.",
                    "Stats: Translated: 3/3",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 0s",
                ]
            ),
        )

    def test_translate_cli_sends_partial_with_failures(self) -> None:
        from src.cli import translate as translate_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with (
            patch.object(translate_module, "get_notifier", return_value=_Stub()),
            patch.object(translate_module, "format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 12s"),
        ):
            translate_module._notify_translation(
                translate_module.get_notifier(),
                "demo-novel",
                "success",
                "",
                {"total": 5, "success": 3, "failed": 2},
            )

        self.assertEqual(
            sent[0],
            "\n".join(
                [
                    "Status: Failed",
                    "Task: Translation",
                    "Novel: demo-novel",
                    "Detail: Translation finished with errors.",
                    "Stats: Translated: 3/5 · Failed: 2",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 12s",
                ]
            ),
        )

    def test_translate_cli_sends_on_failure(self) -> None:
        from src.cli import translate as translate_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with (
            patch.object(translate_module, "get_notifier", return_value=_Stub()),
            patch.object(translate_module, "format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 0s"),
        ):
            translate_module._notify_translation(
                translate_module.get_notifier(),
                "demo-novel",
                "failed",
                "no input chapters",
                {"total": 0, "success": 0, "failed": 0},
            )

        self.assertEqual(
            sent[0],
            "\n".join(
                [
                    "Status: Failed",
                    "Task: Translation",
                    "Novel: demo-novel",
                    "Detail: no input chapters",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 0s",
                ]
            ),
        )

    def test_translate_cli_skips_notification_on_skipped(self) -> None:
        from src.cli import translate as translate_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with patch.object(translate_module, "get_notifier", return_value=_Stub()):
            translate_module._notify_translation(
                translate_module.get_notifier(),
                "demo-novel",
                "skipped",
                "",
                {"total": 0, "success": 0, "failed": 0},
            )

        self.assertEqual(sent, [])

    def test_translate_cli_sends_on_interrupted(self) -> None:
        from src.cli import translate as translate_module

        sent: list[str] = []

        class _Stub:
            @property
            def is_configured(self) -> bool:
                return True

            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        with (
            patch.object(translate_module, "get_notifier", return_value=_Stub()),
            patch.object(translate_module, "format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 45s"),
        ):
            translate_module._notify_translation(
                translate_module.get_notifier(),
                "demo-novel",
                "interrupted",
                "",
                {"total": 5, "success": 2, "failed": 0},
            )

        self.assertEqual(
            sent[0],
            "\n".join(
                [
                    "Status: Success",
                    "Task: Translation",
                    "Novel: demo-novel",
                    "Detail: Translation interrupted.",
                    "Stats: Translated: 2/5",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 45s",
                ]
            ),
        )


class FormatRunFooterTest(unittest.TestCase):
    def test_footer_has_timestamp_and_runtime(self) -> None:
        import re
        import time as _time

        started = _time.time() - 30.0
        footer = format_run_footer(started)
        lines = footer.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^Time: \d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertRegex(lines[1], r"^Runtime: (\d+)s$")
        match = re.search(r"Runtime: (\d+)s", lines[1])
        assert match is not None
        runtime = int(match.group(1))
        self.assertGreaterEqual(runtime, 29)

    def test_footer_clamps_negative_runtime_to_zero(self) -> None:
        footer = format_run_footer(2_000_000_000.0)
        # started_at far in the future → now - started_at negative → clamped to 0
        self.assertRegex(footer.split("\n")[1], r"^Runtime: \d+s$")
        runtime = int(footer.split("\n")[1].removeprefix("Runtime: ").removesuffix("s"))
        self.assertGreaterEqual(runtime, 0)


class ModuleReloadTest(unittest.TestCase):
    def test_module_reload_after_config_change(self) -> None:
        # Smoke test: notifier module can be re-imported without errors.
        importlib.reload(notifier_module)


if __name__ == "__main__":
    unittest.main()
