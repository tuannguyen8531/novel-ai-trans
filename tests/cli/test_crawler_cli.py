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
    _resolve_config_path,
    build_import_parser,
    build_parser,
    build_short_parser,
)
from src.models import CrawlProgress
from src.utils.logging import get_logger, setup_logging


class CliTest(unittest.TestCase):
    def test_short_parser_accepts_novel_and_max_alias(self) -> None:
        args = build_short_parser().parse_args(["sfacg-760079", "--max", "5"])

        self.assertEqual(args.target, "sfacg-760079")
        self.assertEqual(args.max_chapters, 5)

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
        )

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


if __name__ == "__main__":
    unittest.main()
