"""Prompt template engine.

Templates live in src/prompts/ as .md files with {{var}} placeholders.
Target-language prompts can live in src/prompts/{target}/.
Usage:
    from src.prompts import render_prompt
    prompt = render_prompt("translate", target_language="vi", lang_name="Chinese")
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_prompt_cache: ContextVar[dict[tuple[str, str | None], str] | None] = ContextVar(
    "translation_prompt_cache",
    default=None,
)


@contextmanager
def prompt_cache_scope() -> Iterator[None]:
    """Cache raw prompt templates within one translation job."""
    token = _prompt_cache.set({})
    try:
        yield
    finally:
        _prompt_cache.reset(token)


def _resolve_template_path(template_name: str, target_language: str | None = None) -> Path:
    """Resolve a template path, checking target-specific folders first."""
    candidates = []
    if target_language:
        candidates.append(_PROMPTS_DIR / target_language / f"{template_name}.md")
    candidates.append(_PROMPTS_DIR / f"{template_name}.md")

    for path in candidates:
        if path.exists():
            return path

    checked = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Prompt template not found: {checked}")


def _read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_template(template_name: str, target_language: str | None) -> str:
    cache = _prompt_cache.get()
    cache_key = (template_name, target_language)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    content = _read_template(_resolve_template_path(template_name, target_language))
    if cache is not None:
        cache[cache_key] = content
    return content


def render_prompt(template_name: str, target_language: str | None = None, **variables: str) -> str:
    """Load a prompt template and replace {{var}} placeholders.

    Args:
        template_name: Filename without extension (e.g. "translate")
        target_language: Optional target language folder (e.g. "vi", "en")
        **variables: Key-value pairs to substitute in the template

    Returns:
        Rendered prompt string

    Raises:
        FileNotFoundError: Template file does not exist
    """
    content = _load_template(template_name, target_language)

    for key, value in variables.items():
        content = content.replace("{{" + key + "}}", value)

    return content.strip()


__all__ = ["prompt_cache_scope", "render_prompt"]
