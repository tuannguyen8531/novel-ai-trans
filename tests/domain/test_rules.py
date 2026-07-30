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
