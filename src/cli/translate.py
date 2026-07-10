"""Batch translate + glossary CLI commands.

- :func:`translate_main` runs the batch translation pipeline for a single
  novel. It is a thin argparse adapter over :func:`src.application.translate.run_translation`.
- :func:`glossary_main` is the per-novel glossary manager.

The translation logic itself lives in :mod:`src.application.translate`. The
helpers :func:`scan_chapters`, :func:`find_untranslated`, :func:`load_progress`,
:func:`save_progress`, and :func:`translate_file` are re-exported here for
backward compatibility with existing tests and external callers.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from pathlib import Path

from src import paths as _paths
from src.application import config as app_config
from src.application import glossary as app_glossary
from src.application import translate as _app_translate
from src.application.config import get_config  # legacy reference for patches
from src.application.errors import ResourceNotFoundError as _ApplicationNotFoundError
from src.application.progress import ProgressEvent
from src.application.translate import (
    TranslationRequest,
    notify_translation_result,
    run_translation,
)
from src.cli.glossary import glossary_main
from src.domain.language import (
    SUPPORTED_TARGET_LANGUAGES,
    target_language_name,
)
from src.services.notifier import format_run_footer, get_notifier  # noqa: F401 - exposed for tests
from src.utils.display import (
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    check_provider,
)
from src.utils.progress import ProgressTracker

# Re-exported helpers for tests and external callers.
__all__ = [
    "find_untranslated",
    "glossary_main",
    "load_progress",
    "save_progress",
    "scan_chapters",
    "translate_file",
    "translate_main",
    "audit_glossary_outputs",
    "INPUT_DIR",
    "OUTPUT_DIR",
    "PROGRESS_DIR",
    "REPORT_DIR",
]

INPUT_DIR = _paths.INPUT_DIR
OUTPUT_DIR = _paths.OUTPUT_DIR
REPORT_DIR = _paths.REPORT_DIR
PROGRESS_DIR = _paths.PROGRESS_DIR

_shutdown_requested = False
_cancel_event = threading.Event()
_graph = None


# ---------------------------------------------------------------------------
# Backward-compatible thin wrappers around the application helpers
# ---------------------------------------------------------------------------


def _signal_handler(signum, frame) -> None:  # noqa: ARG001
    global _shutdown_requested
    _shutdown_requested = True
    _cancel_event.set()
    print(f"\n{YELLOW}⚠ Shutting down gracefully...{DIM}")


def _get_input_dir(novel_name: str) -> Path:
    config = app_config.get_config()
    return _paths.novel_input_dir(config, novel_name)


def _get_output_dir(novel_name: str, target_language: str | None = None) -> Path:
    config = app_config.get_config()
    return _paths.novel_output_dir(config, novel_name, target_language)


def scan_chapters(novel_name: str) -> dict[int, Path]:
    """Backward-compatible wrapper around the application helper."""
    try:
        return _app_translate.scan_chapters(_get_input_dir(novel_name))
    except _ApplicationNotFoundError as error:
        print(f"{RED}✗ {error.message}{RESET}")
        sys.exit(1)


def find_untranslated(
    novel_name: str,
    chapters: dict[int, Path],
    force: bool = False,
    target_language: str | None = None,
) -> list[int]:
    """Backward-compatible wrapper around the application helper."""
    config = app_config.get_config()
    output_dir = _get_output_dir(novel_name, target_language or config.target_language)
    return _app_translate.find_untranslated(output_dir, chapters, force=force)


def _progress_path(novel_name: str, target_language: str | None = None) -> Path:
    config = get_config()
    return _paths.translation_progress_path(config, novel_name, target_language, progress_root=PROGRESS_DIR)


def load_progress(novel_name: str, target_language: str | None = None) -> dict:
    return _app_translate.load_progress(_progress_path(novel_name, target_language))


def save_progress(novel_name: str, progress: dict, target_language: str | None = None) -> None:
    _app_translate.save_progress(_progress_path(novel_name, target_language), progress)


def _report_path(novel_name: str, chapter_number: int, target_language: str | None = None) -> Path:
    config = get_config()
    return _paths.translation_report_path(config, novel_name, chapter_number, target_language, report_root=REPORT_DIR)


def save_quality_report(
    novel_name: str,
    chapter_number: int,
    report: dict,
    target_language: str | None = None,
) -> None:
    _app_translate.save_quality_report(_report_path(novel_name, chapter_number, target_language), report)


def audit_glossary_outputs(
    novel_name: str,
    terms: dict[str, str],
    target_language: str | None = None,
) -> list[dict]:
    """Audit translated chapters for obvious glossary consistency problems."""
    return app_glossary.audit_terms(novel_name, terms, target=target_language)


def translate_file(
    input_path: Path,
    novel_name: str,
    chapter_number: int,
    language: str = "",
    target_language: str = "vi",
    graph=None,
) -> tuple[bool, int, float, int]:
    """Backward-compatible wrapper that delegates to the application workflow."""
    get_config()
    output_dir = _get_output_dir(novel_name, target_language)
    report_path = _report_path(novel_name, chapter_number, target_language)
    if graph is None:
        from src.graph.builder import build_graph

        graph = build_graph()
    return _app_translate.translate_file(
        input_path,
        novel_name=novel_name,
        chapter_number=chapter_number,
        source_language=language,
        target_language=target_language,
        graph=graph,
        output_dir=output_dir,
        report_path=report_path,
    )


# ---------------------------------------------------------------------------
# Translate command
# ---------------------------------------------------------------------------


def _notify_translation(notifier, novel_name: str, outcome: str, reason: str, stats: dict, started_at: float = 0.0) -> None:
    """Send a Telegram notification summarising the translation run outcome.

    Backward-compatible thin wrapper around :func:`notify_translation_result`
    from :mod:`src.application.translate`.
    """
    from dataclasses import dataclass

    @dataclass
    class _StubResult:
        novel: str
        total: int
        success: int
        failed: int
        skipped: bool
        dry_run: bool
        cancelled: bool

        @property
        def started_at(self) -> float:
            return started_at

    if outcome == "skipped":
        return
    if outcome == "success":
        cancelled = False
    elif outcome == "interrupted":
        cancelled = True
    else:
        cancelled = False
    skipped = outcome == "skipped"
    _StubResult(
        novel=novel_name,
        total=stats.get("total", 0),
        success=stats.get("success", 0),
        failed=stats.get("failed", 0),
        skipped=skipped,
        dry_run=False,
        cancelled=cancelled,
    )
    # Build message inline to keep exact prior wording.
    esc = notifier.escape
    title = esc(novel_name) if novel_name else "novel"
    if cancelled:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation interrupted.\n"
            f"Stats: Translated: {stats['success']}/{stats['total']}"
        )
    elif stats["failed"] > 0:
        message = (
            "Status: Failed\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished with errors.\n"
            f"Stats: Translated: {stats['success']}/{stats['total']} · Failed: {stats['failed']}"
        )
    else:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished.\n"
            f"Stats: Translated: {stats['success']}/{stats['total']}"
        )
    if outcome == "failed":
        detail = esc(reason) if reason else "Translation failed."
        message = f"Status: Failed\nTask: Translation\nNovel: {title}\nDetail: {detail}"
    message += "\n" + format_run_footer(started_at)
    notifier.send(message)


def _print_progress_callback(event: ProgressEvent) -> None:
    """Mirror :class:`ProgressEvent` updates onto the CLI's ProgressTracker."""
    progress: ProgressTracker | None = getattr(_print_progress_callback, "_tracker", None)
    if progress is None:
        return
    if event.kind == "chapter_started":
        index = event.current
        chapter = event.chapter or 0
        size = event.extra.get("source_size", event.extra.get("file_size", 0))
        size_unit = event.extra.get("size_unit", "chars")
        progress.start_chapter(index, chapter, size, size_unit)
    elif event.kind == "chapter_completed":
        ok = event.extra.get("ok", False)
        elapsed = event.extra.get("elapsed", 0.0)
        output_size = event.extra.get("output_size", event.extra.get("chars_out", 0))
        size_unit = event.extra.get("size_unit", "chars")
        new_terms = event.extra.get("new_terms", 0)
        progress.chapter_done(ok)
        if ok:
            terms_msg = f" [+ {new_terms} terms]" if new_terms > 0 else ""
            chapter = event.chapter or 0
            print(f"  {GREEN}✓ Ch.{chapter}{RESET} {DIM}→ {output_size:,} {size_unit} · {elapsed:.1f}s{terms_msg}{RESET}")
    elif event.kind == "chapter_failed":
        progress.chapter_done(False)
        chapter = event.chapter or 0
        error = event.extra.get("error")
        if error:
            print(f"  {RED}✗ Ch.{chapter}: {error}{RESET}")
    elif event.kind == "completed":
        progress.print_summary()


