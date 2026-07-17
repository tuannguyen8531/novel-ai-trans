from src.services.packaging.images import image_media_type, resolve_chapter_images, resolve_illustration


def test_resolve_illustration_rejects_traversal_and_missing_files(tmp_path) -> None:
    illustration = tmp_path / "001-001.jpg"
    illustration.write_bytes(b"image")

    assert resolve_illustration(tmp_path, illustration.name) == illustration
    assert resolve_illustration(tmp_path, "../001-001.jpg") is None
    assert resolve_illustration(tmp_path, "missing.jpg") is None


def test_image_media_type_preserves_known_and_unknown_types(tmp_path) -> None:
    assert image_media_type(tmp_path / "image.JPEG") == "image/jpeg"
    assert image_media_type(tmp_path / "image.webp") == "image/webp"
    assert image_media_type(tmp_path / "image.bin") == "application/octet-stream"


def test_resolve_chapter_images_preserves_marker_order(tmp_path) -> None:
    for filename in ("002.png", "001.jpg"):
        (tmp_path / filename).write_bytes(filename.encode())
    chapters = [
        ("One", ["Before", "[[ILLUSTRATION:002.png]]"]),
        ("Two", ["[[ILLUSTRATION:001.jpg]]", "[[ILLUSTRATION:002.png]]"]),
    ]

    resolved = resolve_chapter_images(tmp_path, chapters)

    assert list(resolved) == ["002.png", "001.jpg"]
    assert resolved["002.png"].media_type == "image/png"
