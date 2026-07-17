from unittest.mock import MagicMock, patch

from src.services.packaging.covers import cleanup_cover_image, resolve_cover_image


def test_resolve_cover_local_absolute_path(tmp_path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"\xff\xd8")

    assert resolve_cover_image({"illustration_url": str(cover)}) == cover


def test_resolve_cover_relative_to_novel_root_and_illustrations(tmp_path) -> None:
    root_cover = tmp_path / "root.jpg"
    root_cover.write_bytes(b"root")
    illustrations_dir = tmp_path / "illustrations"
    illustrations_dir.mkdir()
    illustration_cover = illustrations_dir / "nested.jpg"
    illustration_cover.write_bytes(b"nested")

    assert resolve_cover_image({"illustration_url": "root.jpg"}, tmp_path) == root_cover
    assert resolve_cover_image({"illustration_url": "nested.jpg"}, tmp_path) == illustration_cover


def test_resolve_cover_preserves_missing_and_empty_behavior() -> None:
    assert resolve_cover_image({"illustration_url": "/nonexistent/cover.jpg"}) is None
    assert resolve_cover_image({}) is None
    assert resolve_cover_image({"illustration_url": ""}) is None


def test_remote_cover_acquisition_and_cleanup_are_independent_of_builder() -> None:
    response = MagicMock()
    response.headers = {"Content-Type": "image/png"}
    response.read.return_value = b"remote-cover"
    response.__enter__.return_value = response

    with patch("src.services.packaging.covers.urlopen", return_value=response):
        cover = resolve_cover_image({"illustration_url": "https://example.com/cover"})

    assert cover is not None
    assert cover.suffix == ".png"
    assert cover.read_bytes() == b"remote-cover"

    cleanup_cover_image(cover)
    assert not cover.exists()
