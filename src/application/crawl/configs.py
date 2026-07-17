"""Crawler-config and generated-draft application operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.application.crawl.generator import save_generated_metadata
from src.application.errors import ApplicationValidationError, PersistenceError, ResourceNotFoundError
from src.services.drafts import DraftRepository
from src.services.generation.repository import ConfigRepository


@dataclass(frozen=True)
class ConfigRecord:
    name: str
    version: int
    source_url: str
    toc_url: str


@dataclass(frozen=True)
class DraftRecord:
    draft_id: str
    name: str
    created_at: datetime
    expires_at: datetime
    source_url: str | None
    config: dict[str, Any]
    metadata: dict[str, Any]


def list_configs(root: Path) -> list[ConfigRecord]:
    return [
        ConfigRecord(
            name=str(data["name"]),
            version=int(data.get("version", 1)),
            source_url=str(data.get("source_url", "")),
            toc_url=str(data.get("toc_url", "")),
        )
        for data in ConfigRepository(root).list()
    ]


def load_config(root: Path, name: str) -> dict[str, Any]:
    try:
        return ConfigRepository(root).load(name)
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error
    except (OSError, ValueError) as error:
        raise PersistenceError(str(error)) from error


def save_config(root: Path, drafts_root: Path, name: str, config: dict[str, Any], draft_id: str | None) -> None:
    drafts = DraftRepository(drafts_root)
    try:
        ConfigRepository.validate_name(name)
        draft = drafts.load(draft_id) if draft_id else None
        if draft is not None and draft.get("name") != name:
            raise ApplicationValidationError("Draft name does not match the target config name.")
        site_config = ConfigRepository.validate(config)
        if site_config.name != name:
            raise ApplicationValidationError(f"Config name {site_config.name!r} does not match novel {name!r}.")
        ConfigRepository(root).save(config)
        if draft is not None and draft.get("metadata"):
            save_generated_metadata(name, dict(draft["metadata"]), translated_root=root)
        if draft_id:
            drafts.delete(draft_id)
    except ApplicationValidationError:
        raise
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error
    except (KeyError, OSError, ValueError) as error:
        raise ApplicationValidationError(f"Invalid config: {error}") from error


def list_drafts(root: Path) -> list[DraftRecord]:
    repository = DraftRepository(root)
    repository.cleanup()
    records: list[DraftRecord] = []
    for data in repository.list():
        try:
            records.append(_draft_record(data))
        except KeyError, TypeError, ValueError:
            continue
    return records


def load_draft(root: Path, draft_id: str) -> DraftRecord:
    try:
        return _draft_record(DraftRepository(root).load(draft_id))
    except FileNotFoundError as error:
        raise ResourceNotFoundError(str(error)) from error
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise PersistenceError(str(error)) from error


def delete_draft(root: Path, draft_id: str) -> None:
    try:
        DraftRepository(root).delete(draft_id)
    except ValueError as error:
        raise ApplicationValidationError(str(error)) from error


def _draft_record(data: dict[str, Any]) -> DraftRecord:
    return DraftRecord(
        draft_id=str(data["draft_id"]),
        name=str(data.get("name", "")),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        expires_at=datetime.fromisoformat(str(data["expires_at"])),
        source_url=str(data["source_url"]) if data.get("source_url") is not None else None,
        config=dict(data.get("config", {})),
        metadata=dict(data.get("metadata", {})),
    )


__all__ = [
    "ConfigRecord",
    "DraftRecord",
    "delete_draft",
    "list_configs",
    "list_drafts",
    "load_config",
    "load_draft",
    "save_config",
]
