import json

from src.services.packaging.metadata import load_metadata, resolve_book_author, resolve_book_title


def test_load_metadata_reads_explicit_path(tmp_path) -> None:
    metadata = {"title": "Test Title", "author": "Author"}
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    assert load_metadata(metadata_path) == metadata


def test_load_metadata_returns_empty_dict_when_missing(tmp_path) -> None:
    assert load_metadata(tmp_path / "missing.json") == {}


def test_load_metadata_returns_empty_dict_on_invalid_json(tmp_path) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("not json", encoding="utf-8")

    assert load_metadata(metadata_path) == {}


def test_resolve_title_uses_localized_name_for_target() -> None:
    metadata = {
        "title": "原标题",
        "localized": {"vi": {"title": "Tiêu đề"}, "en": {"title": "English Title"}},
    }
    assert resolve_book_title(metadata, "en", "fallback") == "English Title"
    assert resolve_book_title(metadata, "vi", "fallback") == "Tiêu đề"


def test_resolve_title_preserves_fallback_chain() -> None:
    assert resolve_book_title({"title": "原标题", "localized": {}}, "en", "fallback") == "原标题"
    assert resolve_book_title({}, "en", "my-novel") == "My Novel"
    assert resolve_book_title({"title": "原标题", "localized": {"en": {"title": ""}}}, "en", "fallback") == "原标题"


def test_resolve_title_ignores_removed_legacy_translated_field() -> None:
    metadata = {"title": "原标题", "translated": {"en": "Legacy title"}}
    assert resolve_book_title(metadata, "en", "fallback") == "原标题"


def test_resolve_author_preserves_metadata_and_fallback_behavior() -> None:
    assert resolve_book_author({"author": "Real Author"}, "AI Translator") == "Real Author"
    assert resolve_book_author({}, "AI Translator") == "AI Translator"
    assert resolve_book_author({"author": None}, "AI Translator") == "AI Translator"
    assert resolve_book_author({"author": ""}, "AI Translator") == "AI Translator"
