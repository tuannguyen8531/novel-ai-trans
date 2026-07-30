from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.application.errors import ExternalServiceError
from src.application.novel.localization import localize_metadata
from src.config import Config, active_config_scope


def _novel(tmp_path: Path, metadata: dict) -> tuple[Path, Path]:
    root = tmp_path / "translated"
    novel_root = root / "demo"
    novel_root.mkdir(parents=True)
    (novel_root / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return root, novel_root


def _llm(response: str) -> Mock:
    llm = Mock()
    llm.generate.return_value = response
    return llm


def test_localize_metadata_translates_title_and_summary(tmp_path: Path) -> None:
    root, novel_root = _novel(
        tmp_path,
        {
            "title": "原題",
            "summary": "物語の紹介",
            "source_language": "japanese",
        },
    )
    llm = _llm('{"title":"Tên truyện","summary":"Phần giới thiệu truyện"}')

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="vi")),
        patch("src.application.novel.localization.get_llm", return_value=llm),
    ):
        result = localize_metadata(root, "demo", "vi")

    assert result.localized == {"title": "Tên truyện", "summary": "Phần giới thiệu truyện"}
    data = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    assert data["localized"]["vi"] == result.localized
    assert data["localization_meta"]["vi"]["title"]["origin"] == "ai"
    assert data["localization_meta"]["vi"]["summary"]["origin"] == "ai"
    llm.generate.assert_called_once()


def test_localize_metadata_uses_only_active_terms_and_characters(tmp_path: Path) -> None:
    root, novel_root = _novel(
        tmp_path,
        {
            "summary": "墨青川和第一校花互换了身体，于苗苗对此一无所知。",
            "source_language": "chinese",
        },
    )
    (novel_root / "glossary.json").write_text(
        json.dumps(
            {
                "terms": {
                    "校花": "hoa khôi",
                    "洛城": "Lạc Thành",
                },
                "entities": {
                    "墨青川": {"translated_name": "Mặc Thanh Xuyên", "role": "protagonist"},
                    "于苗苗": {"translated_name": "Vu Miêu Miêu", "role": "supporting"},
                    "叶凡": {"translated_name": "Diệp Phàm", "role": "minor"},
                },
                "edges": [
                    ["墨青川", "于苗苗", "classmate", 1],
                    ["墨青川", "叶凡", "friend", 1],
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    llm = _llm('{"summary":"Mặc Thanh Xuyên đã hoán đổi cơ thể với hoa khôi số một."}')

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="vi")),
        patch("src.application.novel.localization.get_llm", return_value=llm),
    ):
        localize_metadata(root, "demo", "vi")

    user_prompt = llm.generate.call_args.args[1]
    assert "校花 → hoa khôi" in user_prompt
    assert "洛城 → Lạc Thành" not in user_prompt
    assert "墨青川 => Mặc Thanh Xuyên [protagonist]" in user_prompt
    assert "于苗苗 => Vu Miêu Miêu [supporting]" in user_prompt
    assert "墨青川(classmate)->于苗苗" in user_prompt
    assert "叶凡" not in user_prompt


def test_localize_metadata_skips_fresh_ai_values(tmp_path: Path) -> None:
    root, novel_root = _novel(tmp_path, {"title": "原題", "summary": "紹介"})
    llm = _llm('{"title":"Tên truyện","summary":"Giới thiệu"}')

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="vi")),
        patch("src.application.novel.localization.get_llm", return_value=llm),
    ):
        localize_metadata(root, "demo", "vi")
        second = localize_metadata(root, "demo", "vi")

    assert second.localized == {}
    assert set(second.skipped) == {"title", "summary"}
    assert llm.generate.call_count == 1
    assert json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))["localized"]["vi"]["title"] == "Tên truyện"


def test_localize_metadata_preserves_manual_value_but_updates_stale_ai_value(tmp_path: Path) -> None:
    root, novel_root = _novel(tmp_path, {"title": "原題", "summary": "紹介"})
    first_llm = _llm('{"title":"AI title","summary":"AI summary"}')
    with (
        active_config_scope(Config(translated_dir=str(root), target_language="en")),
        patch("src.application.novel.localization.get_llm", return_value=first_llm),
    ):
        localize_metadata(root, "demo", "en")

    data = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    data["localized"]["en"]["title"] = "My manual title"
    data["localization_meta"]["en"]["title"]["origin"] = "manual"
    data["summary"] = "更新された紹介"
    (novel_root / "metadata.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    second_llm = _llm('{"summary":"Updated summary"}')

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="en")),
        patch("src.application.novel.localization.get_llm", return_value=second_llm),
    ):
        result = localize_metadata(root, "demo", "en")

    assert result.localized == {"summary": "Updated summary"}
    updated = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    assert updated["localized"]["en"]["title"] == "My manual title"
    assert updated["localized"]["en"]["summary"] == "Updated summary"


def test_force_regenerates_ai_value_without_overwriting_manual_value(tmp_path: Path) -> None:
    root, novel_root = _novel(tmp_path, {"title": "原題", "summary": "紹介"})
    initial_llm = _llm('{"title":"AI title","summary":"AI summary"}')
    with (
        active_config_scope(Config(translated_dir=str(root), target_language="en")),
        patch("src.application.novel.localization.get_llm", return_value=initial_llm),
    ):
        localize_metadata(root, "demo", "en")

    data = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    data["localized"]["en"]["title"] = "Manual title"
    data["localization_meta"]["en"]["title"]["origin"] = "manual"
    (novel_root / "metadata.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    forced_llm = _llm('{"summary":"Regenerated summary"}')

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="en")),
        patch("src.application.novel.localization.get_llm", return_value=forced_llm),
    ):
        result = localize_metadata(root, "demo", "en", force=True)

    assert result.localized == {"summary": "Regenerated summary"}
    updated = json.loads((novel_root / "metadata.json").read_text(encoding="utf-8"))
    assert updated["localized"]["en"]["title"] == "Manual title"


def test_localize_metadata_does_not_write_partial_invalid_response(tmp_path: Path) -> None:
    root, novel_root = _novel(tmp_path, {"title": "原題", "summary": "紹介"})
    original = (novel_root / "metadata.json").read_text(encoding="utf-8")

    with (
        active_config_scope(Config(translated_dir=str(root), target_language="vi")),
        patch("src.application.novel.localization.get_llm", return_value=_llm('{"title":"Tên"}')),
        pytest.raises(ExternalServiceError, match="summary"),
    ):
        localize_metadata(root, "demo", "vi")

    assert (novel_root / "metadata.json").read_text(encoding="utf-8") == original
