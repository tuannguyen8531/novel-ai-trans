from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from src.application.crawl import (
    ConfigIssue,
    CrawlRequest,
    ImportRequest,
    generate_config,
    import_epub_workflow,
    run_crawl,
    save_generated_config,
    validate_config,
)
from src.application.errors import ApplicationError, ExternalServiceError
from src.application.progress import ProgressEvent
from src.paths import CONFIG_DIR
from src.services.notifier import format_run_footer, get_notifier
from src.utils.logging import get_logger, setup_logging

_quiet_output = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-crawler",
        description="Download chapters from public novel websites using a per-site JSON config.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress crawler progress and non-error logs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl = subparsers.add_parser(
        "crawl",
        help="Download a novel into text files.",
        add_help=False,
    )
    _add_crawl_arguments(crawl, target_help="Config path or novel name from configs/{novel}.json.")

    gen = subparsers.add_parser(
        "generate",
        help="Use AI to generate a site config from a novel information URL.",
        add_help=False,
    )
    _add_generate_arguments(gen)

    validate = subparsers.add_parser(
        "validate",
        help="Test a config's selectors against live HTML.",
    )
    _add_validate_arguments(validate)

    import_parser = subparsers.add_parser(
        "import",
        help="Import an EPUB into the translated input directory.",
    )
    _add_import_arguments(import_parser)

    return parser


def build_short_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawl",
        description="Download chapters from public novel websites.",
        add_help=False,
    )
    _add_crawl_arguments(parser, target_help="Config path or novel name from configs/{novel}.json.")
    return parser


def build_generate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate",
        description="Use AI to generate a site config from a novel information URL.",
        add_help=False,
    )
    _add_generate_arguments(parser)
    return parser


def build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate",
        description="Test a config's selectors against live HTML.",
    )
    _add_validate_arguments(parser)
    return parser


def build_import_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import",
        description="Import an EPUB into the translated input directory.",
    )
    _add_import_arguments(parser)
    return parser


def _add_crawl_arguments(parser: argparse.ArgumentParser, *, target_help: str) -> None:
    parser.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument("target", type=str, help=target_help)
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
        help="Re-download chapter files even if the shared chapter_N.txt already exists.",
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


def _add_generate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument("url", type=str, help="URL of the novel's main information page.")
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Config name (default: derived from URL).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider override (ollama/gemini).",
    )
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument(
        "-b",
        "--browser",
        action="store_true",
        help="Use an ephemeral headless browser to fetch pages.",
    )
    browser_mode.add_argument(
        "-h",
        "--headed",
        action="store_true",
        help="Use a visible browser to fetch pages.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the HTML cache and always re-fetch pages.",
    )
    parser.add_argument(
        "--ignore-sample",
        action="store_true",
        help="Ignore bundled samples and known-domain configs; analyze live HTML with the LLM.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CONFIG_DIR,
        help=f"Output directory (default: {CONFIG_DIR}).",
    )


def _add_validate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        type=str,
        help="Config path or novel name from configs/{novel}.json.",
    )
    parser.add_argument(
        "-b",
        "--browser",
        action="store_true",
        help="Use headless browser to fetch pages.",
    )


