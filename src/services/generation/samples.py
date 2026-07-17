"""Bundled samples and known-domain lookup for config generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def load_sample(domain: str, samples_dir: Path) -> dict[str, Any] | None:
    """Load an isolated copy of the bundled sample matching a domain."""
    if not samples_dir.is_dir():
        return None
    for path in sorted(samples_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            toc_url = data.get("toc_url", "")
            if urlparse(toc_url).netloc == domain:
                return json.loads(json.dumps(data))
        except OSError, ValueError:
            continue
    return None


def load_known_config(domain: str, translated_root: Path) -> dict[str, Any] | None:
    """Load the first persisted novel config matching a domain."""
    if not translated_root.is_dir():
        return None
    for path in sorted(translated_root.glob("*/config.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            toc_url = data.get("toc_url", "")
            if urlparse(toc_url).netloc == domain:
                return data
        except OSError, ValueError:
            continue
    return None


def prepare_sample(
    sample: dict[str, Any],
    *,
    name: str,
    toc_url: str,
    source_url: str,
    novel_info: dict[str, Any],
) -> dict[str, Any]:
    """Adapt a domain sample for one novel without mutating the source."""
    result = json.loads(json.dumps(sample))
    for key in ("novel_title_selector", "author_selector", "illustration_selector"):
        result.pop(key, None)
    result["name"] = name
    result["toc_url"] = toc_url
    return add_novel_info(result, source_url, novel_info)


def add_novel_info(config: dict[str, Any], source_url: str, novel_info: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical novel metadata to a generated config."""
    config["source_url"] = source_url
    for key in ("title", "author", "illustration_url", "summary"):
        config[key] = novel_info.get(key)
    return config


__all__ = ["add_novel_info", "load_known_config", "load_sample", "prepare_sample"]
