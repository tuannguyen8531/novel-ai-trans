from src.graph.nodes.title import title_node
from src.models.state import initial_state


def test_title_node_removes_heading_and_resolves_hanzi_series_suffix() -> None:
    catalog = {
        203: "第203章 暴雨夜的苏雨晴！",
        204: "第204章 暴雨夜的苏雨晴！（二）",
        205: "第205章 暴雨夜的苏雨晴！（三）",
    }
    state = initial_state(
        "第204章 暴雨夜的苏雨晴！（二）\n\n正文",
        "chinese",
        "novel",
        204,
        title_catalog=catalog,
    )

    result = title_node(state)

    assert result["source_text"] == "正文"
    assert result["source_title"] == "暴雨夜的苏雨晴!(二)"
    assert result["source_title_base"] == "暴雨夜的苏雨晴!"
    assert result["source_title_part"] == 2
    assert result["source_title_series"] is True


def test_title_node_leaves_unconfirmed_parenthetical_in_title() -> None:
    state = initial_state(
        "第204章 暴雨夜的苏雨晴！（二）\n\n正文",
        "chinese",
        "novel",
        204,
    )

    result = title_node(state)

    assert result["source_text"] == "正文"
    assert result["source_title_base"] == "暴雨夜的苏雨晴!(二)"
    assert result["source_title_part"] is None
    assert result["source_title_series"] is False


def test_title_node_marks_numbered_heading_without_title() -> None:
    state = initial_state("第7章\n\n正文", "chinese", "novel", 7, title_catalog={7: "第7章"})

    result = title_node(state)

    assert result["source_heading_present"] is True
    assert result["source_title"] == ""
    assert result["source_text"] == "正文"
