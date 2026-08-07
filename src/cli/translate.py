"""CLI adapter for batch chapter translation and glossary commands."""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time

from src import paths
from src.application import config as app_config
from src.application.languages import SUPPORTED_TARGET_LANGUAGES, target_language_name
from src.application.progress import ProgressEvent
from src.application.translation.inspection import scan_input, source_language
from src.application.translation.models import TranslationRequest
from src.application.translation.workflow import close_translation_provider, run_translation
from src.cli import glossary as glossary_cli
from src.cli.logging import enable_verbose, llm_console
from src.cli.notifications import notify_translation_failure, notify_translation_result
from src.utils.display import DIM, GREEN, RED, RESET, YELLOW, check_provider
from src.utils.progress import ProgressTracker

_shutdown_requested = False
_hard_stop_requested = False
_cancel_event = threading.Event()
_progress_tracker: ProgressTracker | None = None


def _signal_handler(signum, frame) -> None:  # noqa: ARG001
    global _hard_stop_requested, _shutdown_requested
    if not _shutdown_requested:
        _shutdown_requested = True
        _cancel_event.set()
        print(
            f"\n{YELLOW}⚠ Shutting down gracefully... Press Ctrl+C again to stop immediately.{RESET}",
            flush=True,
        )
        return

    _hard_stop_requested = True
    print(f"\n{YELLOW}⚠ Force stopping now.{RESET}", flush=True)
    raise SystemExit(130)


