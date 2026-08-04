"""Batch translation orchestration and canonical entry point."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Protocol, cast

from src import paths
from src.application import config as app_config
from src.application.errors import ApplicationValidationError, OperationCancelledError, ResourceNotFoundError
from src.application.genres import normalize_genres
from src.application.locks import novel_lock
from src.application.progress import ProgressEvent
from src.application.translation.chapter import TranslationGraph, translate_chapter
from src.application.translation.models import TranslationRequest, TranslationResult
from src.application.translation.selection import select_chapters
from src.application.translation.validation import apply_request_overrides, validate_provider
from src.config import Config
from src.domain.chunking import estimate_token_count
from src.domain.language import normalize_source_language
from src.graph.builder import TranslationQualityError, build_graph
from src.models import TranslationProfile
from src.prompts import prompt_cache_scope
from src.services.genres import genre_cache_scope
from src.services.logger import log_error
from src.services.metadata import load_translation_profile
from src.services.rules import rule_snapshot_scope
from src.services.translation.checkpoints import CheckpointStore
from src.services.translation.reports import ReportStore
from src.services.translation.storage import TranslationStorage


class GraphFactory(Protocol):
    def __call__(self) -> TranslationGraph: ...


@dataclass
class TranslationWorkflow:
    """Coordinate translation collaborators without owning their persistence."""

    config: Config
    storage: TranslationStorage
    checkpoints: CheckpointStore
    reports: ReportStore
    graph_factory: GraphFactory
    profile_loader: Callable[[str], TranslationProfile]
    progress_root: Path | None = None
    report_root: Path | None = None
    clock: Callable[[], float] = time.time

    def run(
        self,
        request: TranslationRequest,
        *,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
        cancel_event: Event | None = None,
    ) -> TranslationResult:
        started_at = self.clock()
        novel = request.novel
        target = apply_request_overrides(self.config, request)
        input_dir = paths.novel_input_dir(self.config, novel)
        output_dir = paths.novel_output_dir(self.config, novel, target)
        checkpoint_path = paths.translation_progress_path(
            self.config,
            novel,
            target,
            progress_root=self.progress_root,
        )

        if not self.storage.directory_exists(input_dir):
            raise ResourceNotFoundError(f"Input directory not found: {input_dir}")
        chapters = self.storage.scan(input_dir)
        if not chapters:
            raise ResourceNotFoundError(f"No chapter files found in {input_dir}")

        translated_numbers = self.storage.translated_numbers(output_dir)
        checkpoint = self.checkpoints.load(checkpoint_path)
        checkpoint["completed"] = sorted(translated_numbers)
        selected = select_chapters(
            request,
            chapters,
            translated_numbers,
            checkpoint,
        )

        if not selected:
            self._emit(
                progress_callback,
                ProgressEvent(kind="skipped", novel=novel, total=len(chapters), current=len(chapters)),
            )
            return TranslationResult(
                novel=novel,
                total=0,
                success=0,
                failed=0,
                skipped=True,
                dry_run=False,
                chapters_attempted=[],
                failures=[],
                started_at=started_at,
                finished_at=self.clock(),
            )

        if request.dry_run:
            self._emit(
                progress_callback,
                ProgressEvent(
                    kind="dry_run",
                    novel=novel,
                    total=len(chapters),
                    current=len(selected),
                    message=f"{len(selected)} of {len(chapters)} chapters would be translated",
                ),
            )
            return TranslationResult(
                novel=novel,
                total=len(selected),
                success=0,
                failed=0,
                skipped=True,
                dry_run=True,
                chapters_attempted=list(selected),
                failures=[],
                started_at=started_at,
                finished_at=self.clock(),
            )

        self._check_cancel(cancel_event)
        validate_provider(self.config)

        total = len(selected)
        self._emit(
            progress_callback,
            ProgressEvent(
                kind="started",
                novel=novel,
                current=0,
                total=total,
                message=f"{len(chapters)} chapters found, {total} to translate",
            ),
        )

        requested_source_language = normalize_source_language(request.source_language)
        try:
            profile = self.profile_loader(novel)
        except ValueError as error:
            raise ApplicationValidationError(str(error)) from error
        metadata_source_language = normalize_source_language(profile.source_language)
        source_language = requested_source_language or metadata_source_language
        stored_genres = list(profile.genres)
        if stored_genres and requested_source_language and requested_source_language != metadata_source_language:
            raise ApplicationValidationError("Translation source-language override does not match the novel metadata genres.")
        genres = normalize_genres(source_language, stored_genres)
        graph = self.graph_factory()
        success_count = 0
        failures: list[int] = []
        attempted: list[int] = []
        cancelled = False

        for chapter_number in selected:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            chapter_path = chapters[chapter_number]
            file_size, source_size, size_unit = self._source_size(chapter_path)
            done_count = success_count + len(failures)
            self._emit(
                progress_callback,
                ProgressEvent(
                    kind="chapter_started",
                    novel=novel,
                    current=done_count,
                    total=total,
                    chapter=chapter_number,
                    pct=round(done_count / total * 100, 2),
                    extra={"file_size": file_size, "source_size": source_size, "size_unit": size_unit},
                ),
            )

            try:
                ok, output_chars, elapsed, new_terms = translate_chapter(
                    chapter_path,
                    novel=novel,
                    chapter=chapter_number,
                    source_language=source_language,
                    target_language=target,
                    genres=genres,
                    graph=graph,
                    output_dir=output_dir,
                    report_path=paths.translation_report_path(
                        self.config,
                        novel,
                        chapter_number,
                        target,
                        report_root=self.report_root,
                    ),
                    storage=self.storage,
                    reports=self.reports,
                    clock=self.clock,
                )
            except OperationCancelledError:
                cancelled = True
                break
            except TranslationQualityError as error:
                report_path = paths.translation_report_path(
                    self.config,
                    novel,
                    chapter_number,
                    target,
                    report_root=self.report_root,
                )
                self.reports.save_rejection(
                    report_path,
                    issues=[
                        {
                            "key": f"rejected:{index}:{code}",
                            "code": code,
                            "severity": "error",
                            "message": error.feedback,
                        }
                        for index, code in enumerate(error.issue_codes)
                    ],
                    candidate_translation=error.candidate_translation,
                    partial=error.failed_chunk_index < error.total_chunks - 1,
                    failed_chunk_index=error.failed_chunk_index,
                    total_chunks=error.total_chunks,
                )
                self._record_failure(
                    checkpoint,
                    checkpoint_path,
                    failures,
                    attempted,
                    chapter_number,
                    error,
                    progress_callback,
                    success_count,
                    total,
                    novel,
                )
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                continue
            except Exception as error:  # noqa: BLE001 - record and continue
                self._record_failure(
                    checkpoint,
                    checkpoint_path,
                    failures,
                    attempted,
                    chapter_number,
                    error,
                    progress_callback,
                    success_count,
                    total,
                    novel,
                )
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                continue

            attempted.append(chapter_number)
            if ok:
                success_count += 1
                checkpoint.setdefault("completed", []).append(chapter_number)
                checkpoint["failed"] = [chapter for chapter in checkpoint.get("failed", []) if chapter != chapter_number]
            else:
                failures.append(chapter_number)
                checkpoint.setdefault("failed", []).append(chapter_number)
            self.checkpoints.save(checkpoint_path, checkpoint)

            post_count = success_count + len(failures)
            output_size, output_unit = self._output_size(output_dir, chapter_number, output_chars, ok)
            self._emit(
                progress_callback,
                ProgressEvent(
                    kind="chapter_completed" if ok else "chapter_failed",
                    novel=novel,
                    current=post_count,
                    total=total,
                    chapter=chapter_number,
                    pct=round(post_count / total * 100, 2),
                    extra={
                        "ok": ok,
                        "elapsed": round(elapsed, 3),
                        "chars_out": output_chars,
                        "output_size": output_size,
                        "size_unit": output_unit,
                        "new_terms": new_terms,
                    },
                ),
            )
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

        self._emit(
            progress_callback,
            ProgressEvent(
                kind=("completed" if not cancelled and not failures else ("cancelled" if cancelled else "completed_with_errors")),
                novel=novel,
                current=len(attempted),
                total=total,
            ),
        )
        return TranslationResult(
            novel=novel,
            total=total,
            success=success_count,
            failed=len(failures),
            skipped=False,
            dry_run=False,
            chapters_attempted=attempted,
            failures=failures,
            started_at=started_at,
            finished_at=self.clock(),
            cancelled=cancelled,
        )

    def _record_failure(
        self,
        checkpoint: dict,
        checkpoint_path: Path,
        failures: list[int],
        attempted: list[int],
        chapter_number: int,
        error: Exception,
        progress_callback: Callable[[ProgressEvent], None] | None,
        success_count: int,
        total: int,
        novel: str,
    ) -> None:
        failures.append(chapter_number)
        attempted.append(chapter_number)
        checkpoint.setdefault("failed", []).append(chapter_number)
        self.checkpoints.save(checkpoint_path, checkpoint)
        log_error(
            f"Translation failed for chapter {chapter_number}",
            error,
            chapter=chapter_number,
            novel=novel,
        )
        post_count = success_count + len(failures)
        self._emit(
            progress_callback,
            ProgressEvent(
                kind="chapter_failed",
                novel=novel,
                current=post_count,
                total=total,
                chapter=chapter_number,
                pct=round(post_count / total * 100, 2),
                extra={"error": str(error)},
            ),
        )

    def _source_size(self, chapter_path: Path) -> tuple[int, int, str]:
        try:
            source = self.storage.read(chapter_path)
            file_size = len(source)
            source_size = estimate_token_count(source) if self.config.chunk_mode == "tokens" else file_size
        except OSError:
            file_size = 0
            source_size = 0
        unit = "tokens" if self.config.chunk_mode == "tokens" else "chars"
        return file_size, source_size, unit

    def _output_size(
        self,
        output_dir: Path,
        chapter: int,
        output_chars: int,
        succeeded: bool,
    ) -> tuple[int, str]:
        if succeeded and self.config.chunk_mode == "tokens":
            try:
                return estimate_token_count(self.storage.read_translation(output_dir, chapter)), "tokens"
            except OSError:
                pass
        return output_chars, "chars"

    @staticmethod
    def _emit(callback: Callable[[ProgressEvent], None] | None, event: ProgressEvent) -> None:
        if callback is not None:
            with suppress(Exception):
                callback(event)

    @staticmethod
    def _check_cancel(cancel_event: Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelledError("Translation cancelled.")


def run_translation(
    request: TranslationRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
    report_root: Path | None = None,
) -> TranslationResult:
    """Construct default collaborators and run one locked translation batch."""
    with (
        novel_lock(request.novel),
        genre_cache_scope(),
        rule_snapshot_scope(),
        prompt_cache_scope(),
    ):
        workflow = TranslationWorkflow(
            config=app_config.get_config(),
            storage=TranslationStorage(),
            checkpoints=CheckpointStore(),
            reports=ReportStore(),
            graph_factory=cast(GraphFactory, build_graph),
            profile_loader=load_translation_profile,
            report_root=report_root,
        )
        return workflow.run(
            request,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
