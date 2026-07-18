"""Pure EPUB archive construction."""

from __future__ import annotations

import html
import uuid
import zipfile
from pathlib import Path

from src.domain.illustrations import parse_illustration_marker
from src.domain.language import normalize_target_language
from src.services.packaging.images import ResolvedImage, image_media_type


def package_file_stem(novel_name: str, target_language: str) -> str:
    """Return the target-specific EPUB file stem."""
    return f"{novel_name}.{normalize_target_language(target_language)}"


class EPUBBuilder:
    """Construct an EPUB from already-resolved content and image inputs."""

    def __init__(
        self,
        title: str,
        author: str = "AI Translator",
        language: str = "vi",
        cover_image: Path | None = None,
        illustrations: dict[str, ResolvedImage] | None = None,
    ) -> None:
        self.title = title
        self.author = author
        self.language = language
        self.chapters: list[dict[str, str]] = []
        self.book_id = f"urn:uuid:{uuid.uuid4()}"
        self.cover_image = cover_image
        self.available_illustrations = illustrations or {}
        self.illustrations: dict[str, ResolvedImage] = {}

    def add_chapter(self, title: str, paragraphs: list[str]) -> None:
        chapter_id = f"chapter_{len(self.chapters) + 1}"
        content_html = f"<h1>{html.escape(title)}</h1>\n"
        for paragraph in paragraphs:
            illustration_name = parse_illustration_marker(paragraph)
            illustration = self.available_illustrations.get(illustration_name or "")
            if illustration_name and illustration is not None:
                self.illustrations[illustration_name] = illustration
                content_html += (
                    f'<div class="illustration"><img src="images/{html.escape(illustration_name)}" alt="Illustration"/></div>\n'
                )
                continue
            content_html += f"<p>{html.escape(paragraph)}</p>\n"
        self.chapters.append({"id": chapter_id, "title": title, "content_html": content_html})

    def write(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
            archive.writestr("META-INF/container.xml", container_xml)

            style_css = """body {
  font-family: "DejaVu Serif", serif;
  margin: 5%;
  line-height: 1.6;
}
h1 {
  text-align: center;
  margin-top: 1em;
  margin-bottom: 2em;
}
p {
  margin-bottom: 0.8em;
  text-align: justify;
}
.illustration {
  margin: 1.2em 0;
  text-align: center;
}
.illustration img {
  max-width: 100%;
  height: auto;
}"""
            archive.writestr("OEBPS/style.css", style_css)

            if self.cover_image and self.cover_image.exists():
                suffix = self.cover_image.suffix.lower()
                cover_filename = f"cover{suffix}"
                archive.write(str(self.cover_image), f"OEBPS/{cover_filename}")

                cover_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{self.language}">
<head>
  <title>Cover</title>
  <style type="text/css">
    body {{ margin: 0; padding: 0; text-align: center; }}
    img {{ max-width: 100%; max-height: 100%; }}
  </style>
</head>
<body>
  <div>
    <img src="{cover_filename}" alt="Cover"/>
  </div>
</body>
</html>"""
                archive.writestr("OEBPS/cover.xhtml", cover_xhtml)

            for illustration in self.illustrations.values():
                archive.write(str(illustration.path), f"OEBPS/images/{illustration.filename}")

            for chapter in self.chapters:
                chapter_html = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{self.language}">
<head>
  <title>{html.escape(chapter["title"])}</title>
  <link rel="stylesheet" href="style.css" type="text/css"/>
</head>
<body>
  {chapter["content_html"]}
</body>
</html>"""
                archive.writestr(f"OEBPS/{chapter['id']}.xhtml", chapter_html)

            archive.writestr("OEBPS/toc.ncx", self._build_toc_ncx())
            archive.writestr("OEBPS/content.opf", self._build_content_opf())

    def _build_toc_ncx(self) -> str:
        nav_points = []
        for index, chapter in enumerate(self.chapters, 1):
            nav_points.append(f"""    <navPoint id="{chapter["id"]}" playOrder="{index}">
      <navLabel>
        <text>{html.escape(chapter["title"])}</text>
      </navLabel>
      <content src="{chapter["id"]}.xhtml"/>
    </navPoint>""")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.safaribooksonline.com/codex/1.2/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{self.book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle>
    <text>{html.escape(self.title)}</text>
  </docTitle>
  <navMap>
{"\n".join(nav_points)}
  </navMap>
</ncx>"""

    def _build_content_opf(self) -> str:
        manifest_items = [
            '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            '    <item id="style" href="style.css" media-type="text/css"/>',
        ]
        spine_items = []
        cover_meta = ""

        if self.cover_image and self.cover_image.exists():
            suffix = self.cover_image.suffix.lower()
            cover_filename = f"cover{suffix}"
            manifest_items.append(
                f'    <item id="cover-image" href="{cover_filename}" media-type="{image_media_type(self.cover_image)}"/>'
            )
            manifest_items.append('    <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
            spine_items.append('    <itemref idref="cover"/>')
            cover_meta = '\n    <meta name="cover" content="cover-image"/>'

        for chapter in self.chapters:
            manifest_items.append(
                f'    <item id="{chapter["id"]}" href="{chapter["id"]}.xhtml" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'    <itemref idref="{chapter["id"]}"/>')

        for index, illustration in enumerate(self.illustrations.values(), start=1):
            manifest_items.append(
                f'    <item id="illustration-{index}" href="images/{html.escape(illustration.filename)}" '
                f'media-type="{illustration.media_type}"/>'
            )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="BookId">{self.book_id}</dc:identifier>
    <dc:title>{html.escape(self.title)}</dc:title>
    <dc:creator opf:role="aut">{html.escape(self.author)}</dc:creator>
    <dc:language>{self.language}</dc:language>{cover_meta}
  </metadata>
  <manifest>
{"\n".join(manifest_items)}
  </manifest>
  <spine toc="ncx">
{"\n".join(spine_items)}
  </spine>
</package>"""


__all__ = ["EPUBBuilder", "package_file_stem"]
