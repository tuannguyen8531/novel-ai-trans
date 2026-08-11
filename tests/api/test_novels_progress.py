"""Tests for novel listing and progress computation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from src.api.factory import create_app
from src.application import config as _config
from src.config import Config
from src.services.translation.reports import content_hash


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        translated = tmp_path / "translated"
        translated.mkdir(parents=True, exist_ok=True)
        drafts = tmp_path / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        snapshot = Config(translated_dir=str(translated))
        original = _config.get_config()
        _config.set_default(snapshot)
        try:
            with patch.dict(
                os.environ,
                {"API_HOST": "127.0.0.1", "CORS_ORIGINS": "http://localhost:5173"},
                clear=True,
            ):
                app = create_app(
                    dist_dir=tmp_path / "dist",
                    drafts_dir=drafts,
                    history_root=translated,
                    jobs_dir=tmp_path / "jobs",
                )
                with TestClient(app) as test_client:
                    yield test_client, translated
        finally:
            _config.set_default(original)


def _write_chapter(parent: Path, number: int) -> None:
    parent.mkdir(parents=True, exist_ok=True)
    (parent / f"chapter_{number:03d}.txt").write_text(f"chapter {number}", encoding="utf-8")


def test_progress_reflects_on_disk_output_when_progress_file_missing(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 4):
        _write_chapter(output_dir, i)
    # No progress.json file exists.

    response = test_client.get("/api/novels")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    targets = {t["target"]: t for t in body[0]["targets"]}
    assert targets["vi"]["completed"] == 3
    assert targets["vi"]["total"] == 5
    assert targets["en"]["completed"] == 0


def test_progress_uses_on_disk_output_as_completion_truth(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 3):
        _write_chapter(output_dir, i)
    # Legacy progress says chapters 3-5 are completed but only 1-2 are on disk.
    (novel / "progress.json").write_text(
        json.dumps({"completed": [3, 4, 5], "failed": []}),
        encoding="utf-8",
    )

    response = test_client.get("/api/novels")
    assert response.status_code == 200
    body = response.json()
    targets = {t["target"]: t for t in body[0]["targets"]}
    assert targets["vi"]["completed"] == 2


def test_failed_count_only_from_progress_file(client):
    test_client, translated = client
    novel = translated / "demo"
    input_dir = novel / "input"
    for i in range(1, 6):
        _write_chapter(input_dir, i)
    output_dir = novel / "output"
    for i in range(1, 4):
        _write_chapter(output_dir, i)
    (novel / "progress.json").write_text(
        json.dumps({"completed": [1, 2, 3], "failed": [4, 5]}),
        encoding="utf-8",
    )

    response = test_client.get("/api/novels")
    body = response.json()
    targets = {t["target"]: t for t in body[0]["targets"]}
    assert targets["vi"]["completed"] == 3
    assert targets["vi"]["failed"] == 2


def test_failed_count_reads_runtime_progress_written_by_translation(client, tmp_path):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    progress_dir = tmp_path / "progress"
    progress_dir.mkdir()
    (progress_dir / "demo.json").write_text(
        json.dumps({"completed": [], "failed": [1]}),
        encoding="utf-8",
    )

    with patch("src.application.novel.catalog.PROGRESS_DIR", progress_dir):
        response = test_client.get("/api/novels")

    targets = {item["target"]: item for item in response.json()[0]["targets"]}
    assert targets["vi"]["failed"] == 1


def test_source_warning_count_and_chapters_are_exposed(client):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    _write_chapter(novel / "output", 1)
    reports_dir = translated.parent / "reports" / "vi" / "demo"
    reports_dir.mkdir(parents=True)
    (reports_dir / "chapter_001.json").write_text(
        json.dumps(
            {
                "manual_post_check_issues": ["contains_source_language_chars"],
            }
        ),
        encoding="utf-8",
    )

    list_response = test_client.get("/api/novels")
    progress_response = test_client.get("/api/novels/demo/translation-progress?target=vi")

    targets = {item["target"]: item for item in list_response.json()[0]["targets"]}
    assert targets["vi"]["warnings"] == 1
    assert progress_response.json()["warnings"] == [1]
    assert progress_response.json()["source_warnings"] == [1]


def test_warning_progress_separates_source_warning_chapters(client):
    test_client, translated = client
    novel = translated / "demo"
    for chapter in (1, 2):
        _write_chapter(novel / "input", chapter)
        _write_chapter(novel / "output", chapter)

    reports_dir = translated.parent / "reports" / "vi" / "demo"
    reports_dir.mkdir(parents=True)
    (reports_dir / "chapter_001.json").write_text(
        json.dumps({"manual_post_check_issues": ["contains_code_fence"]}),
        encoding="utf-8",
    )
    (reports_dir / "chapter_002.json").write_text(
        json.dumps({"manual_post_check_issues": ["contains_source_language_chars"]}),
        encoding="utf-8",
    )
    (novel / "output" / "chapter_001.txt").write_text("```text\nwarning\n```", encoding="utf-8")
    (novel / "output" / "chapter_002.txt").write_text("Cô bé 囡 đến rồi.", encoding="utf-8")

    response = test_client.get("/api/novels/demo/translation-progress?target=vi")

    assert response.status_code == 200
    assert response.json()["warnings"] == [1, 2]
    assert response.json()["source_warnings"] == [2]


def test_ignore_all_warning_chapters(client):
    test_client, translated = client
    novel = translated / "demo"
    for chapter in (1, 2):
        _write_chapter(novel / "input", chapter)
        _write_chapter(novel / "output", chapter)
    reports_dir = translated.parent / "reports" / "vi" / "demo"
    reports_dir.mkdir(parents=True)
    (reports_dir / "chapter_001.json").write_text(
        json.dumps({"manual_post_check_issues": ["contains_source_language_chars"]}),
        encoding="utf-8",
    )
    (reports_dir / "chapter_002.json").write_text(
        json.dumps({"manual_post_check_issues": ["contains_code_fence"]}),
        encoding="utf-8",
    )
    (novel / "output" / "chapter_001.txt").write_text("Cô bé 囡 đến rồi.", encoding="utf-8")
    (novel / "output" / "chapter_002.txt").write_text("```text\nwarning\n```", encoding="utf-8")

    response = test_client.put("/api/novels/demo/warnings/ignore?target=vi")

    assert response.status_code == 200
    assert response.json() == {"novel": "demo", "target": "vi", "ignored_chapters": 2}
    assert test_client.get("/api/novels/demo/translation-progress?target=vi").json()["warnings"] == []


def test_manual_translation_edit_refreshes_source_warning(client):
    test_client, translated = client
    novel = translated / "demo"
    source_dir = novel / "input"
    source_dir.mkdir(parents=True)
    (source_dir / "chapter_001.txt").write_text("囡囡来了", encoding="utf-8")

    response = test_client.put(
        "/api/novels/demo/chapters/1?view=translation&target=vi",
        json={"content": "Cô bé 囡 đến rồi."},
    )
    assert response.status_code == 200
    progress_response = test_client.get("/api/novels/demo/translation-progress?target=vi")
    assert progress_response.json()["warnings"] == [1]

    warning_response = test_client.get("/api/novels/demo/chapters/1/warnings/source?target=vi")
    assert warning_response.json() == {
        "code": "contains_source_language_chars",
        "present": True,
        "ignored": False,
        "fragments": ["囡"],
    }

    review_response = test_client.put(
        "/api/novels/demo/chapters/1/warnings/source?target=vi",
        json={"ignored": True},
    )
    assert review_response.status_code == 200
    assert review_response.json()["ignored"] is True
    progress_response = test_client.get("/api/novels/demo/translation-progress?target=vi")
    assert progress_response.json()["warnings"] == []
    list_response = test_client.get("/api/novels")
    targets = {item["target"]: item for item in list_response.json()[0]["targets"]}
    assert targets["vi"]["warnings"] == 0

    review_response = test_client.put(
        "/api/novels/demo/chapters/1/warnings/source?target=vi",
        json={"ignored": False},
    )
    assert review_response.json()["ignored"] is False
    progress_response = test_client.get("/api/novels/demo/translation-progress?target=vi")
    assert progress_response.json()["warnings"] == [1]

    response = test_client.put(
        "/api/novels/demo/chapters/1?view=translation&target=vi",
        json={"content": "Cô bé đã đến."},
    )
    assert response.status_code == 200
    progress_response = test_client.get("/api/novels/demo/translation-progress?target=vi")
    assert progress_response.json()["warnings"] == []


def test_chapter_post_check_reviews_each_fragment_individually(client):
    test_client, translated = client
    novel = translated / "demo"
    source_dir = novel / "input"
    source_dir.mkdir(parents=True)
    (source_dir / "chapter_001.txt").write_text("囡和李来了", encoding="utf-8")
    test_client.put(
        "/api/novels/demo/chapters/1?view=translation&target=vi",
        json={"content": "Cô bé 囡 và 李 đã đến."},
    )

    response = test_client.get("/api/novels/demo/chapters/1/post-check?target=vi")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [(item["detail"], item["ignored"]) for item in items] == [
        ("囡", False),
        ("李", False),
    ]

    response = test_client.put(
        "/api/novels/demo/chapters/1/post-check?target=vi",
        json={"key": items[0]["key"], "ignored": True},
    )
    assert [item["ignored"] for item in response.json()["items"]] == [True, False]
    assert test_client.get("/api/novels/demo/translation-progress?target=vi").json()["warnings"] == [1]

    response = test_client.put(
        "/api/novels/demo/chapters/1/post-check?target=vi",
        json={"key": items[1]["key"], "ignored": True},
    )
    assert [item["ignored"] for item in response.json()["items"]] == [True, True]
    assert test_client.get("/api/novels/demo/translation-progress?target=vi").json()["warnings"] == []


def test_chapter_post_check_includes_candidate_without_output(client):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    report_path = translated.parent / "reports" / "vi" / "demo" / "chapter_001.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "manual_post_check_issues": [],
                "ignored_post_checks": [],
                "issues": [
                    {
                        "key": "rejected:0:translation_empty",
                        "code": "translation_empty",
                        "severity": "error",
                        "message": "Translation is empty.",
                    }
                ],
                "candidate_translation": "",
                "partial": True,
                "failed_chunk_index": 0,
                "total_chunks": 2,
            }
        ),
        encoding="utf-8",
    )

    response = test_client.get("/api/novels/demo/chapters/1/post-check?target=vi")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["origin"] == "rejected"
    assert body["items"][0]["severity"] == "error"
    assert body["items"][0]["reviewable"] is False
    assert body["candidate_translation"] == ""
    assert body["candidate_hash"] == content_hash("")
    assert body["partial"] is True
    assert body["previous_output_exists"] is False


def test_accept_complete_candidate_publishes_output_and_clears_failure(client):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    candidate = "A complete candidate translation for chapter one."
    runtime_root = translated.parent
    report_path = runtime_root / "reports" / "vi" / "demo" / "chapter_001.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"candidate_translation": candidate, "partial": False}),
        encoding="utf-8",
    )
    progress_path = runtime_root / "progress" / "demo.json"
    progress_path.parent.mkdir(parents=True)
    progress_path.write_text(json.dumps({"completed": [], "failed": [1]}), encoding="utf-8")

    review_response = test_client.get("/api/novels/demo/chapters/1/post-check?target=vi")
    candidate_fingerprint = review_response.json()["candidate_hash"]
    response = test_client.post(
        "/api/novels/demo/chapters/1/post-check/accept?target=vi",
        json={"candidate_hash": candidate_fingerprint, "overwrite": False},
    )

    assert response.status_code == 200
    assert response.json()["candidate_translation"] is None
    assert response.json()["candidate_hash"] is None
    assert response.json()["previous_output_exists"] is True
    assert (novel / "output" / "chapter_001.txt").read_text(encoding="utf-8") == candidate
    assert json.loads(progress_path.read_text(encoding="utf-8")) == {"completed": [1], "failed": []}


def test_accept_candidate_api_rejects_stale_hash_and_unconfirmed_overwrite(client):
    test_client, translated = client
    novel = translated / "demo"
    _write_chapter(novel / "input", 1)
    _write_chapter(novel / "output", 1)
    candidate = "Replacement candidate translation."
    report_path = translated.parent / "reports" / "vi" / "demo" / "chapter_001.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps({"candidate_translation": candidate, "partial": False}),
        encoding="utf-8",
    )

    stale = test_client.post(
        "/api/novels/demo/chapters/1/post-check/accept?target=vi",
        json={"candidate_hash": "0" * 64, "overwrite": True},
    )
    unconfirmed = test_client.post(
        "/api/novels/demo/chapters/1/post-check/accept?target=vi",
        json={"candidate_hash": content_hash(candidate), "overwrite": False},
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["error"]["details"] == {"requires_overwrite_confirmation": True}
    assert (novel / "output" / "chapter_001.txt").read_text(encoding="utf-8") == "chapter 1"
