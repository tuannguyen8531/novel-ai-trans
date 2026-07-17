from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from src.application.crawl.importer import ImportRequest
from src.application.crawl.importer import import_epub as run_import
from src.utils.files import write_text_atomic


def import_epub(
    epub_path: Path,
    share_root: Path,
    *,
    name: str | None = None,
    keep_existing: bool = False,
    source_url: str | None = None,
):
    return run_import(
        ImportRequest(
            epub_path=epub_path,
            name=name,
            keep_existing=keep_existing,
            source_url=source_url,
        ),
        share_root,
    )


class EpubImporterTest(unittest.TestCase):
    def test_import_writes_shared_input_and_metadata_with_name_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "demo.epub"
            write_epub(
                epub_path,
                title="Demo EPUB Title",
                author="Demo Author",
                sections=[
                    ("chapter-1.xhtml", "Chapter 1: Start", "Hello world."),
                    ("chapter-2.xhtml", "Chapter 2: Next", "Second chapter."),
                ],
            )

            result = import_epub(epub_path, root / "translated", name="Military Training")
            novel_dir = root / "translated" / "military-training"
            chapter_dir = novel_dir / "input"
            metadata = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))
            chapter_one = (chapter_dir / "chapter_001.txt").read_text(encoding="utf-8")

        self.assertEqual(result.output_dir, str(novel_dir))
        self.assertEqual(result.chapter_output_dir, str(chapter_dir))
        self.assertEqual(len(result.chapters), 2)
        self.assertEqual(
            metadata,
            {
                "title": "Demo EPUB Title",
                "localized": {},
                "localization_meta": {},
                "author": "Demo Author",
                "source_url": epub_path.resolve().as_uri(),
                "illustration_url": None,
                "summary": None,
                "site_name": "military-training",
                "source_language": None,
            },
        )
        self.assertIn("Chapter 1: Start", chapter_one)
        self.assertIn("Hello world.", chapter_one)

    def test_import_with_custom_source_url(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "demo.epub"
            write_epub(
                epub_path,
                title="Demo EPUB Title",
                author="Demo Author",
                sections=[
                    ("chapter-1.xhtml", "Chapter 1: Start", "Hello world."),
                ],
            )

            import_epub(
                epub_path,
                root / "translated",
                name="Military Training",
                source_url="epub://my-custom-file.epub",
            )
            novel_dir = root / "translated" / "military-training"
            metadata = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["source_url"], "epub://my-custom-file.epub")

    def test_import_preserves_explicit_empty_source_url(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "demo.epub"
            write_epub(
                epub_path,
                title="Demo",
                author=None,
                sections=[("chapter-1.xhtml", "Chapter 1", "Body.")],
            )

            import_epub(epub_path, root / "translated", source_url="")
            metadata = json.loads((root / "translated" / "demo" / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["source_url"], "")

    def test_import_reads_summary_from_epub_description(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "described.epub"
            write_epub(
                epub_path,
                title="Demo",
                author=None,
                description="<p>First summary paragraph.</p><p>Second summary paragraph.</p>",
                sections=[("chapter-1.xhtml", "Chapter 1", "Chapter body.")],
            )

            import_epub(epub_path, root / "translated")
            metadata = json.loads((root / "translated" / "described" / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["summary"], "First summary paragraph.\n\nSecond summary paragraph.")

    def test_import_falls_back_to_clearly_labelled_summary_section(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "front-matter.epub"
            write_epub(
                epub_path,
                title="Demo",
                author=None,
                sections=[
                    ("synopsis.xhtml", "Synopsis", "The original novel synopsis."),
                    ("chapter-1.xhtml", "Chapter 1", "Chapter body."),
                ],
            )

            result = import_epub(epub_path, root / "translated")
            metadata = json.loads((root / "translated" / "front-matter" / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["summary"], "The original novel synopsis.")
        self.assertEqual(len(result.chapters), 1)
        self.assertEqual(result.chapters[0].title, "Chapter 1")

    def test_import_extracts_summary_from_combined_metadata_page(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "metadata-page.epub"
            write_epub(
                epub_path,
                title="Demo",
                author=None,
                sections=[
                    (
                        "info.xhtml",
                        "Demo",
                        "Author: Example\nTags: Romance\nStatus: Complete\nSynopsis\nThe synopsis from the metadata page.",
                    ),
                    ("chapter-1.xhtml", "Chapter 1", "Chapter body."),
                ],
            )

            result = import_epub(epub_path, root / "translated")
            metadata = json.loads((root / "translated" / "metadata-page" / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["summary"], "The synopsis from the metadata page.")
        self.assertEqual(len(result.chapters), 1)

    def test_reimport_fills_missing_summary_without_overwriting_existing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "demo.epub"
            write_epub(
                epub_path,
                title="Demo",
                author=None,
                description="Summary from EPUB.",
                sections=[("chapter-1.xhtml", "Chapter 1", "Chapter body.")],
            )
            novel_dir = root / "translated" / "demo"
            novel_dir.mkdir(parents=True)
            metadata_path = novel_dir / "metadata.json"
            metadata_path.write_text(json.dumps({"title": "Existing", "summary": None}), encoding="utf-8")

            import_epub(epub_path, root / "translated", name="demo")
            filled = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata_path.write_text(json.dumps({**filled, "summary": "Manual summary"}), encoding="utf-8")
            import_epub(epub_path, root / "translated", name="demo")
            preserved = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(filled["summary"], "Summary from EPUB.")
        self.assertEqual(preserved["summary"], "Manual summary")

    def test_import_defaults_output_slug_to_filename_not_epub_title(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "downloaded-book.epub"
            write_epub(
                epub_path,
                title="Completely Different EPUB Title",
                author=None,
                sections=[("chapter-1.xhtml", "Chapter 1: Start", "Hello world.")],
            )

            result = import_epub(epub_path, root / "translated")

        self.assertEqual(result.output_dir, str(root / "translated" / "downloaded-book"))
        self.assertEqual(result.metadata.title, "Completely Different EPUB Title")

    def test_reimport_preserves_existing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "updated.epub"
            write_epub(
                epub_path,
                title="Updated EPUB Title",
                author="Updated EPUB Author",
                sections=[("chapter-2.xhtml", "Chapter 2: Next", "New chapter.")],
            )
            novel_dir = root / "translated" / "existing-novel"
            novel_dir.mkdir(parents=True)
            existing_metadata = {
                "title": "Existing Title",
                "localized": {
                    "en": {"title": "Existing English Title"},
                    "vi": {"title": "Tiêu đề hiện tại"},
                },
                "localization_meta": {},
                "author": "Existing Author",
                "source_url": "https://example.com/original",
                "illustration_url": "https://example.com/cover.jpg",
                "site_name": "existing-novel",
                "source_language": "korean",
                "custom_field": "keep me",
            }
            (novel_dir / "metadata.json").write_text(
                json.dumps(existing_metadata, ensure_ascii=False),
                encoding="utf-8",
            )

            import_epub(
                epub_path,
                root / "translated",
                name="existing-novel",
                keep_existing=True,
            )
            metadata = json.loads((novel_dir / "metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata, existing_metadata)

    def test_reimport_reports_retained_unchanged_overwritten_and_added_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            initial_epub = root / "initial.epub"
            updated_epub = root / "updated.epub"
            write_epub(
                initial_epub,
                title="Demo",
                author=None,
                sections=[
                    ("chapter-1.xhtml", "Chapter 1: Retained", "Only in the old import."),
                    ("chapter-2.xhtml", "Chapter 2: Same", "Unchanged content."),
                    ("chapter-3.xhtml", "Chapter 3: Old", "Old content."),
                ],
            )
            write_epub(
                updated_epub,
                title="Demo",
                author=None,
                sections=[
                    ("chapter-2.xhtml", "Chapter 2: Same", "Unchanged content."),
                    ("chapter-3.xhtml", "Chapter 3: Revised", "Revised content."),
                    ("chapter-4.xhtml", "Chapter 4: Added", "New content."),
                ],
            )
            import_epub(initial_epub, root / "translated", name="demo")

            with patch("src.services.importing.storage.write_text_atomic", wraps=write_text_atomic) as write_text:
                result = import_epub(
                    updated_epub,
                    root / "translated",
                    name="demo",
                    keep_existing=True,
                )

            written_chapters = {call.args[0].name for call in write_text.call_args_list}

        self.assertEqual(result.retained_chapters, (1,))
        self.assertEqual(result.unchanged_chapters, (2,))
        self.assertEqual([(change.number, change.title) for change in result.overwritten_chapters], [(3, "Chapter 3: Revised")])
        self.assertEqual(result.added_chapters, (4,))
        self.assertEqual(result.removed_chapters, ())
        self.assertEqual(written_chapters, {"chapter_003.txt", "chapter_004.txt"})

    def test_import_writes_illustrations_with_order_and_chapter_number(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "illustrated.epub"
            write_epub(
                epub_path,
                title="Illustrated",
                author=None,
                sections=[
                    ("Text/chapter-1.xhtml", "Chapter 1: Start", "Hello world."),
                    ("Text/chapter-2.xhtml", "Chapter 2: Next", "Second chapter."),
                ],
                section_images={
                    "Text/chapter-1.xhtml": ["../Images/first.jpg"],
                    "Text/chapter-2.xhtml": ["../Images/second.png", "../Images/third.webp"],
                },
                image_files={
                    "OPS/Images/first.jpg": b"first-image",
                    "OPS/Images/second.png": b"second-image",
                    "OPS/Images/third.webp": b"third-image",
                },
            )

            result = import_epub(epub_path, root / "translated", name="Illustrated")
            illustrations_dir = root / "translated" / "illustrated" / "illustrations"
            first_image = (illustrations_dir / "001-001.jpg").read_bytes()
            second_image = (illustrations_dir / "002-001.png").read_bytes()
            chapter_one = (root / "translated" / "illustrated" / "input" / "chapter_001.txt").read_text(encoding="utf-8")
            chapter_two = (root / "translated" / "illustrated" / "input" / "chapter_002.txt").read_text(encoding="utf-8")

        self.assertEqual(
            [Path(illustration.path).name for illustration in result.illustrations],
            [
                "001-001.jpg",
                "002-001.png",
                "002-002.webp",
            ],
        )
        self.assertEqual(
            [illustration.chapter_number for illustration in result.illustrations],
            [1, 2, 2],
        )
        self.assertEqual(first_image, b"first-image")
        self.assertEqual(second_image, b"second-image")
        self.assertIn("Hello world.\n\n[[ILLUSTRATION:001-001.jpg]]", chapter_one)
        self.assertIn(
            "Second chapter.\n\n[[ILLUSTRATION:002-001.png]]\n\n[[ILLUSTRATION:002-002.webp]]",
            chapter_two,
        )

    def test_import_falls_back_to_name_and_cleans_existing_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            epub_path = root / "untitled.epub"
            write_epub(
                epub_path,
                title=None,
                author=None,
                sections=[
                    ("intro.xhtml", "Unnumbered opening", "Story text."),
                ],
            )
            stale_path = root / "translated" / "manual-name" / "input" / "chapter_99.txt"
            stale_path.parent.mkdir(parents=True)
            stale_path.write_text("stale", encoding="utf-8")

            result = import_epub(epub_path, root / "translated", name="Manual Name")
            metadata = json.loads((root / "translated" / "manual-name" / "metadata.json").read_text(encoding="utf-8"))

            self.assertEqual(result.metadata.title, "Manual Name")
            self.assertEqual(metadata["title"], "Manual Name")
            self.assertEqual(result.removed_chapters, (99,))
            self.assertFalse(stale_path.exists())
            self.assertTrue((stale_path.parent / "chapter_001.txt").is_file())


def write_epub(
    path: Path,
    *,
    title: str | None,
    author: str | None,
    description: str | None = None,
    sections: list[tuple[str, str, str]],
    section_images: dict[str, list[str]] | None = None,
    image_files: dict[str, bytes] | None = None,
) -> None:
    section_images = section_images or {}
    image_files = image_files or {}
    metadata = []
    if title is not None:
        metadata.append(f"<dc:title>{escape(title)}</dc:title>")
    if author is not None:
        metadata.append(f"<dc:creator>{escape(author)}</dc:creator>")
    if description is not None:
        metadata.append(f"<dc:description>{escape(description)}</dc:description>")

    manifest = []
    spine = []
    for index, (href, _section_title, _text) in enumerate(sections, start=1):
        item_id = f"section-{index}"
        manifest.append(f'<item id="{item_id}" href="{escape(href)}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{item_id}"/>')

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    {"".join(metadata)}
  </metadata>
  <manifest>
    {"".join(manifest)}
  </manifest>
  <spine>
    {"".join(spine)}
  </spine>
</package>
"""
    container_xml = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    with zipfile.ZipFile(path, "w") as epub:
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OPS/content.opf", content_opf)
        for href, section_title, text in sections:
            image_markup = "".join(f'<img src="{escape(image_ref)}" alt=""/>' for image_ref in section_images.get(href, []))
            epub.writestr(
                f"OPS/{href}",
                (
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<html xmlns="http://www.w3.org/1999/xhtml">'
                    f"<body><h1>{escape(section_title)}</h1><p>{escape(text)}</p>"
                    f"{image_markup}</body>"
                    "</html>"
                ),
            )
        for image_path, image_data in image_files.items():
            epub.writestr(image_path, image_data)


if __name__ == "__main__":
    unittest.main()