def _add_import_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("epub", type=Path, help="EPUB file path to import.")
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help="Output slug name. Defaults to the EPUB filename.",
    )
    parser.add_argument(
        "--translated-output",
        type=Path,
        default=None,
        help="Per-novel translated root. Default: TRANSLATED_DIR or ./translated.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing chapter_*.txt files in the target input directory.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_cli_logging(verbose=args.verbose, quiet=args.quiet)

    if args.command == "crawl":
        return _crawl(args)
    if args.command == "generate":
        return _generate(args)
    if args.command == "validate":
        return _validate(args)
    if args.command == "import":
        return _import_epub(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def crawl_main(argv: list[str] | None = None) -> int:
    parser = build_short_parser()
    args = parser.parse_args(argv)
    _setup_cli_logging()
    return _crawl(args)


def generate_main(argv: list[str] | None = None) -> int:
    parser = build_generate_parser()
    args = parser.parse_args(argv)
    _setup_cli_logging()
    return _generate(args)


def validate_main(argv: list[str] | None = None) -> int:
    parser = build_validate_parser()
    args = parser.parse_args(argv)
    _setup_cli_logging()
    return _validate(args)


def import_main(argv: list[str] | None = None) -> int:
    parser = build_import_parser()
    args = parser.parse_args(argv)
    _setup_cli_logging()
    return _import_epub(args)


def _setup_cli_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    global _quiet_output
    _quiet_output = quiet
    log_level = "debug" if verbose else ("error" if quiet else "info")
    setup_logging(log_level)


def _print_output(*args: object, **kwargs: Any) -> None:
    if not _quiet_output:
        print(*args, **kwargs)


def _crawl(args: argparse.Namespace) -> int:
    started_at = time.time()
    try:
        result = run_crawl(
            CrawlRequest(
                target=args.target,
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
            progress_callback=_print_progress,
        )
    except ExternalServiceError as error:
        get_logger().error("Error: %s", error)
        get_notifier().send(
            "Status: Failed\n"
            "Task: Crawl\n"
            f"Novel: {_notifier_escape(str(error.details.get('novel') or args.target))}\n"
            f"Detail: {_notifier_escape(str(error))}\n"
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
        _print_output(f"Title: {result.title}")
        if result.author:
            _print_output(f"Author: {result.author}")
        _print_output(f"Chapters found: {result.total}")
        for item in result.preview[:10]:
            _print_output(f"{item.index:04d}. {item.title} - {item.url}")
        if result.total > 10:
            _print_output(f"... {result.total - 10} more")
        return 0

    _print_output(f"Done: {result.title} ({result.fetched}/{result.total} new, {result.skipped}/{result.total} skipped)")
    status = "Success" if result.failed == 0 else "Failed"
    detail = "Crawl finished." if result.failed == 0 else "Crawl finished with chapter errors."
    get_notifier().send(
        f"Status: {status}\n"
        "Task: Crawl\n"
        f"Novel: {_notifier_escape(result.novel)}\n"
        f"Detail: {detail}\n"
        f"Stats: New: {result.fetched}/{result.total} · "
        f"Skipped: {result.skipped}/{result.total} · Failed: {result.failed}/{result.total}\n"
        f"{format_run_footer(started_at)}"
    )
    return 0


def _import_epub(args: argparse.Namespace) -> int:
    try:
        result = import_epub_workflow(
            ImportRequest(
                epub_path=args.epub,
                name=args.name,
                translated_output=args.translated_output,
                keep_existing=args.keep_existing,
            )
        )
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1

    for warning in result.warnings:
        get_logger().warning(warning)
    _print_output(f"Imported: {result.title} ({result.chapters} chapters, {result.illustrations} illustrations)")
    _print_output(
        "Chapters: "
        f"retained {result.retained} · unchanged {result.unchanged} · "
        f"overwritten {result.overwritten} · added {result.added} · removed {result.removed}"
    )
    for chapter in result.overwritten_chapters:
        _print_output(f"Overwritten chapter {chapter.number}: {chapter.title}")
    _print_output(f"Output: {result.output_dir}")
    return 0


def _print_progress(event: ProgressEvent) -> None:
    if event.kind != "chapter":
        return

    status = event.extra.get("status")
    if status in ("started", "skipped"):
        return
    if status == "fetched":
        _print_output(f"[{event.current}/{event.total}] {event.message}", flush=True)
        return
    if status == "failed":
        detail = event.extra.get("error") or "unknown error"
        print(
            f"[{event.current}/{event.total}] {event.message} (fail: {detail})",
            file=sys.stderr,
            flush=True,
        )
        return

    _print_output(
        f"[{event.current}/{event.total}] {event.message} ({status})",
        flush=True,
    )


def _notifier_escape(text: str) -> str:
    """HTML-escape text for Telegram HTML parse mode."""
    return get_notifier().escape(text)


def _generate(args: argparse.Namespace) -> int:
    """Generate a site config using AI."""
    try:
        result = generate_config(
            url=args.url,
            name=args.name,
            provider=args.provider,
            use_browser=args.browser,
            headed=args.headed,
            no_cache=args.no_cache,
            ignore_sample=args.ignore_sample,
            progress_callback=_print_generation_progress,
        )

        print(f"\n{'═' * 60}")
        print("Generated config:")
        print(f"{'═' * 60}")
        print(json.dumps(result.config, ensure_ascii=False, indent=2))
        print(f"{'═' * 60}")

        output_dir: Path = args.output
        name = result.config.get("name", "generated")
        dest = output_dir / f"{name}.json"
        answer = input(f"\nSave to {dest}? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            path = save_generated_config(result.config, output_dir)
            print(f"✅ Config saved to {path}")
            return 0

        print("Cancelled.")
        return 0

    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - CLI must report unexpected generation failures.
        get_logger().error("Error: %s", error)
        return 1


def _print_generation_progress(event: ProgressEvent) -> None:
    if event.kind == "log":
        get_logger().warning(event.message)


def _validate(args: argparse.Namespace) -> int:
    """Test a config's selectors against live HTML."""
    try:
        result = validate_config(target=args.target, use_browser=args.browser)
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - keep CLI validation failures user-visible.
        get_logger().error("Error: %s", error)
        return 1

    print(f"\n{'═' * 60}")
    print("Validating config selectors")
    print(f"{'═' * 60}")
    print(f"Config: {result.config_path}")
    print(f"Start URL: {result.start_url}")
    print(f"Fetcher: {result.fetcher}")
    print()

    toc_labels = {
        "novel_title_selector",
        "author_selector",
        "chapter_link_selector",
        "toc_next_selector",
        "toc_expand_selector",
    }
    chapter_labels = {
        "chapter_title_selector",
        "chapter_content_selector",
    }
    toc_issues = [issue for issue in result.issues if issue.label in toc_labels]
    chapter_issues = [issue for issue in result.issues if issue.label in chapter_labels]
    remove_issues = [issue for issue in result.issues if issue.label == "remove_selectors"]

    print("📖 TOC Page")
    print(f"   URL: {result.start_url}")
    for issue in toc_issues:
        _print_selector_issue(issue)

    print()
    print(f"📚 Discovered {result.chapter_count} chapters")
    print(f"   Title: {result.metadata.get('title')}")
    if result.metadata.get("author"):
        print(f"   Author: {result.metadata['author']}")

    if result.sample_url:
        print()
        print("📄 Sample Chapter")
        print(f"   URL: {result.sample_url}")
        for issue in chapter_issues:
            _print_selector_issue(issue)

        if remove_issues:
            print("   remove_selectors:")
            for issue in remove_issues:
                _print_selector_issue(issue, indent="      ")
        else:
            print("   remove_selectors: [] (none configured)")

        if result.content_length is not None:
            print(f"   Extracted content length: {result.content_length} chars")
            if result.content_length < 100:
                print("   ⚠️  Content very short — check selectors or remove_selectors")
        else:
            print("   ❌ Could not extract content — chapter_content_selector returned 0 matches")

    print(f"\n{'═' * 60}")
    return 0


def _print_selector_issue(issue: ConfigIssue, *, indent: str = "   ") -> None:
    if issue.status == "skipped":
        print(f"{indent}⏭  {issue.label}: null (skipped)")
        return

    if issue.label == "remove_selectors":
        status = "✅" if issue.status == "ok" else "⚠️"
        print(f"{indent}{status} '{issue.selector}' → {issue.matches} match(es)")
        return

    status = "✅" if issue.status == "ok" else "❌"
    print(f"{indent}{status} {issue.label}: '{issue.selector}' → {issue.matches} match(es)")
