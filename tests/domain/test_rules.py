from pathlib import Path

import pytest

from src.domain.rules import select_relevant_rules


def test_select_relevant_rules_keeps_only_mappings_used_in_source():
    markdown = """# Rules

## Terms
- 修炼 → tu luyện
- 丹药 → đan dược

## Style
- Preserve a concise narrative rhythm"""

    result = select_relevant_rules(markdown, "他开始修炼。")

    assert "修炼 → tu luyện" in result
    assert "丹药 → đan dược" not in result
    assert "Preserve a concise narrative rhythm" in result


def test_select_relevant_rules_handles_alternatives_and_romanization_notes():
    markdown = """- ~さん (san) → anh / chị
- S급 / A급 -> S-rank / A-rank
- ~야/아 (ya/a) → call name directly"""

    result = select_relevant_rules(markdown, "田中さん은 A급 헌터다. 민준아!")

    assert "~さん (san) → anh / chị" in result
    assert "S급 / A급 -> S-rank / A-rank" in result
    assert "~야/아 (ya/a) → call name directly" in result


def test_select_relevant_rules_keeps_general_rules_that_contain_examples():
    markdown = "- Translate names naturally (e.g., 李明 → Lý Minh)"

    result = select_relevant_rules(markdown, "张三走了。")

    assert result == markdown


def test_select_relevant_rules_keeps_everything_without_source_text():
    markdown = "- 修炼 → tu luyện"

    assert select_relevant_rules(markdown, "") == markdown


@pytest.mark.parametrize(
    ("target_language", "source_language", "genre", "expected_rule"),
    [
        ("vi", "chinese", "xianxia", "修炼 → tu luyện"),
        ("vi", "chinese", "fantasy", "魔法 → ma pháp"),
        ("vi", "chinese", "urban", "总裁 → tổng giám đốc"),
        ("vi", "korean", "hunter", "헌터 → Hunter"),
        ("vi", "korean", "fantasy", "마법 → ma pháp"),
        ("vi", "korean", "academy", "아카데미 → học viện"),
        ("vi", "japanese", "isekai", "異世界 → dị giới"),
        ("vi", "japanese", "fantasy", "魔法 → ma pháp"),
        ("en", "chinese", "xianxia", "修炼 -> cultivate"),
        ("en", "chinese", "fantasy", "魔法 -> magic"),
        ("en", "chinese", "urban", "总裁 -> CEO"),
        ("en", "korean", "hunter", "헌터 -> Hunter"),
        ("en", "korean", "fantasy", "마법 -> magic"),
        ("en", "korean", "academy", "아카데미 -> academy"),
        ("en", "japanese", "isekai", "異世界 -> another world"),
        ("en", "japanese", "fantasy", "魔法 -> magic"),
    ],
)
def test_genre_rule_files_keep_moved_language_mappings(
    target_language,
    source_language,
    genre,
    expected_rule,
):
    content = Path(f"rules/{target_language}/{source_language}/{genre}.md").read_text(encoding="utf-8")

    assert expected_rule in content


@pytest.mark.parametrize(
    ("target_language", "source_language", "expected_genres"),
    [
        ("vi", "chinese", {"fantasy", "school-life", "urban", "wuxia", "xianxia"}),
        ("vi", "korean", {"academy", "fantasy", "hunter", "murim", "school-life"}),
        ("vi", "japanese", {"fantasy", "isekai", "school-life"}),
        ("en", "chinese", {"fantasy", "school-life", "urban", "wuxia", "xianxia"}),
        ("en", "korean", {"academy", "fantasy", "hunter", "murim", "school-life"}),
        ("en", "japanese", {"fantasy", "isekai", "school-life"}),
    ],
)
def test_genre_rule_files_are_namespaced_by_source_language(
    target_language,
    source_language,
    expected_genres,
):
    genre_dir = Path(f"rules/{target_language}/{source_language}")

    assert {path.stem for path in genre_dir.glob("*.md")} == expected_genres


def test_every_genre_rule_file_contains_style_guidance():
    genre_files = [
        path
        for target_language in ("vi", "en")
        for source_language in ("chinese", "korean", "japanese")
        for path in Path(f"rules/{target_language}/{source_language}").glob("*.md")
    ]

    assert genre_files
    for path in genre_files:
        content = path.read_text(encoding="utf-8")
        assert "## Style" in content, path
        assert content.split("## Style", maxsplit=1)[1].strip().startswith("- "), path


