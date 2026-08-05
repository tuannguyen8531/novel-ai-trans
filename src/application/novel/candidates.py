"""Rejected translation candidate acceptance."""

from __future__ import annotations

from pathlib import Path

from src import paths
from src.application import config as app_config
from src.application.errors import (
    ApplicationValidationError,
    PersistenceError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.application.locks import novel_lock
from src.application.novel import chapters
from src.application.novel.identity import require_path
from src.application.translation.chapter import normalize_translation
from src.domain.language import normalize_target_language
from src.domain.quality import post_check_translation
from src.services import catalog as catalog_repository
from src.services import chapters as chapter_service
from src.services.translation.checkpoints import CheckpointStore
from src.services.translation.publisher import ChapterPublication, ChapterPublisher, PublicationError
from src.services.translation.reports import ReportStore, content_hash
from src.services.translation.storage import TranslationStorage


def accept_candidate(
    root: Path,
    name: str,
    number: int,
    target: str,
    expected_hash: str,
    *,
    overwrite: bool = False,
    progress_root: Path | None = None,
    report_root: Path | None = None,
    transaction_root: Path | None = None,
    lock_dir: Path | None = None,
) -> chapters.PostCheckReview:
    """Validate and atomically publish one complete rejected candidate."""
    config = app_config.get_config()
    normalized_target = normalize_target_language(target)
    report_path = paths.translation_report_path(
        config,
        name,
        number,
        normalized_target,
        report_root=report_root,
    )
    progress_path = paths.translation_progress_path(
        config,
        name,
        normalized_target,
        progress_root=progress_root,
    )
    transaction_dir = paths.translation_transaction_dir(
        name,
        normalized_target,
        transaction_root=transaction_root,
    )
    storage = TranslationStorage()
    reports = ReportStore()
    checkpoints = CheckpointStore()
    publisher = ChapterPublisher(storage, reports, checkpoints)

    with novel_lock(name, lock_dir=lock_dir):
        novel_root = require_path(root, name)
        input_dir = paths.novel_input_dir_from_root(novel_root)
        output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
        source_path = chapter_service.chapter_path(input_dir, number)
        if not source_path.exists():
            raise ResourceNotFoundError(f"Source chapter not found: chapter {number}")

        try:
            publisher.recover(
                output_dir=output_dir,
                report_dir=report_path.parent,
                progress_path=progress_path,
                transaction_dir=transaction_dir,
            )
        except PublicationError as error:
            raise PersistenceError(f"Could not recover interrupted publication for {name!r}.") from error

        if not report_path.is_file():
            raise ResourceNotFoundError("The candidate report no longer exists.")
        report = reports.load(report_path)
        candidate = report.get("candidate_translation")
        if not isinstance(candidate, str):
            raise ResourceConflictError("The rejected candidate is no longer available.")

        candidate_hash = content_hash(candidate)
        if candidate_hash != expected_hash:
            raise ResourceConflictError(
                "The rejected candidate changed after it was reviewed.",
                details={"candidate_hash": candidate_hash},
            )
        if not candidate.strip():
            raise ApplicationValidationError("An empty rejected candidate cannot be accepted.")
        if report.get("partial") is not False:
            raise ApplicationValidationError("A partial rejected candidate cannot be accepted.")

        output_path = storage.path(output_dir, number)
        if output_path.exists() and not overwrite:
            raise ResourceConflictError(
                "Accepting this candidate would overwrite the current translation.",
                details={"requires_overwrite_confirmation": True},
            )

        normalized_candidate = normalize_translation(candidate)
        if not normalized_candidate.strip():
            raise ApplicationValidationError("The rejected candidate is empty after normalization.")

        source = chapter_service.deduplicate_leading_headings(storage.read(source_path))
        glossary_path = novel_root / ("glossary.json" if normalized_target == "vi" else f"glossary.{normalized_target}.json")
        issue_codes = [
            issue.code
            for issue in post_check_translation(
                source,
                normalized_candidate,
                catalog_repository.load_glossary_terms(glossary_path),
            )
        ]
        publication = ChapterPublication(
            chapter=number,
            output_dir=output_dir,
            report_path=report_path,
            progress_path=progress_path,
            transaction_dir=transaction_dir,
            content=normalized_candidate,
            report=reports.prepare_output_check(
                report_path,
                issue_codes=issue_codes,
                content=normalized_candidate,
            ),
            checkpoint=checkpoints.load(progress_path),
        )
        try:
            publisher.publish(publication)
        except PublicationError as error:
            raise PersistenceError(f"Could not safely publish candidate for chapter {number}; recovery is required.") from error

        return chapters.chapter_post_check(
            root,
            name,
            number,
            normalized_target,
            report_root=report_root,
        )


__all__ = ["accept_candidate"]
