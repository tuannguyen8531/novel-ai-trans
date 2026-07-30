from unittest.mock import patch

from src.graph.nodes.chunker import chunker_node
from src.models.state import initial_state


def test_chunker_keeps_overlap_out_of_translatable_chunks():
    source = "Đoạn một đủ dài abcdef.\n\nĐoạn hai đủ dài ghijkl.\n\nĐoạn ba đủ dài mnopqr."
    state = initial_state(source, "chinese", "novel", 1)

    with patch("src.graph.nodes.chunker.config") as config:
        config.chunk_size = 30
        config.chunk_overlap = 10
        config.chunk_mode = "chars"

        result = chunker_node(state)

    assert len(result["chunks"]) == 3
    assert "\n\n".join(result["chunks"]) == source
