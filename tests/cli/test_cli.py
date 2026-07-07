"""Tests for batch translator CLI (chapter scanning, progress, glossary, quality audit)."""

import json
import tempfile
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest

from src.application.progress import ProgressEvent
from src.application.translate import TranslationRequest, run_translation
from src.cli.translate import (
    find_untranslated,
    load_progress,
    save_progress,
    scan_chapters,
    translate_file,
    translate_main,
)
from src.config import Config


@pytest.fixture(autouse=True)
def _patch_cli_paths():
    """Each test patches the application config_context default rather than
    the legacy module-level ``config`` global."""
    with patch("src.services.glossary.config") as mock_glossary_config:
        mock_glossary_config.translated_dir = ""
        mock_glossary_config.target_language = "vi"
        yield


def _patch_config(**attrs):
    """Return a context manager that overrides the application config snapshot."""
    from src.application import config_context

    class _FakeConfig:
        def __init__(self):
            for key, value in attrs.items():
                setattr(self, key, value)

        def __getattr__(self, name):
            return ""

    return patch.object(config_context, "get_config", lambda: _FakeConfig())


class TestScanChapters:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher_get = _patch_config(translated_dir=self.temp_dir.name, target_language="vi")
        self.patcher_get.start()

    def teardown_method(self):
        self.patcher_get.stop()
        self.temp_dir.cleanup()

    def _create_chapter(self, novel: str, num: int, content: str = "test"):
        path = Path(self.temp_dir.name) / novel / "input" / f"chapter_{num}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_scan_finds_all_chapters(self):
        self._create_chapter("my-novel", 1)
        self._create_chapter("my-novel", 2)
        self._create_chapter("my-novel", 10)
        chapters = scan_chapters("my-novel")
        assert list(chapters.keys()) == [1, 2, 10]

    def test_scan_sorted_by_number(self):
        self._create_chapter("my-novel", 5)
        self._create_chapter("my-novel", 1)
        self._create_chapter("my-novel", 3)
        chapters = scan_chapters("my-novel")
        assert list(chapters.keys()) == [1, 3, 5]

    def test_scan_ignores_non_chapter_files(self):
        (Path(self.temp_dir.name) / "my-novel" / "input").mkdir(parents=True)
        (Path(self.temp_dir.name) / "my-novel" / "input" / "notes.txt").write_text("ignore")
        (Path(self.temp_dir.name) / "my-novel" / "input" / "chapter_1.txt").write_text("keep")
        chapters = scan_chapters("my-novel")
        assert list(chapters.keys()) == [1]

    def test_scan_missing_directory(self):
        with pytest.raises(SystemExit):
            scan_chapters("nonexistent")


class TestFindUntranslated:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def teardown_method(self):
        self.temp_dir.cleanup()

    def _create_input(self, novel: str, chapters: list[int]):
        for ch in chapters:
            path = self.base / novel / "input" / f"chapter_{ch}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source", encoding="utf-8")

    def _create_output(self, novel: str, chapters: list[int]):
        for ch in chapters:
            path = self.base / novel / "output" / f"chapter_{ch:03d}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("translated", encoding="utf-8")

    def test_all_untranslated(self):
        self._create_input("my-novel", [1, 2, 3])
        chapters = {
            1: self.base / "my-novel/input/chapter_1.txt",
            2: self.base / "my-novel/input/chapter_2.txt",
            3: self.base / "my-novel/input/chapter_3.txt",
        }
        with _patch_config(translated_dir=str(self.base), target_language="vi"):
            result = find_untranslated("my-novel", chapters)
        assert result == [1, 2, 3]

    def test_some_translated(self):
        self._create_input("my-novel", [1, 2, 3])
        self._create_output("my-novel", [1])
        chapters = {
            1: self.base / "my-novel/input/chapter_1.txt",
            2: self.base / "my-novel/input/chapter_2.txt",
            3: self.base / "my-novel/input/chapter_3.txt",
        }
        with _patch_config(translated_dir=str(self.base), target_language="vi"):
            result = find_untranslated("my-novel", chapters)
        assert result == [2, 3]

    def test_all_translated(self):
        self._create_input("my-novel", [1, 2])
        self._create_output("my-novel", [1, 2])
        chapters = {
            1: self.base / "my-novel/input/chapter_1.txt",
            2: self.base / "my-novel/input/chapter_2.txt",
        }
        with _patch_config(translated_dir=str(self.base), target_language="vi"):
            result = find_untranslated("my-novel", chapters)
        assert result == []

    def test_target_language_uses_separate_output_dir(self):
        self._create_input("my-novel", [1, 2])
        self._create_output("my-novel", [1])
        en_output = self.base / "my-novel" / "output" / "en" / "chapter_002.txt"
        en_output.parent.mkdir(parents=True, exist_ok=True)
        en_output.write_text("translated", encoding="utf-8")

        chapters = {
            1: self.base / "my-novel/input/chapter_1.txt",
            2: self.base / "my-novel/input/chapter_2.txt",
        }
        with _patch_config(translated_dir=str(self.base), target_language="vi"):
            result = find_untranslated("my-novel", chapters, target_language="en")

        assert result == [1]