def _print_progress_callback(event: ProgressEvent) -> None:
    """Mirror application progress events onto the terminal tracker."""
    progress = _progress_tracker
    if progress is None:
        return
    if event.total:
        progress.total_chapters = event.total
    if event.kind == "chapter_started":
        chapter = event.chapter or 0
        size = event.extra.get("source_size", event.extra.get("file_size", 0))
        size_unit = event.extra.get("size_unit", "chars")
        progress.start_chapter(event.current, chapter, size, size_unit)
    elif event.kind == "chapter_completed":
        ok = event.extra.get("ok", False)
        elapsed = event.extra.get("elapsed", 0.0)
        output_size = event.extra.get("output_size", event.extra.get("chars_out", 0))
        size_unit = event.extra.get("size_unit", "chars")
        new_terms = event.extra.get("new_terms", 0)
        progress.chapter_done(ok)
        if ok:
            terms_message = f" [+ {new_terms} terms]" if new_terms > 0 else ""
            chapter = event.chapter or 0
            print(f"  {GREEN}✓ Ch.{chapter}{RESET} {DIM}→ {output_size:,} {size_unit} · {elapsed:.1f}s{terms_message}{RESET}")
    elif event.kind == "chapter_failed":
        progress.chapter_done(False)
        chapter = event.chapter or 0
        error = event.extra.get("error")
        if error:
            print(f"  {RED}✗ Ch.{chapter}: {error}{RESET}")
    elif event.kind == "completed":
        progress.print_summary()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="📚 Novel Translator — Batch translate chapters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py translate my-novel
  python main.py translate my-novel -l chinese
  python main.py translate my-novel --target en
  python main.py translate my-novel -p gemini -r -s
        """,
    )
    parser.add_argument(
        "novel",
        help="Novel name (must match directory in translated/{novel}/input or input/)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        choices=["chinese", "korean", "japanese"],
        default="",
        help="Source language (auto-detect if omitted)",
    )
    parser.add_argument(
        "-t",
        "--target",
        choices=sorted(SUPPORTED_TARGET_LANGUAGES),
        default=app_config.get_config().target_language,
        help="Target language (default: vi)",
    )
    parser.add_argument(
        "-p",
        "--provider",
        choices=["ollama", "gemini", "openrouter"],
        default=None,
        help="LLM provider (overrides .env)",
    )
    parser.add_argument("-r", "--review", action="store_true", help="Enable review step")
    parser.add_argument("-s", "--summary", action="store_true", help="Enable chapter summary generation")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print full AI request/response to console")
    parser.add_argument(
        "-n",
        "--start",
        dest="start_chapter",
        type=int,
        default=0,
        help="Start from this chapter number",
    )
    parser.add_argument(
        "-e",
        "--to",
        dest="end_chapter",
        type=int,
        default=0,
        help="Stop at this chapter number (0 = all)",
    )
    parser.add_argument("-f", "--force", action="store_true", help="Re-translate already translated chapters")
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="List chapters to translate without actually translating",
    )
    parser.add_argument(
        "-R",
        "--resume",
        action="store_true",
        help="Skip chapters marked completed in target-specific progress",
    )
    parser.add_argument(
        "-F",
        "--failed-only",
        action="store_true",
        help="Translate only chapters marked failed in target-specific progress",
    )
    parser.add_argument(
        "-m",
        "--limit",
        type=int,
        default=0,
        help="Translate at most N chapters (0 = no limit)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    global _hard_stop_requested, _progress_tracker, _shutdown_requested
    _shutdown_requested = False
    _hard_stop_requested = False
    _cancel_event.clear()
    resolved_argv = sys.argv[1:] if argv is None else argv
    if resolved_argv[:1] == ["glossary"]:
        glossary_cli.main(resolved_argv[1:])
        return

    args = _parser().parse_args(resolved_argv)
    config = app_config.get_config()
    if args.provider:
        config.llm_provider = args.provider
    config.target_language = args.target
    if args.verbose:
        enable_verbose()

    started_at = time.time()
    novel = args.novel
    input_dir = paths.novel_input_dir(config, novel)
    chapters = scan_input(input_dir)
    if not chapters:
        print(f"{RED}✗ No chapter files found in {input_dir}{RESET}")
        print(f"  Expected format: {input_dir}/chapter_001.txt{RESET}")
        notify_translation_failure(novel, "No input chapters found.", started_at=started_at)
        raise SystemExit(1)

    total = len(chapters)
    print(f"{DIM}📕 {novel}: {total} chapters found{RESET}")

    metadata_language = source_language(novel)
    language = args.lang or metadata_language
    if args.lang:
        print(f"{DIM}🌐 Language: {language} (specified){RESET}")
    elif language:
        print(f"{DIM}🌐 Language: {language} (from metadata){RESET}")
    else:
        print(f"{DIM}🌐 Language: auto-detect{RESET}")
    print(f"{DIM}🎯 Target: {target_language_name(args.target)} ({args.target}){RESET}")
    chunk_unit = "tokens" if config.chunk_mode == "tokens" else "chars"
    print(f"{DIM}📦 Chunking: {config.chunk_size:,} {chunk_unit} · overlap {config.chunk_overlap:,} {chunk_unit}{RESET}")
    print()

    previous_sigint_handler = signal.signal(signal.SIGINT, _signal_handler)
    try:
        request = TranslationRequest(
            novel=novel,
            source_language=args.lang or "",
            target_language=args.target,
            provider=args.provider,
            review=args.review,
            summary=args.summary,
            start_chapter=args.start_chapter,
            end_chapter=args.end_chapter,
            force=args.force,
            resume=args.resume,
            failed_only=args.failed_only,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        if not args.dry_run and not check_provider(config):
            notify_translation_failure(novel, "LLM provider check failed.", started_at=started_at)
            raise SystemExit(1)

        _progress_tracker = ProgressTracker(total, novel)
        try:
            with llm_console():
                result = run_translation(
                    request,
                    progress_callback=_print_progress_callback,
                    cancel_event=_cancel_event,
                )
        except KeyboardInterrupt:
            print(f"\n{YELLOW}⚠ Force stopping now.{RESET}")
            raise SystemExit(130) from None
        except SystemExit:
            raise
        except Exception as error:
            notify_translation_failure(
                novel,
                str(error) or type(error).__name__,
                started_at=started_at,
            )
            print(f"{RED}✗ {error}{RESET}")
            raise SystemExit(1) from error

        if result.dry_run:
            print(f"{DIM}📕 {novel}: {len(chapters)} chapters total, {result.total} would be translated{RESET}")
            print(f"{DIM}   Chapters: {', '.join(str(chapter) for chapter in result.chapters_attempted)}{RESET}")
        elif result.skipped:
            print(f"{GREEN}✓ All {len(chapters)} chapters already translated.{RESET}")
        elif result.cancelled:
            print(f"\n{YELLOW}⚠ Interrupted. Progress saved.{RESET}")

        notify_translation_result(result, started_at=started_at)
    finally:
        _progress_tracker = None
        signal.signal(signal.SIGINT, previous_sigint_handler)
        if not _hard_stop_requested:
            close_translation_provider()