def translate_main() -> None:
    global _shutdown_requested
    _shutdown_requested = False
    _cancel_event.clear()
    if len(sys.argv) > 1 and sys.argv[1] == "glossary":
        glossary_main(sys.argv[2:])
        return

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
        default=get_config().target_language,
        help="Target language (default: vi)",
    )
    parser.add_argument(
        "-p",
        "--provider",
        choices=["ollama", "gemini", "openrouter"],
        default=None,
        help="LLM provider (overrides .env)",
    )
    parser.add_argument(
        "-r",
        "--review",
        action="store_true",
        help="Enable review step",
    )
    parser.add_argument(
        "-s",
        "--summary",
        action="store_true",
        help="Enable chapter summary generation",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print full AI request/response to console",
    )
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
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Re-translate already translated chapters",
    )
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

    args = parser.parse_args()
    config = get_config()

    if args.provider:
        config.llm_provider = args.provider
    config.target_language = args.target
    if args.review:
        config.enable_review = True
    if args.summary:
        config.enable_summary = True
    if args.verbose:
        from src.services.logger import set_verbose

        set_verbose(True)

    started_at = time.time()
    novel_name = args.novel
    notifier = get_notifier()

    try:
        chapters = scan_chapters(novel_name)
    except SystemExit:
        _notify_translation(
            notifier,
            novel_name,
            "failed",
            "No input chapters found.",
            {"total": 0, "success": 0, "failed": 0},
            started_at,
        )
        raise
    if not chapters:
        input_dir = _get_input_dir(novel_name)
        print(f"{RED}✗ No chapter files found in {input_dir}{RESET}")
        print(f"  Expected format: {input_dir}/chapter_1.txt{RESET}")
        _notify_translation(
            notifier,
            novel_name,
            "failed",
            "No input chapters found.",
            {"total": 0, "success": 0, "failed": 0},
            started_at,
        )
        sys.exit(1)

    total = len(chapters)
    print(f"{DIM}📕 {novel_name}: {total} chapters found{RESET}")

    language = args.lang
    if not language:
        from src.services.metadata import load_source_language

        language = load_source_language(novel_name)
        if language:
            print(f"{DIM}🌐 Language: {language} (from metadata){RESET}")
        else:
            print(f"{DIM}🌐 Language: auto-detect{RESET}")
    else:
        print(f"{DIM}🌐 Language: {language} (specified){RESET}")
    print(f"{DIM}🎯 Target: {target_language_name(args.target)} ({args.target}){RESET}")
    chunk_unit = "tokens" if config.chunk_mode == "tokens" else "chars"
    print(f"{DIM}📦 Chunking: {config.chunk_size:,} {chunk_unit} · overlap {config.chunk_overlap:,} {chunk_unit}{RESET}")
    print()

    signal.signal(signal.SIGINT, _signal_handler)

    # Pre-compute total for the ProgressTracker; the application workflow will
    # update it via the callback we attach.
    request = TranslationRequest(
        novel=novel_name,
        source_language=language,
        target_language=args.target,
        provider=args.provider,
        enable_review=args.review,
        enable_summary=args.summary,
        start_chapter=args.start_chapter,
        end_chapter=args.end_chapter,
        force=args.force,
        resume=args.resume,
        failed_only=args.failed_only,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    if not args.dry_run and not check_provider(config):
        _notify_translation(
            notifier,
            novel_name,
            "failed",
            "LLM provider check failed.",
            {"total": total, "success": 0, "failed": 0},
            started_at,
        )
        sys.exit(1)

    # Track progress locally so the terminal output remains consistent.
    progress = ProgressTracker(total, novel_name)
    callback = _print_progress_callback
    callback._tracker = progress  # type: ignore[attr-defined]

    try:
        result = run_translation(request, progress_callback=callback, cancel_event=_cancel_event)
    except KeyboardInterrupt:
        if _shutdown_requested:
            print(f"\n{YELLOW}⚠ Interrupted. Progress saved.{RESET}")
        raise
    except SystemExit:
        raise
    except Exception as error:
        _notify_translation(
            notifier,
            novel_name,
            "failed",
            str(error) or type(error).__name__,
            {"total": total, "success": 0, "failed": 0},
            started_at,
        )
        print(f"{RED}✗ {error}{RESET}")
        sys.exit(1)

    if result.dry_run:
        print(f"{DIM}📕 {novel_name}: {len(chapters)} chapters total, {result.total} would be translated{RESET}")
        print(f"{DIM}   Chapters: {', '.join(str(c) for c in result.chapters_attempted)}{RESET}")
    elif result.skipped:
        print(f"{GREEN}✓ All {len(chapters)} chapters already translated.{RESET}")
    elif result.cancelled:
        print(f"\n{YELLOW}⚠ Interrupted. Progress saved.{RESET}")

    notify_translation_result(result, started_at=started_at)
