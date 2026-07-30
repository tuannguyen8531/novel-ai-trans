"""Characterization tests for translation batch orchestration."""

from __future__ import annotations

import json
from threading import Event
from typing import Literal

import pytest

from src.application.errors import ApplicationValidationError
from src.application.progress import ProgressEvent
from src.application.translation.models import TranslationRequest
from src.application.translation.workflow import TranslationWorkflow
from src.config import Config
from src.graph.builder import TranslationQualityError
from src.services.translation.checkpoints import CheckpointStore
from src.services.translation.reports import ReportStore
from src.services.translation.storage import TranslationStorage


class SuccessGraph:
    def __init__(self, output: str = "translated", cancel_event: Event | None = None) -> None:
        self.output = output
        self.cancel_event = cancel_event
        self.calls = 0

    def invoke(self, state):
        self.calls += 1
        if self.cancel_event is not None:
            self.cancel_event.set()
        return {
            "final_translation": self.output,
            "new_terms": {},
            "new_characters": {"entities": {}},
            "quality_reports": [],
        }


class FailingGraph:
    def invoke(self, state):
        raise RuntimeError("provider failed")


class QualityFailingGraph:
    def invoke(self, state):
        raise TranslationQualityError(
            "post-check failed",
            issue_codes=["contains_source_language_chars"],
            feedback="Source fragment: 张三",
            retry_count=2,
            failed_chunk_index=0,
            total_chunks=2,
            candidate_translation="Rejected 张三 candidate",
        )


class RecordingGraph(SuccessGraph):
    def __init__(self) -> None:
        super().__init__()
        self.genre_snapshots: list[list[str]] = []

    def invoke(self, state):
        self.genre_snapshots.append(state["genres"])
        return super().invoke(state)


def make_workflow(
    tmp_path,
    graph,
    *,
    chunk_mode: Literal["chars", "tokens"] = "chars",
) -> TranslationWorkflow:
    return TranslationWorkflow(
        config=Config(translated_dir=str(tmp_path / "translated"), chunk_mode=chunk_mode),
        storage=TranslationStorage(),
        checkpoints=CheckpointStore(),
        reports=ReportStore(),
        graph_factory=lambda: graph,
        source_language_loader=lambda _novel: "chinese",
        genre_loader=lambda _novel: [],
        progress_root=tmp_path / "progress",
        report_root=tmp_path / "reports",
        rejected_root=tmp_path / "rejected",
    )


def write_chapters(tmp_path, numbers: tuple[int, ...], content: str = "source") -> None:
    input_dir = tmp_path / "translated" / "novel" / "input"
    input_dir.mkdir(parents=True)
    for number in numbers:
        (input_dir / f"chapter_{number}.txt").write_text(
            f"{content} {number}",
            encoding="utf-8",
        )


def test_progress_sizes_follow_token_chunk_mode(tmp_path) -> None:
    write_chapters(tmp_path, (1,))
    (tmp_path / "translated" / "novel" / "input" / "chapter_1.txt").write_text(
        "甲乙丙丁",
        encoding="utf-8",
    )
    events: list[ProgressEvent] = []
    workflow = make_workflow(tmp_path, SuccessGraph("abcdefgh"), chunk_mode="tokens")

    workflow.run(TranslationRequest(novel="novel"), progress_callback=events.append)

    started = next(event for event in events if event.kind == "chapter_started")
    completed = next(event for event in events if event.kind == "chapter_completed")
    assert started.extra["source_size"] == 4
    assert started.extra["size_unit"] == "tokens"
    assert completed.extra["output_size"] == 2
    assert completed.extra["size_unit"] == "tokens"


def test_chapter_exception_is_counted_once(tmp_path) -> None:
    write_chapters(tmp_path, (1,))
    events: list[ProgressEvent] = []

    result = make_workflow(tmp_path, FailingGraph()).run(
        TranslationRequest(novel="novel"),
        progress_callback=events.append,
    )

    assert result.total == 1
    assert result.failed == 1
    assert result.failures == [1]
    assert result.chapters_attempted == [1]
    failed_event = next(event for event in events if event.kind == "chapter_failed")
    assert failed_event.current == 1
    assert failed_event.pct == 100.0


