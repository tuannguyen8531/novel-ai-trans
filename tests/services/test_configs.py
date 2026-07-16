from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bs4 import BeautifulSoup

from src.services.configs import ConfigGenerator, _HtmlCache
from src.services.http import FetchResponse


class _BoomLLM:
    """Stub LLM provider that fails loudly for every call."""

    @property
    def provider_name(self) -> str:
        return "boom"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        raise AssertionError(f"LLM should not be called when a sample exists (call_type={call_type!r})")


class _JsonLLM:
    """Stub LLM provider for exercising the live generator path."""

    def __init__(self) -> None:
        self.call_types: list[str] = []

    @property
    def provider_name(self) -> str:
        return "json"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        self.call_types.append(call_type)
        if call_type == "gen_novel_info":
            return json.dumps(
                {
                    "title": "Canonical Title",
                    "author": "Canonical Author",
                    "illustration_url": "/covers/999999.jpg",
                    "summary": "Canonical summary.",
                    "toc_url": "https://ixdzs8.com/read/999999/",
                }
            )
        if call_type == "gen_config_toc":
            return json.dumps(
                {
                    "chapter_link_selector": ".llm-chapters a",
                    "toc_next_selector": None,
                    "toc_expand_selector": None,
                }
            )
        if call_type == "gen_config_chapter":
            return json.dumps(
                {
                    "chapter_title_selector": ".llm-chapter-title",
                    "chapter_content_selector": ".llm-content",
                    "remove_selectors": ["script", "style", ".llm-chapter-title"],
                }
            )
        raise AssertionError(f"Unexpected call_type: {call_type!r}")


class _SampleLLM:
    """Return novel metadata while ensuring sample selectors avoid more calls."""

    def __init__(self, toc_url: str) -> None:
        self.toc_url = toc_url
        self.call_types: list[str] = []

    @property
    def provider_name(self) -> str:
        return "sample"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        self.call_types.append(call_type)
        if call_type != "gen_novel_info":
            raise AssertionError(f"Sample selectors should avoid call_type={call_type!r}")
        return json.dumps(
            {
                "title": "Sample Novel",
                "author": "Sample Author",
                "illustration_url": "/cover.jpg",
                "summary": "Sample summary.",
                "toc_url": self.toc_url,
            }
        )


class _RetryLLM:
    def __init__(self) -> None:
        self.call_types: list[str] = []

    @property
    def provider_name(self) -> str:
        return "retry"

    def generate(self, system_prompt: str, user_prompt: str, call_type: str) -> str:
        self.call_types.append(call_type)
        selector = ".missing" if call_type == "gen_config_toc" else ".chapters a"
        return json.dumps({"chapter_link_selector": selector})


class _StaticFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, body=self._pages[url], content_type="text/html")


class _StaticConfigGenerator(ConfigGenerator):
    def __init__(self, llm: Any, pages: dict[str, str]) -> None:
        super().__init__(llm)
        self._pages = pages

    @contextmanager
    def _open_fetcher(self):
        yield _StaticFetcher(self._pages)


_SAMPLE_FULL = {
    "name": "ixdzs8",
    "toc_url": "https://ixdzs8.com/",
    "version": 1,
    "chapter_link_selector": "ul.u-chapter li a",
    "toc_next_selector": None,
    "toc_expand_selector": "text=查看完整章节目录",
    "chapter_title_selector": ".page-d-name",
    "chapter_content_selector": ".page-content section",
    "remove_selectors": ["script", "style", ".page-content h3"],
    "same_domain": True,
    "reverse_chapter_order": False,
    "filter_non_chapter_links": True,
    "request_delay_seconds": 2.0,
    "timeout_seconds": 30.0,
    "retry_attempts": 3,
    "retry_backoff_seconds": 2.0,
    "max_toc_pages": 1,
    "user_agent": "test-ua/1.0",
}