@pytest.mark.parametrize(
    ("target_language", "source_language"),
    [
        (target_language, source_language)
        for target_language in ("vi", "en")
        for source_language in ("chinese", "korean", "japanese")
    ],
)
def test_every_language_base_contains_narrative_style(target_language, source_language):
    content = Path(f"rules/{target_language}/{source_language}.md").read_text(encoding="utf-8")

    assert "## Narrative Style" in content


@pytest.mark.parametrize("target_language", ["vi", "en"])
def test_common_rules_preserve_emotional_relationship_style(target_language):
    content = Path(f"rules/{target_language}/common.md").read_text(encoding="utf-8")

    assert "preserve subtext, intimacy changes, hesitation, romantic banter" in content
    assert "without making feelings more explicit" in content


@pytest.mark.parametrize("target_language", ["vi", "en"])
def test_chinese_urban_owns_contemporary_style(target_language):
    base = Path(f"rules/{target_language}/chinese.md").read_text(encoding="utf-8")
    urban = Path(f"rules/{target_language}/chinese/urban.md").read_text(encoding="utf-8")

    assert "## Contemporary Settings" not in base
    assert "Preserve differences between narration, speech, messages, posts, livestreams" in urban


@pytest.mark.parametrize(
    ("target_language", "source_language", "expected_rule"),
    [
        ("en", "korean", "재벌 -> chaebol"),
        ("vi", "korean", "Preserve short paragraphs, rapid scene transitions"),
        ("en", "korean", "Preserve short paragraphs, rapid scene transitions"),
        ("vi", "japanese", "Preserve first-person internal monologue"),
        ("en", "japanese", "Preserve first-person internal monologue"),
    ],
)
def test_non_genre_rules_are_merged_into_language_base(
    target_language,
    source_language,
    expected_rule,
):
    content = Path(f"rules/{target_language}/{source_language}.md").read_text(encoding="utf-8")

    assert expected_rule in content


@pytest.mark.parametrize(
    ("target_language", "source_language", "expected_rule"),
    [
        ("vi", "chinese", "凯尔 → Kyle"),
        ("vi", "korean", "카일 → Kyle"),
        ("vi", "japanese", "カイル → Kyle"),
        ("en", "chinese", "凯尔 -> Kyle"),
        ("en", "korean", "카일 -> Kyle"),
        ("en", "japanese", "カイル -> Kyle"),
    ],
)
def test_language_naming_policy_handles_western_derived_names(
    target_language,
    source_language,
    expected_rule,
):
    content = Path(f"rules/{target_language}/{source_language}.md").read_text(encoding="utf-8")

    assert expected_rule in content


@pytest.mark.parametrize(("target_language", "arrow"), [("vi", "→"), ("en", "->")])
def test_isekai_keeps_only_otherworld_specific_terms(target_language, arrow):
    fantasy = Path(f"rules/{target_language}/japanese/fantasy.md").read_text(encoding="utf-8")
    isekai = Path(f"rules/{target_language}/japanese/isekai.md").read_text(encoding="utf-8")

    assert f"魔法 {arrow}" in fantasy
    assert f"魔法 {arrow}" not in isekai
    assert f"転生 {arrow}" in isekai


@pytest.mark.parametrize(
    ("target_language", "source_language", "expected_style"),
    [
        ("vi", "chinese", "face or status dynamics"),
        ("vi", "korean", "comic shifts in 존댓말, 반말"),
        ("vi", "japanese", "boke/tsukkomi roles"),
        ("en", "chinese", "face or status dynamics"),
        ("en", "korean", "comic shifts in 존댓말, 반말"),
        ("en", "japanese", "boke/tsukkomi roles"),
    ],
)
def test_language_base_keeps_minimal_source_specific_humor(
    target_language,
    source_language,
    expected_style,
):
    content = Path(f"rules/{target_language}/{source_language}.md").read_text(encoding="utf-8")

    assert expected_style in content


@pytest.mark.parametrize(
    ("target_language", "source_language", "genre_heading"),
    [
        ("vi", "chinese", "Xianxia / Xuanhuan Terms"),
        ("vi", "korean", "Regression / Hunter Genre Terms"),
        ("vi", "japanese", "Isekai / Light Novel Terms"),
        ("en", "chinese", "Xianxia / Xuanhuan Terms"),
        ("en", "korean", "Regression / Hunter Genre Terms"),
        ("en", "japanese", "Isekai / Light Novel Terms"),
    ],
)
def test_language_rule_files_no_longer_embed_genre_sections(target_language, source_language, genre_heading):
    content = Path(f"rules/{target_language}/{source_language}.md").read_text(encoding="utf-8")

    assert genre_heading not in content
