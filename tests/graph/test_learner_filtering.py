"""Tests for learner node kinship/role filtering and relationship normalization."""

from src.graph.nodes.learner import (
    _build_existing_chars_str,
    _is_english,
    _is_kinship_or_role,
    _normalize_relationship,
    _prepare_address_rule_candidate_verdicts,
    _sample_across_text,
    _sample_aligned_chunks,
)


class TestIsKinshipOrRole:
    def test_english_kinship_terms(self):
        assert _is_kinship_or_role("papa") is True
        assert _is_kinship_or_role("mama") is True
        assert _is_kinship_or_role("father") is True
        assert _is_kinship_or_role("mother") is True
        assert _is_kinship_or_role("brother") is True
        assert _is_kinship_or_role("sister") is True

    def test_chinese_kinship_terms(self):
        assert _is_kinship_or_role("爸爸") is True
        assert _is_kinship_or_role("妈妈") is True
        assert _is_kinship_or_role("父亲") is True
        assert _is_kinship_or_role("母亲") is True
        assert _is_kinship_or_role("哥哥") is True
        assert _is_kinship_or_role("姐姐") is True

    def test_korean_kinship_terms(self):
        assert _is_kinship_or_role("아빠") is True
        assert _is_kinship_or_role("엄마") is True
        assert _is_kinship_or_role("아버지") is True
        assert _is_kinship_or_role("어머니") is True

    def test_japanese_kinship_terms(self):
        assert _is_kinship_or_role("お父さん") is True
        assert _is_kinship_or_role("お母さん") is True
        assert _is_kinship_or_role("パパ") is True
        assert _is_kinship_or_role("ママ") is True

    def test_role_descriptors(self):
        assert _is_kinship_or_role("teacher") is True
        assert _is_kinship_or_role("student") is True
        assert _is_kinship_or_role("guard") is True
        assert _is_kinship_or_role("医生") is True
        assert _is_kinship_or_role("선생님") is True

    def test_proper_names_not_kinship(self):
        assert _is_kinship_or_role("陆远秋") is False
        assert _is_kinship_or_role("白清夏") is False
        assert _is_kinship_or_role("John") is False
        assert _is_kinship_or_role("Min-su") is False

    def test_case_insensitive(self):
        assert _is_kinship_or_role("Papa") is True
        assert _is_kinship_or_role("MAMA") is True
        assert _is_kinship_or_role("  Father  ") is True


class TestIsEnglish:
    def test_ascii_text(self):
        assert _is_english("friend") is True
        assert _is_english("mother") is True
        assert _is_english("romantic interest") is True

    def test_non_ascii_text(self):
        assert _is_english("mẹ") is False
        assert _is_english("Bạn") is False
        assert _is_english("朋友") is False
        assert _is_english("친구") is False


class TestNormalizeRelationship:
    def test_allowed_types_unchanged(self):
        assert _normalize_relationship("friend") == "friend"
        assert _normalize_relationship("mother") == "mother"
        assert _normalize_relationship("romantic interest") == "romantic interest"
        assert _normalize_relationship("classmate") == "classmate"

    def test_vietnamese_to_english(self):
        assert _normalize_relationship("mẹ") == "mother"
        assert _normalize_relationship("bố") == "father"
        assert _normalize_relationship("vợ") == "wife"
        assert _normalize_relationship("chồng") == "husband"
        assert _normalize_relationship("bạn") == "friend"
        assert _normalize_relationship("kẻ thù") == "enemy"

    def test_chinese_to_english(self):
        assert _normalize_relationship("母亲") == "mother"
        assert _normalize_relationship("爸爸") == "father"
        assert _normalize_relationship("朋友") == "friend"
        assert _normalize_relationship("敌人") == "enemy"
        assert _normalize_relationship("老师") == "teacher"

    def test_korean_to_english(self):
        assert _normalize_relationship("어머니") == "mother"
        assert _normalize_relationship("아빠") == "father"
        assert _normalize_relationship("친구") == "friend"

    def test_japanese_to_english(self):
        assert _normalize_relationship("お母さん") == "mother"
        assert _normalize_relationship("父") == "father"
        assert _normalize_relationship("友達") == "friend"

    def test_unknown_english_term_preserved(self):
        assert _normalize_relationship("acquaintance") == "acquaintance"
        assert _normalize_relationship("mentor") == "mentor"

    def test_case_normalization(self):
        assert _normalize_relationship("Friend") == "friend"
        assert _normalize_relationship("MOTHER") == "mother"


def test_sample_across_text_covers_beginning_middle_and_end():
    text = "A" * 4000 + "MIDDLE" + "B" * 4000 + "ENDING"

    sample = _sample_across_text(text, max_chars=300)

    assert sample.startswith("A")
    assert "MIDDLE" in sample
    assert sample.endswith("ENDING")
    assert len(sample) <= 300


def test_sample_aligned_chunks_uses_matching_beginning_middle_and_end_pairs():
    source_chunks = [f"source-{index}" for index in range(5)]
    translated_chunks = [f"translated-{index}" for index in range(5)]

    sample = _sample_aligned_chunks(source_chunks, translated_chunks, "chinese", "Vietnamese")

    assert "source-0" in sample and "translated-0" in sample
    assert "source-2" in sample and "translated-2" in sample
    assert "source-4" in sample and "translated-4" in sample
    assert "source-1" not in sample and "translated-1" not in sample


def test_existing_character_context_labels_pending_address_hypotheses():
    entities = {
        "李明": {"translated_name": "Lý Minh"},
        "张伟": {"translated_name": "Trương Vĩ"},
    }
    rules = [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cô"}]
    candidates = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "observations": 1,
            "reason": "relationship_change",
        }
    ]

    result = _build_existing_chars_str(entities, [], rules, candidates)

    assert '李明->张伟: self="tôi", other="cô"' in result
    assert "Pending address hypotheses (re-evaluate from source only):" in result
    assert '李明->张伟: self="anh", other="em", observations=1' in result
    assert 'reason="relationship_change"' in result


def test_candidate_verdicts_accept_translated_names_and_default_omissions_to_inconclusive():
    entities = {
        "许韵": {"translated_name": "Hứa Vận"},
        "温渝": {"translated_name": "Ôn Du"},
    }
    candidates = [
        {"speaker": "许韵", "listener": "温渝"},
        {"speaker": "温渝", "listener": "许韵"},
    ]

    result = _prepare_address_rule_candidate_verdicts(
        [{"speaker": "Hứa Vận", "listener": "Ôn Du", "verdict": "CONFIRMED"}],
        candidates,
        entities,
    )

    assert result == [
        {"speaker": "许韵", "listener": "温渝", "verdict": "confirmed"},
        {"speaker": "温渝", "listener": "许韵", "verdict": "inconclusive"},
    ]
