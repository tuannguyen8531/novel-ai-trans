"""Tests for batch translator CLI (chapter scanning, progress, glossary, quality audit)."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.progress import ProgressEvent
from src.cli import translate as translate_cli
from src.cli.translate import _print_progress_callback, main
from src.config import Config
from src.utils.progress import ProgressTracker


@pytest.fixture(autouse=True)
def _patch_cli_paths(tmp_path: Path):
    """Each test patches the application config default rather than
    the legacy module-level ``config`` global."""
    with patch("src.services.glossary.repository.config") as mock_glossary_config:
        mock_glossary_config.translated_dir = str(tmp_path / "translated")
        mock_glossary_config.target_language = "vi"
        yield


def _patch_config(**attrs):
    """Return a context manager that overrides the application config snapshot."""
    from src.application import config

    snapshot = Config(**attrs)
    return patch.object(config, "get_config", lambda: snapshot)


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
            main()

        mock_check_provider.assert_not_called()
        output = capsys.readouterr().out
        assert "1 chapters total" in output
        assert "1 would be translated" in output


def test_missing_input_directory_uses_no_chapters_error(capsys, tmp_path: Path):
    with (
        _patch_config(translated_dir=str(tmp_path), target_language="vi"),
        patch("src.cli.translate.notify_translation_failure") as notify_failure,
        pytest.raises(SystemExit) as exit_info,
    ):
        main(["missing-novel"])

    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert f"No chapter files found in {tmp_path / 'missing-novel' / 'input'}" in output
    assert "Input directory not found" not in output
    notify_failure.assert_called_once()


def test_translation_sigint_uses_graceful_then_hard_stop(capsys):
    translate_cli._shutdown_requested = False
    translate_cli._hard_stop_requested = False
    translate_cli._cancel_event.clear()
    try:
        translate_cli._signal_handler(signal.SIGINT, None)

        assert translate_cli._shutdown_requested is True
        assert translate_cli._cancel_event.is_set()
        assert translate_cli._hard_stop_requested is False

        with pytest.raises(SystemExit) as exit_info:
            translate_cli._signal_handler(signal.SIGINT, None)

        assert exit_info.value.code == 130
        assert translate_cli._hard_stop_requested is True
        output = capsys.readouterr().out
        assert "Shutting down gracefully" in output
        assert "Press Ctrl+C again" in output
        assert "Force stopping now" in output
    finally:
        translate_cli._shutdown_requested = False
        translate_cli._hard_stop_requested = False
        translate_cli._cancel_event.clear()


def test_translation_cli_restores_sigint_handler_after_run(tmp_path: Path):
    input_dir = tmp_path / "demo" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")
    previous_handler = signal.getsignal(signal.SIGINT)

    with _patch_config(translated_dir=str(tmp_path), target_language="vi"):
        main(["demo", "--dry-run"])

    assert signal.getsignal(signal.SIGINT) is previous_handler


@pytest.mark.skipif(os.name != "posix", reason="SIGINT subprocess semantics require POSIX")
def test_second_sigint_stops_blocking_provider_promptly_without_output(tmp_path: Path):
    translated_root = tmp_path / "translated"
    input_dir = translated_root / "demo" / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "chapter_1.txt").write_text("source", encoding="utf-8")
    ready_path = tmp_path / "provider-ready"
    output_path = translated_root / "demo" / "output" / "chapter_001.txt"
    project_root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent(
        f"""
        import time
        from pathlib import Path
        from unittest.mock import patch

        from src.application import config as app_config
        from src.cli.translate import main
        from src.services.llm.base import BaseProvider

        ready_path = Path({str(ready_path)!r})
        output_path = Path({str(output_path)!r})

        class BlockingProvider(BaseProvider):
            @property
            def provider_name(self):
                return "blocking"

            def _do_generate(self, system_prompt, user_prompt, call_type):
                ready_path.write_text("ready", encoding="utf-8")
                while True:
                    time.sleep(0.05)

        def blocking_translation(request, *, progress_callback, cancel_event):
            content = BlockingProvider().generate("system", "user", "translate")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")

        app_config.set_default(
            app_config.get_config().clone(
                translated_dir={str(translated_root)!r},
                telegram_enabled=False,
            )
        )

        with (
            patch("src.cli.translate.check_provider", return_value=True),
            patch("src.cli.translate.run_translation", blocking_translation),
        ):
            main(["demo"])
        """
    )
    environment = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready_path.exists():
            output = process.stdout.read() if process.poll() is not None and process.stdout else ""
            pytest.fail(f"Blocking provider did not start. {output}")

        process.send_signal(signal.SIGINT)
        time.sleep(0.2)
        assert process.poll() is None

        started = time.monotonic()
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=2) == 130
        assert time.monotonic() - started < 2
        assert not output_path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


class TestCliProgress:
    def test_cli_progress_uses_run_total_not_input_total(self):
        tracker = ProgressTracker(10, "novel")

        with patch("src.cli.translate._progress_tracker", tracker):
            _print_progress_callback(ProgressEvent(kind="started", novel="novel", current=0, total=3))
            _print_progress_callback(ProgressEvent(kind="chapter_started", novel="novel", current=0, total=3, chapter=8))

        assert tracker.total_chapters == 3
        assert tracker.current_index == 0
        assert tracker.current_chapter == 8


class TestGlossaryCli:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.lock_patcher = patch("src.application.locks.LOCK_DIR", self.base / "locks")
        self.lock_patcher.start()
        self.backup_patcher = patch(
            "src.application.glossary.replacements.GLOSSARY_BACKUP_DIR",
            self.base / "backups",
        )
        self.backup_patcher.start()
        self.config_patcher = patch("src.services.glossary.repository.config")
        self.mock_config = self.config_patcher.start()
        self.mock_config.translated_dir = str(self.base)
        self.mock_config.target_language = "vi"

    def teardown_method(self):
        self.config_patcher.stop()
        self.backup_patcher.stop()
        self.lock_patcher.stop()
        self.temp_dir.cleanup()

    def test_glossary_add_and_list(self, capsys):
        with patch("sys.argv", ["translate", "glossary", "add", "my-novel", "李白", "Lý Bạch"]):
            main()

        with patch("sys.argv", ["translate", "glossary", "list", "my-novel"]):
            main()

        output = capsys.readouterr().out
        assert "李白\tLý Bạch" in output

    def test_glossary_character_relationship_validate_and_audit(self, capsys):
        novel_dir = self.base / "my-novel"
        novel_dir.mkdir()
        glossary_file = novel_dir / "glossary.json"
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

        (novel_dir / "input").mkdir(parents=True)
        (novel_dir / "output").mkdir(parents=True)
        (novel_dir / "input" / "chapter_1.txt").write_text("李白 đi chơi.", encoding="utf-8")
        (novel_dir / "output" / "chapter_001.txt").write_text("李白 đi chơi.", encoding="utf-8")

        with patch(
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
        ):
            main()

        with patch(
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
        ):
            main()

        with patch("sys.argv", ["translate", "glossary", "validate", "my-novel"]):
            main()

        with (
            patch("sys.argv", ["translate", "glossary", "audit", "my-novel"]),
            _patch_config(translated_dir=str(self.base), target_language="vi"),
            pytest.raises(SystemExit),
        ):
            main()

        data = json.loads(glossary_file.read_text(encoding="utf-8"))
        output = capsys.readouterr().out
        assert data["entities"]["李白"]["translated_name"] == "Lý Thái Bạch"
        assert data["entities"]["李白"]["role"] == "supporting"
        assert data["edges"] == [["李白", "杜甫", "friend", 1]]
        assert "Glossary valid" in output
        assert "missing_translation" in output

    def test_glossary_apply_dismiss_and_rollback(self, capsys):
        translated_root = self.base / "translated"
        novel_root = translated_root / "my-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)

        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次出现。魔法。", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text('Ma thuật cũ. "ma thuật" mới.', encoding="utf-8")

        config_patcher = patch("src.services.glossary.repository.config")
        mock_config = config_patcher.start()
        mock_config.translated_dir = str(translated_root)
        mock_config.target_language = "vi"

        try:
            with _patch_config(translated_dir=str(translated_root), target_language="vi"):
                from src.services.glossary.repository import (
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
                    main()

                output = capsys.readouterr().out
                assert "SAFE" in output
                assert "ma thuật → ma pháp" in output
                assert "2/2 occurrences" in output

                # Run apply --write
                with patch("sys.argv", ["translate", "glossary", "apply", "my-novel", "--write"]):
                    main()

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
                    main()

                assert load_glossary_data("my-novel")[PENDING_REPLACEMENTS_KEY] == []

                # Rollback command test
                with patch("sys.argv", ["translate", "glossary", "rollback", "my-novel", backup_id]):
                    main()

                assert output_path.read_text(encoding="utf-8") == 'Ma thuật cũ. "ma thuật" mới.'
        finally:
            config_patcher.stop()
