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
from src.services import chapters as chapter_service
from src.services.translation.reports import ReportStore, content_hash, issue_is_ignored

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
        issue_codes = [issue.code for issue in post_check_translation(source, content) if issue.code == _SOURCE_WARNING_CODE]
        ReportStore().save_manual_check(
            paths.translation_report_path(
                app_config.get_config(),
                name,
                number,
                normalized_target,
                report_root=report_root,
            ),
            chapter=number,
            target_language=normalized_target,
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
    ignored = bool(source_fragments) and issue_is_ignored(
        report,
        _SOURCE_WARNING_CODE,
        content_hash(translation),
    )
    return SourceWarning(
        code=_SOURCE_WARNING_CODE,
        present=bool(source_fragments),
        ignored=ignored,
        fragments=fragments,
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
        chapter=number,
        target_language=normalized_target,
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
    "SourceWarning",
    "delete_chapter",
    "list_chapters",
    "read_chapter",
    "review_source_warning",
    "source_warning_status",
    "write_chapter",
]
