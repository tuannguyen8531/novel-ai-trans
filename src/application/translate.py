"""Application-layer translation workflow.

This module contains the pure :func:`run_translation` function. It is shared
by the CLI command and the FastAPI route. It does not parse arguments,
print, or install signal handlers.

Long-running workflows in this module accept:

- ``progress_callback``: optional callable receiving :class:`ProgressEvent`
- ``cancel_event``: optional :class:`threading.Event` for cooperative cancel
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from src.application import config_context
from src.application import paths as _paths
from src.application.errors import (
    ApplicationValidationError,
    OperationCancelledError,
    ResourceNotFoundError,
)
from src.application.progress import ProgressEvent
from src.config import Config
from src.domain.target_language import normalize_target_language
from src.graph.builder import build_graph
from src.models.state import initial_state
from src.services.logger import log_error
from src.services.notifier import get_notifier
from src.utils.text import normalize_paragraph_spacing

# Re-export for backward compat with the CLI adapter.
_normalize_target = normalize_target_language


def get_config() -> Config:
    """Indirection so tests can patch ``config_context.get_config``."""
    return config_context.get_config()


# ---------------------------------------------------------------------------
# Path helpers (operate on the active config snapshot)
# ---------------------------------------------------------------------------


def _input_dir(config: Config, novel_name: str) -> Path:
    if config.translated_dir:
        return Path(config.translated_dir) / novel_name / "input"
    return _paths.INPUT_DIR / novel_name


def _output_dir(config: Config, novel_name: str, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    if config.translated_dir:
        base = Path(config.translated_dir) / novel_name / "output"
        return base if target == "vi" else base / target
    if target == "vi":
        return _paths.OUTPUT_DIR / novel_name
    return _paths.OUTPUT_DIR / target / novel_name


def _progress_path(config: Config, novel_name: str, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    if target == "vi":
        return _paths.PROGRESS_DIR / f"{novel_name}.json"
    return _paths.PROGRESS_DIR / target / f"{novel_name}.json"


def _report_path(config: Config, novel_name: str, chapter_number: int, target_language: str | None = None) -> Path:
    target = normalize_target_language(target_language or config.target_language)
    base = _paths.REPORT_DIR
    if target == "vi":
        return base / novel_name / f"chapter_{chapter_number:03d}.json"
    return base / target / novel_name / f"chapter_{chapter_number:03d}.json"


# ---------------------------------------------------------------------------
# Chapter scanning and progress
# ---------------------------------------------------------------------------


_CHAPTER_PATTERN = re.compile(r"^chapter_(\d+)\.txt$")


def scan_chapters(input_dir: Path) -> dict[int, Path]:
    """Scan *input_dir* for chapter files. Returns chapter number -> path."""
    if not input_dir.exists():
        raise ResourceNotFoundError(f"Input directory not found: {input_dir}")
    chapters: dict[int, Path] = {}
    for f in input_dir.iterdir():
        if f.is_file():
            match = _CHAPTER_PATTERN.match(f.name)
            if match:
                chapters[int(match.group(1))] = f
    return dict(sorted(chapters.items()))


def find_untranslated(
    output_dir: Path,
    chapters: dict[int, Path],
    *,
    force: bool = False,
) -> list[int]:
    """Return chapter numbers that still need translation under *output_dir*."""
    if force:
        return sorted(chapters.keys())
    translated: set[int] = set()
    if output_dir.exists():
        for f in output_dir.iterdir():
            match = _CHAPTER_PATTERN.match(f.name)
            if match:
                translated.add(int(match.group(1)))
    return [ch for ch in chapters if ch not in translated]


def load_progress(progress_path: Path) -> dict:
    """Load a progress JSON file. Returns a default on missing or invalid file."""
    import json

    if not progress_path.exists():
        return {"completed": [], "failed": []}
    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"completed": [], "failed": []}


def save_progress(progress_path: Path, progress: dict) -> None:
    """Persist a normalized progress JSON file."""
    import json

    progress_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        "completed": sorted(set(progress.get("completed", []))),
        "failed": sorted(set(progress.get("failed", []))),
    }
    progress_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_quality_report(report_path: Path, report: dict) -> None:
    """Persist a chapter quality report."""
    import json

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Translation request/result
# ---------------------------------------------------------------------------


@dataclass
class TranslationRequest:
    novel: str
    source_language: str = ""
    target_language: str | None = None
    provider: str | None = None
    enable_review: bool = False
    enable_summary: bool = False
    start_chapter: int = 0
    end_chapter: int = 0
    force: bool = False
    resume: bool = False
    failed_only: bool = False
    limit: int = 0
    dry_run: bool = False


@dataclass
class TranslationResult:
    novel: str
    total: int
    success: int
    failed: int
    skipped: bool
    dry_run: bool
    chapters_attempted: list[int]
    failures: list[int]
    started_at: float
    finished_at: float
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Per-chapter translation
# ---------------------------------------------------------------------------


def translate_file(
    input_path: Path,
    *,
    novel_name: str,
    chapter_number: int,
    source_language: str,
    target_language: str,
    graph: object,
    output_dir: Path,
    report_path: Path,
) -> tuple[bool, int, float, int]:
    """Translate one chapter file. Returns (success, char_count, elapsed, new_terms)."""
    source_text = input_path.read_text(encoding="utf-8")
    if not source_text.strip():
        return False, 0, 0, 0

    start = time.time()
    result = graph.invoke(  # type: ignore[attr-defined]
        initial_state(
            source_text=source_text,
            source_language=source_language,
            target_language=target_language,
            novel_name=novel_name,
            chapter_number=chapter_number,
        )
    )
    elapsed = time.time() - start

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"chapter_{chapter_number:03d}.txt"
    final_text = result.get("final_translation", "")
    normalized_text = normalize_paragraph_spacing(final_text)
    new_terms_count = len(result.get("new_terms", {}))
    output_file.write_text(normalized_text, encoding="utf-8")

    quality_report = {
        "chapter": chapter_number,
        "target_language": target_language,
        "output_chars": len(normalized_text),
        "elapsed_seconds": round(elapsed, 3),
        "new_terms_count": new_terms_count,
        "new_characters_count": len(result.get("new_characters", {}).get("entities", {})),
        "chunks": result.get("quality_reports", []),
    }
    save_quality_report(report_path, quality_report)
    return True, len(normalized_text), elapsed, new_terms_count


# ---------------------------------------------------------------------------
# Workflow entry point
# ---------------------------------------------------------------------------


def _emit(
    callback: Callable[[ProgressEvent], None] | None,
    event: ProgressEvent,
) -> None:
    if callback is not None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - never let a callback crash the workflow
            pass


def _check_cancel(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError("Translation cancelled.")


def run_translation(
    request: TranslationRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> TranslationResult:
    """Run the batch translation pipeline for a single novel.

    The function is synchronous; adapters run it inside a background worker.
    The function does not print to stdout/stderr; it returns a structured
    :class:`TranslationResult` and emits progress events to *progress_callback*.
    """
    config = config_context.get_config()
    started_at = time.time()
    novel_name = request.novel
    target_language = request.target_language or config.target_language

    if request.target_language and request.target_language != config.target_language:
        config.target_language = request.target_language
    if request.provider:
        config.llm_provider = request.provider
    if request.enable_review:
        config.enable_review = True
    if request.enable_summary:
        config.enable_summary = True

    input_dir = _input_dir(config, novel_name)
    output_dir = _output_dir(config, novel_name, target_language)
    progress_path = _progress_path(config, novel_name, target_language)

    chapters = scan_chapters(input_dir)
    if not chapters:
        raise ResourceNotFoundError(f"No chapter files found in {input_dir}")

    target_normalized = normalize_target_language(target_language)

    untranslated = find_untranslated(output_dir, chapters, force=request.force)
    if request.start_chapter > 0:
        untranslated = [ch for ch in untranslated if ch >= request.start_chapter]
    if request.end_chapter > 0:
        untranslated = [ch for ch in untranslated if ch <= request.end_chapter]

    progress_state = load_progress(progress_path)
    if request.failed_only:
        failed = set(progress_state.get("failed", []))
        untranslated = [ch for ch in untranslated if ch in failed]
    elif request.resume:
        completed = set(progress_state.get("completed", []))
        untranslated = [ch for ch in untranslated if ch not in completed]

    if request.limit > 0:
        untranslated = untranslated[: request.limit]

    if not untranslated:
        _emit(
            progress_callback,
            ProgressEvent(kind="skipped", novel=novel_name, total=len(chapters), current=len(chapters)),
        )
        return TranslationResult(
            novel=novel_name,
            total=0,
            success=0,
            failed=0,
            skipped=True,
            dry_run=False,
            chapters_attempted=[],
            failures=[],
            started_at=started_at,
            finished_at=time.time(),
        )

    if request.dry_run:
        _emit(
            progress_callback,
            ProgressEvent(
                kind="dry_run",
                novel=novel_name,
                total=len(chapters),
                current=len(untranslated),
                message=f"{len(untranslated)} of {len(chapters)} chapters would be translated",
            ),
        )
        return TranslationResult(
            novel=novel_name,
            total=len(untranslated),
            success=0,
            failed=0,
            skipped=True,
            dry_run=True,
            chapters_attempted=list(untranslated),
            failures=[],
            started_at=started_at,
            finished_at=time.time(),
        )

    _check_cancel(cancel_event)
    _validate_provider(config)

    total = len(untranslated)
    _emit(
        progress_callback,
        ProgressEvent(
            kind="started",
            novel=novel_name,
            current=0,
            total=total,
            message=f"{len(chapters)} chapters found, {total} to translate",
        ),
    )

    source_language = request.source_language
    if not source_language:
        from src.services.glossary import load_source_language

        source_language = load_source_language(novel_name)
    if not source_language:
        source_language = ""

    graph = build_graph()

    success_count = 0
    failed_chapters: list[int] = []
    attempted: list[int] = []
    cancelled = False

    for index, chapter_num in enumerate(untranslated, 1):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        chapter_path = chapters[chapter_num]
        try:
            file_size = len(chapter_path.read_text(encoding="utf-8"))
        except OSError:
            file_size = 0

        # The progress bar advances when a chapter finishes, not when it
        # starts. ``done_count`` reflects the work already completed before
        # this chapter; the post-translation events bump it to include
        # the current one.
        done_count = success_count + len(failed_chapters)
        _emit(
            progress_callback,
            ProgressEvent(
                kind="chapter_started",
                novel=novel_name,
                current=done_count,
                total=total,
                chapter=chapter_num,
                pct=round(done_count / total * 100, 2),
                extra={"file_size": file_size},
            ),
        )

        try:
            ok, out_chars, elapsed, new_terms_count = translate_file(
                chapter_path,
                novel_name=novel_name,
                chapter_number=chapter_num,
                source_language=source_language,
                target_language=target_normalized,
                graph=graph,
                output_dir=output_dir,
                report_path=_report_path(config, novel_name, chapter_num, target_normalized),
            )
        except OperationCancelledError:
            cancelled = True
            break
        except Exception as error:  # noqa: BLE001 - record and continue
            failed_chapters.append(chapter_num)
            attempted.append(chapter_num)
            progress_state.setdefault("failed", []).append(chapter_num)
            save_progress(progress_path, progress_state)
            log_error(
                f"Translation failed for chapter {chapter_num}",
                error,
                chapter=chapter_num,
                novel=novel_name,
            )
            failed_chapters.append(chapter_num)
            post_count = success_count + len(failed_chapters)
            _emit(
                progress_callback,
                ProgressEvent(
                    kind="chapter_failed",
                    novel=novel_name,
                    current=post_count,
                    total=total,
                    chapter=chapter_num,
                    pct=round(post_count / total * 100, 2),
                    extra={"error": str(error)},
                ),
            )
            continue

        attempted.append(chapter_num)
        if ok:
            success_count += 1
            progress_state.setdefault("completed", []).append(chapter_num)
            progress_state["failed"] = [ch for ch in progress_state.get("failed", []) if ch != chapter_num]
        else:
            failed_chapters.append(chapter_num)
            progress_state.setdefault("failed", []).append(chapter_num)
        save_progress(progress_path, progress_state)
        post_count = success_count + len(failed_chapters)
        _emit(
            progress_callback,
            ProgressEvent(
                kind="chapter_completed" if ok else "chapter_failed",
                novel=novel_name,
                current=post_count,
                total=total,
                chapter=chapter_num,
                pct=round(post_count / total * 100, 2),
                extra={
                    "ok": ok,
                    "elapsed": round(elapsed, 3),
                    "chars_out": out_chars,
                    "new_terms": new_terms_count,
                },
            ),
        )

    _emit(
        progress_callback,
        ProgressEvent(
            kind="completed"
            if not cancelled and not failed_chapters
            else ("cancelled" if cancelled else "completed_with_errors"),
            novel=novel_name,
            current=len(attempted),
            total=total,
        ),
    )

    return TranslationResult(
        novel=novel_name,
        total=total,
        success=success_count,
        failed=len(failed_chapters),
        skipped=False,
        dry_run=False,
        chapters_attempted=attempted,
        failures=failed_chapters,
        started_at=started_at,
        finished_at=time.time(),
        cancelled=cancelled,
    )


def _validate_provider(config: Config) -> None:
    """Validate the LLM provider is configured. Mirrors src.utils.display.check_provider."""
    provider = config.llm_provider.lower()
    if provider == "ollama":
        return
    if provider == "gemini" and not config.gemini_api_key:
        raise ApplicationValidationError("Gemini API key is not configured.")
    if provider == "openrouter" and not config.openrouter_api_key:
        raise ApplicationValidationError("OpenRouter API key is not configured.")


# ---------------------------------------------------------------------------
# Notification helper (shared with CLI for now)
# ---------------------------------------------------------------------------


def notify_translation_result(result: TranslationResult, started_at: float | None = None) -> None:
    """Send a Telegram notification summarising *result*."""
    notifier = get_notifier()
    esc = notifier.escape
    title = esc(result.novel) if result.novel else "novel"
    started = started_at if started_at is not None else result.started_at

    if result.skipped:
        return

    if result.cancelled:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation interrupted.\n"
            f"Stats: Translated: {result.success}/{result.total}"
        )
    elif result.failed > 0:
        message = (
            "Status: Failed\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished with errors.\n"
            f"Stats: Translated: {result.success}/{result.total} · Failed: {result.failed}"
        )
    else:
        message = (
            "Status: Success\n"
            "Task: Translation\n"
            f"Novel: {title}\n"
            "Detail: Translation finished.\n"
            f"Stats: Translated: {result.success}/{result.total}"
        )

    from src.services.notifier import format_run_footer

    message += "\n" + format_run_footer(started)
    notifier.send(message)
