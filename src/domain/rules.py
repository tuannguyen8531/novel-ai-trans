"""Selection of relevant bundled translation rules for a source chapter."""

import re

_MAPPING_RE = re.compile(r"^\s*-\s*(?P<source>.+?)\s*(?:→|->)\s*.+$")
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _mapping_sources(line: str) -> list[str]:
    match = _MAPPING_RE.match(line)
    if not match:
        return []

    raw_source = match.group("source")
    if "(e.g." in raw_source:
        return []
    raw_source = _PARENTHETICAL_RE.sub("", raw_source).strip()

    sources = []
    for candidate in re.split(r"\s*/\s*", raw_source):
        normalized = candidate.strip().lstrip("~")
        if normalized:
            sources.append(normalized)
    return sources


def select_relevant_rules(markdown: str, source_text: str) -> str:
    """Drop bundled term mappings whose source forms do not occur in the chapter."""
    if not markdown or not source_text:
        return markdown

    selected = []
    for line in markdown.splitlines():
        sources = _mapping_sources(line)
        if not sources or any(source in source_text for source in sources):
            selected.append(line)
    return "\n".join(selected).strip()