class TestDryRun:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        input_dir = self.base / "my-novel" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_dry_run_does_not_check_provider(self, capsys):
        with (
            patch("sys.argv", ["translate", "my-novel", "--dry-run"]),
            _patch_config(translated_dir=str(self.base), target_language="vi"),
            patch("src.cli.translate.check_provider") as mock_check_provider,
        ):
            translate_main()

        mock_check_provider.assert_not_called()
        output = capsys.readouterr().out
        assert "1 chapters total" in output
        assert "1 would be translated" in output


class TestProgressState:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_save_and_load_progress_normalizes_lists(self):
        with patch("src.cli.translate.PROGRESS_DIR", self.base / ".progress"), _patch_config(target_language="vi"):
            save_progress("my-novel", {"completed": [2, 1, 2], "failed": [3, 3]})
            assert load_progress("my-novel") == {"completed": [1, 2], "failed": [3]}

    def test_target_language_uses_separate_progress_file(self):
        with patch("src.cli.translate.PROGRESS_DIR", self.base / ".progress"), _patch_config(target_language="vi"):
            save_progress("my-novel", {"completed": [1], "failed": []})
            save_progress("my-novel", {"completed": [2], "failed": []}, target_language="en")

            assert load_progress("my-novel") == {"completed": [1], "failed": []}
            assert load_progress("my-novel", target_language="en") == {"completed": [2], "failed": []}


class TestQualityReport:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.input_path = self.base / "chapter_1.txt"
        self.input_path.write_text("source", encoding="utf-8")

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_translate_file_writes_quality_report(self):
        class FakeGraph:
            def invoke(self, state):
                return {
                    "final_translation": "translated",
                    "new_terms": {"李白": "Lý Bạch"},
                    "new_characters": {"entities": {"李白": {}}},
                    "quality_reports": [
                        {
                            "chunk_index": 0,
                            "score": 0.9,
                            "feedback": "Good",
                            "post_check_issues": [],
                            "retry_count": 0,
                        }
                    ],
                }

        with (
            tempfile.TemporaryDirectory() as translated_tmp,
            patch("src.cli.translate.REPORT_DIR", self.base / "reports"),
            _patch_config(translated_dir=translated_tmp, target_language="vi"),
        ):
            success, out_chars, elapsed, new_terms_count = translate_file(
                self.input_path,
                "my-novel",
                1,
                "chinese",
                graph=FakeGraph(),
            )

        assert success
        assert out_chars == len("translated")
        assert elapsed >= 0
        assert new_terms_count == 1

        report = json.loads((self.base / "reports" / "my-novel" / "chapter_001.json").read_text(encoding="utf-8"))
        assert report["chapter"] == 1
        assert report["target_language"] == "vi"
        assert report["new_terms_count"] == 1
        assert report["new_characters_count"] == 1
        assert report["chunks"][0]["score"] == 0.9


