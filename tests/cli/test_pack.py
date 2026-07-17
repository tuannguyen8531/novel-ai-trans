from types import SimpleNamespace
from unittest.mock import patch

from src.cli.pack import package_file_stem


def test_package_file_stem_preserves_cli_default_target() -> None:
    config = SimpleNamespace(target_language="vi")

    with patch("src.cli.pack.get_config", return_value=config):
        assert package_file_stem("my-novel") == "my-novel.vi"
    assert package_file_stem("my-novel", "en") == "my-novel.en"
