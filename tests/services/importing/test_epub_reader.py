import zipfile

from src.services.importing.reader import read_epub_book


def test_reader_parses_epub_without_writing_outside_input(tmp_path) -> None:
    epub_path = tmp_path / "book.epub"
    container_xml = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OPS/content.opf"/></rootfiles>
</container>"""
    content_opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Demo Book</dc:title><dc:creator>Author</dc:creator>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>"""
    with zipfile.ZipFile(epub_path, "w") as epub:
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OPS/content.opf", content_opf)
        epub.writestr("OPS/chapter.xhtml", "<html><body><h1>Chapter 1</h1><p>Body.</p></body></html>")
    files_before = set(tmp_path.rglob("*"))

    book = read_epub_book(epub_path)

    assert book.metadata.title == "Demo Book"
    assert book.metadata.author == "Author"
    assert [(section.title, section.text) for section in book.sections] == [("Chapter 1", "Chapter 1\n\nBody.")]
    assert set(tmp_path.rglob("*")) == files_before
