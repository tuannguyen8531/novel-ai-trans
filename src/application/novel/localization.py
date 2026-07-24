"""Translate novel-level title and summary metadata with the configured LLM."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Literal

from src.application.errors import ExternalServiceError, OperationCancelledError
from src.application.novel.identity import require_path
from src.application.novel.metadata import metadata
from src.domain.formatting import format_relationships_shorthand
from src.domain.glossary import format_glossary_for_prompt, select_active_glossary_terms
from src.domain.language import normalize_source_language, normalize_target_language, target_language_name
from src.prompts import render_prompt
from src.services.glossary.repository import get_active_context, load_glossary
from src.services.llm import get_llm
from src.services.logger import log_ai_call
from src.utils import files as file_utils
from src.utils.json import parse_json_object

MetadataField = Literal["title", "summary"]
SUPPORTED_FIELDS: tuple[MetadataField, ...] = ("title", "summary")


@dataclass(frozen=True)
class LocalizationResult:
    novel: str
    target_language: str
    localized: dict[str, str]
    skipped: list[str]


def _source_hash(value: str) -> str:
    normalized = " ".join(value.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _target_data(metadata: dict, target: str) -> dict:
    localized = metadata.get("localized")
    if not isinstance(localized, dict):
        return {}
    data = localized.get(target)
    return data if isinstance(data, dict) else {}


def _field_meta(metadata: dict, target: str, field: str) -> dict:
    all_meta = metadata.get("localization_meta")
    if not isinstance(all_meta, dict):
        return {}
    target_meta = all_meta.get(target)
    if not isinstance(target_meta, dict):
        return {}
    field_meta = target_meta.get(field)
    return field_meta if isinstance(field_meta, dict) else {}


def _persist_values(
    path: Path,
    *,
    target: str,
    values: dict[str, str],
    source_values: dict[str, str],
    origin: str,
) -> dict:
    now = datetime.now(UTC).isoformat()

    def updater(current: dict) -> dict:
        localized = dict(current.get("localized", {})) if isinstance(current.get("localized"), dict) else {}
        target_values = dict(localized.get(target, {})) if isinstance(localized.get(target), dict) else {}
        target_values.update(values)
        localized[target] = target_values

        localization_meta = (
            dict(current.get("localization_meta", {})) if isinstance(current.get("localization_meta"), dict) else {}
        )
        target_meta = dict(localization_meta.get(target, {})) if isinstance(localization_meta.get(target), dict) else {}
        for field in values:
            target_meta[field] = {
                "source_hash": _source_hash(source_values[field]),
                "origin": origin,
                "updated_at": now,
            }
        localization_meta[target] = target_meta
        return {**current, "localized": localized, "localization_meta": localization_meta}

    return file_utils.merge_json_locked(path, updater)


def localize_metadata(
    root: Path,
    novel_name: str,
    target_language: str,
    *,
    fields: tuple[MetadataField, ...] = SUPPORTED_FIELDS,
    force: bool = False,
    cancel_event: Event | None = None,
) -> LocalizationResult:
    """Translate missing/stale AI metadata fields for one target language."""
    novel_root = require_path(root, novel_name)
    target = normalize_target_language(target_language)
    novel_metadata = metadata(root, novel_name)
    requested = tuple(dict.fromkeys(fields))
    invalid = [field for field in requested if field not in SUPPORTED_FIELDS]
    if invalid:
        raise ValueError(f"Unsupported metadata fields: {', '.join(invalid)}")

    source_values: dict[str, str] = {}
    pending: dict[str, str] = {}
    skipped: list[str] = []
    existing_target = _target_data(novel_metadata, target)

    for field in requested:
        source = novel_metadata.get(field)
        source_text = source.strip() if isinstance(source, str) else ""
        if not source_text:
            skipped.append(field)
            continue
        source_values[field] = source_text

        existing = existing_target.get(field)
        existing_text = existing.strip() if isinstance(existing, str) else ""
        field_meta = _field_meta(novel_metadata, target, field)
        if existing_text:
            origin = field_meta.get("origin")
            if not field_meta or origin == "manual":
                skipped.append(field)
                continue
            if not force and field_meta.get("source_hash") == _source_hash(source_text):
                skipped.append(field)
                continue
        pending[field] = source_text

    metadata_path = novel_root / "metadata.json"
    if not pending:
        return LocalizationResult(novel_name, target, {}, skipped)
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelledError("Metadata translation cancelled.")

    source_context = "\n\n".join(pending.values())
    active_terms = select_active_glossary_terms(load_glossary(novel_name), source_context)
    glossary = format_glossary_for_prompt(active_terms)
    active_entities, active_edges, _ = get_active_context(novel_name, source_context)
    characters = format_relationships_shorthand(active_entities, active_edges)
    system_prompt = render_prompt("localize", target_language=target)
    source_language = normalize_source_language(novel_metadata.get("source_language") if isinstance(novel_metadata, dict) else "")
    user_payload = {
        "source_language": source_language or "auto",
        "target_language": target_language_name(target),
        "fields": pending,
    }
    user_prompt = "Translate this metadata and return the requested JSON object:\n\n"
    if glossary:
        user_prompt += f"{glossary}\n\n"
    if characters:
        user_prompt += f"{characters}\n\n"
    user_prompt += json.dumps(user_payload, ensure_ascii=False, indent=2)

    try:
        response = get_llm().generate(system_prompt, user_prompt, "localize")
        parsed = parse_json_object(response)
    except Exception as error:
        raise ExternalServiceError(f"Failed to translate novel metadata: {error}") from error

    localized: dict[str, str] = {}
    for field in pending:
        value = parsed.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ExternalServiceError(f"Metadata translation response is missing a non-empty {field!r} value.")
        localized[field] = value.strip()

    log_ai_call(
        "localize",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=response,
        novel=novel_name,
        target_language=target,
    )
    _persist_values(
        metadata_path,
        target=target,
        values=localized,
        source_values=source_values,
        origin="ai",
    )
    return LocalizationResult(novel_name, target, localized, skipped)