class TestTranslationWorkflow:
    def test_progress_sizes_follow_token_chunk_mode(self, tmp_path):
        translated_root = tmp_path / "translated"
        input_dir = translated_root / "novel" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "chapter_1.txt").write_text("甲乙丙丁", encoding="utf-8")
        config = Config(translated_dir=str(translated_root), chunk_mode="tokens")
        events: list[ProgressEvent] = []

        def translate_success(*_args, output_dir, **_kwargs):
            output_dir.mkdir(parents=True, exist_ok=True)
            output = "abcdefgh"
            (output_dir / "chapter_001.txt").write_text(output, encoding="utf-8")
            return True, len(output), 1.0, 0

        with (
            patch("src.application.translate.config_context.get_config", return_value=config),
            patch("src.application.translate._paths.PROGRESS_DIR", tmp_path / "progress"),
            patch("src.application.translate._validate_provider"),
            patch("src.application.translate.build_graph", return_value=object()),
            patch("src.application.translate.translate_file", side_effect=translate_success),
        ):
            run_translation(TranslationRequest(novel="novel"), progress_callback=events.append)

        started = next(event for event in events if event.kind == "chapter_started")
        completed = next(event for event in events if event.kind == "chapter_completed")
        assert started.extra["source_size"] == 4
        assert started.extra["size_unit"] == "tokens"
        assert completed.extra["output_size"] == 2
        assert completed.extra["size_unit"] == "tokens"

    def test_chapter_exception_is_counted_once(self, tmp_path):
        translated_root = tmp_path / "translated"
        input_dir = translated_root / "novel" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")
        events: list[ProgressEvent] = []
        config = Config(translated_dir=str(translated_root))

        with (
            patch("src.application.translate.config_context.get_config", return_value=config),
            patch("src.application.translate._paths.PROGRESS_DIR", tmp_path / "progress"),
            patch("src.application.translate._validate_provider"),
            patch("src.application.translate.build_graph", return_value=object()),
            patch("src.application.translate.translate_file", side_effect=RuntimeError("provider failed")),
        ):
            result = run_translation(TranslationRequest(novel="novel"), progress_callback=events.append)

        assert result.total == 1
        assert result.failed == 1
        assert result.failures == [1]
        assert result.chapters_attempted == [1]
        failed_event = next(event for event in events if event.kind == "chapter_failed")
        assert failed_event.current == 1
        assert failed_event.pct == 100.0

    def test_cancel_finishes_current_chapter_then_stops_before_the_next(self, tmp_path):
        translated_root = tmp_path / "translated"
        input_dir = translated_root / "novel" / "input"
        input_dir.mkdir(parents=True)
        (input_dir / "chapter_1.txt").write_text("source 1", encoding="utf-8")
        (input_dir / "chapter_2.txt").write_text("source 2", encoding="utf-8")
        config = Config(translated_dir=str(translated_root))
        cancel_event = Event()

        def finish_current_chapter(*_args, **_kwargs):
            cancel_event.set()
            return True, 10, 1.0, 0

        with (
            patch("src.application.translate.config_context.get_config", return_value=config),
            patch("src.application.translate._paths.PROGRESS_DIR", tmp_path / "progress"),
            patch("src.application.translate._validate_provider"),
            patch("src.application.translate.build_graph", return_value=object()),
            patch("src.application.translate.translate_file", side_effect=finish_current_chapter) as mocked_translate,
        ):
            result = run_translation(TranslationRequest(novel="novel"), cancel_event=cancel_event)

        assert result.cancelled is True
        assert result.success == 1
        assert result.chapters_attempted == [1]
        mocked_translate.assert_called_once()


