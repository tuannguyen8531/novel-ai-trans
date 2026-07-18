"""Crawler chapter, metadata, and manifest persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from src.config import SiteConfig
from src.models import ChapterLink, ChapterResult, CrawlError, NovelMetadata
from src.paths import resolve_novel_root
from src.services.chapters import chapter_path as resolve_chapter_path
from src.services.metadata import metadata_to_dict
from src.utils.files import write_text_atomic
from src.utils.text import normalize_text, slugify


def merge_metadata(path: Path, metadata: NovelMetadata, config: SiteConfig) -> NovelMetadata:
    """Apply canonical per-novel metadata to newly discovered source metadata."""
    if not path.is_file():
        return metadata
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return metadata
    if not isinstance(existing, dict):
        return metadata

    localized = existing.get("localized")
    if not isinstance(localized, dict):
        localized = metadata.localized
    localization_meta = existing.get("localization_meta")
    if not isinstance(localization_meta, dict):
        localization_meta = metadata.localization_meta
    use_existing_title = not config.title and not config.novel_title_selector
    return NovelMetadata(
        title=(existing.get("title") if use_existing_title else None) or metadata.title,
        localized=localized,
        localization_meta=localization_meta,
        author=metadata.author or existing.get("author"),
        source_url=config.source_url or existing.get("source_url") or metadata.source_url,
        illustration_url=metadata.illustration_url or existing.get("illustration_url"),
        summary=metadata.summary or existing.get("summary"),
        site_name=metadata.site_name,
        source_language=metadata.source_language or existing.get("source_language"),
    )


class CrawlStorage:
    """Persist all filesystem state produced by one crawl."""

    def __init__(self, config: SiteConfig, output_root: Path, share_root: Path | None) -> None:
        novel_slug = slugify(config.name)
        self.config = config
        self.output_root = output_root
        self.manifest_path = output_root / f"{novel_slug}.json"
        novel_root = resolve_novel_root(share_root, novel_slug) if share_root else resolve_novel_root(output_root, novel_slug)
        self.chapter_output_dir = novel_root / ("input" if share_root else "chapters")
        self.metadata_path = self.chapter_output_dir.parent / "metadata.json"

    def prepare(self) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.chapter_output_dir.mkdir(parents=True, exist_ok=True)

    def chapter_path(self, index: int) -> Path:
        return resolve_chapter_path(self.chapter_output_dir, index)

    def chapter_exists(self, path: Path) -> bool:
        return path.is_file() and path.stat().st_size > 0

    def merge_metadata(self, metadata: NovelMetadata) -> NovelMetadata:
        return merge_metadata(self.metadata_path, metadata, self.config)

    def write_chapter(self, path: Path, title: str, body: str) -> None:
        content = f"{normalize_text(title)}\n\n{body.strip()}\n"
        write_text_atomic(path, content)

    def write_metadata(self, metadata: NovelMetadata) -> None:
        data = metadata_to_dict(metadata)
        if self.metadata_path.is_file():
            try:
                existing = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                existing = {}
            if isinstance(existing, dict):
                localized = existing.get("localized")
                if isinstance(localized, dict):
                    data["localized"] = localized
                localization_meta = existing.get("localization_meta")
                if isinstance(localization_meta, dict):
                    data["localization_meta"] = localization_meta
                source_language = existing.get("source_language")
                if source_language and not data.get("source_language"):
                    data["source_language"] = source_language
                for key in ("author", "illustration_url", "summary"):
                    if existing.get(key) and not data.get(key):
                        data[key] = existing[key]
                for key, value in existing.items():
                    data.setdefault(key, value)
        self._write_json(self.metadata_path, data)

    def write_manifest(
        self,
        *,
        generated_at: str,
        status: str,
        metadata: NovelMetadata,
        chapter_links: list[ChapterLink],
        results: list[ChapterResult],
        errors: list[CrawlError],
    ) -> None:
        skipped_count = sum(1 for result in results if result.skipped)
        manifest = {
            "generated_at": generated_at,
            "updated_at": datetime.now(UTC).isoformat(),
            "status": status,
            "config": asdict(self.config),
            "metadata": metadata_to_dict(metadata),
            "runtime_output_dir": str(self.output_root),
            "chapter_output_dir": str(self.chapter_output_dir),
            "total_chapters": len(chapter_links),
            "completed_chapters": len(results) + len(errors),
            "fetched_chapters": len(results) - skipped_count,
            "skipped_chapters": skipped_count,
            "failed_chapters": len(errors),
            "discovered_chapters": [
                {"index": index, "title": chapter.title, "source_url": chapter.url}
                for index, chapter in enumerate(chapter_links, start=1)
            ],
            "chapters": [asdict(result) for result in results],
            "errors": errors,
        }
        self._write_json(self.manifest_path, manifest)

    @staticmethod
    def generated_at() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _write_json(path: Path, data: object) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
