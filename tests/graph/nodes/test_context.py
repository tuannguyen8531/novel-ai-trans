from unittest.mock import patch

from src.graph.nodes.context import context_node
from src.models.state import initial_state


def test_context_loads_target_specific_rules():
    state = initial_state(
        source_text="张三走了",
        source_language="chinese",
        target_language="en",
        novel_name="novel",
        chapter_number=1,
    )

    with (
        patch("src.graph.nodes.context.load_glossary", return_value={}),
        patch("src.graph.nodes.context.get_active_context_with_candidates", return_value=({}, [], [], [])),
    ):
        result = context_node(state)

    assert "# Common Translation Rules (All Languages -> English)" in result["translation_rules"]
    assert "# Chinese -> English" in result["translation_rules"]
    assert "All Languages → Vietnamese" not in result["translation_rules"]


def test_context_loads_vietnamese_rules_from_vi_folder():
    state = initial_state(
        source_text="张三走了",
        source_language="chinese",
        target_language="vi",
        novel_name="novel",
        chapter_number=1,
    )

    with (
        patch("src.graph.nodes.context.load_glossary", return_value={}),
        patch("src.graph.nodes.context.get_active_context_with_candidates", return_value=({}, [], [], [])),
    ):
        result = context_node(state)

    assert "# Common Translation Rules (All Languages → Vietnamese)" in result["translation_rules"]
    assert "# Chinese → Vietnamese" in result["translation_rules"]
    assert "identify the speaker and listener" in result["translation_rules"]
    assert "use RTAS only as a qualitative fallback" in result["translation_rules"]
    assert "not by a relationship label alone" in result["translation_rules"]
    assert "follow any provided address rules exactly" not in result["translation_rules"]


def test_context_keeps_only_language_term_mappings_used_in_chapter():
    state = initial_state(
        source_text="他开始修炼。",
        source_language="chinese",
        target_language="vi",
        novel_name="novel",
        chapter_number=1,
    )

    with (
        patch("src.graph.nodes.context.load_glossary", return_value={}),
        patch("src.graph.nodes.context.get_active_context_with_candidates", return_value=({}, [], [], [])),
    ):
        result = context_node(state)

    assert "修炼 → tu luyện" in result["translation_rules"]
    assert "丹药 → đan dược" not in result["translation_rules"]
    assert "Translate character names to Hán Việt when appropriate" in result["translation_rules"]


def test_context_filters_glossary_terms_to_source_text():
    state = initial_state(
        source_text="玄天宗 đệ tử rời núi.",
        source_language="chinese",
        target_language="vi",
        novel_name="novel",
        chapter_number=1,
    )

    with (
        patch(
            "src.graph.nodes.context.load_glossary",
            return_value={
                "玄天宗": "Huyền Thiên Tông",
                "归墟": "Quy Khư",
            },
        ),
        patch("src.graph.nodes.context.get_active_context_with_candidates", return_value=({}, [], [], [])),
    ):
        result = context_node(state)

    assert result["glossary"] == {"玄天宗": "Huyền Thiên Tông"}


def test_context_exposes_pending_address_hypotheses_separately():
    state = initial_state(
        source_text="李明和张伟说话。",
        source_language="chinese",
        target_language="vi",
        novel_name="novel",
        chapter_number=11,
    )
    entities = {"李明": {"translated_name": "Lý Minh"}, "张伟": {"translated_name": "Trương Vĩ"}}
    rules = [{"speaker": "李明", "listener": "张伟", "self": "tôi", "other": "cô", "since": 1}]
    candidates = [
        {
            "speaker": "李明",
            "listener": "张伟",
            "self": "anh",
            "other": "em",
            "first_seen": 10,
            "last_seen": 10,
            "observations": 1,
            "scope": "stable",
            "reason": "relationship_change",
        }
    ]

    with (
        patch("src.graph.nodes.context.load_glossary", return_value={}),
        patch(
            "src.graph.nodes.context.get_active_context_with_candidates",
            return_value=(entities, [], rules, candidates),
        ),
    ):
        result = context_node(state)

    assert result["characters"]["address_rules"] == rules
    assert result["characters"]["address_rule_candidates"] == candidates
