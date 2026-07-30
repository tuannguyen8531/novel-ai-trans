"""Tests for learner node term filtering."""

from src.domain.terms import MIN_TERM_FREQUENCY, count_occurrences, filter_extracted_terms, filter_terms_by_frequency


class TestCountOccurrences:
    def test_basic_match(self):
        assert count_occurrences("李白 李白 李白", "李白") == 3

    def test_case_insensitive(self):
        assert count_occurrences("hello Hello HELLO", "hello") == 3

    def test_no_match(self):
        assert count_occurrences("foo bar baz", "xyz") == 0

    def test_empty_term(self):
        assert count_occurrences("some text", "") == 0

    def test_single_char_term(self):
        assert count_occurrences("a b a c a", "a") == 0  # min length 2

    def test_overlapping(self):
        assert count_occurrences("aaaa", "aa") == 2  # non-overlapping regex


class TestFilterByFrequency:
    def test_keeps_frequent_terms(self):
        text = "张三 张三 张三 李四 李四"
        terms = {"张三": "Trương Tam", "李四": "Lý Tứ"}
        result = filter_terms_by_frequency(text, terms, min_count=3)
        assert result == {"张三": "Trương Tam"}

    def test_removes_rare_terms(self):
        text = "张三 张三 张三 王五"
        terms = {"张三": "Trương Tam", "王五": "Vương Ngũ"}
        result = filter_terms_by_frequency(text, terms, min_count=3)
        assert "王五" not in result

    def test_empty_terms(self):
        result = filter_terms_by_frequency("text text text", {}, min_count=3)
        assert result == {}

    def test_default_min_frequency(self):
        text = "term " * 3 + "rare " * 1
        terms = {"term": "thuật ngữ", "rare": "hiếm"}
        result = filter_terms_by_frequency(text, terms, MIN_TERM_FREQUENCY)
        assert "term" in result
        assert "rare" not in result

    def test_keeps_llm_extracted_terms_when_present_below_frequency_threshold(self):
        text = "天赋“卷王的恩赐 (异常/诅咒)”从宿主灵魂中移除。【天赋：卷王的恩赐 (异常/诅咒) 已激活。】"
        terms = {"卷王的恩赐": "Ân tứ của Cuộn Vương"}

        result = filter_extracted_terms(text, terms)

        assert result == {"卷王的恩赐": "Ân tứ của Cuộn Vương"}

    def test_drops_llm_extracted_terms_absent_from_source_text(self):
        result = filter_extracted_terms("这里只有真实术语", {"不存在术语": "thuật ngữ ảo"})
        assert result == {}

    def test_drops_llm_extracted_terms_with_source_chars_in_translation(self):
        text = "창궁무애검법을 펼쳤다."
        terms = {"창궁무애검법": "Thương Cung Vô 애 Kiếm Pháp"}

        result = filter_extracted_terms(text, terms)

        assert result == {}

    def test_keeps_term_translation_grounded_in_translated_text(self):
        result = filter_extracted_terms(
            "他加入了玄天宗。",
            {"玄天宗": "Huyền Thiên Tông"},
            translated_text="Cậu gia nhập Huyền Thiên Tông.",
        )

        assert result == {"玄天宗": "Huyền Thiên Tông"}

    def test_drops_term_translation_absent_from_translated_text(self):
        result = filter_extracted_terms(
            "他加入了玄天宗。",
            {"玄天宗": "Thiên Đạo Tông"},
            translated_text="Cậu gia nhập Huyền Thiên Tông.",
        )

        assert result == {}

    def test_drops_existing_term_instead_of_overwriting_it(self):
        result = filter_extracted_terms(
            "他加入了玄天宗。",
            {"玄天宗": "Thiên Đạo Tông"},
            translated_text="Cậu gia nhập Thiên Đạo Tông.",
            existing_terms={"玄天宗": "Huyền Thiên Tông"},
        )

        assert result == {}
