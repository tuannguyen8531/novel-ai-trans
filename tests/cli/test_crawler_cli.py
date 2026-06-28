from __future__ import annotations

import contextlib
import io
import logging
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from src.cli import crawl
from src.cli.crawl import (
    _browser_profile_dir,
    _resolve_config_path,
    build_import_parser,
    build_parser,
    build_short_parser,
)
from src.models import ChapterResult, CrawlProgress, CrawlResult, NovelMetadata
from src.utils.logging import get_logger, setup_logging


class CliTest(unittest.TestCase):
    def test_short_parser_accepts_novel_and_max_alias(self) -> None:
        args = build_short_parser().parse_args(["sfacg-760079", "--max", "5"])

        self.assertEqual(args.target, "sfacg-760079")
        self.assertEqual(args.max_chapters, 5)

    def test_short_parser_accepts_headed_browser(self) -> None:
        args = build_short_parser().parse_args(["example", "-h"])

        self.assertTrue(args.headed)

    def test_browser_modes_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            build_short_parser().parse_args(["example", "-b", "-h"])

    def test_browser_profile_is_scoped_by_domain(self) -> None:
        self.assertEqual(
            _browser_profile_dir("https://www.69shuba.com/book/84642/"),
            Path("runtime/crawler/browser-profiles/www.69shuba.com"),
        )

    def test_resolve_config_path_accepts_novel_name(self) -> None:
        self.assertEqual(_resolve_config_path("example"), Path("configs/example.json"))

    def test_resolve_config_path_accepts_direct_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text("{}", encoding="utf-8")

            self.assertEqual(_resolve_config_path(str(config_path)), config_path)

    def test_validate_parser_exists(self) -> None:
        args = build_parser().parse_args(["validate", "demo"])
        self.assertEqual(args.command, "validate")
        self.assertEqual(args.target, "demo")

    def test_generate_parser_accepts_ignore_sample(self) -> None:
        args = build_parser().parse_args(["generate", "https://example.com/book/", "--ignore-sample"])
        self.assertEqual(args.command, "generate")
        self.assertTrue(args.ignore_sample)

    def test_import_parser_accepts_name_and_translated_output(self) -> None:
        args = build_parser().parse_args(["import", "book.epub", "-n", "manual-name", "--translated-output", "/tmp/translated"])
        short_args = build_import_parser().parse_args(["book.epub", "--keep-existing"])

        self.assertEqual(args.command, "import")
        self.assertEqual(args.epub, Path("book.epub"))
        self.assertEqual(args.name, "manual-name")
        self.assertEqual(args.translated_output, Path("/tmp/translated"))
        self.assertEqual(short_args.epub, Path("book.epub"))
        self.assertTrue(short_args.keep_existing)

    def test_crawl_validation_rejects_zero_workers(self) -> None:
        import argparse

        from src.cli.crawl import _crawl

        args = argparse.Namespace(
            target="example",
            workers=0,
            browser=False,
            max_chapters=None,
            translated_output=None,
        )
        res = _crawl(args)
        self.assertEqual(res, 1)

    @unittest.mock.patch("src.cli.crawl.BrowserFetcher")
    @unittest.mock.patch("src.cli.crawl._crawl_with_fetcher")
    def test_crawl_browser_passes_worker_count_to_fetcher(self, mock_crawl_with_fetcher, mock_browser_fetcher) -> None:
        import argparse

        from src.cli.crawl import _crawl

        args = argparse.Namespace(
            target="example",
            workers=4,
            browser=True,
            max_chapters=None,
            translated_output=None,
        )
        _crawl(args)
        self.assertEqual(args.workers, 4)
        mock_browser_fetcher.assert_called_once_with(
            user_agent=unittest.mock.ANY,
            timeout_seconds=unittest.mock.ANY,
            delay_seconds=unittest.mock.ANY,
            retry_attempts=unittest.mock.ANY,
            retry_backoff_seconds=unittest.mock.ANY,
            max_concurrency=4,
            profile_dir=None,
            headless=True,
            challenge_timeout_seconds=30.0,
        )

    @unittest.mock.patch("src.cli.crawl.BrowserFetcher")
    @unittest.mock.patch("src.cli.crawl._crawl_with_fetcher")
    def test_crawl_defaults_to_one_worker(self, mock_crawl_with_fetcher, mock_browser_fetcher) -> None:
        import argparse

        from src.cli.crawl import _crawl

        args = argparse.Namespace(
            target="example",
            workers=None,
            browser=True,
            max_chapters=None,
            translated_output=None,
        )
        _crawl(args)
        self.assertEqual(args.workers, 1)
        mock_browser_fetcher.assert_called_once_with(
            user_agent=unittest.mock.ANY,
            timeout_seconds=unittest.mock.ANY,
            delay_seconds=unittest.mock.ANY,
            retry_attempts=unittest.mock.ANY,
            retry_backoff_seconds=unittest.mock.ANY,
            max_concurrency=1,
            profile_dir=None,
            headless=True,
            challenge_timeout_seconds=30.0,
        )

    @unittest.mock.patch("src.cli.crawl.BrowserFetcher")
    @unittest.mock.patch("src.cli.crawl._crawl_with_fetcher")
    def test_headed_implies_browser_mode(self, mock_crawl_with_fetcher, mock_browser_fetcher) -> None:
        import argparse

        from src.cli.crawl import _crawl

        args = argparse.Namespace(
            target="example",
            workers=None,
            browser=None,
            headed=True,
            max_chapters=None,
            translated_output=None,
        )
        _crawl(args)

        self.assertEqual(args.workers, 1)
        mock_browser_fetcher.assert_called_once_with(
            user_agent=None,
            timeout_seconds=unittest.mock.ANY,
            delay_seconds=unittest.mock.ANY,
            retry_attempts=unittest.mock.ANY,
            retry_backoff_seconds=unittest.mock.ANY,
            max_concurrency=1,
            profile_dir=unittest.mock.ANY,
            headless=False,
            challenge_timeout_seconds=120.0,
        )
        mock_crawl_with_fetcher.assert_called_once()

    def test_logging_stderr_and_quiet_mode(self) -> None:
        setup_logging("info")
        logger = get_logger("novel_crawler")
        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        assert isinstance(handler, logging.StreamHandler)
        self.assertEqual(handler.stream, sys.stderr)

        crawl._setup_cli_logging(quiet=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            crawl._print_progress(
                CrawlProgress(
                    current=1,
                    total=3,
                    status="fetched",
                    title="Chapter 1",
                    source_url="url",
                )
            )
        self.assertEqual(output.getvalue(), "")

    def test_short_crawl_entrypoint_configures_logging(self) -> None:
        error_output = io.StringIO()
        with contextlib.redirect_stderr(error_output):
            result = crawl.crawl_main(["missing-config"])
        self.assertEqual(result, 1)
        self.assertIn("Config not found", error_output.getvalue())

    def test_crawl_notification_counts_result_errors(self) -> None:
        import argparse

        sent: list[str] = []

        class _StubNotifier:
            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        crawler = unittest.mock.MagicMock()
        crawler.config = unittest.mock.MagicMock()
        crawler.config.name = "demo-slug"
        crawler.crawl.return_value = CrawlResult(
            metadata=NovelMetadata(title="Demo <Novel>", author=None, source_url="url", site_name="demo"),
            chapters=[
                ChapterResult(index=1, title="C1", source_url="u1", path="p1"),
                ChapterResult(index=2, title="C2", source_url="u2", path="p2", skipped=True),
            ],
            output_dir="runtime/demo",
            chapter_output_dir="runtime/demo/chapters",
            errors=[{"index": 3, "url": "u3", "error": "failed"}],
        )
        args = argparse.Namespace(dry_run=False, fail_fast=False, overwrite=False, workers=1)

        with (
            unittest.mock.patch("src.cli.crawl.get_notifier", return_value=_StubNotifier()),
            unittest.mock.patch("src.cli.crawl.format_run_footer", return_value="Time: 2026-01-01 00:00\nRuntime: 0s"),
        ):
            result = crawl._run_crawl(crawler, args, max_chapters=None, share_root=None, started_at=0.0)

        self.assertEqual(result, 0)
        self.assertEqual(len(sent), 1)
        self.assertEqual(
            sent[0],
            "\n".join(
                [
                    "Status: Failed",
                    "Task: Crawl",
                    "Novel: demo-slug",
                    "Detail: Crawl finished with chapter errors.",
                    "Stats: New: 1 · Skipped: 1 · Failed: 1",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 0s",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
