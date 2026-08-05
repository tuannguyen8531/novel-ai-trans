"""Novel chapter queries and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src import paths
from src.application import config as app_config
from src.application.errors import ApplicationValidationError, ResourceNotFoundError
from src.application.novel.identity import require_path
from src.domain.language import SUPPORTED_TARGET_LANGUAGES, normalize_target_language
from src.domain.quality import post_check_translation, source_language_fragments
from src.services import catalog as catalog_repository
from src.services import chapters as chapter_service
from src.services.translation.reports import (
    ReportStore,
    content_hash,
    issue_is_ignored,
    post_check_review_key,
    review_key_is_ignored,
)

_SOURCE_WARNING_CODE = "contains_source_language_chars"


@dataclass(frozen=True)
class Chapter:
    number: int
    has_source: bool
    has_translation: bool
    target: str | None
    title: str | None
    source_title: str | None


@dataclass(frozen=True)
class Content:
    novel: str
    chapter: int
    view: str
    target: str | None
    content: str


@dataclass(frozen=True)
class SourceWarning:
    code: str
    present: bool
    ignored: bool
    fragments: list[str]


@dataclass(frozen=True)
class PostCheckItem:
    key: str
    code: str
    severity: str
    detail: str
    ignored: bool
    reviewable: bool
    origin: str


@dataclass(frozen=True)
class PostCheckReview:
    chapter: int
    target: str
    items: list[PostCheckItem]
    candidate_translation: str | None
    candidate_hash: str | None
    partial: bool
    failed_chunk_index: int | None
    total_chunks: int | None
    previous_output_exists: bool


def list_chapters(root: Path, name: str) -> list[Chapter]:
    novel_root = require_path(root, name)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    sources = chapter_service.scan(input_dir)
    outputs = {
        target: chapter_service.scan(paths.novel_output_dir_from_root(novel_root, target))
        for target in SUPPORTED_TARGET_LANGUAGES
    }
    result: list[Chapter] = []
    for number in sources:
        source_title = chapter_service.read_title(sources[number], f"Chapter {number}")
        for target in SUPPORTED_TARGET_LANGUAGES:
            translated = number in outputs[target]
            title = f"Chapter {number}"
            if translated:
                title = chapter_service.read_title(outputs[target][number], title)
            result.append(
                Chapter(
                    number=number,
                    has_source=True,
                    has_translation=translated,
                    target=target,
                    title=title,
                    source_title=source_title,
                )
            )
    return result


def read_chapter(
    root: Path,
    name: str,
    number: int,
    *,
    view: Literal["source", "translation"],
    target: str | None = None,
) -> Content:
    novel_root = require_path(root, name)
    if view == "source":
        chapter_path = chapter_service.chapter_path(paths.novel_input_dir_from_root(novel_root), number)
        if not chapter_path.exists():
            raise ResourceNotFoundError(f"Source chapter not found: chapter {number}")
        return Content(name, number, view, None, chapter_service.read(paths.novel_input_dir_from_root(novel_root), number))

    normalized_target = normalize_target_language(target)
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    chapter_path = chapter_service.chapter_path(output_dir, number)
    if chapter_path.exists():
        return Content(name, number, view, normalized_target, chapter_service.read(output_dir, number))
    raise ResourceNotFoundError(f"Translated chapter not found: chapter {number}")


def write_chapter(
    root: Path,
    name: str,
    number: int,
    content: str,
    *,
    view: Literal["source", "translation"] = "source",
    target: str | None = None,
    report_root: Path | None = None,
) -> Content:
    novel_root = require_path(root, name)
    if view == "source":
        input_dir = paths.novel_input_dir_from_root(novel_root)
        chapter_service.write(input_dir, number, content)
        return Content(name, number, view, None, content)

    normalized_target = normalize_target_language(target)
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    chapter_service.write(output_dir, number, content)
    input_dir = paths.novel_input_dir_from_root(novel_root)
    source_path = chapter_service.chapter_path(input_dir, number)
    if source_path.exists():
        source = chapter_service.read(input_dir, number)
        issue_codes = [issue.code for issue in post_check_translation(source, content)]
        ReportStore().save_manual_check(
            paths.translation_report_path(
                app_config.get_config(),
                name,
                number,
                normalized_target,
                report_root=report_root,
            ),
            issue_codes=issue_codes,
            content=content,
        )
    return Content(name, number, view, normalized_target, content)


def source_warning_status(
    root: Path,
    name: str,
    number: int,
    target: str,
    *,
    report_root: Path | None = None,
) -> SourceWarning:
    """Return the source-character warning and review state for one translation."""
    normalized_target = normalize_target_language(target)
    translation = read_chapter(
        root,
        name,
        number,
        view="translation",
        target=normalized_target,
    ).content
    source_fragments = source_language_fragments(translation)
    fragments = list(dict.fromkeys(fragment[:20] for fragment in source_fragments))[:10]
    report_path = paths.translation_report_path(
        app_config.get_config(),
        name,
        number,
        normalized_target,
        report_root=report_root,
    )
    report = ReportStore().load(report_path)
    fingerprint = content_hash(translation)
    legacy_ignored = issue_is_ignored(report, _SOURCE_WARNING_CODE, fingerprint)
    ignored = bool(source_fragments) and (
        legacy_ignored
        or all(
            review_key_is_ignored(
                report,
                post_check_review_key(_SOURCE_WARNING_CODE, fragment),
                fingerprint,
            )
            for fragment in dict.fromkeys(source_fragments)
        )
    )
    return SourceWarning(
        code=_SOURCE_WARNING_CODE,
        present=bool(source_fragments),
        ignored=ignored,
        fragments=fragments,
    )


def chapter_post_check(
    root: Path,
    name: str,
    number: int,
    target: str,
    *,
    report_root: Path | None = None,
) -> PostCheckReview:
    """Build the review table for current output and its latest candidate."""
    novel_root = require_path(root, name)
    normalized_target = normalize_target_language(target)
    items: list[PostCheckItem] = []
    output_dir = paths.novel_output_dir_from_root(novel_root, normalized_target)
    output_path = chapter_service.chapter_path(output_dir, number)
    previous_output_exists = output_path.exists()
    report = ReportStore().load(
        paths.translation_report_path(
            app_config.get_config(),
            name,
            number,
            normalized_target,
            report_root=report_root,
        )
    )
    warning_codes = {code for code in report.get("manual_post_check_issues", []) if isinstance(code, str)}

    if previous_output_exists:
        translation = chapter_service.read(output_dir, number)
        input_dir = paths.novel_input_dir_from_root(novel_root)
        input_path = chapter_service.chapter_path(input_dir, number)
        source = (
            chapter_service.deduplicate_leading_headings(chapter_service.read(input_dir, number)) if input_path.exists() else ""
        )
        glossary_path = novel_root / ("glossary.json" if normalized_target == "vi" else f"glossary.{normalized_target}.json")
        issues = post_check_translation(
            source,
            translation,
            catalog_repository.load_glossary_terms(glossary_path),
        )
        fragments = list(dict.fromkeys(source_language_fragments(translation)))
        fingerprint = content_hash(translation)
        legacy_ignored = issue_is_ignored(report, _SOURCE_WARNING_CODE, fingerprint)
        for issue in issues:
            severity = "warning" if issue.code in warning_codes else issue.severity
            if issue.code == _SOURCE_WARNING_CODE:
                items.extend(
                    PostCheckItem(
                        key=post_check_review_key(issue.code, fragment),
                        code=issue.code,
                        severity=severity,
                        detail=fragment[:40],
                        ignored=legacy_ignored
                        or review_key_is_ignored(
                            report,
                            post_check_review_key(issue.code, fragment),
                            fingerprint,
                        ),
                        reviewable=True,
                        origin="output",
                    )
                    for fragment in fragments[:20]
                )
                continue
            key = post_check_review_key(issue.code, issue.message)
            items.append(
                PostCheckItem(
                    key=key,
                    code=issue.code,
                    severity=severity,
                    detail=issue.message,
                    ignored=review_key_is_ignored(report, key, fingerprint),
                    reviewable=True,
                    origin="output",
                )
            )

    rejected_issues = report.get("issues")
    if isinstance(rejected_issues, list):
        for issue in rejected_issues:
            if not isinstance(issue, dict):
                continue
            key = issue.get("key")
            code = issue.get("code")
            severity = issue.get("severity")
            message = issue.get("message")
            if not (
                isinstance(key, str) and isinstance(code, str) and severity in {"warning", "error"} and isinstance(message, str)
            ):
                continue
            items.append(
                PostCheckItem(
                    key=key,
                    code=code,
                    severity=severity,
                    detail=message,
                    ignored=False,
                    reviewable=False,
                    origin="rejected",
                )
            )

    candidate = report.get("candidate_translation")
    candidate_value = candidate if isinstance(candidate, str) else None
    failed_chunk_index = report.get("failed_chunk_index")
    total_chunks = report.get("total_chunks")
    return PostCheckReview(
        chapter=number,
        target=normalized_target,
        items=items,
        candidate_translation=candidate_value,
        candidate_hash=content_hash(candidate_value) if candidate_value is not None else None,
        partial=bool(report.get("partial", False)),
        failed_chunk_index=failed_chunk_index if isinstance(failed_chunk_index, int) else None,
        total_chunks=total_chunks if isinstance(total_chunks, int) else None,
        previous_output_exists=previous_output_exists,
    )


def review_post_check_item(
    root: Path,
    name: str,
    number: int,
    target: str,
    key: str,
    *,
    ignored: bool,
    report_root: Path | None = None,
) -> PostCheckReview:
    """Review one current-output post-check row."""
    normalized_target = normalize_target_language(target)
    review = chapter_post_check(
        root,
        name,
        number,
        normalized_target,
        report_root=report_root,
    )
    item = next((item for item in review.items if item.key == key and item.reviewable), None)
    if item is None:
        raise ApplicationValidationError("The post-check item is not available for review.")
    translation = read_chapter(
        root,
        name,
        number,
        view="translation",
        target=normalized_target,
    ).content
    ReportStore().set_review_ignored(
        paths.translation_report_path(
            app_config.get_config(),
            name,
            number,
            normalized_target,
            report_root=report_root,
        ),
        key=item.key,
        code=item.code,
        detail=item.detail,
        content=translation,
        ignored=ignored,
    )
    return chapter_post_check(
        root,
        name,
        number,
        normalized_target,
        report_root=report_root,
    )


def review_source_warning(
    root: Path,
    name: str,
    number: int,
    target: str,
    *,
    ignored: bool,
    report_root: Path | None = None,
) -> SourceWarning:
    """Set the manual review decision for the current translation."""
    normalized_target = normalize_target_language(target)
    status = source_warning_status(
        root,
        name,
        number,
        normalized_target,
        report_root=report_root,
    )
    if ignored and not status.present:
        raise ApplicationValidationError("The chapter has no source-character warning to ignore.")
    translation = read_chapter(
        root,
        name,
        number,
        view="translation",
        target=normalized_target,
    ).content
    ReportStore().set_issue_ignored(
        paths.translation_report_path(
            app_config.get_config(),
            name,
            number,
            normalized_target,
            report_root=report_root,
        ),
        code=_SOURCE_WARNING_CODE,
        fragments=status.fragments,
        content=translation,
        ignored=ignored,
    )
    return source_warning_status(
        root,
        name,
        number,
        normalized_target,
        report_root=report_root,
    )


def delete_chapter(root: Path, name: str, number: int) -> None:
    novel_root = require_path(root, name)
    chapter_path = chapter_service.chapter_path(paths.novel_input_dir_from_root(novel_root), number)
    if not chapter_path.exists():
        raise ResourceNotFoundError(f"Input chapter not found: chapter {number}")
    chapter_service.delete(paths.novel_input_dir_from_root(novel_root), number)


__all__ = [
    "Chapter",
    "Content",
    "PostCheckItem",
    "PostCheckReview",
    "SourceWarning",
    "delete_chapter",
    "list_chapters",
    "chapter_post_check",
    "read_chapter",
    "review_post_check_item",
    "review_source_warning",
    "source_warning_status",
    "write_chapter",
]
