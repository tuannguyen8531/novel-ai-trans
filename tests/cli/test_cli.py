"""Tests for batch translator CLI (chapter scanning, progress, glossary, quality audit)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cli.translate import (
    find_untranslated,
    load_progress,
    save_progress,
    scan_chapters,
    translate_file,
    translate_main,
)


@pytest.fixture(autouse=True)
def _patch_cli_paths():
    """Each test patches the application config_context default rather than
    the legacy module-level ``config`` global."""
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
        self.patcher_input = patch("src.cli.translate.INPUT_DIR", Path(self.temp_dir.name))
        self.patcher_input.start()
        self.patcher_get = _patch_config(translated_dir="", target_language="vi")
        self.patcher_get.start()

    def teardown_method(self):
        self.patcher_input.stop()
        self.patcher_get.stop()
        self.temp_dir.cleanup()

    def _create_chapter(self, novel: str, num: int, content: str = "test"):
        path = Path(self.temp_dir.name) / novel / f"chapter_{num}.txt"
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
        (Path(self.temp_dir.name) / "my-novel").mkdir(parents=True)
        (Path(self.temp_dir.name) / "my-novel" / "notes.txt").write_text("ignore")
        (Path(self.temp_dir.name) / "my-novel" / "chapter_1.txt").write_text("keep")
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
            path = self.base / "input" / novel / f"chapter_{ch}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source", encoding="utf-8")

    def _create_output(self, novel: str, chapters: list[int]):
        for ch in chapters:
            path = self.base / "output" / novel / f"chapter_{ch:03d}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("translated", encoding="utf-8")

    def test_all_untranslated(self):
        self._create_input("my-novel", [1, 2, 3])
        chapters = {
            1: self.base / "input/my-novel/chapter_1.txt",
            2: self.base / "input/my-novel/chapter_2.txt",
            3: self.base / "input/my-novel/chapter_3.txt",
        }
        with _patch_config(translated_dir="", target_language="vi"):
            result = find_untranslated("my-novel", chapters)
        assert result == [1, 2, 3]

    def test_some_translated(self):
        self._create_input("my-novel", [1, 2, 3])
        self._create_output("my-novel", [1])
        chapters = {
            1: self.base / "input/my-novel/chapter_1.txt",
            2: self.base / "input/my-novel/chapter_2.txt",
            3: self.base / "input/my-novel/chapter_3.txt",
        }
        with (
            patch("src.cli.translate.OUTPUT_DIR", self.base / "output"),
            _patch_config(translated_dir="", target_language="vi"),
        ):
            result = find_untranslated("my-novel", chapters)
        assert result == [2, 3]

    def test_all_translated(self):
        self._create_input("my-novel", [1, 2])
        self._create_output("my-novel", [1, 2])
        chapters = {1: self.base / "input/my-novel/chapter_1.txt", 2: self.base / "input/my-novel/chapter_2.txt"}
        with (
            patch("src.cli.translate.OUTPUT_DIR", self.base / "output"),
            _patch_config(translated_dir="", target_language="vi"),
        ):
            result = find_untranslated("my-novel", chapters)
        assert result == []

    def test_target_language_uses_separate_output_dir(self):
        self._create_input("my-novel", [1, 2])
        self._create_output("my-novel", [1])
        en_output = self.base / "output" / "en" / "my-novel" / "chapter_002.txt"
        en_output.parent.mkdir(parents=True, exist_ok=True)
        en_output.write_text("translated", encoding="utf-8")

        chapters = {1: self.base / "input/my-novel/chapter_1.txt", 2: self.base / "input/my-novel/chapter_2.txt"}
        with (
            patch("src.cli.translate.OUTPUT_DIR", self.base / "output"),
            _patch_config(translated_dir="", target_language="vi"),
        ):
            result = find_untranslated("my-novel", chapters, target_language="en")

        assert result == [1]


class TestDryRun:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        input_dir = self.base / "input" / "my-novel"
        input_dir.mkdir(parents=True)
        (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_dry_run_does_not_check_provider(self, capsys):
        with (
            patch("sys.argv", ["translate", "my-novel", "--dry-run"]),
            patch("src.application.paths.INPUT_DIR", self.base / "input"),
            patch("src.application.paths.OUTPUT_DIR", self.base / "output"),
            patch("src.cli.translate.INPUT_DIR", self.base / "input"),
            patch("src.cli.translate.OUTPUT_DIR", self.base / "output"),
            _patch_config(translated_dir="", target_language="vi"),
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
            patch("src.cli.translate.OUTPUT_DIR", self.base / "output"),
            patch("src.cli.translate.REPORT_DIR", self.base / "reports"),
            _patch_config(translated_dir="", target_language="vi"),
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


class TestGlossaryCli:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)

    def teardown_method(self):
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

        input_dir = self.base / "input"
        output_dir = self.base / "output"
        (input_dir / "my-novel").mkdir(parents=True)
        (output_dir / "my-novel").mkdir(parents=True)
        (input_dir / "my-novel" / "chapter_1.txt").write_text("李白 đi chơi.", encoding="utf-8")
        (output_dir / "my-novel" / "chapter_001.txt").write_text("李白 đi chơi.", encoding="utf-8")

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
            patch("src.cli.translate.INPUT_DIR", input_dir),
            patch("src.cli.translate.OUTPUT_DIR", output_dir),
            _patch_config(translated_dir="", target_language="vi"),
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
