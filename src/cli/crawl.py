from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.config import SiteConfig, config
from src.models import CrawlProgress
from src.services.browser import BrowserFetcher
from src.services.config_generator import ConfigGenerator
from src.services.crawler import ConsecutiveFailureError, NovelCrawler
from src.services.epub_importer import EpubImportError, import_epub
from src.services.http import FetchError, HttpClient
from src.services.llm import get_llm
from src.services.notifier import format_run_footer, get_notifier
from src.utils.logging import get_logger, setup_logging

RUNTIME_OUTPUT_ROOT = Path("runtime/crawler")
CONFIG_DIR = Path("configs")
DEFAULT_TRANSLATED_ROOT = Path("translated")
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

    gen = subparsers.add_parser("generate", help="Use AI to generate a site config from a TOC URL.")
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
        description="Use AI to generate a site config from a TOC URL.",
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
        help="Use an ephemeral headless browser. Default: USE_BROWSER env.",
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
    parser.add_argument("url", type=str, help="URL of the novel's table-of-contents page.")
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
    parser.add_argument(
        "-b",
        "--browser",
        action="store_true",
        help="Use headless browser to fetch pages.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the HTML cache and always re-fetch pages.",
    )
    parser.add_argument(
        "--ignore-sample",
        action="store_true",
        help="Ignore bundled sample templates and generate from live HTML.",
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
        config_path = _resolve_config_path(args.target)
        site_config = SiteConfig.from_file(config_path)

        headed = getattr(args, "headed", False)
        use_browser = True if headed else (args.browser if args.browser is not None else config.use_browser)
        if args.workers is None:
            args.workers = 1
        if args.workers < 1:
            raise ValueError("Number of workers must be at least 1.")

        max_chapters = args.max_chapters if args.max_chapters is not None else None
        if max_chapters is None and config.max_chapters > 0:
            max_chapters = config.max_chapters

        share_root = args.translated_output or config.translated_path

        if use_browser:
            with BrowserFetcher(
                # Preserve the old ephemeral/headless fingerprint for -b.
                # Headed mode uses native Chrome identity with a reusable
                # profile because challenge clearance can be device-bound.
                user_agent=None if headed else site_config.user_agent,
                timeout_seconds=site_config.timeout_seconds,
                delay_seconds=site_config.request_delay_seconds,
                retry_attempts=site_config.retry_attempts,
                retry_backoff_seconds=site_config.retry_backoff_seconds,
                max_concurrency=args.workers,
                profile_dir=_browser_profile_dir(site_config.start_url) if headed else None,
                headless=not headed,
                challenge_timeout_seconds=120.0 if headed else 30.0,
            ) as fetcher:
                return _crawl_with_fetcher(site_config, fetcher, args, max_chapters, share_root, started_at)
        else:
            crawler = NovelCrawler(site_config, respect_robots=not args.ignore_robots)
            return _run_crawl(crawler, args, max_chapters, share_root, started_at)
    except (OSError, ValueError, FetchError) as error:
        get_logger().error("Error: %s", error)
        return 1
    except KeyboardInterrupt:
        get_logger().warning("Interrupted. Progress saved.")
        return 130


def _crawl_with_fetcher(
    site_config: SiteConfig,
    fetcher: object,
    args: argparse.Namespace,
    max_chapters: int | None,
    share_root: Path | None,
    started_at: float,
) -> int:
    crawler = NovelCrawler(
        site_config,
        respect_robots=not args.ignore_robots,
        fetcher=fetcher,  # type: ignore[arg-type]
    )
    return _run_crawl(crawler, args, max_chapters, share_root, started_at)


def _run_crawl(
    crawler: NovelCrawler,
    args: argparse.Namespace,
    max_chapters: int | None,
    share_root: Path | None,
    started_at: float,
) -> int:
    try:
        if args.dry_run:
            metadata, chapters = crawler.discover_chapters()
            if max_chapters is not None:
                chapters = chapters[:max_chapters]
            _print_output(f"Title: {metadata.title}")
            if metadata.author:
                _print_output(f"Author: {metadata.author}")
            _print_output(f"Chapters found: {len(chapters)}")
            for index, chapter in enumerate(chapters[:10], start=1):
                _print_output(f"{index:04d}. {chapter.title} - {chapter.url}")
            if len(chapters) > 10:
                _print_output(f"... {len(chapters) - 10} more")
            return 0

        result = crawler.crawl(
            RUNTIME_OUTPUT_ROOT,
            max_chapters=max_chapters,
            fail_fast=args.fail_fast,
            overwrite=args.overwrite,
            share_root=share_root,
            progress_callback=_print_progress,
            workers=args.workers,
        )
    except ConsecutiveFailureError as error:
        get_logger().error("Error: %s", error)
        get_notifier().send(
            "Status: Failed\n"
            "Task: Crawl\n"
            f"Novel: {_notifier_escape(_novel_label(crawler))}\n"
            f"Detail: {_notifier_escape(str(error))}\n"
            f"{format_run_footer(started_at)}"
        )
        return 1
    except (OSError, ValueError, FetchError) as error:
        get_logger().error("Error: %s", error)
        return 1

    skipped = sum(1 for ch in result.chapters if ch.skipped)
    fetched = len(result.chapters) - skipped
    failed = len(result.errors)
    _print_output(f"Done: {result.metadata.title} ({fetched} new, {skipped} skipped)")
    status = "Success" if failed == 0 else "Failed"
    detail = "Crawl finished." if failed == 0 else "Crawl finished with chapter errors."
    get_notifier().send(
        f"Status: {status}\n"
        "Task: Crawl\n"
        f"Novel: {_notifier_escape(_novel_label(crawler))}\n"
        f"Detail: {detail}\n"
        f"Stats: New: {fetched} · Skipped: {skipped} · Failed: {failed}\n"
        f"{format_run_footer(started_at)}"
    )
    return 0


def _import_epub(args: argparse.Namespace) -> int:
    try:
        share_root = args.translated_output or config.translated_path or DEFAULT_TRANSLATED_ROOT
        result = import_epub(
            args.epub,
            share_root,
            name=args.name,
            keep_existing=args.keep_existing,
        )
    except (OSError, ValueError, EpubImportError) as error:
        get_logger().error("Error: %s", error)
        return 1

    for warning in result.warnings:
        get_logger().warning(warning)
    _print_output(
        f"Imported: {result.metadata.title} ({len(result.chapters)} chapters, {len(result.illustrations)} illustrations)"
    )
    _print_output(f"Output: {result.output_dir}")
    return 0


def _resolve_config_path(target: str) -> Path:
    path = Path(target)
    if path.is_file():
        return path

    candidates = []
    if path.suffix == ".json":
        candidates.append(CONFIG_DIR / path)
    else:
        candidates.append(CONFIG_DIR / f"{target}.json")
        candidates.append(CONFIG_DIR / target / "config.json")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked = ", ".join(str(candidate) for candidate in candidates)
    raise ValueError(f"Config not found for '{target}'. Checked: {checked}")


def _browser_profile_dir(start_url: str) -> Path:
    hostname = urlparse(start_url).hostname
    if not hostname:
        raise ValueError(f"Could not determine browser profile domain from URL: {start_url}")
    safe_hostname = "".join(character if character.isalnum() or character in ".-_" else "_" for character in hostname.lower())
    return RUNTIME_OUTPUT_ROOT / "browser-profiles" / safe_hostname


def _print_progress(progress: CrawlProgress) -> None:
    if progress.status in ("started", "skipped"):
        return
    if progress.status == "fetched":
        _print_output(f"[{progress.current}/{progress.total}] {progress.title}", flush=True)
        return
    if progress.status == "failed":
        detail = progress.error or "unknown error"
        print(
            f"[{progress.current}/{progress.total}] {progress.title} (fail: {detail})",
            file=sys.stderr,
            flush=True,
        )
        return

    _print_output(
        f"[{progress.current}/{progress.total}] {progress.title} ({progress.status})",
        flush=True,
    )


def _notifier_escape(text: str) -> str:
    """HTML-escape text for Telegram HTML parse mode."""
    return get_notifier().escape(text)


def _novel_label(crawler: NovelCrawler) -> str:
    """Best-effort display name for a crawler in a notification."""
    return getattr(crawler.config, "name", None) or "novel"


def _fetch_toc_for_config(fetcher: object, site_config: SiteConfig) -> Any:
    if not site_config.toc_expand_selector:
        return fetcher.fetch(site_config.start_url)  # type: ignore[attr-defined]

    fetch_with_clicks = getattr(fetcher, "fetch_with_clicks", None)
    if fetch_with_clicks is None:
        raise FetchError("toc_expand_selector requires browser mode (-b/--browser).")
    return fetch_with_clicks(
        site_config.start_url,
        [site_config.toc_expand_selector],
        wait_for_selector=site_config.chapter_link_selector,
    )


def _generate(args: argparse.Namespace) -> int:
    """Generate a site config using AI."""
    try:
        # Use override provider if --provider was given.
        if args.provider:
            from src.services.llm.factory import _create_provider

            llm = _create_provider(args.provider)
        else:
            llm = get_llm()

        generator = ConfigGenerator(llm, use_browser=args.browser)
        cache_dir = None if args.no_cache else Path("runtime/crawler") / ".gen-cache"
        config_dict = generator.generate(
            args.url,
            name=args.name,
            cache_dir=cache_dir,
            use_samples=not args.ignore_sample,
        )

        # Validate before showing.
        try:
            ConfigGenerator.validate(config_dict)
        except ValueError as e:
            get_logger().warning("Validation warning: %s", e)

        # Show result for review.
        print(f"\n{'═' * 60}")
        print("Generated config:")
        print(f"{'═' * 60}")
        print(json.dumps(config_dict, ensure_ascii=False, indent=2))
        print(f"{'═' * 60}")

        # Ask for confirmation.
        output_dir: Path = args.output
        name = config_dict.get("name", "generated")
        dest = output_dir / f"{name}.json"
        answer = input(f"\nSave to {dest}? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            path = ConfigGenerator.save(config_dict, output_dir)
            print(f"✅ Config saved to {path}")
            return 0
        else:
            print("Cancelled.")
            return 0

    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as e:
        get_logger().error("Error: %s", e)
        return 1


def _validate(args: argparse.Namespace) -> int:
    """Test a config's selectors against live HTML."""
    try:
        config_path = _resolve_config_path(args.target)
        site_config = SiteConfig.from_file(config_path)

        use_browser = args.browser if args.browser is not None else config.use_browser

        if use_browser:
            browser_fetcher = BrowserFetcher(
                user_agent=site_config.user_agent,
                timeout_seconds=site_config.timeout_seconds,
                delay_seconds=site_config.request_delay_seconds,
            )
            browser_fetcher.__enter__()
            fetcher: BrowserFetcher | HttpClient = browser_fetcher
        else:
            fetcher = HttpClient(
                user_agent=site_config.user_agent,
                timeout_seconds=site_config.timeout_seconds,
                delay_seconds=site_config.request_delay_seconds,
                respect_robots=False,
            )

        try:
            print(f"\n{'═' * 60}")
            print("Validating config selectors")
            print(f"{'═' * 60}")
            print(f"Config: {config_path}")
            print(f"Start URL: {site_config.start_url}")
            print(f"Fetcher: {'browser' if use_browser else 'http'}")
            print()

            # --- TOC validation ---
            print("📖 TOC Page")
            print(f"   URL: {site_config.start_url}")
            toc_html = _fetch_toc_for_config(fetcher, site_config).body
            toc_soup = BeautifulSoup(toc_html, "html.parser")

            for label, selector in [
                ("novel_title_selector", site_config.novel_title_selector),
                ("author_selector", site_config.author_selector),
                ("chapter_link_selector", site_config.chapter_link_selector),
                ("toc_next_selector", site_config.toc_next_selector),
                ("toc_expand_selector", site_config.toc_expand_selector),
            ]:
                if selector:
                    matches = len(toc_soup.select(selector))
                    status = "✅" if matches > 0 else "❌"
                    print(f"   {status} {label}: '{selector}' → {matches} match(es)")
                else:
                    print(f"   ⏭  {label}: null (skipped)")

            # --- Chapter validation ---
            from src.services.crawler import NovelCrawler

            crawler = NovelCrawler(site_config, fetcher=fetcher)
            metadata, chapters = crawler.discover_chapters()

            print()
            print(f"📚 Discovered {len(chapters)} chapters")
            print(f"   Title: {metadata.title}")
            if metadata.author:
                print(f"   Author: {metadata.author}")

            if chapters:
                first = chapters[0]
                print()
                print("📄 Sample Chapter")
                print(f"   URL: {first.url}")
                ch_html = fetcher.fetch(first.url).body
                ch_soup = BeautifulSoup(ch_html, "html.parser")

                for label, selector in [
                    ("chapter_title_selector", site_config.chapter_title_selector),
                    ("chapter_content_selector", site_config.chapter_content_selector),
                ]:
                    if selector:
                        matches = len(ch_soup.select(selector))
                        status = "✅" if matches > 0 else "❌"
                        print(f"   {status} {label}: '{selector}' → {matches} match(es)")
                    else:
                        print(f"   ⏭  {label}: null (skipped)")

                if site_config.remove_selectors:
                    print("   remove_selectors:")
                    for sel in site_config.remove_selectors:
                        matches = len(ch_soup.select(sel))
                        status = "✅" if matches > 0 else "⚠️"
                        print(f"      {status} '{sel}' → {matches} match(es)")
                else:
                    print("   remove_selectors: [] (none configured)")

                # Test content extraction
                content_node = ch_soup.select_one(site_config.chapter_content_selector)
                if content_node:
                    text_len = len(content_node.get_text(strip=True))
                    print(f"   Extracted content length: {text_len} chars")
                    if text_len < 100:
                        print("   ⚠️  Content very short — check selectors or remove_selectors")
                else:
                    print("   ❌ Could not extract content — chapter_content_selector returned 0 matches")

            print(f"\n{'═' * 60}")

        finally:
            if use_browser and isinstance(fetcher, BrowserFetcher):
                fetcher.__exit__(None, None, None)

        return 0

    except (OSError, ValueError, FetchError) as error:
        get_logger().error("Error: %s", error)
        return 1
