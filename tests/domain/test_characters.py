from src.domain.context import normalize_character_data
from src.domain.entities import count_name_occurrences, find_name_in_text


def test_normalize_character_data_normalizes_sections_and_drops_legacy_examples() -> None:
    normalized = normalize_character_data(
        {
            "entities": {"Alice": {"name_vi": "Alice", "role": "protagonist"}},
            "edges": [],
            "pronoun_examples": {"Alice": ["she"]},
        }
    )

    assert normalized["entities"]["Alice"]["translated_name"] == "Alice"
    assert normalized["address_rules"] == []
    assert "pronoun_examples" not in normalized


def test_name_matching_respects_word_boundaries_and_cjk_names() -> None:
    assert find_name_in_text("Ann", "Ann met Anna")
    assert not find_name_in_text("Ann", "Anna arrived")
    assert count_name_occurrences("Ann", "Ann met Anna, then Ann left") == 2
    assert count_name_occurrences("李明", "李明 gặp 李明") == 2
