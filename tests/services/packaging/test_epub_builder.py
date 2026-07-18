import zipfile

from src.services.packaging.builder import EPUBBuilder, package_file_stem
from src.services.packaging.images import resolve_chapter_images


def test_package_file_stem_includes_target_language() -> None:
    assert package_file_stem("my-novel", "vi") == "my-novel.vi"
    assert package_file_stem("my-novel", "en") == "my-novel.en"


def test_epub_builder_embeds_resolved_illustration_at_marker_position(tmp_path) -> None:
    illustrations_dir = tmp_path / "illustrations"
    illustrations_dir.mkdir()
    illustration = illustrations_dir / "001-001.jpg"
    illustration.write_bytes(b"image-data")
    output = tmp_path / "book.epub"
    chapters = [("Chapter 1", ["Before.", "[[ILLUSTRATION:001-001.jpg]]", "After."])]
    images = resolve_chapter_images(illustrations_dir, chapters)

    builder = EPUBBuilder("Book", illustrations=images)
    for title, paragraphs in chapters:
        builder.add_chapter(title, paragraphs)
    builder.write(output)

    with zipfile.ZipFile(output) as epub:
        chapter = epub.read("OEBPS/chapter_1.xhtml").decode("utf-8")
        manifest = epub.read("OEBPS/content.opf").decode("utf-8")
        embedded = epub.read("OEBPS/images/001-001.jpg")

    assert chapter.index("Before.") < chapter.index("images/001-001.jpg") < chapter.index("After.")
    assert 'href="images/001-001.jpg" media-type="image/jpeg"' in manifest
    assert embedded == b"image-data"


def test_epub_builder_uses_cover_media_type_from_file_suffix(tmp_path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"png-data")
    output = tmp_path / "book.epub"

    EPUBBuilder("Book", cover_image=cover).write(output)

    with zipfile.ZipFile(output) as epub:
        manifest = epub.read("OEBPS/content.opf").decode("utf-8")
    assert 'href="cover.png" media-type="image/png"' in manifest
