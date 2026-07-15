from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from src.application.crawl.common import resolve_config_path
from src.application.crawl.crawler import CrawlResult, browser_profile_dir
from src.application.errors import ResourceNotFoundError
from src.application.progress import ProgressEvent
from src.cli.crawl import common, crawler
from src.cli.crawl.crawler import build_parser as build_short_parser
from src.cli.crawl.dispatcher import build_parser
from src.cli.crawl.generator import build_parser as build_generate_parser
from src.cli.crawl.importer import build_parser as build_import_parser
from src.paths import RUNTIME_DIR
from src.utils.logging import get_logger, setup_logging


def _dry_crawl_result() -> CrawlResult:
    return CrawlResult(
        novel="example",
        title="Example",
        author=None,
        fetched=0,
        skipped=0,
        failed=0,
        total=0,
        output_dir="",
        chapter_output_dir="",
        started_at=0.0,
        finished_at=0.0,
        dry_run=True,
    )


def _crawl_args(**overrides: object) -> argparse.Namespace:
    values = {
        "novel": "example",
        "workers": 1,
        "browser": False,
        "headed": False,
        "max_chapters": None,
        "translated_output": None,
        "fail_fast": False,
        "ignore_robots": False,
        "overwrite": False,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class CliTest(unittest.TestCase):
    def test_short_parser_accepts_novel_and_max_alias(self) -> None:
        args = build_short_parser().parse_args(["sfacg-760079", "--max", "5"])

        self.assertEqual(args.novel, "sfacg-760079")
        self.assertEqual(args.max_chapters, 5)

    def test_short_parser_accepts_headed_browser(self) -> None:
        args = build_short_parser().parse_args(["example", "-h"])

        self.assertTrue(args.headed)

    def test_browser_modes_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            build_short_parser().parse_args(["example", "-b", "-h"])

    def test_browser_profile_is_scoped_by_domain(self) -> None:
        self.assertEqual(
            browser_profile_dir("https://www.69shuba.com/book/84642/"),
            RUNTIME_DIR / "browser-profiles/www.69shuba.com",
        )

    def test_resolve_config_path_accepts_novel_name(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            translated_root = Path(tempdir)
            config_path = translated_root / "example" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text("{}", encoding="utf-8")

            self.assertEqual(
                resolve_config_path("example", translated_root=translated_root),
                config_path,
            )

    def test_resolve_config_path_rejects_direct_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.json"
            config_path.write_text("{}", encoding="utf-8")

            with self.assertRaises(ResourceNotFoundError):
                resolve_config_path(str(config_path))

    def test_validate_parser_exists(self) -> None:
        args = build_parser().parse_args(["validate", "demo"])
        self.assertEqual(args.command, "validate")
        self.assertEqual(args.novel, "demo")

    def test_generate_parser_accepts_ignore_sample(self) -> None:
        args = build_parser().parse_args(["generate", "https://example.com/book/", "--ignore-sample"])
        self.assertEqual(args.command, "generate")
        self.assertTrue(args.ignore_sample)

    def test_generate_parser_uses_translated_output_only(self) -> None:
        args = build_generate_parser().parse_args(["https://example.com/book/", "--translated-output", "/tmp/books"])
        self.assertEqual(args.translated_output, Path("/tmp/books"))

        with self.assertRaises(SystemExit):
            build_generate_parser().parse_args(["https://example.com/book/", "--output", "/tmp/configs"])

    def test_generate_parser_accepts_headed_browser(self) -> None:
        args = build_generate_parser().parse_args(["https://example.com/book/", "-h"])
        dispatched_args = build_parser().parse_args(["generate", "https://example.com/book/", "-h"])

        self.assertTrue(args.headed)
        self.assertFalse(args.browser)
        self.assertTrue(dispatched_args.headed)
        self.assertFalse(dispatched_args.browser)

    def test_generate_browser_modes_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            build_generate_parser().parse_args(["https://example.com/book/", "-b", "-h"])

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
        self.assertEqual(crawler.run(_crawl_args(workers=0)), 1)

    @unittest.mock.patch("src.cli.crawl.crawler.run_crawl")
    def test_crawl_browser_passes_worker_count_to_application(self, mock_run_crawl) -> None:
        mock_run_crawl.return_value = _dry_crawl_result()
        crawler.run(_crawl_args(workers=4, browser=True, dry_run=True))
        request = mock_run_crawl.call_args.args[0]
        self.assertEqual(request.workers, 4)
        self.assertTrue(request.use_browser)
        self.assertFalse(request.headed)

    @unittest.mock.patch("src.cli.crawl.crawler.run_crawl")
    def test_crawl_defaults_to_one_worker(self, mock_run_crawl) -> None:
        mock_run_crawl.return_value = _dry_crawl_result()
        crawler.run(_crawl_args(workers=None, browser=True, dry_run=True))
        request = mock_run_crawl.call_args.args[0]
        self.assertEqual(request.workers, 1)

    @unittest.mock.patch("src.cli.crawl.crawler.run_crawl")
    def test_headed_implies_browser_mode(self, mock_run_crawl) -> None:
        mock_run_crawl.return_value = _dry_crawl_result()
        crawler.run(_crawl_args(workers=None, browser=None, headed=True, dry_run=True))
        request = mock_run_crawl.call_args.args[0]
        self.assertEqual(request.workers, 1)
        self.assertIsNone(request.use_browser)
        self.assertTrue(request.headed)

    def test_logging_stderr_and_quiet_mode(self) -> None:
        setup_logging("info")
        logger = get_logger("novel_crawler")
        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        assert isinstance(handler, logging.StreamHandler)
        self.assertEqual(handler.stream, sys.stderr)

        common.configure_logging(quiet=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            crawler.print_progress(
                ProgressEvent(
                    kind="chapter",
                    current=1,
                    total=3,
                    message="Chapter 1",
                    extra={"status": "fetched", "url": "url"},
                )
            )
        self.assertEqual(output.getvalue(), "")

    def test_short_crawl_entrypoint_configures_logging(self) -> None:
        error_output = io.StringIO()
        with contextlib.redirect_stderr(error_output):
            result = crawler.main(["missing-config"])
        self.assertEqual(result, 1)
        self.assertIn("Config not found", error_output.getvalue())

    def test_crawl_notification_counts_result_errors(self) -> None:
        sent: list[str] = []

        class _StubNotifier:
            def send(self, message: str, *, silent: bool | None = None) -> bool:
                sent.append(message)
                return True

            @staticmethod
            def escape(text: str) -> str:
                return text

        crawl_result = CrawlResult(
            novel="demo-slug",
            title="Demo <Novel>",
            author=None,
            fetched=1,
            skipped=1,
            failed=1,
            total=3,
            output_dir="runtime/demo",
            chapter_output_dir="runtime/demo/chapters",
            started_at=0.0,
            finished_at=0.0,
        )
        args = _crawl_args(
            novel="demo",
            dry_run=False,
        )

        with (
            unittest.mock.patch("src.cli.crawl.crawler.get_notifier", return_value=_StubNotifier()),
            unittest.mock.patch(
                "src.cli.crawl.crawler.format_run_footer",
                return_value="Time: 2026-01-01 00:00\nRuntime: 0s",
            ),
            unittest.mock.patch("src.cli.crawl.crawler.run_crawl", return_value=crawl_result),
        ):
            result = crawler.run(args)

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
                    "Stats: New: 1/3 · Skipped: 1/3 · Failed: 1/3",
                    "Time: 2026-01-01 00:00",
                    "Runtime: 0s",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
