"""Output text normalization for EPUB packaging."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Replace CJK punctuation and remove residual untranslated CJK text."""
    if not text:
        return ""

    replacements = {
        "『": '"',
        "』": '"',
        "「": '"',
        "」": '"',
        "【": "[",
        "】": "]",
        "〖": "[",
        "〗": "]",
        "—": "-",
        "–": "-",
        "﹏": "~",
    }
    for original, replacement in replacements.items():
        text = text.replace(original, replacement)

    cjk_pattern = re.compile(
        r"[\u4e00-\u9fff"
        r"\u3040-\u309f"
        r"\u30a0-\u30ff"
        r"\uac00-\ud7af"
        r"\u1100-\u11ff"
        r"\u3130-\u318f"
        r"\ufe30-\ufe4f"
        r"]"
    )
    text = cjk_pattern.sub("", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


__all__ = ["clean_text"]
