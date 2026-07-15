"""AI-assisted site config generator.

Given a novel information URL, extracts canonical metadata and the TOC URL,
then analyses the TOC and a sample chapter. The result is a validated
``SiteConfig`` ready to write to disk.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from src.config import DEFAULT_USER_AGENT, SiteConfig
from src.paths import CONFIG_DIR, DEFAULT_TRANSLATED_ROOT
from src.services.http import FetchResponse, HttpClient
from src.services.llm.base import BaseProvider
from src.utils.html import clean_html_for_analysis
from src.utils.logging import get_logger


class Fetcher(Protocol):
    """Minimal interface shared by HttpClient and BrowserFetcher."""

    def fetch(self, url: str) -> FetchResponse: ...


class _HtmlCache:
    """Simple file-based cache for raw HTML responses.

    Automatically invalidates entries that look like error or challenge pages.
    """

    def __init__(self, cache_dir: Path, *, enabled: bool = True) -> None:
        self._dir = cache_dir
        self._enabled = enabled
        if enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16] + ".html"

    def get(self, url: str) -> str | None:
        if not self._enabled:
            return None
        path = self._dir / self._key(url)
        if not path.is_file():
            return None
        html = path.read_text(encoding="utf-8")
        if self._is_bad(html):
            print(f"   ⚠  Cached HTML looks bad — invalidating cache for {url}")
            self.invalidate(url)
            return None
        return html

    def set(self, url: str, html: str) -> None:
        if not self._enabled:
            return
        path = self._dir / self._key(url)
        path.write_text(html, encoding="utf-8")

    def invalidate(self, url: str) -> None:
        if not self._enabled:
            return
        path = self._dir / self._key(url)
        if path.exists():
            path.unlink()

    @staticmethod
    def _is_bad(html: str) -> bool:
        """Detect if cached HTML is useless (error, challenge, or empty)."""
        if not html or len(html.strip()) < 200:
            return True
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string or "").lower() if soup.title else ""
        body_text = soup.get_text(" ", strip=True)[:300].lower()

        bad_signals = (
            "just a moment",
            "checking your browser",
            "ddos protection",
            "attention required",
            "cloudflare",
            "404",
            "not found",
            "error",
            "access denied",
            "forbidden",
        )
        return any(sig in title for sig in bad_signals) or any(sig in body_text for sig in bad_signals)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_NOVEL_INFO = """\
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

_SYSTEM_TOC = """\
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

_SYSTEM_CHAPTER = """\
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
- Output **pure JSON only** — no commentary, no markdown.

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

_RETRY_TOC = """\
Your previous selectors did not match any elements in the provided HTML.

Please look again at the cleaned HTML and return corrected selectors.
Pay special attention to:
- The list of chapter links — what ``id`` or ``class`` wraps the <ul> or <ol> of links?
- Hidden TOCs — if the HTML has a "show all chapters" control, return it as ``toc_expand_selector``.

Return **only** the JSON object, no markdown.\
"""