def test_quality_failure_saves_one_rejected_json(tmp_path) -> None:
    write_chapters(tmp_path, (1,))

    result = make_workflow(tmp_path, QualityFailingGraph()).run(
        TranslationRequest(novel="novel"),
    )

    assert result.failed == 1
    rejected_path = tmp_path / "rejected" / "vi" / "novel" / "chapter_001.json"
    rejected = json.loads(rejected_path.read_text(encoding="utf-8"))
    assert rejected["candidate_translation"] == "Rejected 张三 candidate"
    assert rejected["issues"] == [
        {
            "key": "rejected:0:contains_source_language_chars",
            "code": "contains_source_language_chars",
            "severity": "error",
            "message": "Source fragment: 张三",
        }
    ]
    assert rejected["partial"] is True
    assert rejected["failed_chunk_index"] == 0
    assert rejected["total_chunks"] == 2
    assert rejected["previous_output_exists"] is False
    assert "source_hash" not in rejected


def test_successful_translation_removes_previous_rejected_candidate(tmp_path) -> None:
    write_chapters(tmp_path, (1,))
    rejected_path = tmp_path / "rejected" / "vi" / "novel" / "chapter_001.json"
    rejected_path.parent.mkdir(parents=True)
    rejected_path.write_text("{}", encoding="utf-8")

    result = make_workflow(tmp_path, SuccessGraph()).run(TranslationRequest(novel="novel"))

    assert result.success == 1
    assert not rejected_path.exists()


def test_cancel_finishes_current_chapter_then_stops_before_next(tmp_path) -> None:
    write_chapters(tmp_path, (1, 2))
    cancel_event = Event()
    graph = SuccessGraph(cancel_event=cancel_event)

    result = make_workflow(tmp_path, graph).run(
        TranslationRequest(novel="novel"),
        cancel_event=cancel_event,
    )

    assert result.cancelled is True
    assert result.success == 1
    assert result.chapters_attempted == [1]
    assert graph.calls == 1


@pytest.mark.parametrize(
    ("options", "checkpoint", "expected"),
    [
        ({"resume": True}, {"completed": [1, 3], "failed": []}, [2]),
        ({"failed_only": True}, {"completed": [2], "failed": [1, 3]}, [1, 3]),
    ],
)
def test_checkpoint_filters_translation_selection(tmp_path, options, checkpoint, expected) -> None:
    write_chapters(tmp_path, (1, 2, 3))
    store = CheckpointStore()
    checkpoint_path = tmp_path / "progress" / "novel.json"
    store.save(checkpoint_path, checkpoint)
    workflow = make_workflow(tmp_path, SuccessGraph())

    result = workflow.run(TranslationRequest(novel="novel", source_language="chinese", **options))

    assert result.chapters_attempted == expected
    assert result.total == len(expected)
    assert result.success == len(expected)


def test_dry_run_emits_selection_without_building_graph(tmp_path) -> None:
    write_chapters(tmp_path, (1, 2))
    built = False

    def graph_factory():
        nonlocal built
        built = True
        return SuccessGraph()

    workflow = make_workflow(tmp_path, SuccessGraph())
    workflow.graph_factory = graph_factory

    result = workflow.run(TranslationRequest(novel="novel", dry_run=True, limit=1))

    assert result.dry_run is True
    assert result.chapters_attempted == [1]
    assert built is False


def test_genres_are_loaded_once_and_snapshotted_for_every_chapter(tmp_path) -> None:
    write_chapters(tmp_path, (1, 2))
    graph = RecordingGraph()
    workflow = make_workflow(tmp_path, graph)
    load_calls = 0

    def load_genre_snapshot(_novel):
        nonlocal load_calls
        load_calls += 1
        return ["urban"]

    workflow.genre_loader = load_genre_snapshot

    result = workflow.run(TranslationRequest(novel="novel"))

    assert result.success == 2
    assert load_calls == 1
    assert graph.genre_snapshots == [["urban"], ["urban"]]


def test_source_override_cannot_reinterpret_stored_genres(tmp_path) -> None:
    write_chapters(tmp_path, (1,))
    workflow = make_workflow(tmp_path, SuccessGraph())
    workflow.genre_loader = lambda _novel: ["urban"]

    with pytest.raises(ApplicationValidationError, match="does not match"):
        workflow.run(TranslationRequest(novel="novel", source_language="korean"))
