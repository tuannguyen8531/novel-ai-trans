"""Filesystem persistence for per-novel translation rules."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from src.domain.language import normalize_source_language
from src.prompts import RULES_DIR
from src.services.genres import normalize_genres


@dataclass(frozen=True, slots=True)
class TranslationRuleSnapshot:
    """Static rule contents reused throughout one translation job."""

    common: str
    language: str
    genres: tuple[tuple[str, str], ...]
    novel: str


_RuleCacheKey = tuple[str, str, str, tuple[str, ...], str]
_rule_cache: ContextVar[dict[_RuleCacheKey, TranslationRuleSnapshot] | None] = ContextVar(
    "translation_rule_cache",
    default=None,
)


@contextmanager
def rule_snapshot_scope() -> Iterator[None]:
    """Keep immutable rule-file snapshots isolated to one translation job."""
    token = _rule_cache.set({})
    try:
        yield
    finally:
        _rule_cache.reset(token)


def _read_first(paths: Iterable[Path]) -> str:
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def read(root: Path) -> str:
    path = root / "rules.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_translation_snapshot(
    *,
    target_language: str,
    source_language: str,
    genres: Iterable[str],
    novel_root: Path | None,
    rules_dir: Path = RULES_DIR,
) -> TranslationRuleSnapshot:
    """Load static translation rules, reusing them inside an active job scope."""
    source = normalize_source_language(source_language)
    if isinstance(genres, str | bytes):
        raise ValueError("Genres must be a list of genre IDs.")
    requested_genres = tuple(genres)
    if any(not isinstance(genre, str) for genre in requested_genres):
        raise ValueError("Every genre ID must be a string.")
    cache_key = (
        str(rules_dir),
        target_language,
        source,
        requested_genres,
        str(novel_root) if novel_root is not None else "",
    )
    cache = _rule_cache.get()
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    selected_genres = normalize_genres(source, requested_genres, rules_dir=rules_dir)
    common = _read_first(
        (
            rules_dir / target_language / "common.md",
            rules_dir / "common.md",
        )
    )
    language = _read_first(
        (
            rules_dir / target_language / f"{source}.md",
            rules_dir / f"{source}.md",
        )
    )
    genre_rules = tuple(
        (
            genre,
            (rules_dir / target_language / source / f"{genre}.md").read_text(encoding="utf-8"),
        )
        for genre in selected_genres
    )
    novel = read(novel_root).strip() if novel_root is not None else ""
    snapshot = TranslationRuleSnapshot(
        common=common,
        language=language,
        genres=genre_rules,
        novel=novel,
    )
    if cache is not None:
        cache[cache_key] = snapshot
    return snapshot


def write(root: Path, content: str) -> None:
    (root / "rules.md").write_text(content, encoding="utf-8")


__all__ = [
    "RULES_DIR",
    "TranslationRuleSnapshot",
    "load_translation_snapshot",
    "read",
    "rule_snapshot_scope",
    "write",
]
