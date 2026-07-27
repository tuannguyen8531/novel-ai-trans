"""Tests for prompt template engine."""

import pytest

from src.prompts import render_prompt


class TestRenderPrompt:
    def test_render_simple_template(self):
        result = render_prompt("detect")
        assert "language detector" in result
        assert "chinese" in result
        assert "korean" in result
        assert "japanese" in result

    def test_render_with_variables(self):
        result = render_prompt("translate", target_language="vi", lang_name="Chinese", target_name="Vietnamese")
        assert "Chinese" in result
        assert "Vietnamese" in result
        assert "{{lang_name}}" not in result
        assert result == result.strip()

    def test_render_with_multiple_variables(self):
        result = render_prompt(
            "learn",
            target_language="vi",
            translation_rules="- Dịch toàn bộ tên nhân vật sang Hán Việt",
            existing_terms_str="term1 → dịch 1",
            existing_chars_str="Entities:\n  李明 (Lý Minh)",
            chapter_number="12",
        )
        assert "Dịch toàn bộ tên nhân vật sang Hán Việt" in result
        assert "term1 → dịch 1" in result
        assert "李明 (Lý Minh)" in result
        assert '"since": 12' in result
        assert "{{translation_rules}}" not in result
        assert "{{existing_terms_str}}" not in result
        assert "{{existing_chars_str}}" not in result
        assert "{{chapter_number}}" not in result

    def test_render_missing_template_raises(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            render_prompt("nonexistent")

    def test_render_unknown_variable_left_untouched(self):
        result = render_prompt("translate", target_language="vi", lang_name="Chinese", target_name="Vietnamese")
        assert "{{unknown_var}}" not in result

    def test_render_reviewer_template(self):
        result = render_prompt("review", target_language="vi")
        assert "completeness" in result
        assert "naturalness" in result
        assert "consistency" in result
        assert "accuracy" in result

    def test_render_summarize_template(self):
        result = render_prompt("summarize", target_language="vi")
        assert "summary" in result.lower()
        assert "50 words" in result

    def test_render_target_specific_template(self):
        result = render_prompt("translate", target_language="en", lang_name="Chinese", target_name="English")
        assert "Chinese to English" in result
        assert "English translation" in result

    def test_vietnamese_translation_formats_source_chapter_heading(self):
        result = render_prompt("translate", target_language="vi", lang_name="Chinese", target_name="Vietnamese")

        assert "always translate it; never omit it or copy it unchanged" in result
        assert "Chương N: <tiêu đề chương đã dịch>" in result
        assert "preserve the source number" in result
        assert 'without adding "Chương" or inventing a number' in result

    def test_english_translation_formats_source_chapter_heading(self):
        result = render_prompt("translate", target_language="en", lang_name="Chinese", target_name="English")

        assert "always translate it; never omit it or copy it unchanged" in result
        assert "Chapter N: <translated chapter title>" in result
        assert "preserve the source number" in result
        assert 'without adding "Chapter" or inventing a number' in result

    @pytest.mark.parametrize(("target_language", "target_name"), [("vi", "Vietnamese"), ("en", "English")])
    def test_translate_uses_address_rules_as_source_overridable_defaults(self, target_language, target_name):
        result = render_prompt(
            "translate",
            target_language=target_language,
            lang_name="Chinese",
            target_name=target_name,
        )

        assert "Address rules are persistent defaults, not absolute constraints" in result
        assert "use the newly supported address style immediately" in result
        assert "preserve it only in the supported lines or scene" in result
        assert "Never generalize a temporary form" in result
        assert "An unconfirmed hypothesis is a provisional continuity hint" in result
        assert 'For a "relationship_change" hypothesis, prefer the candidate' in result
        assert 'For a "default" hypothesis, use the candidate only' in result
        assert "address rules exactly when provided" not in result

    @pytest.mark.parametrize("target_language", ["vi", "en"])
    def test_learner_requires_source_grounding_for_address_changes(self, target_language):
        result = render_prompt(
            "learn",
            target_language=target_language,
            translation_rules="(none)",
            existing_terms_str="(none)",
            existing_chars_str="(none)",
            chapter_number="12",
        )

        assert "Determine persistence primarily from source events" in result
        assert "do not treat them as proof that the existing rule is still stable" in result
        assert "Treat an existing address rule as a prior default" in result
        assert "only when the source supports it independently" in result
        assert "translation may help with target wording but not with persistence" in result
        assert "neither the hypothesis nor the resulting translated" in result
        assert "Return exactly one address_rule_candidate_verdict" in result
        assert "another chapter that continues the same relationship" in result
        assert "Exact source equivalents" in result
        assert 'Use "inconclusive" only when this chapter has no relevant interaction' in result
        assert '"verdict": "confirmed | temporary | rejected | inconclusive"' in result
