from src.domain.quality import has_blocking_issues, post_check_translation


def test_post_check_accepts_normal_translation():
    issues = post_check_translation("他说：“你好。”", "Anh ấy nói: “Xin chào.”", {})
    assert issues == []


def test_post_check_flags_empty_translation_as_blocking():
    issues = post_check_translation("source", "  ", {})
    assert [issue.code for issue in issues] == ["translation_empty"]
    assert has_blocking_issues(issues)


def test_post_check_flags_code_fence_as_blocking():
    issues = post_check_translation("source", "```text\nbản dịch\n```", {})
    assert "contains_code_fence" in [issue.code for issue in issues]
    assert has_blocking_issues(issues)


def test_post_check_flags_leftover_source_chars_as_blocking():
    issues = post_check_translation("张三走了", "张三走了 rồi.", {})
    assert "contains_source_language_chars" in [issue.code for issue in issues]
    assert has_blocking_issues(issues)


def test_post_check_warns_for_one_or_two_leftover_source_chars():
    for untranslated in ("囡", "囡囡"):
        issues = post_check_translation("囡囡来了", f"Cô bé {untranslated} đến rồi.", {})

        issue = next(issue for issue in issues if issue.code == "contains_source_language_chars")
        assert issue.severity == "warning"
        assert not has_blocking_issues(issues)


def test_post_check_gives_actionable_unique_source_fragments():
    issues = post_check_translation("囡囡来了", "N囡囡 đến rồi. Cứ nghe lời 囡囡!", {})

    issue = next(issue for issue in issues if issue.code == "contains_source_language_chars")
    assert "Translate or transliterate every occurrence" in issue.message
    assert "source fragments: 囡囡." in issue.message
    assert "including in notes or parentheses" in issue.message


def test_post_check_accepts_explained_terminology():
    issues = post_check_translation("ひきこもり", "Anh ấy là hikikomori (ひきこもり).", {})
    assert "contains_source_language_chars" not in [issue.code for issue in issues]

    issues = post_check_translation("李明", "Lý Minh 「李明」 đi học.", {})
    assert "contains_source_language_chars" not in [issue.code for issue in issues]

    issues = post_check_translation("ひきこもり", "Anh ấy là ひきこもり (hikikomori).", {})
    assert "contains_source_language_chars" in [issue.code for issue in issues]
    assert has_blocking_issues(issues)


def test_post_check_warns_for_missing_glossary_term():
    issues = post_check_translation("李明走了", "Anh ấy rời đi.", {"李明": "Lý Minh"})
    assert [issue.code for issue in issues] == ["missing_glossary_term"]
    assert not has_blocking_issues(issues)


def test_post_check_requires_illustration_markers_to_be_preserved():
    source = "Before.\n\n[[ILLUSTRATION:001-001.jpg]]\n\nAfter."
    issues = post_check_translation(source, "Trước.\n\nSau.", {})

    assert "illustration_marker_mismatch" in [issue.code for issue in issues]
    assert has_blocking_issues(issues)