class TestGlossaryCli:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.lock_patcher = patch("src.services.glossary.LOCK_DIR", self.base / "locks")
        self.lock_patcher.start()
        self.backup_patcher = patch("src.services.glossary.GLOSSARY_BACKUP_DIR", self.base / "backups")
        self.backup_patcher.start()

    def teardown_method(self):
        self.backup_patcher.stop()
        self.lock_patcher.stop()
        self.temp_dir.cleanup()

    def test_glossary_add_and_list(self, capsys):
        with (
            patch("sys.argv", ["translate", "glossary", "add", "my-novel", "李白", "Lý Bạch"]),
            patch("src.services.glossary.GLOSSARY_DIR", self.base / "glossary"),
        ):
            translate_main()

        with (
            patch("sys.argv", ["translate", "glossary", "list", "my-novel"]),
            patch("src.services.glossary.GLOSSARY_DIR", self.base / "glossary"),
        ):
            translate_main()

        output = capsys.readouterr().out
        assert "李白\tLý Bạch" in output

    def test_glossary_character_relationship_validate_and_audit(self, capsys):
        glossary_dir = self.base / "glossary"
        glossary_dir.mkdir()
        glossary_file = glossary_dir / "my-novel.json"
        glossary_file.write_text(
            json.dumps(
                {
                    "terms": {"李白": "Lý Bạch"},
                    "entities": {
                        "李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": ""},
                        "杜甫": {"translated_name": "Đỗ Phủ", "role": "supporting", "pronoun": ""},
                    },
                    "edges": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        novel_dir = self.base / "my-novel"
        (novel_dir / "input").mkdir(parents=True)
        (novel_dir / "output").mkdir(parents=True)
        (novel_dir / "input" / "chapter_1.txt").write_text("李白 đi chơi.", encoding="utf-8")
        (novel_dir / "output" / "chapter_001.txt").write_text("李白 đi chơi.", encoding="utf-8")

        with (
            patch(
                "sys.argv",
                [
                    "translate",
                    "glossary",
                    "character",
                    "my-novel",
                    "李白",
                    "--translated-name",
                    "Lý Thái Bạch",
                    "--role",
                    "supporting",
                ],
            ),
            patch("src.services.glossary.GLOSSARY_DIR", glossary_dir),
        ):
            translate_main()

        with (
            patch(
                "sys.argv",
                [
                    "translate",
                    "glossary",
                    "relationship",
                    "my-novel",
                    "李白",
                    "杜甫",
                    "friend",
                    "--since",
                    "1",
                ],
            ),
            patch("src.services.glossary.GLOSSARY_DIR", glossary_dir),
        ):
            translate_main()

        with (
            patch("sys.argv", ["translate", "glossary", "validate", "my-novel"]),
            patch("src.services.glossary.GLOSSARY_DIR", glossary_dir),
        ):
            translate_main()

        with (
            patch("sys.argv", ["translate", "glossary", "audit", "my-novel"]),
            patch("src.services.glossary.GLOSSARY_DIR", glossary_dir),
            _patch_config(translated_dir=str(self.base), target_language="vi"),
            pytest.raises(SystemExit),
        ):
            translate_main()

        data = json.loads(glossary_file.read_text(encoding="utf-8"))
        output = capsys.readouterr().out
        assert data["entities"]["李白"]["translated_name"] == "Lý Thái Bạch"
        assert data["entities"]["李白"]["role"] == "supporting"
        assert data["edges"] == [["李白", "杜甫", "friend", 1]]
        assert "Glossary valid" in output
        assert "missing_translation" in output

    def test_glossary_apply_dismiss_and_rollback(self, capsys):
        glossary_dir = self.base / "glossary"
        glossary_dir.mkdir(parents=True, exist_ok=True)

        translated_root = self.base / "translated"
        novel_root = translated_root / "my-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)

        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次出现。魔法。", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text('Ma thuật cũ. "ma thuật" mới.', encoding="utf-8")

        config_patcher = patch("src.services.glossary.config")
        mock_config = config_patcher.start()
        mock_config.translated_dir = str(translated_root)
        mock_config.target_language = "vi"

        try:
            with (
                patch("src.services.glossary.GLOSSARY_DIR", glossary_dir),
                patch("src.cli.translate.INPUT_DIR", novel_root / "input"),
                patch("src.cli.translate.OUTPUT_DIR", novel_root / "output"),
                _patch_config(translated_dir=str(translated_root), target_language="vi"),
            ):
                from src.services.glossary import (
                    PENDING_REPLACEMENTS_KEY,
                    load_glossary_data,
                    save_glossary,
                    update_glossary_term,
                )

                save_glossary("my-novel", {"魔法": "ma thuật"})
                update_glossary_term("my-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

                assert load_glossary_data("my-novel")[PENDING_REPLACEMENTS_KEY] != []

                # Run apply preview
                with patch("sys.argv", ["translate", "glossary", "apply", "my-novel"]):
                    translate_main()

                output = capsys.readouterr().out
                assert "SAFE" in output
                assert "ma thuật → ma pháp" in output
                assert "2/2 occurrences" in output

                # Run apply --write
                with patch("sys.argv", ["translate", "glossary", "apply", "my-novel", "--write"]):
                    translate_main()

                output = capsys.readouterr().out
                assert "APPLIED" in output
                assert output_path.read_text(encoding="utf-8") == 'Ma pháp cũ. "Ma pháp" mới.'

                manifests = list((self.base / "backups").rglob("manifest.json"))
                assert len(manifests) == 1
                backup_id = manifests[0].parent.name

                # Dismiss command test
                update_glossary_term("my-novel", "魔法", "魔法", "ma pháp siêu cấp", is_user_edit=True)
                assert load_glossary_data("my-novel")[PENDING_REPLACEMENTS_KEY] != []

                with patch("sys.argv", ["translate", "glossary", "dismiss", "my-novel"]):
                    translate_main()

                assert load_glossary_data("my-novel")[PENDING_REPLACEMENTS_KEY] == []

                # Rollback command test
                with patch("sys.argv", ["translate", "glossary", "rollback", "my-novel", backup_id]):
                    translate_main()

                assert output_path.read_text(encoding="utf-8") == 'Ma thuật cũ. "ma thuật" mới.'
        finally:
            config_patcher.stop()
