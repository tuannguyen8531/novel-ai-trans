from src.services.packaging.cleaning import clean_text


def test_clean_text_preserves_existing_normalization() -> None:
    assert clean_text("  『Hello』  世界 — test  ") == '"Hello" - test'
    assert clean_text("") == ""