_RETRY_CHAPTER = """\
Your previous selectors did not match any elements in the provided HTML.

Please look again at the cleaned HTML and return corrected selectors.
Pay special attention to:
- The smallest container that holds **only** the story text.
- If the chapter title is inside that container, include its selector in ``remove_selectors``.
- Remove ads, navigation, share buttons, and any non-story markup.

Return **only** the JSON object, no markdown.\
"""


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ConfigGenerator:
    """AI config generator with selector validation and retry."""

    def __init__(
        self,
        llm: BaseProvider,
        *,
        use_browser: bool = False,
        headed: bool = False,
        user_agent: str = DEFAULT_USER_AGENT,
        samples_dir: Path | None = None,
    ) -> None:
        self._llm = llm
        self._use_browser = use_browser or headed
        self._headed = headed
        self._user_agent = user_agent
        self._samples_dir = samples_dir

    # -- public API ---------------------------------------------------------

    def generate(
        self,
        source_url: str,
        *,
        name: str | None = None,
        translated_root: Path | None = None,
        samples_dir: Path | None = None,
        cache_dir: Path | None = None,
        use_cache: bool = True,
        use_samples: bool = True,
    ) -> dict[str, Any]:
        """Extract novel info, analyse its TOC/chapter pages, and return a config.

        When ``use_samples`` is true, matching bundled samples and known-domain
        configs may replace selector-analysis LLM calls. Novel metadata and the
        TOC URL are always extracted from the supplied source page first.
        Disabling samples forces live HTML selector analysis. Returns the raw
        dict (not yet a SiteConfig) so the caller can review it before saving.
        """
        translated_root = translated_root or DEFAULT_TRANSLATED_ROOT
        effective_samples_dir = samples_dir or self._samples_dir or CONFIG_DIR
        cache = _HtmlCache(
            cache_dir or Path("runtime/crawler") / ".gen-cache",
            enabled=use_cache,
        )

        with self._open_fetcher() as fetcher:
            # Phase 1: canonical metadata and TOC discovery from the novel page.
            source_html = self._fetch_or_cache(fetcher, cache, source_url, "Novel info")
            if source_html is None:
                raise RuntimeError(f"Failed to fetch novel information page: {source_url}")
            source_clean = self._clean_novel_page_for_analysis(source_html)
            novel_info = self._ask_llm(
                system=_SYSTEM_NOVEL_INFO,
                user=f"Page URL: {source_url}\n\nHTML:\n{source_clean}",
                call_type="gen_novel_info",
            )
            novel_info = self._normalise_novel_info(novel_info, source_url)
            toc_url = novel_info["toc_url"]
            domain = urlparse(toc_url).netloc

            if use_samples:
                sample = self._load_sample(domain, effective_samples_dir)
                if sample is not None:
                    print(f"✅ Using bundled sample template for domain {domain}.")
                    result = json.loads(json.dumps(sample))
                    for key in ("novel_title_selector", "author_selector", "illustration_selector"):
                        result.pop(key, None)
                    result["name"] = name or self._derive_name(source_url)
                    result["toc_url"] = toc_url
                    return self._add_novel_info(result, source_url, novel_info)

            known = self._load_known_domain_config(domain, translated_root) if use_samples else None

            # Phase 2: TOC and sample chapter selector analysis.
            toc_html = self._fetch_or_cache(fetcher, cache, toc_url, "TOC")
            if toc_html is None:
                raise RuntimeError(f"Failed to fetch TOC page: {toc_url}")

            # Detect 404 / error pages and retry with trailing slash.
            if self._is_error_page(toc_html) and not toc_url.endswith("/"):
                alt_url = toc_url.rstrip("/") + "/"
                print(f"⚠  Page looks like a 404 — retrying with: {alt_url}")
                alt_html = self._fetch_or_cache(fetcher, cache, alt_url, "TOC")
                if alt_html is not None and not self._is_error_page(alt_html):
                    toc_html = alt_html
                    toc_url = alt_url
                else:
                    get_logger().warning("Still a 404 — proceeding with original page.")

            toc_soup = BeautifulSoup(toc_html, "html.parser")
            toc_clean = clean_html_for_analysis(toc_html)

            # Try known-domain selectors first; fall back to LLM.
            toc_result = self._try_known_selectors(known, toc_soup, "toc", toc_clean, _SYSTEM_TOC, _RETRY_TOC)

            # Discover a sample chapter URL from the TOC result.
            chapter_url = self._find_first_chapter(toc_soup, toc_url, toc_result.get("chapter_link_selector", ""))

            chapter_result: dict[str, Any] = {}
            if chapter_url:
                # Analyse the sample chapter with automatic browser fallback.
                ch_html, ch_soup = self._fetch_chapter_with_fallback(fetcher, chapter_url, cache)
                if ch_soup is not None:
                    ch_clean = clean_html_for_analysis(ch_html)
                    chapter_result = self._try_known_selectors(
                        known, ch_soup, "chapter", ch_clean, _SYSTEM_CHAPTER, _RETRY_CHAPTER
                    )
                else:
                    get_logger().warning("Could not fetch chapter content even with browser — skipping Phase 2.")
            else:
                get_logger().warning("Could not find a chapter link — skipping Phase 2.")

        # Merge results
        site_name = name or self._derive_name(source_url)
        config_dict = self._build_config(
            toc_url,
            site_name,
            toc_result,
            chapter_result,
            source_url=source_url,
            novel_info=novel_info,
        )
        return config_dict

    def _try_known_selectors(
        self,
        known: dict[str, Any] | None,
        soup: BeautifulSoup,
        phase: str,
        clean_html: str,
        system_prompt: str,
        retry_prompt: str,
    ) -> dict[str, Any]:
        """Use known-domain selectors if they validate, else ask the LLM."""
        if known:
            result = (
                {
                    "chapter_link_selector": known.get("chapter_link_selector"),
                    "toc_next_selector": known.get("toc_next_selector"),
                    "toc_expand_selector": known.get("toc_expand_selector"),
                }
                if phase == "toc"
                else {
                    "chapter_title_selector": known.get("chapter_title_selector"),
                    "chapter_content_selector": known.get("chapter_content_selector"),
                    "remove_selectors": list(known.get("remove_selectors", [])),
                }
            )
            issues = self._validate_selectors(result, soup, f"gen_config_{phase}")
            if not issues:
                print(f"✅ Reusing known {phase} selectors for this domain.")
                return result
            print(f"⚠  Known {phase} selectors stale ({', '.join(issues)}) — falling back to LLM.")

        return self._ask_llm_with_retry(
            system=system_prompt,
            user=f"HTML:\n{clean_html}",
            call_type=f"gen_config_{phase}",
            soup=soup,
            retry_system=retry_prompt,
        )

    @staticmethod
    def validate(config_dict: dict[str, Any]) -> SiteConfig:
        """Validate a config dict by constructing a SiteConfig."""
        return SiteConfig.from_dict(config_dict)

    @staticmethod
    def save(config_dict: dict[str, Any], translated_root: Path) -> Path:
        """Write a novel-owned config JSON and return its path."""
        name = str(config_dict.get("name", "generated"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name) or name in {".", ".."}:
            raise ValueError(f"Invalid novel slug: {name!r}")
        path = translated_root / name / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(config_dict, ensure_ascii=False, indent=2) + "\n"
        path.write_text(content, encoding="utf-8")
        return path

    # -- private helpers ----------------------------------------------------

    @contextmanager
    def _open_fetcher(self) -> Generator[Fetcher]:
        """Yield a fetcher, using context manager for BrowserFetcher."""
        if self._use_browser:
            from src.services.browser import BrowserFetcher

            if self._headed:
                # Headed mode uses the host's real Chrome identity and a
                # longer challenge window; persistent profile is left to
                # the caller (the crawler wires one for repeat runs).
                with BrowserFetcher(
                    user_agent=None,
                    headless=False,
                    challenge_timeout_seconds=120.0,
                ) as fetcher:
                    yield fetcher
            else:
                with BrowserFetcher(
                    user_agent=self._user_agent,
                    timeout_seconds=30,
                    delay_seconds=1.0,
                ) as fetcher:
                    yield fetcher
        else:
            yield HttpClient(
                user_agent=self._user_agent,
                timeout_seconds=30,
                delay_seconds=1.5,
                respect_robots=False,
            )

    def _fetch_or_cache(
        self,
        fetcher: Fetcher,
        cache: _HtmlCache,
        url: str,
        label: str,
    ) -> str | None:
        """Return cached HTML if present, else fetch and cache."""
        cached = cache.get(url)
        if cached is not None:
            print(f"📦 {label} cache hit: {url}")
            return cached

        print(f"🌐 {label} cache miss — fetching: {url}")
        try:
            response = fetcher.fetch(url)
            cache.set(url, response.body)
            return response.body
        except Exception as e:
            get_logger().warning("Failed to fetch %s: %s", url, e)
            return None

    @staticmethod
    def _clean_novel_page_for_analysis(html: str, *, max_length: int = 60_000) -> str:
        """Remove executable/noisy markup while retaining metadata attributes.

        ``clean_html_for_analysis`` intentionally drops image and Open Graph
        attributes because selector generation does not need their values. The
        novel-info phase does need those values, so it uses this less aggressive
        cleaner instead.
        """
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.select("script, style, noscript, svg, iframe"):
            tag.decompose()
        cleaned = str(soup)
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length] + "\n<!-- truncated -->"
        return cleaned

    @staticmethod
    def _normalise_novel_info(info: dict[str, Any], source_url: str) -> dict[str, Any]:
        """Validate LLM metadata and resolve relative URLs against the source page."""

        def _text(key: str, *, required: bool = False) -> str | None:
            value = info.get(key)
            if value is None:
                if required:
                    raise ValueError(f"LLM did not return a {key} for the novel page.")
                return None
            text = str(value).strip()
            if not text and required:
                raise ValueError(f"LLM did not return a {key} for the novel page.")
            return text or None

        def _url(key: str, *, required: bool = False) -> str | None:
            value = _text(key)
            if value is None:
                if required:
                    raise ValueError(f"LLM did not return a {key} for the novel page.")
                return None
            absolute = urljoin(source_url, value)
            if urlparse(absolute).scheme not in {"http", "https"}:
                if required:
                    raise ValueError(f"LLM returned an invalid {key}: {value!r}")
                return None
            return absolute

        return {
            "title": _text("title", required=True),
            "author": _text("author"),
            "illustration_url": _url("illustration_url"),
            "summary": _text("summary"),
            "toc_url": _url("toc_url", required=True),
        }

    @staticmethod
    def _add_novel_info(
        config: dict[str, Any],
        source_url: str,
        novel_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Attach canonical novel metadata to a generated selector config."""
        config["source_url"] = source_url
        config["title"] = novel_info.get("title")
        config["author"] = novel_info.get("author")
        config["illustration_url"] = novel_info.get("illustration_url")
        config["summary"] = novel_info.get("summary")
        return config

    def _fetch_chapter_with_fallback(
        self,
        fetcher: Fetcher,
        chapter_url: str,
        cache: _HtmlCache,
    ) -> tuple[str, BeautifulSoup | None]:
        """Fetch a chapter page; fallback to browser if blocked by anti-bot."""
        ch_html = self._fetch_or_cache(fetcher, cache, chapter_url, "Chapter")
        if ch_html is None:
            return "", None
        ch_soup = BeautifulSoup(ch_html, "html.parser")

        if not self._is_challenge_page(ch_html):
            return ch_html, ch_soup

        if self._use_browser:
            get_logger().warning("Chapter page is an anti-bot challenge — skipping Phase 2.")
            return ch_html, None

        get_logger().warning("Chapter page looks like an anti-bot challenge — trying browser fallback...")
        from src.services.browser import BrowserFetcher

        with BrowserFetcher(
            user_agent=self._user_agent,
            timeout_seconds=30,
            delay_seconds=1.0,
        ) as browser_fetcher:
            ch_html = browser_fetcher.fetch(chapter_url).body
            cache.set(chapter_url, ch_html)
            ch_soup = BeautifulSoup(ch_html, "html.parser")
            if self._is_challenge_page(ch_html):
                get_logger().warning("Browser also hit a challenge page. Site may require advanced bypass.")
                return ch_html, None
            get_logger().info("Browser fetch succeeded.")
            return ch_html, ch_soup

    @staticmethod
    def _is_error_page(html: str) -> bool:
        """Detect if the fetched page is a 404 or error page."""
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string or "") if soup.title else ""
        title_lower = title.lower()
        # Common 404 indicators in page title.
        if any(sig in title_lower for sig in ("404", "not found", "错误", "不存在")):
            return True
        # Check body text for error messages.
        body_text = soup.get_text(" ", strip=True)[:500].lower()
        return any(sig in body_text for sig in ("页面不存在", "页面已删除", "page not found"))

    @staticmethod
    def _load_sample(domain: str, samples_dir: Path) -> dict[str, Any] | None:
        """Return a deep copy of a sample config matching ``domain``.

        ``samples_dir`` is a directory of per-site sample JSONs. Each file's
        ``toc_url`` netloc is compared against ``domain``; the first match
        wins. Returns a deep copy so callers can mutate freely, or ``None``
        if the directory is missing or contains no matching sample.
        """
        if not samples_dir.is_dir():
            return None
        for path in sorted(samples_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                toc_url = data.get("toc_url", "")
                if urlparse(toc_url).netloc == domain:
                    return json.loads(json.dumps(data))
            except (OSError, ValueError):
                continue
        return None

    @staticmethod
    def _load_known_domain_config(domain: str, translated_root: Path) -> dict[str, Any] | None:
        """Scan novel directories for a config whose toc_url netloc matches domain."""
        if not translated_root.is_dir():
            return None
        for path in sorted(translated_root.glob("*/config.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                toc_url = data.get("toc_url", "")
                if urlparse(toc_url).netloc == domain:
                    return data
            except (OSError, ValueError):
                continue
        return None

    @staticmethod
    def _is_challenge_page(html: str) -> bool:
        """Detect Cloudflare or anti-bot challenge pages."""
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.string or "") if soup.title else ""
        title_lower = title.lower()

        challenge_titles = (
            "just a moment",
            "checking your browser",
            "ddos protection",
            "attention required",
            "cloudflare",
            "wait",
        )
        if any(sig in title_lower for sig in challenge_titles):
            return True

        body_text = soup.get_text(" ", strip=True)[:500].lower()
        challenge_texts = (
            "just a moment",
            "checking your browser",
            "ddos protection",
            "cloudflare",
            "please enable javascript",
            "please wait",
            "redirecting",
        )
        if any(sig in body_text for sig in challenge_texts):
            return True

        # Very small body with known challenge wrapper.
        return len(html) < 1500 and bool(soup.select_one(".main-wrapper, #cf-wrapper, #challenge-form"))

    def _ask_llm_with_retry(
        self,
        *,
        system: str,
        user: str,
        call_type: str,
        soup: BeautifulSoup,
        retry_system: str,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """Send prompt to LLM, validate selectors, and retry once if they fail."""
        result = self._ask_llm(system=system, user=user, call_type=call_type)
        issues = self._validate_selectors(result, soup, call_type)

        if issues and max_retries > 0:
            print(f"⚠  Selector issues detected — retrying ({', '.join(issues)})")
            retry_user = f"Previous issues: {', '.join(issues)}\n\n{user}"
            result = self._ask_llm(system=retry_system, user=retry_user, call_type=f"{call_type}_retry")
            issues = self._validate_selectors(result, soup, call_type)
            if issues:
                print(f"⚠  Still has issues after retry: {', '.join(issues)}")

        return result

    def _ask_llm(self, *, system: str, user: str, call_type: str) -> dict[str, Any]:
        """Send prompt to LLM and parse JSON response."""
        raw = self._llm.generate(system, user, call_type)
        return self._parse_json(raw)

    @staticmethod
    def _validate_selectors(result: dict[str, Any], soup: BeautifulSoup, call_type: str) -> list[str]:
        """Check that returned selectors actually match elements in the HTML."""
        issues: list[str] = []

        if call_type.startswith("gen_config_toc"):
            selector = result.get("chapter_link_selector")
            if selector and not soup.select(selector):
                issues.append("chapter_link_selector matches 0 elements")
        elif call_type.startswith("gen_config_chapter"):
            content_sel = result.get("chapter_content_selector")
            if content_sel and not soup.select(content_sel):
                issues.append("chapter_content_selector matches 0 elements")
            for key in ("chapter_title_selector",):
                selector = result.get(key)
                if selector and not soup.select(selector):
                    issues.append(f"{key} matches 0 elements")

        return issues

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """Extract the first JSON object from LLM output."""
        # Try direct parse first.
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Strip markdown code fences if present.
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Last resort: find first { … } block.
        brace_match = re.search(r"\{.*}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"LLM output is not valid JSON:\n{text[:500]}")

    @staticmethod
    def _find_first_chapter(soup: BeautifulSoup, base_url: str, selector: str) -> str | None:
        """Use the LLM-suggested selector to find the first chapter link."""
        if not selector:
            return None
        anchors = soup.select(selector)
        base_netloc = urlparse(base_url).netloc
        for anchor in anchors:
            href = anchor.get("href")
            if not isinstance(href, str) or not href:
                continue
            url = urljoin(base_url, href)
            # basic sanity: same domain
            if urlparse(url).netloc == base_netloc:
                return url
        return None

    @staticmethod
    def _derive_name(url: str) -> str:
        """Derive a short config name from the URL."""
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if parts:
            return parts[-1].rstrip("/")
        return parsed.netloc.replace(".", "-")

    @staticmethod
    def _build_config(
        toc_url: str,
        name: str,
        toc: dict[str, Any],
        chapter: dict[str, Any],
        *,
        source_url: str | None = None,
        novel_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Merge Phase 1 + Phase 2 results into a full config dict."""
        remove = list(chapter.get("remove_selectors") or ["script", "style"])
        if "script" not in remove:
            remove.insert(0, "script")
        if "style" not in remove:
            remove.insert(1, "style")

        # Deduplicate while preserving order.
        seen: set[str] = set()
        deduped = [s for s in remove if not (s in seen or seen.add(s))]

        # Smart default for max_toc_pages: 1 when no pagination, else 50.
        toc_next = toc.get("toc_next_selector")
        max_toc_pages = 1 if toc_next is None else 50

        # Handle null values from LLM — .get(key, default) returns None when
        # the key exists with a null value, so we must normalise explicitly.
        def _or(val: Any, default: Any) -> Any:
            return val if val is not None else default

        config = {
            "name": name,
            "toc_url": toc_url,
            "version": 1,
            "chapter_link_selector": _or(toc.get("chapter_link_selector"), "a"),
            "toc_next_selector": _or(toc_next, None),
            "toc_expand_selector": _or(toc.get("toc_expand_selector"), None),
            "chapter_title_selector": _or(chapter.get("chapter_title_selector"), None),
            "chapter_content_selector": _or(chapter.get("chapter_content_selector"), "body"),
            "remove_selectors": deduped,
            "same_domain": True,
            "reverse_chapter_order": False,
            "filter_non_chapter_links": True,
            "request_delay_seconds": 2.0,
            "timeout_seconds": 30,
            "max_toc_pages": max_toc_pages,
            "user_agent": DEFAULT_USER_AGENT,
        }
        if source_url is not None:
            ConfigGenerator._add_novel_info(config, source_url, novel_info or {})
        return config