class ConfigGeneratorTest(unittest.TestCase):
    def test_save_writes_config_inside_novel_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            translated_root = Path(tempdir)

            path = ConfigGenerator.save({"name": "demo"}, translated_root)

            self.assertEqual(path, translated_root / "demo" / "config.json")
            self.assertTrue(path.is_file())

    def test_save_rejects_non_slug_name(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir, self.assertRaises(ValueError):
            ConfigGenerator.save({"name": "../demo"}, Path(tempdir))

    def test_load_known_domain_config_finds_match(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            translated_root = Path(tempdir)
            config_path = translated_root / "known" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text(
                '{"toc_url": "https://example.com/book/1/", "chapter_link_selector": "a"}',
                encoding="utf-8",
            )
            result = ConfigGenerator._load_known_domain_config("example.com", translated_root)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["chapter_link_selector"], "a")

    def test_load_known_domain_config_returns_none_for_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            translated_root = Path(tempdir)
            config_path = translated_root / "known" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text(
                '{"toc_url": "https://example.com/book/1/"}',
                encoding="utf-8",
            )
            result = ConfigGenerator._load_known_domain_config("other.com", translated_root)
            self.assertIsNone(result)

    def test_html_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cache = _HtmlCache(Path(tempdir))
            html = "<html><head><title>Real Page</title></head><body><p>" + "x" * 300 + "</p></body></html>"
            cache.set("https://example.com", html)
            self.assertEqual(cache.get("https://example.com"), html)
            self.assertIsNone(cache.get("https://other.com"))

    def test_html_cache_can_be_disabled_without_reading_or_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cache_dir = Path(tempdir) / "disabled-cache"
            cache = _HtmlCache(cache_dir, enabled=False)
            cache.set("https://example.com", "<html>fresh</html>")

            self.assertIsNone(cache.get("https://example.com"))
            self.assertFalse(cache_dir.exists())

    def test_headless_browser_challenge_skips_chapter_analysis(self) -> None:
        url = "https://example.com/chapter-1"
        challenge = "<html><title>Just a moment...</title><div id='cf-wrapper'></div></html>"
        generator = ConfigGenerator(_BoomLLM(), use_browser=True)  # type: ignore[arg-type]

        with tempfile.TemporaryDirectory() as tempdir:
            html, soup = generator._fetch_chapter_with_fallback(
                _StaticFetcher({url: challenge}),
                url,
                _HtmlCache(Path(tempdir)),
            )

        self.assertEqual(html, challenge)
        self.assertIsNone(soup)

    def test_chapter_fetch_uses_browser_fallback_for_challenge(self) -> None:
        url = "https://example.com/chapter-1"
        challenge = "<html><title>Just a moment...</title><div id='cf-wrapper'></div></html>"
        browser_html = f"<html><body><section class='content'>Chapter body. {'x' * 300}</section></body></html>"
        generator = ConfigGenerator(_BoomLLM(), use_browser=False)  # type: ignore[arg-type]

        class _Browser:
            def __init__(self) -> None:
                self.assert_url: str | None = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def fetch(self, requested_url: str) -> FetchResponse:
                self.assert_url = requested_url
                return FetchResponse(url=requested_url, body=browser_html, content_type="text/html")

        browser = _Browser()
        with tempfile.TemporaryDirectory() as tempdir:
            cache = _HtmlCache(Path(tempdir))
            with patch("src.services.browser.BrowserFetcher", return_value=browser):
                html, soup = generator._fetch_chapter_with_fallback(
                    _StaticFetcher({url: challenge}),
                    url,
                    cache,
                )

            self.assertEqual(cache.get(url), browser_html)

        self.assertEqual(html, browser_html)
        self.assertIsNotNone(soup)
        assert soup is not None
        content = soup.select_one(".content")
        assert content is not None
        self.assertTrue(content.get_text(strip=True).startswith("Chapter body."))
        self.assertEqual(browser.assert_url, url)

    def test_selector_validation_retries_once_with_feedback(self) -> None:
        llm = _RetryLLM()
        generator = ConfigGenerator(llm)  # type: ignore[arg-type]
        soup = BeautifulSoup("<html><body><div class='chapters'><a href='1'>One</a></div></body></html>", "html.parser")

        result = generator._ask_llm_with_retry(
            system="initial",
            user="HTML",
            call_type="gen_config_toc",
            soup=soup,
            retry_system="retry",
        )

        self.assertEqual(result["chapter_link_selector"], ".chapters a")
        self.assertEqual(llm.call_types, ["gen_config_toc", "gen_config_toc_retry"])

    def test_html_cache_invalidates_bad_html(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cache = _HtmlCache(Path(tempdir))
            cache.set("https://example.com", "<html></html>")
            self.assertIsNone(cache.get("https://example.com"))

    def test_build_config_includes_toc_selectors_but_not_legacy_metadata_selectors(self) -> None:
        result = ConfigGenerator._build_config(
            "https://example.com/book/1/",
            "example",
            {
                "novel_title_selector": "h1",
                "author_selector": ".author",
                "illustration_selector": ".cover img",
                "chapter_link_selector": ".chapters a",
                "toc_next_selector": None,
                "toc_expand_selector": "text=Show all chapters",
            },
            {
                "chapter_title_selector": "h1",
                "chapter_content_selector": ".content",
                "remove_selectors": ["script", "style"],
            },
        )

        self.assertEqual(result["toc_expand_selector"], "text=Show all chapters")
        self.assertNotIn("novel_title_selector", result)
        self.assertNotIn("author_selector", result)
        self.assertNotIn("illustration_selector", result)

    # -- sample short-circuit ------------------------------------------------

    def test_load_sample_returns_match(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir)
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            result = ConfigGenerator._load_sample("ixdzs8.com", samples_dir)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["chapter_link_selector"], "ul.u-chapter li a")

    def test_load_sample_returns_deep_copy(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir)
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            first = ConfigGenerator._load_sample("ixdzs8.com", samples_dir)
            second = ConfigGenerator._load_sample("ixdzs8.com", samples_dir)
            assert first is not None and second is not None
            self.assertIsNot(first, second)
            first["remove_selectors"].append("mutated")
            self.assertNotIn("mutated", second["remove_selectors"])

    def test_load_sample_returns_none_for_unknown_domain(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir)
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            self.assertIsNone(ConfigGenerator._load_sample("unknown.com", samples_dir))

    def test_load_sample_returns_none_for_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            self.assertIsNone(ConfigGenerator._load_sample("ixdzs8.com", Path(tempdir) / "nope"))

    def test_generate_short_circuits_when_sample_matches(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir) / "samples"
            samples_dir.mkdir()
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")

            source_url = "https://ixdzs8.com/book/999999/"
            toc_url = "https://ixdzs8.com/read/999999/"
            llm = _SampleLLM(toc_url)
            generator = _StaticConfigGenerator(llm, {source_url: "<html><h1>Sample Novel</h1></html>"})
            result = generator.generate(source_url, samples_dir=samples_dir)

            self.assertEqual(result["toc_url"], toc_url)
            self.assertEqual(result["name"], "999999")
            self.assertEqual(result["source_url"], source_url)
            self.assertEqual(result["summary"], "Sample summary.")
            self.assertNotIn("novel_title_selector", result)
            self.assertNotIn("author_selector", result)
            self.assertNotIn("illustration_selector", result)
            self.assertEqual(result["chapter_link_selector"], "ul.u-chapter li a")
            self.assertEqual(result["remove_selectors"], ["script", "style", ".page-content h3"])
            self.assertEqual(result["user_agent"], "test-ua/1.0")
            self.assertEqual(llm.call_types, ["gen_novel_info"])

    def test_generate_uses_explicit_name_when_sample_matches(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir) / "samples"
            samples_dir.mkdir()
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")

            source_url = "https://ixdzs8.com/book/999999/"
            toc_url = "https://ixdzs8.com/read/999999/"
            generator = _StaticConfigGenerator(
                _SampleLLM(toc_url),
                {source_url: "<html><h1>Sample Novel</h1></html>"},
            )
            result = generator.generate(source_url, name="my-novel", samples_dir=samples_dir)
            self.assertEqual(result["name"], "my-novel")
            self.assertEqual(result["toc_url"], toc_url)

    def test_generate_does_not_mutate_sample_on_disk(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir) / "samples"
            samples_dir.mkdir()
            sample_path = samples_dir / "ixdzs8.json"
            sample_path.write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            original = json.loads(sample_path.read_text(encoding="utf-8"))

            source_url = "https://ixdzs8.com/book/12345/"
            toc_url = "https://ixdzs8.com/read/12345/"
            generator = _StaticConfigGenerator(
                _SampleLLM(toc_url),
                {source_url: "<html><h1>Sample Novel</h1></html>"},
            )
            generator.generate(
                source_url,
                name="different",
                samples_dir=samples_dir,
            )

            after = json.loads(sample_path.read_text(encoding="utf-8"))
            self.assertEqual(original, after)

    def test_generate_can_ignore_samples_and_known_domain_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            translated_root = root / "translated"
            samples_dir = root / "configs" / "samples"
            samples_dir.mkdir(parents=True)
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            known_path = translated_root / "known" / "config.json"
            known_path.parent.mkdir(parents=True)
            known_path.write_text(
                json.dumps(
                    {
                        **_SAMPLE_FULL,
                        "chapter_link_selector": ".known-chapters a",
                        "chapter_title_selector": ".known-chapter-title",
                        "chapter_content_selector": ".known-content",
                    }
                ),
                encoding="utf-8",
            )

            source_url = "https://ixdzs8.com/book/999999/"
            toc_url = "https://ixdzs8.com/read/999999/"
            chapter_url = "https://ixdzs8.com/read/999999/1.html"
            pages = {
                source_url: """
                    <html><body><h1>Canonical Title</h1></body></html>
                """,
                toc_url: """
                    <html><body>
                      <h1 class="llm-title">Live Title</h1>
                      <ul class="llm-chapters"><li><a href="1.html">Chapter 1</a></li></ul>
                    </body></html>
                """,
                chapter_url: """
                    <html><body>
                      <h1 class="llm-chapter-title">Chapter 1</h1>
                      <section class="llm-content"><p>Live chapter text.</p></section>
                    </body></html>
                """,
            }
            llm = _JsonLLM()
            generator = _StaticConfigGenerator(llm, pages)  # type: ignore[arg-type]

            result = generator.generate(
                source_url,
                translated_root=translated_root,
                samples_dir=samples_dir,
                cache_dir=root / "cache",
                use_samples=False,
            )

            self.assertEqual(result["chapter_link_selector"], ".llm-chapters a")
            self.assertEqual(result["chapter_content_selector"], ".llm-content")
            self.assertEqual(result["source_url"], source_url)
            self.assertEqual(result["title"], "Canonical Title")
            self.assertEqual(result["illustration_url"], "https://ixdzs8.com/covers/999999.jpg")
            self.assertEqual(result["summary"], "Canonical summary.")
            self.assertNotEqual(result["user_agent"], "test-ua/1.0")
            self.assertEqual(llm.call_types, ["gen_novel_info", "gen_config_toc", "gen_config_chapter"])


class SiteSampleFilesTest(unittest.TestCase):
    """Bundled sample JSONs must populate every SiteConfig field."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "name",
        "toc_url",
        "chapter_link_selector",
        "chapter_content_selector",
        "version",
        "toc_next_selector",
        "toc_expand_selector",
        "chapter_title_selector",
        "remove_selectors",
        "same_domain",
        "reverse_chapter_order",
        "filter_non_chapter_links",
        "request_delay_seconds",
        "timeout_seconds",
        "retry_attempts",
        "retry_backoff_seconds",
        "max_toc_pages",
        "user_agent",
    )

    def test_all_samples_have_every_field(self) -> None:
        import json

        samples_dir = Path("configs")
        self.assertTrue(samples_dir.is_dir(), f"Missing samples dir: {samples_dir}")
        sample_files = sorted(samples_dir.glob("*.json"))
        self.assertGreaterEqual(len(sample_files), 4)

        for path in sample_files:
            with self.subTest(file=path.name):
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                missing = [key for key in self.REQUIRED_FIELDS if key not in data]
                self.assertEqual(missing, [], f"{path.name} missing fields: {missing}")
                SiteConfig = _import_site_config()
                SiteConfig.from_dict(data)

    def test_samples_cover_all_supported_non_8book_sites(self) -> None:
        samples_dir = Path("configs")
        domains = set()
        for path in samples_dir.glob("*.json"):
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            from urllib.parse import urlparse

            domains.add(urlparse(data["toc_url"]).netloc)

        expected = {"ixdzs8.com", "www.69shuba.com", "book.sfacg.com", "kakuyomu.jp"}
        self.assertTrue(expected.issubset(domains), f"Missing samples for: {expected - domains}")


def _import_site_config():
    from src.config import SiteConfig

    return SiteConfig


if __name__ == "__main__":
    unittest.main()
