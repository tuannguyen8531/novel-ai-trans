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
import re
import signal
import sys
import threading
import time
from pathlib import Path

from src.application import config_context
from src.application import translate as _app_translate
from src.application.config_context import get_config  # legacy reference for patches
from src.application.errors import ResourceNotFoundError as _ApplicationNotFoundError
from src.application.paths import (
    INPUT_DIR as _SHARED_INPUT_DIR,
)
from src.application.paths import (
    OUTPUT_DIR as _SHARED_OUTPUT_DIR,
)
from src.application.paths import (
    PROGRESS_DIR as _SHARED_PROGRESS_DIR,
)
from src.application.paths import (
    REPORT_DIR as _SHARED_REPORT_DIR,
)
from src.application.progress import ProgressEvent
from src.application.translate import (
    TranslationRequest,
    notify_translation_result,
    run_translation,
)
from src.domain.target_language import (
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

INPUT_DIR = _SHARED_INPUT_DIR
OUTPUT_DIR = _SHARED_OUTPUT_DIR
REPORT_DIR = _SHARED_REPORT_DIR
PROGRESS_DIR = _SHARED_PROGRESS_DIR

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
    config = config_context.get_config()
    if config.translated_dir:
        return Path(config.translated_dir) / novel_name / "input"
    return INPUT_DIR / novel_name


def _get_output_dir(novel_name: str, target_language: str | None = None) -> Path:
    config = config_context.get_config()
    target = _app_translate._normalize_target(target_language or config.target_language)
    if config.translated_dir:
        base_dir = Path(config.translated_dir) / novel_name / "output"
        return base_dir if target == "vi" else base_dir / target
    if target == "vi":
        return OUTPUT_DIR / novel_name
    return OUTPUT_DIR / target / novel_name


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
    config = config_context.get_config()
    output_dir = _get_output_dir(novel_name, target_language or config.target_language)
    return _app_translate.find_untranslated(output_dir, chapters, force=force)


def _progress_path(novel_name: str, target_language: str | None = None) -> Path:
    config = get_config()
    target = _app_translate._normalize_target(target_language or config.target_language)
    if target == "vi":
        return PROGRESS_DIR / f"{novel_name}.json"
    return PROGRESS_DIR / target / f"{novel_name}.json"


def load_progress(novel_name: str, target_language: str | None = None) -> dict:
    return _app_translate.load_progress(_progress_path(novel_name, target_language))


def save_progress(novel_name: str, progress: dict, target_language: str | None = None) -> None:
    _app_translate.save_progress(_progress_path(novel_name, target_language), progress)


def _report_path(novel_name: str, chapter_number: int, target_language: str | None = None) -> Path:
    config = get_config()
    target = _app_translate._normalize_target(target_language or config.target_language)
    base = REPORT_DIR
    if target == "vi":
        return base / novel_name / f"chapter_{chapter_number:03d}.json"
    return base / target / novel_name / f"chapter_{chapter_number:03d}.json"


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
    from src.domain.glossary import audit_term_usage

    issues: list[dict] = []
    source_dir = _get_input_dir(novel_name)
    output_dir = _get_output_dir(novel_name, target_language)
    if not source_dir.exists() or not output_dir.exists():
        return issues

    for source_path in sorted(source_dir.glob("chapter_*.txt")):
        match = re.match(r"^chapter_(\d+)\.txt$", source_path.name)
        if not match:
            continue
        chapter = int(match.group(1))
        output_path = output_dir / f"chapter_{chapter:03d}.txt"
        if not output_path.exists():
            output_path = output_dir / source_path.name
        if not output_path.exists():
            continue

        source_text = source_path.read_text(encoding="utf-8")
        translated_text = output_path.read_text(encoding="utf-8")
        for issue in audit_term_usage(terms, source_text, translated_text):
            issues.append({"chapter": chapter, **issue})

    return issues


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
# Glossary command
# ---------------------------------------------------------------------------


def glossary_main(argv: list[str] | None = None) -> None:
    """Manage per-novel glossary data."""
    from src.services.glossary import (
        clean_glossary,
        load_glossary_data,
        remove_glossary_term,
        save_character,
        save_character_pronoun,
        save_glossary,
        save_relationship,
        validate_glossary,
    )

    parser = argparse.ArgumentParser(description="Manage novel glossary data")
    public_commands = "{list,add,remove,export,characters,pronoun,character,relationship,validate,audit}"
    subparsers = parser.add_subparsers(dest="command", required=True, metavar=public_commands)

    list_parser = subparsers.add_parser("list", help="List glossary terms")
    list_parser.add_argument("novel")

    add_parser = subparsers.add_parser("add", help="Add or update a glossary term")
    add_parser.add_argument("novel")
    add_parser.add_argument("original")
    add_parser.add_argument("translated")

    remove_parser = subparsers.add_parser("remove", help="Remove a glossary term")
    remove_parser.add_argument("novel")
    remove_parser.add_argument("original")

    export_parser = subparsers.add_parser("export", help="Print full glossary JSON")
    export_parser.add_argument("novel")

    character_parser = subparsers.add_parser("characters", help="List character memory")
    character_parser.add_argument("novel")

    pronoun_parser = subparsers.add_parser("pronoun", help="Set a character pronoun")
    pronoun_parser.add_argument("novel")
    pronoun_parser.add_argument("original")
    pronoun_parser.add_argument("pronoun")

    character_edit_parser = subparsers.add_parser("character", help="Update a character name or role")
    character_edit_parser.add_argument("novel")
    character_edit_parser.add_argument("original")
    character_edit_parser.add_argument("--translated-name", default="", help="Target-language character name")
    character_edit_parser.add_argument("--name-vi", default="", help=argparse.SUPPRESS)
    character_edit_parser.add_argument("--role", default="", help="Character role")

    relationship_parser = subparsers.add_parser("relationship", help="Add or update a character relationship")
    relationship_parser.add_argument("novel")
    relationship_parser.add_argument("from_char")
    relationship_parser.add_argument("to_char")
    relationship_parser.add_argument("relationship")
    relationship_parser.add_argument("--since", type=int, default=None, help="Chapter where this relationship starts")

    validate_parser = subparsers.add_parser("validate", help="Validate glossary JSON")
    validate_parser.add_argument("novel")

    clean_parser = subparsers.add_parser("clean", help=argparse.SUPPRESS)
    clean_parser.add_argument("novel")
    subparsers._choices_actions = [action for action in subparsers._choices_actions if action.dest != "clean"]

    audit_parser = subparsers.add_parser("audit", help="Audit translated output against glossary terms")
    audit_parser.add_argument("novel")

    args = parser.parse_args(argv)

    if args.command == "list":
        terms = load_glossary_data(args.novel).get("terms", {})
        if not terms:
            print(f"{DIM}No glossary terms for {args.novel}.{RESET}")
            return
        for original, translated in sorted(terms.items()):
            print(f"{original}\t{translated}")
        return

    if args.command == "add":
        save_glossary(args.novel, {args.original: args.translated})
        print(f"{GREEN}✓ Added glossary term:{RESET} {args.original} → {args.translated}")
        return

    if args.command == "remove":
        removed = remove_glossary_term(args.novel, args.original)
        if removed:
            print(f"{GREEN}✓ Removed glossary term:{RESET} {args.original}")
        else:
            print(f"{YELLOW}Term not found:{RESET} {args.original}")
        return

    if args.command == "export":
        import json

        print(json.dumps(load_glossary_data(args.novel), ensure_ascii=False, indent=2))
        return

    if args.command == "characters":
        entities = load_glossary_data(args.novel).get("entities", {})
        if not entities:
            print(f"{DIM}No characters for {args.novel}.{RESET}")
            return
        for original, info in sorted(entities.items()):
            translated_name = info.get("translated_name") or info.get("name_vi", "")
            role = info.get("role", "")
            pronoun = info.get("pronoun", "")
            print(f"{original}\t{translated_name}\t{role}\t{pronoun}")
        return

    if args.command == "pronoun":
        updated = save_character_pronoun(args.novel, args.original, args.pronoun)
        if updated:
            print(f"{GREEN}✓ Updated pronoun:{RESET} {args.original} → {args.pronoun}")
        else:
            print(f"{YELLOW}Character not found:{RESET} {args.original}")
        return

    if args.command == "character":
        translated_name = args.translated_name or args.name_vi
        if not translated_name and not args.role:
            print(f"{YELLOW}Nothing to update. Use --translated-name and/or --role.{RESET}")
            return
        updated = save_character(args.novel, args.original, translated_name=translated_name, role=args.role)
        if updated:
            print(f"{GREEN}✓ Updated character:{RESET} {args.original}")
        else:
            print(f"{YELLOW}Character not found:{RESET} {args.original}")
        return

    if args.command == "relationship":
        updated = save_relationship(
            args.novel,
            args.from_char,
            args.to_char,
            args.relationship,
            since_chapter=args.since,
        )
        if updated:
            print(f"{GREEN}✓ Updated relationship:{RESET} {args.from_char} → {args.to_char} ({args.relationship})")
        else:
            print(f"{YELLOW}Relationship not updated; both characters must exist.{RESET}")
        return

    if args.command == "validate":
        issues = validate_glossary(args.novel)
        if not issues:
            print(f"{GREEN}✓ Glossary valid:{RESET} {args.novel}")
            return
        for issue in issues:
            print(f"{RED}✗ {issue}{RESET}")
        sys.exit(1)

    if args.command == "clean":
        stats = clean_glossary(args.novel)
        print(
            f"{GREEN}✓ Cleaned glossary:{RESET} {args.novel} "
            f"{DIM}entities={stats['entities']} edges={stats['edges_before']}→{stats['edges_after']} "
            f"address_rules={stats['address_rules_before']}→{stats['address_rules_after']} "
            f"pronoun_examples_removed={stats['pronoun_examples_removed']}{RESET}"
        )
        return

    if args.command == "audit":
        terms = load_glossary_data(args.novel).get("terms", {})
        issues = audit_glossary_outputs(args.novel, terms)
        if not issues:
            print(f"{GREEN}✓ No glossary audit issues found:{RESET} {args.novel}")
            return
        for issue in issues:
            print(f"{RED}✗ Ch.{issue['chapter']} {issue['issue']}:{RESET} {issue['term']} → {issue['expected']}")
        sys.exit(1)


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
        size = event.extra.get("file_size", 0)
        progress.start_chapter(index, chapter, size)
    elif event.kind == "chapter_completed":
        ok = event.extra.get("ok", False)
        elapsed = event.extra.get("elapsed", 0.0)
        chars = event.extra.get("chars_out", 0)
        new_terms = event.extra.get("new_terms", 0)
        progress.chapter_done(ok)
        if ok:
            terms_msg = f" [+ {new_terms} terms]" if new_terms > 0 else ""
            chapter = event.chapter or 0
            print(f"  {GREEN}✓ Ch.{chapter}{RESET} {DIM}→ {chars:,} chars · {elapsed:.1f}s{terms_msg}{RESET}")
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
        from src.services.glossary import load_source_language

        language = load_source_language(novel_name)
        if language:
            print(f"{DIM}🌐 Language: {language} (from glossary){RESET}")
        else:
            print(f"{DIM}🌐 Language: auto-detect{RESET}")
    else:
        print(f"{DIM}🌐 Language: {language} (specified){RESET}")
    print(f"{DIM}🎯 Target: {target_language_name(args.target)} ({args.target}){RESET}")
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
