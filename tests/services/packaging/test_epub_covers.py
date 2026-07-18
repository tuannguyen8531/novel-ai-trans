from unittest.mock import MagicMock, patch

from src.services.packaging.covers import cleanup_cover_image, resolve_cover_image


def test_resolve_cover_rejects_local_absolute_path(tmp_path) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"\xff\xd8")

    assert resolve_cover_image({"illustration_url": str(cover)}, tmp_path) is None


def test_resolve_cover_relative_to_novel_root_and_illustrations(tmp_path) -> None:
    root_cover = tmp_path / "cover.jpg"
    root_cover.write_bytes(b"root")
    illustrations_dir = tmp_path / "illustrations"
    illustrations_dir.mkdir()
    illustration_cover = illustrations_dir / "cover.png"
    illustration_cover.write_bytes(b"nested")

    assert resolve_cover_image({"illustration_url": "cover.jpg"}, tmp_path) == root_cover
    assert resolve_cover_image({"illustration_url": "cover.png"}, tmp_path) == illustration_cover
    assert resolve_cover_image({"illustration_url": "illustrations/cover.png"}, tmp_path) == illustration_cover


def test_resolve_cover_rejects_noncanonical_local_names(tmp_path) -> None:
    illustrations_dir = tmp_path / "illustrations"
    illustrations_dir.mkdir()
    for filename in ("poster.png", "cover.txt", "images/cover.png"):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-a-cover")
        assert resolve_cover_image({"illustration_url": filename}, tmp_path) is None


def test_resolve_cover_rejects_path_traversal(tmp_path) -> None:
    novel_root = tmp_path / "novel"
    novel_root.mkdir()
    outside_cover = tmp_path / "outside.jpg"
    outside_cover.write_bytes(b"outside")

    assert resolve_cover_image({"illustration_url": "../outside.jpg"}, novel_root) is None


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


def test_cleanup_preserves_local_novel_cover_in_temporary_tree(tmp_path) -> None:
    cover = tmp_path / "novel_cover_local.jpg"
    cover.write_bytes(b"local-cover")

    cleanup_cover_image(cover, novel_root=tmp_path)

    assert cover.exists()
