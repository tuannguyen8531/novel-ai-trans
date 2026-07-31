from __future__ import annotations

from pathlib import Path

from src.services.genres import available_genres, genre_cache_scope
from src.services.rules import load_translation_snapshot, rule_snapshot_scope


def _write_rule_tree(root: Path, *, marker: str) -> tuple[Path, Path]:
    rules_dir = root / "rules"
    for target in ("vi", "en"):
        genre_dir = rules_dir / target / "chinese"
        genre_dir.mkdir(parents=True, exist_ok=True)
        (genre_dir / "xianxia.md").write_text(f"{target} genre {marker}", encoding="utf-8")

    (rules_dir / "vi" / "common.md").write_text(f"common {marker}", encoding="utf-8")
    (rules_dir / "vi" / "chinese.md").write_text(f"language {marker}", encoding="utf-8")

    novel_root = root / "translated" / "novel"
    novel_root.mkdir(parents=True, exist_ok=True)
    (novel_root / "rules.md").write_text(f"novel {marker}", encoding="utf-8")
    return rules_dir, novel_root


def test_rule_snapshot_is_stable_inside_job_and_refreshed_for_next_job(tmp_path: Path) -> None:
    rules_dir, novel_root = _write_rule_tree(tmp_path, marker="v1")

    with genre_cache_scope(), rule_snapshot_scope():
        first = load_translation_snapshot(
            target_language="vi",
            source_language="chinese",
            genres=["xianxia"],
            novel_root=novel_root,
            rules_dir=rules_dir,
        )
        _write_rule_tree(tmp_path, marker="v2")
        repeated = load_translation_snapshot(
            target_language="vi",
            source_language="chinese",
            genres=["xianxia"],
            novel_root=novel_root,
            rules_dir=rules_dir,
        )

    assert repeated is first
    assert first.common == "common v1"
    assert first.language == "language v1"
    assert first.genres == (("xianxia", "vi genre v1"),)
    assert first.novel == "novel v1"

    with genre_cache_scope(), rule_snapshot_scope():
        refreshed = load_translation_snapshot(
            target_language="vi",
            source_language="chinese",
            genres=["xianxia"],
            novel_root=novel_root,
            rules_dir=rules_dir,
        )

    assert refreshed.common == "common v2"
    assert refreshed.language == "language v2"
    assert refreshed.genres == (("xianxia", "vi genre v2"),)
    assert refreshed.novel == "novel v2"


def test_genre_discovery_is_stable_inside_job_and_refreshed_for_next_job(tmp_path: Path) -> None:
    rules_dir, _ = _write_rule_tree(tmp_path, marker="v1")

    with genre_cache_scope():
        assert available_genres("chinese", rules_dir=rules_dir) == ["xianxia"]
        for target in ("vi", "en"):
            (rules_dir / target / "chinese" / "urban.md").write_text("urban", encoding="utf-8")
        assert available_genres("chinese", rules_dir=rules_dir) == ["xianxia"]

    with genre_cache_scope():
        assert available_genres("chinese", rules_dir=rules_dir) == ["urban", "xianxia"]
