"""LLM prompt definitions for crawler config generation."""

NOVEL_INFO = """\
You are an expert at reading novel information pages. Given the HTML of a \
novel's main information/detail page and its URL, extract the canonical novel \
metadata and the URL of its table of contents.

Return **only** a JSON object (no markdown fences) with these keys:

{
  "title": "<the novel's exact original title>",
  "author": "<the author's name, or null>",
  "illustration_url": "<cover/illustration image URL, or null>",
  "summary": "<the novel synopsis/description, preserving its original language, or null>",
  "toc_url": "<URL of the full chapter list/table of contents>"
}

Rules:
- Use the novel itself, not site slogans, SEO suffixes, breadcrumbs, latest \
  chapter labels, translator names, or uploaders.
- Prefer the main cover over avatars, logos, banners, ads, and chapter images.
- The summary must describe the novel; do not invent or translate text.
- The TOC URL must lead to the complete chapter list when such a link exists. \
  It may be relative to the supplied page URL.
- Image URLs may also be relative to the supplied page URL.
- Output pure JSON only — no commentary or markdown.\
"""

TOC = """\
You are an expert web scraper assistant.  Given the **cleaned HTML** of a \
novel's Table-of-Contents page and its URL, identify the correct CSS selectors.

Return **only** a JSON object (no markdown fences) with these keys:

{
  "chapter_link_selector": "<CSS selector that matches ALL chapter <a> links>",
  "toc_next_selector": "<CSS selector for the 'next page' link if TOC is paginated, or null>",
  "toc_expand_selector": "<Playwright selector for a 'show all chapters' control, or null>"
}

Rules:
- Prefer **id** selectors (e.g. ``#catalog``) or **specific class** chains \
(e.g. ``#catalog ul li a``) over bare tag names or generic classes like \
``.main-content``.
- ``chapter_link_selector`` must match <a> elements whose ``href`` points to \
individual chapter pages. It should NOT match unrelated links (home, profile, \
ads).
- ``toc_expand_selector`` is only for pages that hide most chapters behind a \
button/link such as "show all chapters" or "full chapter list". Prefer a \
Playwright text selector such as ``text=查看完整章节目录`` when no stable \
id/class exists.
- If you cannot determine a selector, set its value to ``null``.
- Output **pure JSON only** — no commentary, no markdown.

Example for a typical Chinese novel site:
{
  "chapter_link_selector": "#catalog ul li a",
  "toc_next_selector": null,
  "toc_expand_selector": null
}\
"""

CHAPTER = """\
You are an expert web scraper assistant.  Given the **cleaned HTML** of a \
single chapter page and its URL, identify CSS selectors for extracting the \
chapter content.

Return **only** a JSON object (no markdown fences) with these keys:

{
  "chapter_title_selector": "<CSS selector for the chapter title, or null>",
  "chapter_content_selector": "<CSS selector for the main reading content>",
  "remove_selectors": ["<list of CSS selectors for elements to remove>"]
}

Rules:
- ``chapter_content_selector`` is the **single smallest container** holding \
the story text. Avoid ``body`` or ``.main-content`` if a more specific inner \
container exists (e.g. ``.txtnav`` or ``#ChapterBody``).
- ``chapter_title_selector`` targets the chapter heading (often ``<h1>``). If \
that heading sits **inside** the content container, you MUST also include the \
title selector in ``remove_selectors`` so it does not appear twice in the \
extracted text.
- ``remove_selectors`` must always include ``"script"`` and ``"style"``. Also \
add: ads (``.ad``, ``.ads``, ``.contentadv``), navigation links (``.page1``, \
``.next-chapter``, ``#txtright``), share buttons, author/info blocks \
(``.txtinfo``, ``.readinline``), and any other non-story elements inside the \
content container.
- Prefer selectors using **id** or **class**.
- Output **pure JSON only** — no commentary or markdown.

Example for a typical Chinese novel site:
{
  "chapter_title_selector": ".txtnav h1",
  "chapter_content_selector": ".txtnav",
  "remove_selectors": [
    "script",
    "style",
    ".txtnav h1",
    ".txtinfo",
    "#txtright",
    ".contentadv",
    ".bottom-ad",
    ".page1",
    ".readinline"
  ]
}\
"""

RETRY_TOC = """\
Your previous selectors did not match any elements in the provided HTML.

Please look again at the cleaned HTML and return corrected selectors.
Pay special attention to:
- The list of chapter links — what ``id`` or ``class`` wraps the <ul> or <ol> of links?
- Hidden TOCs — if the HTML has a "show all chapters" control, return it as ``toc_expand_selector``.

Return **only** the JSON object, no markdown.\
"""

RETRY_CHAPTER = """\
Your previous selectors did not match any elements in the provided HTML.

Please look again at the cleaned HTML and return corrected selectors.
Pay special attention to:
- The smallest container that holds **only** the story text.
- If the chapter title is inside that container, include its selector in ``remove_selectors``.
- Remove ads, navigation, share buttons, and any non-story markup.

Return **only** the JSON object, no markdown.\
"""

__all__ = ["CHAPTER", "NOVEL_INFO", "RETRY_CHAPTER", "RETRY_TOC", "TOC"]
