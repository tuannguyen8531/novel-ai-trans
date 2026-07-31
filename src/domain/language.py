"""Language detection rules for source text."""

import unicodedata

SUPPORTED_TARGET_LANGUAGES = {
    "vi": "Vietnamese",
    "en": "English",
}
SUPPORTED_SOURCE_LANGUAGES = ("chinese", "korean", "japanese")


def normalize_source_language(language: str | None) -> str:
    """Normalize a source-language code to its canonical name."""
    if not language:
        return ""
    normalized = language.lower().strip()
    aliases = {
        "ko": "korean",
        "korean": "korean",
        "zh": "chinese",
        "chinese": "chinese",
        "ja": "japanese",
        "japanese": "japanese",
    }
    return aliases.get(normalized, normalized)


def normalize_target_language(language: str | None) -> str:
    """Return a supported target language code, defaulting to Vietnamese."""
    if language is not None and not isinstance(language, str):
        return "vi"
    code = (language or "vi").strip().lower()
    if code not in SUPPORTED_TARGET_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_TARGET_LANGUAGES))
        raise ValueError(f"Unsupported target language: {language!r}. Supported: {supported}")
    return code


def target_language_name(language: str | None) -> str:
    """Return the display name for a supported target language code."""
    return SUPPORTED_TARGET_LANGUAGES[normalize_target_language(language)]


def detect_language_heuristic(text: str) -> str:
    """
    Detect language based on Unicode character ranges.
    Returns: "chinese" | "korean" | "japanese" | "unknown"

    Heuristic:
    - Korean: Hangul block (U+AC00-U+D7AF, U+1100-U+11FF)
    - Japanese: Hiragana (U+3040-U+309F) or Katakana (U+30A0-U+30FF)
    - Chinese: CJK Unified Ideographs (U+4E00-U+9FFF) without Japanese kana
    """
    hangul_count = 0
    kana_count = 0
    cjk_count = 0
    total_meaningful = 0

    for char in text:
        if char.isspace() or unicodedata.category(char).startswith("P"):
            continue
        total_meaningful += 1
        cp = ord(char)

        if (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF) or (0x3130 <= cp <= 0x318F):
            hangul_count += 1
        elif (0x3040 <= cp <= 0x309F) or (0x30A0 <= cp <= 0x30FF):
            kana_count += 1
        elif 0x4E00 <= cp <= 0x9FFF:
            cjk_count += 1

    if total_meaningful == 0:
        return "unknown"

    hangul_ratio = hangul_count / total_meaningful
    kana_ratio = kana_count / total_meaningful
    cjk_ratio = cjk_count / total_meaningful

    if hangul_ratio > 0.15:
        return "korean"
    if kana_ratio > 0.05:
        return "japanese"
    if cjk_ratio > 0.3:
        return "chinese"

    return "unknown"
