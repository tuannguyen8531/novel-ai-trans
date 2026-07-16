"""Workflow for validating crawler configurations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from src.application.crawl.common import check_cancel, emit, resolve_config_path
from src.application.errors import ApplicationValidationError
from src.application.progress import ProgressEvent
from src.config import SiteConfig
from src.services.crawling.crawler import NovelCrawler


@dataclass
class ConfigIssue:
    label: str
    selector: str | None
    matches: int
    status: str


@dataclass
class ConfigValidationResult:
    ok: bool
    novel: str
    config_path: str = ""
    toc_url: str = ""
    fetcher: str = "http"
    issues: list[ConfigIssue] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    chapter_count: int = 0
    sample_url: str | None = None
    content_length: int | None = None


def validate_config(
    *,
    novel: str,
    use_browser: bool | None = None,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: Event | None = None,
) -> ConfigValidationResult:
    """Test selectors from a config against live HTML."""
    try:
        config_path = resolve_config_path(novel)
        site_config = SiteConfig.from_file(config_path)
    except (OSError, ValueError) as error:
        raise ApplicationValidationError(str(error)) from error
    if site_config.name != novel:
        raise ApplicationValidationError(f"Config name {site_config.name!r} does not match novel directory {novel!r}.")
    use_browser = use_browser if use_browser is not None else False
    check_cancel(cancel_event)
    emit(progress_callback, ProgressEvent(kind="phase", message=f"Validating {site_config.name}"))

    if use_browser:
        from src.services.browser import BrowserFetcher

        fetcher = BrowserFetcher(
            user_agent=site_config.user_agent,
            timeout_seconds=site_config.timeout_seconds,
            delay_seconds=site_config.request_delay_seconds,
        )
        fetcher.__enter__()
        try:
            return _validate_with_fetcher(
                site_config,
                fetcher,
                cancel_event,
                progress_callback,
                config_path=config_path,
                fetcher_name="browser",
            )
        finally:
            fetcher.__exit__(None, None, None)

    from src.services.http import HttpClient

    fetcher = HttpClient(
        user_agent=site_config.user_agent,
        timeout_seconds=site_config.timeout_seconds,
        delay_seconds=site_config.request_delay_seconds,
        respect_robots=False,
    )
    return _validate_with_fetcher(
        site_config,
        fetcher,
        cancel_event,
        progress_callback,
        config_path=config_path,
        fetcher_name="http",
    )


def _validate_with_fetcher(
    site_config,
    fetcher,
    cancel_event,
    progress_callback,
    *,
    config_path: Path,
    fetcher_name: str,
) -> ConfigValidationResult:
    from bs4 import BeautifulSoup

    issues: list[ConfigIssue] = []
    metadata: dict = {}
    chapter_count = 0
    sample_url = None
    content_length = None
    ok = True

    if site_config.toc_expand_selector:
        if not hasattr(fetcher, "fetch_with_clicks"):
            raise ApplicationValidationError("toc_expand_selector requires browser mode (-b/--browser).")
        response = fetcher.fetch_with_clicks(
            site_config.toc_url,
            [site_config.toc_expand_selector],
            wait_for_selector=site_config.chapter_link_selector,
        )
    else:
        response = fetcher.fetch(site_config.toc_url)
    toc_soup = BeautifulSoup(response.body, "html.parser")
    check_cancel(cancel_event)
    for label, selector in [
        ("novel_title_selector", site_config.novel_title_selector),
        ("author_selector", site_config.author_selector),
        ("chapter_link_selector", site_config.chapter_link_selector),
        ("toc_next_selector", site_config.toc_next_selector),
        ("toc_expand_selector", site_config.toc_expand_selector),
    ]:
        if not selector:
            issues.append(ConfigIssue(label=label, selector=None, matches=0, status="skipped"))
            continue
        matches = len(toc_soup.select(selector))
        status = "ok" if matches > 0 else "fail"
        if status == "fail":
            ok = False
        issues.append(ConfigIssue(label=label, selector=selector, matches=matches, status=status))

    crawler = NovelCrawler(site_config, fetcher=fetcher)
    discovered_meta, chapters = crawler.discover_chapters()
    metadata = {
        "title": discovered_meta.title,
        "author": discovered_meta.author,
    }
    chapter_count = len(chapters)
    check_cancel(cancel_event)

    if chapters:
        first = chapters[0]
        sample_url = first.url
        check_cancel(cancel_event)
        chapter_html = fetcher.fetch(first.url).body
        chapter_soup = BeautifulSoup(chapter_html, "html.parser")
        for label, selector in [
            ("chapter_title_selector", site_config.chapter_title_selector),
            ("chapter_content_selector", site_config.chapter_content_selector),
        ]:
            if not selector:
                issues.append(ConfigIssue(label=label, selector=None, matches=0, status="skipped"))
                continue
            matches = len(chapter_soup.select(selector))
            status = "ok" if matches > 0 else "fail"
            if status == "fail":
                ok = False
            issues.append(ConfigIssue(label=label, selector=selector, matches=matches, status=status))
        for selector in site_config.remove_selectors:
            matches = len(chapter_soup.select(selector))
            status = "ok" if matches > 0 else "warn"
            issues.append(ConfigIssue(label="remove_selectors", selector=selector, matches=matches, status=status))
        content_node = chapter_soup.select_one(site_config.chapter_content_selector)
        if content_node is not None:
            content_length = len(content_node.get_text(strip=True))

    return ConfigValidationResult(
        ok=ok,
        novel=site_config.name,
        config_path=str(config_path),
        toc_url=site_config.toc_url,
        fetcher=fetcher_name,
        issues=issues,
        metadata=metadata,
        chapter_count=chapter_count,
        sample_url=sample_url,
        content_length=content_length,
    )


__all__ = ["ConfigIssue", "ConfigValidationResult", "validate_config"]
