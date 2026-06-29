from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from src.services.config_generator import ConfigGenerator, _HtmlCache
from src.services.http import FetchResponse


class _BoomLLM:
    """Stub LLM provider that fails loudly if the generator ever calls it."""

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
        if call_type == "gen_config_toc":
            return json.dumps(
                {
                    "novel_title_selector": ".llm-title",
                    "author_selector": None,
                    "illustration_selector": None,
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
    "start_url": "https://ixdzs8.com/",
    "version": 1,
    "novel_title_selector": ".novel h1",
    "author_selector": ".bauthor",
    "illustration_selector": ".novel img.cover",
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
    def test_load_known_domain_config_finds_match(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            configs_dir = Path(tempdir)
            (configs_dir / "known.json").write_text(
                '{"start_url": "https://example.com/book/1/", "chapter_link_selector": "a"}',
                encoding="utf-8",
            )
            result = ConfigGenerator._load_known_domain_config("example.com", configs_dir)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["chapter_link_selector"], "a")

    def test_load_known_domain_config_returns_none_for_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            configs_dir = Path(tempdir)
            (configs_dir / "known.json").write_text(
                '{"start_url": "https://example.com/book/1/"}',
                encoding="utf-8",
            )
            result = ConfigGenerator._load_known_domain_config("other.com", configs_dir)
            self.assertIsNone(result)

    def test_html_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cache = _HtmlCache(Path(tempdir))
            html = "<html><head><title>Real Page</title></head><body><p>" + "x" * 300 + "</p></body></html>"
            cache.set("https://example.com", html)
            self.assertEqual(cache.get("https://example.com"), html)
            self.assertIsNone(cache.get("https://other.com"))

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

    def test_html_cache_invalidates_bad_html(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            cache = _HtmlCache(Path(tempdir))
            cache.set("https://example.com", "<html></html>")
            self.assertIsNone(cache.get("https://example.com"))

    def test_build_config_includes_toc_expand_selector(self) -> None:
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
        self.assertEqual(result["illustration_selector"], ".cover img")

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

            generator = ConfigGenerator(_BoomLLM(), samples_dir=samples_dir)  # type: ignore[arg-type]
            toc_url = "https://ixdzs8.com/read/999999/"
            result = generator.generate(toc_url, samples_dir=samples_dir)

            self.assertEqual(result["start_url"], toc_url)
            self.assertEqual(result["name"], "999999")
            self.assertEqual(result["chapter_link_selector"], "ul.u-chapter li a")
            self.assertEqual(result["remove_selectors"], ["script", "style", ".page-content h3"])
            self.assertEqual(result["user_agent"], "test-ua/1.0")

    def test_generate_uses_explicit_name_when_sample_matches(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir) / "samples"
            samples_dir.mkdir()
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")

            generator = ConfigGenerator(_BoomLLM(), samples_dir=samples_dir)  # type: ignore[arg-type]
            toc_url = "https://ixdzs8.com/read/999999/"
            result = generator.generate(toc_url, name="my-novel", samples_dir=samples_dir)
            self.assertEqual(result["name"], "my-novel")
            self.assertEqual(result["start_url"], toc_url)

    def test_generate_does_not_mutate_sample_on_disk(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tempdir:
            samples_dir = Path(tempdir) / "samples"
            samples_dir.mkdir()
            sample_path = samples_dir / "ixdzs8.json"
            sample_path.write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            original = json.loads(sample_path.read_text(encoding="utf-8"))

            generator = ConfigGenerator(_BoomLLM(), samples_dir=samples_dir)  # type: ignore[arg-type]
            generator.generate(
                "https://ixdzs8.com/read/12345/",
                name="different",
                samples_dir=samples_dir,
            )

            after = json.loads(sample_path.read_text(encoding="utf-8"))
            self.assertEqual(original, after)

    def test_generate_can_ignore_samples_and_known_domain_config(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            configs_dir = root / "configs"
            samples_dir = configs_dir / "samples"
            samples_dir.mkdir(parents=True)
            (samples_dir / "ixdzs8.json").write_text(json.dumps(_SAMPLE_FULL), encoding="utf-8")
            (configs_dir / "known.json").write_text(
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

            toc_url = "https://ixdzs8.com/read/999999/"
            chapter_url = "https://ixdzs8.com/read/999999/1.html"
            pages = {
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
                toc_url,
                configs_dir=configs_dir,
                samples_dir=samples_dir,
                cache_dir=root / "cache",
                use_samples=False,
            )

            self.assertEqual(result["chapter_link_selector"], ".llm-chapters a")
            self.assertEqual(result["chapter_content_selector"], ".llm-content")
            self.assertNotEqual(result["user_agent"], "test-ua/1.0")
            self.assertEqual(llm.call_types, ["gen_config_toc", "gen_config_chapter"])


class SiteSampleFilesTest(unittest.TestCase):
    """Bundled sample JSONs must populate every SiteConfig field."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "name",
        "start_url",
        "chapter_link_selector",
        "chapter_content_selector",
        "version",
        "novel_title_selector",
        "author_selector",
        "illustration_selector",
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

        samples_dir = Path("configs") / "samples"
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
        samples_dir = Path("configs") / "samples"
        domains = set()
        for path in samples_dir.glob("*.json"):
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            from urllib.parse import urlparse

            domains.add(urlparse(data["start_url"]).netloc)

        expected = {"ixdzs8.com", "www.69shuba.com", "book.sfacg.com", "kakuyomu.jp"}
        self.assertTrue(expected.issubset(domains), f"Missing samples for: {expected - domains}")


def _import_site_config():
    from src.config import SiteConfig

    return SiteConfig


if __name__ == "__main__":
    unittest.main()
