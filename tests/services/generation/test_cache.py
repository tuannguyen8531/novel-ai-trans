from pathlib import Path

from src.services.generation.cache import HtmlCache


def test_cache_round_trip(tmp_path: Path) -> None:
    cache = HtmlCache(tmp_path)
    html = "<html><title>Novel</title><body>" + "x" * 300 + "</body></html>"
    cache.set("https://example.com", html)

    assert cache.get("https://example.com") == html
    assert cache.get("https://other.example") is None


def test_disabled_cache_neither_reads_nor_writes(tmp_path: Path) -> None:
    cache_dir = tmp_path / "disabled"
    cache = HtmlCache(cache_dir, enabled=False)
    cache.set("https://example.com", "<html>fresh</html>")

    assert cache.get("https://example.com") is None
    assert not cache_dir.exists()


def test_cache_invalidates_bad_html(tmp_path: Path) -> None:
    cache = HtmlCache(tmp_path)
    cache.set("https://example.com", "<html></html>")

    assert cache.get("https://example.com") is None
