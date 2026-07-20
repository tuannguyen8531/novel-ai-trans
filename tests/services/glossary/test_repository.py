"""Tests for glossary service."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.application.errors import ResourceConflictError
from src.application.glossary.replacements import (
    apply_pending_replacements,
    dismiss_pending_replacements,
    rollback_glossary_replacement,
)
from src.application.locks import novel_lock
from src.domain.glossary import PENDING_REPLACEMENTS_KEY
from src.services.glossary.repository import (
    clean_glossary,
    get_active_context,
    load_glossary,
    load_glossary_data,
    remove_character,
    remove_glossary_term,
    remove_relationship,
    save_character,
    save_character_pronoun,
    save_characters_batch,
    save_glossary,
    save_relationship,
    update_glossary_term,
    validate_glossary,
)


class TestGlossary:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.patcher = patch("src.services.glossary.repository.GLOSSARY_DIR", Path(self.temp_dir.name))
        self.patcher.start()
        self.backup_patcher = patch(
            "src.application.glossary.replacements.GLOSSARY_BACKUP_DIR",
            Path(self.temp_dir.name) / "backups",
        )
        self.backup_patcher.start()
        self.config_patcher = patch("src.services.glossary.repository.config")
        self.mock_config = self.config_patcher.start()
        self.mock_config.translated_dir = ""
        self.mock_config.target_language = "vi"

    def teardown_method(self):
        self.patcher.stop()
        self.backup_patcher.stop()
        self.config_patcher.stop()
        self.temp_dir.cleanup()

    def test_save_and_load_glossary(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})
        result = load_glossary("test-novel")
        assert result == {"李白": "Lý Bạch"}
        assert load_glossary_data("test-novel")["terms"] == {"李白": "Lý Bạch"}

    def test_merge_glossary(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})
        save_glossary("test-novel", {"杜甫": "Đỗ Phủ"})
        result = load_glossary("test-novel")
        assert result == {"李白": "Lý Bạch", "杜甫": "Đỗ Phủ"}

    def test_merge_overrides_existing(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})
        save_glossary("test-novel", {"李白": "Lý Bạch Mới"}, is_user_edit=True)
        result = load_glossary("test-novel")
        assert result["李白"] == "Lý Bạch Mới"
        pending = load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY]
        assert pending == [
            {
                "kind": "term",
                "sources": ["李白"],
                "old": "Lý Bạch",
                "new": "Lý Bạch Mới",
            }
        ]

    def test_reverting_term_to_original_value_removes_pending_replacement(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})
        save_glossary("test-novel", {"李白": "Lý Thái Bạch"}, is_user_edit=True)
        save_glossary("test-novel", {"李白": "Lý Bạch"}, is_user_edit=True)

        data = load_glossary_data("test-novel")
        assert data["terms"]["李白"] == "Lý Bạch"
        assert data[PENDING_REPLACEMENTS_KEY] == []

    def test_load_nonexistent(self):
        result = load_glossary("nonexistent")
        assert result == {}

    def test_remove_glossary_term(self):
        save_glossary("test-novel", {"李白": "Lý Bạch", "杜甫": "Đỗ Phủ"})

        assert remove_glossary_term("test-novel", "李白")
        assert load_glossary("test-novel") == {"杜甫": "Đỗ Phủ"}

    def test_remove_missing_glossary_term(self):
        assert not remove_glossary_term("test-novel", "missing")

    def test_update_glossary_term_renames_atomically(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})

        update_glossary_term("test-novel", "李白", "诗仙", "Thi Tiên")

        assert load_glossary("test-novel") == {"诗仙": "Thi Tiên"}

    def test_update_glossary_term_rejects_conflict_without_changes(self):
        original = {"李白": "Lý Bạch", "杜甫": "Đỗ Phủ"}
        save_glossary("test-novel", original)

        try:
            update_glossary_term("test-novel", "李白", "杜甫", "Thi Tiên")
        except FileExistsError:
            pass
        else:
            raise AssertionError("Expected conflicting rename to fail")

        assert load_glossary("test-novel") == original

        update_glossary_term("test-novel", "李白", "杜甫", "Thi Tiên", overwrite=True)

        assert load_glossary("test-novel") == {"杜甫": "Thi Tiên"}

    def test_save_character_pronoun(self):
        save_characters_batch(
            "test-novel",
            {"李白": {"translated_name": "Lý Bạch", "role": "supporting", "pronoun": ""}},
            [],
        )

        assert save_character_pronoun("test-novel", "李白", "ông")
        data = load_glossary_data("test-novel")
        assert data["entities"]["李白"]["pronoun"] == "ông"

    def test_save_character_pronoun_missing_character(self):
        assert not save_character_pronoun("test-novel", "missing", "ông")

    def test_save_character_updates_name_and_role(self):
        save_characters_batch(
            "test-novel",
            {"李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": ""}},
            [],
        )

        assert save_character(
            "test-novel",
            "李白",
            translated_name="Lý Thái Bạch",
            role="supporting",
            is_user_edit=True,
        )
        data = load_glossary_data("test-novel")
        assert data["entities"]["李白"]["translated_name"] == "Lý Thái Bạch"
        assert data["entities"]["李白"]["role"] == "supporting"
        assert data[PENDING_REPLACEMENTS_KEY][0] == {
            "kind": "character",
            "sources": ["李白"],
            "old": "Lý Bạch",
            "new": "Lý Thái Bạch",
        }

    def test_save_character_updates_preserves_and_clears_pronoun(self):
        save_characters_batch(
            "test-novel",
            {"李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": "ông"}},
            [],
        )

        assert save_character("test-novel", "李白", pronoun="anh ấy")
        assert load_glossary_data("test-novel")["entities"]["李白"]["pronoun"] == "anh ấy"

        assert save_character("test-novel", "李白", role="supporting")
        assert load_glossary_data("test-novel")["entities"]["李白"]["pronoun"] == "anh ấy"

        assert save_character("test-novel", "李白", pronoun="")
        assert load_glossary_data("test-novel")["entities"]["李白"]["pronoun"] == ""

    def test_reverting_character_name_removes_pending_replacement(self):
        save_characters_batch(
            "test-novel",
            {"李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": ""}},
            [],
        )
        save_character("test-novel", "李白", translated_name="Lý Thái Bạch", is_user_edit=True)
        save_character("test-novel", "李白", translated_name="Lý Bạch", is_user_edit=True)

        data = load_glossary_data("test-novel")
        assert data["entities"]["李白"]["translated_name"] == "Lý Bạch"
        assert data[PENDING_REPLACEMENTS_KEY] == []

    def test_apply_pending_replacements_previews_then_writes(self):
        translated_root = Path(self.temp_dir.name) / "translated"
        novel_root = translated_root / "test-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)
        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次出现。魔法。", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text('Ma thuật cũ. "ma thuật" mới.', encoding="utf-8")
        self.mock_config.translated_dir = str(translated_root)

        save_glossary("test-novel", {"魔法": "ma thuật"})
        update_glossary_term("test-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

        preview = apply_pending_replacements("test-novel")
        assert preview["write"] is False
        assert preview["changed_files"] == 1
        assert preview["replacements"][0]["occurrences"] == 2
        assert output_path.read_text(encoding="utf-8") == 'Ma thuật cũ. "ma thuật" mới.'

        applied = apply_pending_replacements("test-novel", write=True)
        assert applied["changed_files"] == 1
        assert output_path.read_text(encoding="utf-8") == 'Ma pháp cũ. "Ma pháp" mới.'
        assert load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY] == []

    def test_save_character_accepts_legacy_name_vi_argument(self):
        save_characters_batch(
            "test-novel",
            {"李白": {"translated_name": "Lý Bạch", "role": "minor", "pronoun": ""}},
            [],
        )

        assert save_character("test-novel", "李白", name_vi="Lý Thái Bạch")
        data = load_glossary_data("test-novel")
        assert data["entities"]["李白"]["translated_name"] == "Lý Thái Bạch"
        assert "name_vi" not in data["entities"]["李白"]

    def test_save_character_missing_character(self):
        assert not save_character("test-novel", "missing", role="supporting")

    def test_save_relationship_requires_existing_characters(self):
        save_characters_batch(
            "test-novel",
            {
                "李白": {"translated_name": "Lý Bạch", "role": "supporting", "pronoun": ""},
                "杜甫": {"translated_name": "Đỗ Phủ", "role": "supporting", "pronoun": ""},
            },
            [],
        )

        assert save_relationship("test-novel", "李白", "杜甫", "friend", since_chapter=2)
        assert load_glossary_data("test-novel")["edges"] == [["李白", "杜甫", "friend", 2]]
        assert not save_relationship("test-novel", "李白", "missing", "enemy")

    def test_remove_relationship_and_character_references(self):
        save_characters_batch(
            "test-novel",
            {
                "李白": {"translated_name": "Lý Bạch", "role": "supporting"},
                "杜甫": {"translated_name": "Đỗ Phủ", "role": "supporting"},
            },
            [["李白", "杜甫", "friend", 2]],
            address_rules=[{"speaker": "李白", "listener": "杜甫", "self": "ta", "other": "huynh", "since": 2}],
            chapter=2,
        )

        assert remove_relationship("test-novel", "李白", "杜甫")
        assert load_glossary_data("test-novel")["edges"] == []

        assert save_relationship("test-novel", "李白", "杜甫", "friend", since_chapter=2)
        assert remove_character("test-novel", "李白")
        data = load_glossary_data("test-novel")
        assert "李白" not in data["entities"]
        assert data["edges"] == []
        assert data["address_rules"] == []

    def test_save_and_load_active_address_rules(self):
        save_characters_batch(
            "test-novel",
            {
                "李白": {"translated_name": "Lý Bạch", "role": "supporting", "pronoun": "ông"},
                "杜甫": {"translated_name": "Đỗ Phủ", "role": "supporting", "pronoun": "ông"},
            },
            [["李白", "杜甫", "friend"]],
            address_rules=[
                {"speaker": "Lý Bạch", "listener": "Đỗ Phủ", "self": "ta", "other": "huynh", "since": 2},
                {"speaker": "Đỗ Phủ", "listener": "Lý Bạch", "self": "tôi", "other": "ngài", "since": 5},
            ],
            chapter=2,
        )

        entities, edges, address_rules = get_active_context("test-novel", "李白 gặp 杜甫.", chapter_number=3)

        assert set(entities) == {"李白", "杜甫"}
        assert edges == [["李白", "杜甫", "friend", 2]]
        assert address_rules == [{"speaker": "李白", "listener": "杜甫", "self": "ta", "other": "huynh", "since": 2}]

    def test_active_context_does_not_load_address_rules_for_absent_neighbors(self):
        save_characters_batch(
            "test-novel",
            {
                "陆远秋": {"translated_name": "Lục Viễn Thu", "role": "protagonist"},
                "白清夏": {"translated_name": "Bạch Thanh Hạ", "role": "supporting"},
                "梁先生": {"translated_name": "ông Lương", "role": "minor"},
            },
            [
                ["陆远秋", "白清夏", "friend"],
                ["陆远秋", "梁先生", "teacher"],
            ],
            address_rules=[
                {"speaker": "陆远秋", "listener": "白清夏", "self": "tôi", "other": "cậu", "since": 1},
                {"speaker": "陆远秋", "listener": "梁先生", "self": "cháu", "other": "ông", "since": 1},
            ],
            chapter=1,
        )

        entities, edges, address_rules = get_active_context(
            "test-novel",
            "陆远秋 gặp 白清夏.",
            chapter_number=2,
        )

        assert set(entities) == {"陆远秋", "白清夏"}
        assert edges == [["陆远秋", "白清夏", "friend", 1]]
        assert address_rules == [{"speaker": "陆远秋", "listener": "白清夏", "self": "tôi", "other": "cậu", "since": 1}]

    def test_validate_glossary(self):
        save_glossary("test-novel", {"李白": "Lý Bạch"})

        assert validate_glossary("test-novel") == []

    def test_target_language_uses_separate_glossary_file(self):
        self.mock_config.target_language = "vi"
        save_glossary("test-novel", {"李白": "Lý Bạch"})

        self.mock_config.target_language = "en"
        save_glossary("test-novel", {"李白": "Li Bai"})

        assert (Path(self.temp_dir.name) / "test-novel.json").exists()
        assert (Path(self.temp_dir.name) / "test-novel.en.json").exists()

        assert load_glossary("test-novel") == {"李白": "Li Bai"}

        self.mock_config.target_language = "vi"
        assert load_glossary("test-novel") == {"李白": "Lý Bạch"}

    def test_clean_glossary_normalizes_edges_and_removes_pronoun_examples(self):
        path = Path(self.temp_dir.name) / "test-novel.json"
        path.write_text(
            json.dumps(
                {
                    "entities": {
                        "카일": {"name_vi": "Kyle", "role": "protagonist", "pronoun": "hắn"},
                        "이사벨": {"name_vi": "Isabelle", "role": "supporting", "pronoun": "cô ấy"},
                    },
                    "edges": [
                        ["카일", "이사벨", "friend", 1],
                        ["Kyle", "Isabelle", "rival", 2],
                    ],
                    "pronoun_examples": {"카일": ["Hắn đi."]},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        stats = clean_glossary("test-novel")
        data = load_glossary_data("test-novel")

        assert stats["edges_before"] == 2
        assert stats["edges_after"] == 1
        assert stats["address_rules_before"] == 0
        assert stats["address_rules_after"] == 0
        assert stats["pronoun_examples_removed"] == 1
        assert data["entities"]["카일"]["translated_name"] == "Kyle"
        assert "name_vi" not in data["entities"]["카일"]
        assert data["edges"] == [["카일", "이사벨", "friend", 1]]
        assert "pronoun_examples" not in data


class TestGlossaryTranslatedDir:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base = Path(self.temp_dir.name)
        self.project_glossary = self.base / "glossary"
        self.translated_glossary = self.base / "translated" / "my-novel"
        self.translated_glossary.mkdir(parents=True)

        self.patcher_glossary_dir = patch("src.services.glossary.repository.GLOSSARY_DIR", self.project_glossary)
        self.patcher_glossary_dir.start()
        self.patcher_lock_dir = patch("src.application.locks.LOCK_DIR", self.base / "locks")
        self.patcher_lock_dir.start()
        self.patcher_backup_dir = patch(
            "src.application.glossary.replacements.GLOSSARY_BACKUP_DIR",
            self.base / "backups",
        )
        self.patcher_backup_dir.start()

    def teardown_method(self):
        self.patcher_backup_dir.stop()
        self.patcher_lock_dir.stop()
        self.patcher_glossary_dir.stop()
        self.temp_dir.cleanup()

    def test_load_from_translated(self):
        translated_file = self.translated_glossary / "glossary.json"
        translated_file.parent.mkdir(parents=True, exist_ok=True)
        translated_file.write_text(json.dumps({"terms": {"李白": "Lý Bạch"}}), encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(self.base / "translated")
            mock_config.target_language = "vi"
            result = load_glossary("my-novel")

        assert result == {"李白": "Lý Bạch"}
        assert not (self.project_glossary / "my-novel.json").exists()

    def test_no_translated_dir_uses_project_only(self):
        project_file = self.project_glossary / "my-novel.json"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text(json.dumps({"terms": {"李白": "Lý Bạch"}}), encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = ""
            mock_config.target_language = "vi"
            result = load_glossary("my-novel")

        assert result == {"李白": "Lý Bạch"}

    def test_translated_dir_not_set_returns_empty(self):
        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = ""
            mock_config.target_language = "vi"
            result = load_glossary("nonexistent")

        assert result == {}

    def test_save_syncs_to_translated_dir(self):
        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(self.base / "translated")
            mock_config.target_language = "vi"
            save_glossary("my-novel", {"李白": "Lý Bạch"})

        translated_file = self.translated_glossary / "glossary.json"
        assert translated_file.exists()
        data = json.loads(translated_file.read_text(encoding="utf-8"))
        assert data["terms"] == {"李白": "Lý Bạch"}

    def test_save_updates_translated_on_merge(self):
        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(self.base / "translated")
            mock_config.target_language = "vi"
            save_glossary("my-novel", {"李白": "Lý Bạch"})
            save_glossary("my-novel", {"杜甫": "Đỗ Phủ"})

        translated_file = self.translated_glossary / "glossary.json"
        data = json.loads(translated_file.read_text(encoding="utf-8"))
        assert data["terms"] == {"李白": "Lý Bạch", "杜甫": "Đỗ Phủ"}

    def test_no_sync_when_translated_dir_empty(self):
        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = ""
            mock_config.target_language = "vi"
            save_glossary("my-novel", {"李白": "Lý Bạch"})

        translated_file = self.translated_glossary / "glossary.json"
        assert not translated_file.exists()

    def test_apply_pending_replacements_creates_backup_and_supports_rollback(self):
        translated_root = self.base / "translated"
        novel_root = translated_root / "test-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)
        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次出现。魔法。", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text('Ma thuật cũ. "ma thuật" mới.', encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(translated_root)
            mock_config.target_language = "vi"

            save_glossary("test-novel", {"魔法": "ma thuật"})
            update_glossary_term("test-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

            applied = apply_pending_replacements("test-novel", write=True)
            assert applied["changed_files"] == 1
            assert output_path.read_text(encoding="utf-8") == 'Ma pháp cũ. "Ma pháp" mới.'

            # A later glossary edit must survive rollback. Its pending chain
            # should point directly from the restored output to the latest value.
            update_glossary_term("test-novel", "魔法", "魔法", "huyền thuật", is_user_edit=True)

            backup_id = applied["backup_id"]
            assert isinstance(backup_id, str)
            manifests = list((self.base / "backups").rglob("manifest.json"))
            assert len(manifests) == 1
            assert manifests[0].parent.name == backup_id

            # Rollback
            rollback_glossary_replacement("test-novel", backup_id)
            assert output_path.read_text(encoding="utf-8") == 'Ma thuật cũ. "ma thuật" mới.'
            data = load_glossary_data("test-novel")
            assert data["terms"]["魔法"] == "huyền thuật"
            assert data[PENDING_REPLACEMENTS_KEY] == [
                {
                    "kind": "term",
                    "sources": ["魔法"],
                    "old": "ma thuật",
                    "new": "huyền thuật",
                }
            ]

    def test_apply_pending_replacements_novel_locking(self):
        translated_root = self.base / "translated"
        novel_root = translated_root / "test-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)
        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次.", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text("Ma thuật.", encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(translated_root)
            mock_config.target_language = "vi"

            save_glossary("test-novel", {"魔法": "ma thuật"})
            update_glossary_term("test-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

            with novel_lock("test-novel"):
                with pytest.raises(ResourceConflictError, match="locked"), novel_lock("test-novel"):
                    pass
                with pytest.raises(ResourceConflictError, match="locked"):
                    apply_pending_replacements("test-novel")

    def test_apply_ignores_missing_output_and_clears_pending(self):
        translated_root = self.base / "translated"
        novel_root = translated_root / "test-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次.", encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(translated_root)
            mock_config.target_language = "vi"
            save_glossary("test-novel", {"魔法": "ma thuật"})
            update_glossary_term("test-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

            result = apply_pending_replacements("test-novel", write=True)

            assert result["changed_files"] == 0
            assert result["replacements"] == []
            assert load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY] == []

    def test_apply_skips_untranslated_chapters_without_missing_output_issue(self):
        translated_root = self.base / "translated"
        novel_root = translated_root / "test-novel"
        (novel_root / "input").mkdir(parents=True)
        (novel_root / "output").mkdir(parents=True)
        (novel_root / "input" / "chapter_1.txt").write_text("魔法再次.", encoding="utf-8")
        (novel_root / "input" / "chapter_2.txt").write_text("魔法继续.", encoding="utf-8")
        output_path = novel_root / "output" / "chapter_001.txt"
        output_path.write_text("Ma thuật.", encoding="utf-8")

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = str(translated_root)
            mock_config.target_language = "vi"
            save_glossary("test-novel", {"魔法": "ma thuật"})
            update_glossary_term("test-novel", "魔法", "魔法", "ma pháp", is_user_edit=True)

            result = apply_pending_replacements("test-novel", write=True)

            assert result["changed_files"] == 1
            assert [report["chapter"] for report in result["replacements"]] == [1]
            assert {report["status"] for report in result["replacements"]} == {"safe"}
            assert output_path.read_text(encoding="utf-8") == "Ma pháp."
            assert load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY] == []

    def test_dismiss_pending_replacements(self):
        self.temp_dir_extra = tempfile.TemporaryDirectory()
        patcher_glossary_dir = patch("src.services.glossary.repository.GLOSSARY_DIR", Path(self.temp_dir_extra.name))
        patcher_glossary_dir.start()

        with patch("src.services.glossary.repository.config") as mock_config:
            mock_config.translated_dir = ""
            mock_config.target_language = "vi"

            save_glossary("test-novel", {"李白": "Lý Bạch"})
            save_glossary("test-novel", {"李白": "Lý Bạch Mới"}, is_user_edit=True)
            assert load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY] != []

            dismiss_pending_replacements("test-novel")
            assert load_glossary_data("test-novel")[PENDING_REPLACEMENTS_KEY] == []

        patcher_glossary_dir.stop()
        self.temp_dir_extra.cleanup()
