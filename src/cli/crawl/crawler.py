"""CLI adapter for crawling novel chapters."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.application.crawl.crawler import CrawlRequest, run_crawl
from src.application.errors import ApplicationError, ExternalServiceError
from src.application.progress import ProgressEvent
from src.cli.crawl import common
from src.services.notifier import format_run_footer, get_notifier
from src.utils.logging import get_logger


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument("novel", type=str, help="Novel slug from translated/<slug>/config.json.")
    parser.add_argument(
        "--translated-output",
        type=Path,
        default=None,
        help="Per-novel translated root. Default: TRANSLATED_DIR or ./translated",
    )
    parser.add_argument(
        "-m",
        "--max",
        "--max-chapters",
        type=int,
        default=None,
        dest="max_chapters",
        help="Stop after fetching this many new chapters. Default: MAX_CHAPTERS env or unlimited.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first chapter error instead of writing partial output.",
    )
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Do not check robots.txt. Use only when you have permission.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only discover chapter links and print a preview.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download chapter files even if the shared chapter_NNN.txt already exists.",
    )
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument(
        "-b",
        "--browser",
        action="store_true",
        default=None,
        help="Use an ephemeral headless browser. Default: off.",
    )
    browser_mode.add_argument(
        "-h",
        "--headed",
        action="store_true",
        help="Use a visible browser with a persistent per-domain profile.",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=None,
        help="Concurrent chapter downloads. Default: 1.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawl",
        description="Download chapters from public novel websites.",
        add_help=False,
    )
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.configure_logging()
    return run(args)


def run(args: argparse.Namespace) -> int:
    started_at = time.time()
    try:
        result = run_crawl(
            CrawlRequest(
                novel=args.novel,
                translated_output=args.translated_output,
                max_chapters=args.max_chapters,
                fail_fast=args.fail_fast,
                ignore_robots=args.ignore_robots,
                overwrite=args.overwrite,
                use_browser=args.browser,
                headed=getattr(args, "headed", False),
                workers=args.workers if args.workers is not None else 1,
                dry_run=args.dry_run,
            ),
            progress_callback=print_progress,
        )
    except ExternalServiceError as error:
        get_logger().error("Error: %s", error)
        get_notifier().send(
            "Status: Failed\n"
            "Task: Crawl\n"
            f"Novel: {notifier_escape(str(error.details.get('novel') or args.novel))}\n"
            f"Detail: {notifier_escape(str(error))}\n"
            f"{format_run_footer(started_at)}"
        )
        return 1
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1
    except KeyboardInterrupt:
        get_logger().warning("Interrupted. Progress saved.")
        return 130

    if result.dry_run:
        common.print_output(f"Title: {result.title}")
        if result.author:
            common.print_output(f"Author: {result.author}")
        common.print_output(f"Chapters found: {result.total}")
        for item in result.preview[:10]:
            common.print_output(f"{item.index:04d}. {item.title} - {item.url}")
        if result.total > 10:
            common.print_output(f"... {result.total - 10} more")
        return 0

    common.print_output(f"Done: {result.title} ({result.fetched}/{result.total} new, {result.skipped}/{result.total} skipped)")
    status = "Success" if result.failed == 0 else "Failed"
    detail = "Crawl finished." if result.failed == 0 else "Crawl finished with chapter errors."
    get_notifier().send(
        f"Status: {status}\n"
        "Task: Crawl\n"
        f"Novel: {notifier_escape(result.novel)}\n"
        f"Detail: {detail}\n"
        f"Stats: New: {result.fetched}/{result.total} · "
        f"Skipped: {result.skipped}/{result.total} · Failed: {result.failed}/{result.total}\n"
        f"{format_run_footer(started_at)}"
    )
    return 0


def print_progress(event: ProgressEvent) -> None:
    if event.kind != "chapter":
        return

    status = event.extra.get("status")
    if status in ("started", "skipped"):
        return
    if status == "fetched":
        common.print_output(f"[{event.current}/{event.total}] {event.message}", flush=True)
        return
    if status == "failed":
        detail = event.extra.get("error") or "unknown error"
        print(
            f"[{event.current}/{event.total}] {event.message} (fail: {detail})",
            file=sys.stderr,
            flush=True,
        )
        return

    common.print_output(
        f"[{event.current}/{event.total}] {event.message} ({status})",
        flush=True,
    )


def notifier_escape(text: str) -> str:
    """HTML-escape text for Telegram HTML parse mode."""
    return get_notifier().escape(text)
