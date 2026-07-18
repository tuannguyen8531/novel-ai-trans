from __future__ import annotations

from pathlib import Path

from src import paths as _paths
from src.config import config
from src.domain.language import normalize_source_language
from src.models import NovelMetadata
from src.utils import files as file_utils

METADATA_FALLBACK_DIR = _paths.GLOSSARY_DIR
LEGACY_GLOSSARY_FALLBACK_DIR = _paths.GLOSSARY_DIR


def localized_value(metadata: dict[str, object], target_language: str, field: str) -> str:
    """Resolve a localized metadata field, falling back to the source value."""
    localized = metadata.get("localized")
    if isinstance(localized, dict):
        target = localized.get(target_language)
        if isinstance(target, dict):
            value = target.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    source = metadata.get(field)
    return source.strip() if isinstance(source, str) and source.strip() else ""


def metadata_to_dict(metadata: NovelMetadata) -> dict[str, object]:
    return {
        "title": metadata.title,
        "localized": metadata.localized,
        "localization_meta": metadata.localization_meta,
        "author": metadata.author,
        "source_url": metadata.source_url,
        "illustration_url": metadata.illustration_url,
        "summary": metadata.summary,
        "site_name": metadata.site_name,
        "source_language": metadata.source_language,
    }


def metadata_path(novel_name: str) -> Path:
    """Return the metadata file used for a novel."""
    if config.translated_dir:
        return _paths.novel_root_dir(config, novel_name) / "metadata.json"
    _paths.validate_novel_name(novel_name)
    return _paths.resolve_within(METADATA_FALLBACK_DIR, f"{novel_name}.metadata.json")


def _legacy_glossary_path(novel_name: str) -> Path:
    return _paths.novel_glossary_path(
        config,
        novel_name,
        fallback_root=LEGACY_GLOSSARY_FALLBACK_DIR,
    )


def load_source_language(novel_name: str) -> str:
    """Load source language, migrating the legacy glossary field when needed."""
    path = metadata_path(novel_name)
    source_language = ""

    if path.exists():
        metadata = file_utils.read_json_locked(path)
        source_language = normalize_source_language(metadata.get("source_language", ""))

    if source_language:
        return source_language

    glossary_path = _legacy_glossary_path(novel_name)
    if not glossary_path.exists():
        return ""

    glossary = file_utils.read_json_locked(glossary_path)
    source_language = normalize_source_language(glossary.get("source_language", ""))
    if not source_language:
        return ""

    file_utils.merge_json_locked(
        path,
        lambda data: {**data, "source_language": source_language},
    )
    file_utils.merge_json_locked(
        glossary_path,
        lambda data: {key: value for key, value in data.items() if key != "source_language"},
    )
    return source_language


def save_source_language(novel_name: str, language: str) -> None:
    """Persist a detected source language and remove its legacy glossary field."""
    if not language:
        return
    normalized = normalize_source_language(language)

    file_utils.merge_json_locked(
        metadata_path(novel_name),
        lambda data: {**data, "source_language": normalized},
    )

    glossary_path = _legacy_glossary_path(novel_name)
    if glossary_path.exists():
        file_utils.merge_json_locked(
            glossary_path,
            lambda data: {key: value for key, value in data.items() if key != "source_language"},
        )
