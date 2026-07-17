"""Glossary document queries and mutations."""

from __future__ import annotations

import json

from src.application.errors import ResourceConflictError, ResourceNotFoundError
from src.services.glossary import repository as glossary_service


def _empty_glossary() -> dict:
    return {"terms": {}, "entities": {}, "edges": []}


def load_glossary(novel_name: str) -> dict:
    """Load the active glossary document for a novel."""
    path = glossary_service.resolve_glossary_path(novel_name)
    try:
        if not path.exists() or path.stat().st_size == 0:
            return _empty_glossary()
        return glossary_service.load_glossary_data(novel_name)
    except OSError, json.JSONDecodeError, ValueError:
        return _empty_glossary()


def save_terms(novel_name: str, terms: dict[str, str]) -> dict:
    glossary_service.save_glossary(novel_name, terms, is_user_edit=True)
    return load_glossary(novel_name)


def save_term(novel_name: str, original: str, translated: str) -> dict:
    return save_terms(novel_name, {original: translated})


def remove_term(novel_name: str, original: str) -> dict:
    glossary_service.remove_glossary_term(novel_name, original)
    return load_glossary(novel_name)


def update_term(
    novel_name: str,
    old_original: str,
    new_original: str,
    translated: str,
    *,
    overwrite: bool,
) -> dict:
    try:
        glossary_service.update_glossary_term(
            novel_name,
            old_original,
            new_original,
            translated,
            overwrite=overwrite,
            is_user_edit=True,
        )
    except KeyError as error:
        raise ResourceNotFoundError(f"Glossary term not found: {old_original}") from error
    except FileExistsError as error:
        raise ResourceConflictError(f"Glossary term already exists: {new_original}") from error
    return load_glossary(novel_name)


def remove_character(novel_name: str, original: str) -> dict:
    glossary_service.remove_character(novel_name, original)
    return load_glossary(novel_name)


def remove_relationship(novel_name: str, from_char: str, to_char: str) -> dict:
    glossary_service.remove_relationship(novel_name, from_char, to_char)
    return load_glossary(novel_name)


def save_character(
    novel_name: str,
    original: str,
    *,
    translated_name: str,
    role: str,
) -> dict:
    glossary_service.save_character(
        novel_name,
        original,
        translated_name=translated_name,
        role=role,
        is_user_edit=True,
    )
    return load_glossary(novel_name)


def save_character_pronoun(novel_name: str, original: str, pronoun: str) -> bool:
    return glossary_service.save_character_pronoun(novel_name, original, pronoun)


def save_relationship(
    novel_name: str,
    *,
    from_char: str,
    to_char: str,
    relationship: str,
    since: int | None = None,
    update_since: bool = False,
) -> dict:
    glossary_service.save_relationship(
        novel_name,
        from_char,
        to_char,
        relationship,
        since_chapter=since,
        update_since=update_since,
    )
    return load_glossary(novel_name)


def clean_glossary(novel_name: str) -> dict:
    return glossary_service.clean_glossary(novel_name)
