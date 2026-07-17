from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.application.crawl.configs import list_configs, load_config, save_config
from src.application.errors import ApplicationValidationError
from src.services.drafts import DraftRepository


def _config(name: str = "demo") -> dict[str, object]:
    return {
        "name": name,
        "source_url": "https://example.com/book",
        "toc_url": "https://example.com/book/toc",
        "chapter_link_selector": ".chapter",
        "chapter_content_selector": ".content",
    }


def test_save_config_consumes_draft_and_persists_metadata(tmp_path: Path) -> None:
    translated_root = tmp_path / "translated"
    drafts_root = tmp_path / "drafts"
    now = datetime.now(UTC)
    DraftRepository(drafts_root).save(
        {
            "draft_id": "generated-demo",
            "name": "demo",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=1)).isoformat(),
            "config": _config(),
            "metadata": {"title": "Demo", "summary": "Summary"},
        }
    )

    save_config(translated_root, drafts_root, "demo", _config(), "generated-demo")

    assert load_config(translated_root, "demo")["name"] == "demo"
    assert list_configs(translated_root)[0].source_url == "https://example.com/book"
    assert not (drafts_root / "generated-demo.json").exists()
    assert '"title": "Demo"' in (translated_root / "demo" / "metadata.json").read_text(encoding="utf-8")


def test_save_config_rejects_invalid_draft_id(tmp_path: Path) -> None:
    with pytest.raises(ApplicationValidationError):
        save_config(tmp_path / "translated", tmp_path / "drafts", "demo", _config(), "../../escape")
