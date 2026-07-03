"""Chunking rules for long-form translation."""

import re

from src.domain.illustrations import parse_illustration_marker

CHUNK_MODES = {"chars", "tokens"}
_ESTIMATED_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{1,4}|[^\s]")


def estimate_token_count(text: str) -> int:
    """Return a deterministic, provider-neutral token estimate.

    CJK and other non-whitespace characters count as one token each. ASCII
    letters and digits are grouped in runs of at most four characters. This
    intentionally avoids provider calls and model-specific dependencies.
    """
    return sum(1 for _ in _ESTIMATED_TOKEN_PATTERN.finditer(text))


def _measure(text: str, mode: str) -> int:
    return len(text) if mode == "chars" else estimate_token_count(text)


def _overlap_suffix(text: str, overlap: int, mode: str) -> str:
    if overlap <= 0:
        return ""
    if mode == "chars":
        return text[-overlap:]
    tokens = list(_ESTIMATED_TOKEN_PATTERN.finditer(text))
    if len(tokens) <= overlap:
        return text
    return text[tokens[-overlap].start() :]


def _split_by_token_budget(text: str, token_budget: int) -> list[str]:
    tokens = list(_ESTIMATED_TOKEN_PATTERN.finditer(text))
    if len(tokens) <= token_budget:
        return [text]
    parts: list[str] = []
    for start in range(0, len(tokens), token_budget):
        end = min(start + token_budget, len(tokens))
        char_start = tokens[start].start()
        char_end = tokens[end].start() if end < len(tokens) else len(text)
        part = text[char_start:char_end].strip()
        if part:
            parts.append(part)
    return parts


def split_into_chunks(
    text: str,
    chunk_size: int = 1500,
    overlap: int = 100,
    mode: str = "chars",
) -> list[str]:
    """
    Split text into chunks for translation.

    Strategy:
    1. Split by double newlines (paragraphs)
    2. Group paragraphs into chunks of ~chunk_size characters or estimated tokens
    3. Add overlap between chunks for context continuity
    """
    if mode not in CHUNK_MODES:
        raise ValueError(f"Unsupported chunk mode: {mode}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    if not paragraphs:
        return [text] if text.strip() else []

    chunks = []
    current_chunk_parts = []
    current_size = 0

    for para in paragraphs:
        para_size = _measure(para, mode)

        if para_size > chunk_size and not parse_illustration_marker(para):
            if current_chunk_parts:
                chunks.append("\n\n".join(current_chunk_parts))
                current_chunk_parts = []
                current_size = 0

            sentences = split_sentences(para)
            if mode == "tokens":
                sentences = [part for sent in sentences for part in _split_by_token_budget(sent, chunk_size)]
            for sent in sentences:
                sent_size = _measure(sent, mode)
                if current_size + sent_size > chunk_size and current_chunk_parts:
                    chunks.append("\n\n".join(current_chunk_parts))
                    if overlap > 0 and current_chunk_parts:
                        overlap_size = overlap if mode == "chars" else min(overlap, max(0, chunk_size - sent_size))
                        overlap_text = _overlap_suffix(current_chunk_parts[-1], overlap_size, mode)
                        current_chunk_parts = [overlap_text]
                        current_size = _measure(overlap_text, mode)
                    else:
                        current_chunk_parts = []
                        current_size = 0
                current_chunk_parts.append(sent)
                current_size += sent_size
            continue

        if current_size + para_size > chunk_size and current_chunk_parts:
            chunks.append("\n\n".join(current_chunk_parts))
            if overlap > 0 and current_chunk_parts:
                last_part = current_chunk_parts[-1]
                if parse_illustration_marker(last_part):
                    current_chunk_parts = []
                    current_size = 0
                else:
                    overlap_size = overlap if mode == "chars" else min(overlap, max(0, chunk_size - para_size))
                    overlap_text = _overlap_suffix(last_part, overlap_size, mode)
                    current_chunk_parts = [overlap_text]
                    current_size = _measure(overlap_text, mode)
            else:
                current_chunk_parts = []
                current_size = 0

        current_chunk_parts.append(para)
        current_size += para_size

    if current_chunk_parts:
        chunks.append("\n\n".join(current_chunk_parts))

    return chunks


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling CJK and Western punctuation."""
    pattern = r"(?<=[。！？.!?\n])\s*"
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]
