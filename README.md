# novel-ai-trans

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/package%20manager-uv-2b2b2b.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An end-to-end toolkit for turning web novels or EPUB files into translated EPUB
and PDF books with LLMs.

`novel-ai-trans` combines a configurable crawler, an LLM translation pipeline,
glossary memory, quality checks, and EPUB/PDF packaging in one repository.

```text
Website / EPUB
    -> translated/<novel>/input/
    -> translate with Ollama, Gemini, or OpenRouter
    -> translated/<novel>/output/
    -> <novel>.<target>.epub / <novel>.<target>.pdf
```

## Features

- Crawl public novel sites with per-site JSON selector configs.
- Generate and validate crawler configs with an LLM-assisted workflow.
- Import EPUB files into the same chapter pipeline used by the crawler.
- Translate Chinese, Korean, and Japanese source chapters into Vietnamese or
  English.
- Use Ollama, Gemini, or OpenRouter, with optional fallback provider support.
- Maintain per-novel glossary data for terms, character names, pronouns, and
  relationships.
- Preserve EPUB illustrations through source markers and restore them during
  packaging.
- Produce EPUB and PDF output from translated chapter text.
- Run optional review and summary steps when quality is worth the extra tokens.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- One supported LLM provider:
  - local Ollama server, or
  - Gemini API key, or
  - OpenRouter API key
- Playwright Chromium if you crawl JavaScript-heavy sites

## Installation

```bash
git clone <repo-url>
cd novel-ai-trans

uv sync
cp .env.example .env
```

Edit `.env` for your provider:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

For browser-based crawling:

```bash
uv run playwright install chromium
```

## Quick Start

### Option 1: import an EPUB

```bash
uv run import ./book.epub --name my-novel
uv run translate my-novel --target vi
uv run pack my-novel --target vi
```

### Option 2: crawl from a configured site

```bash
uv run generate https://example.com/novel/table-of-contents --name my-novel
uv run validate my-novel
uv run crawl my-novel --max 5
uv run translate my-novel --target vi
uv run pack my-novel --target vi
```

Generated files are written under:

```text
translated/<novel>/
├── input/                  source chapter_*.txt files
├── output/                 Vietnamese translated chapters
├── output/en/              English translated chapters
├── illustrations/          imported or crawled images
├── metadata.json
├── <novel>.vi.epub
├── <novel>.vi.pdf
├── <novel>.en.epub
└── <novel>.en.pdf
```

## Commands

The project exposes short console commands through `pyproject.toml`.

```bash
uv run crawl <config-or-name>
uv run generate <toc-url>
uv run validate <config-or-name>
uv run import <book.epub>
uv run translate <novel>
uv run glossary <command> <novel>
uv run pack <novel>
uv run test
```

`main.py` also provides a single dispatcher for local use:

```bash
uv run python main.py <command> --help
```

### Crawl

Use a config from `configs/<name>.json`. For example, `configs/example.json`
is loaded as `example`:

```bash
uv run crawl example
```

Limit chapters:

```bash
uv run crawl example --max 10
```

Use Playwright browser mode for JavaScript-heavy pages:

```bash
uv run crawl example --browser --workers 1
```

Preview discovered chapters without writing files:

```bash
uv run crawl example --dry-run
```

Ignore `robots.txt` only when you have permission:

```bash
uv run crawl example --ignore-robots
```

### Generate a Site Config

```bash
uv run generate https://example.com/novel/table-of-contents --name my-novel
uv run validate my-novel
uv run crawl my-novel
```

Site configs live in `configs/` and use CSS selectors:

```json
{
  "name": "example-public-site",
  "start_url": "https://example.com/novel/table-of-contents",
  "novel_title_selector": "h1",
  "author_selector": ".author",
  "chapter_link_selector": ".chapter-list a",
  "chapter_title_selector": "h1",
  "chapter_content_selector": ".chapter-content",
  "remove_selectors": ["script", "style", ".ads"],
  "same_domain": true,
  "filter_non_chapter_links": true,
  "request_delay_seconds": 1.5,
  "version": 1
}
```

### Import EPUB

```bash
uv run import ./book.epub --name my-novel
```

Keep existing source chapters in the destination:

```bash
uv run import ./book.epub --name my-novel --keep-existing
```

### Translate

Translate all untranslated chapters:

```bash
uv run translate my-novel
```

Select source language and provider:

```bash
uv run translate my-novel --lang chinese --provider gemini
```

Translate a chapter range:

```bash
uv run translate my-novel --start 20 --to 30
```

Re-translate existing chapters:

```bash
uv run translate my-novel --start 20 --to 20 --force
```

Resume from progress state or retry failed chapters:

```bash
uv run translate my-novel --resume
uv run translate my-novel --failed-only
```

Translate to English:

```bash
uv run translate my-novel --target en
```

Enable token-heavier review and summary steps:

```bash
uv run translate my-novel --review --summary
```

### Glossary

```bash
uv run glossary list my-novel
uv run glossary add my-novel "原名" "Ten dich"
uv run glossary remove my-novel "原名"
uv run glossary characters my-novel
uv run glossary character my-novel "李明" --translated-name "Ly Minh" --role protagonist
uv run glossary pronoun my-novel "李明" "anh"
uv run glossary relationship my-novel "李明" "张伟" friend --since 3
uv run glossary validate my-novel
uv run glossary audit my-novel
```

### Package

Build both EPUB and PDF:

```bash
uv run pack my-novel --target vi
```

Build one format:

```bash
uv run pack my-novel --format epub
uv run pack my-novel --format pdf --dark
```

Override metadata or output directory:

```bash
uv run pack my-novel --title "My Novel" --author "Author Name" --output ./dist
```

## Configuration

Settings are loaded from `.env`.

| Key | Default | Purpose |
| --- | --- | --- |
| `TRANSLATED_DIR` | `translated` | Per-novel input, output, metadata, and package root |
| `MAX_CHAPTERS` | `0` | Crawler chapter cap, `0` means unlimited |
| `USE_BROWSER` | `false` | Default crawler browser mode |
| `LLM_PROVIDER` | `ollama` | Primary provider: `ollama`, `gemini`, or `openrouter` |
| `FALLBACK_PROVIDER` | empty | Optional fallback provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `qwen3:8b` | Ollama model |
| `GEMINI_API_KEY` | empty | Gemini credential |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `OPENROUTER_API_KEY` | empty | OpenRouter credential |
| `OPENROUTER_MODEL` | `qwen/qwen3-8b` | OpenRouter model |
| `TARGET_LANGUAGE` | `vi` | Default target: `vi` or `en` |
| `CHUNK_SIZE` | `1500` | Translation chunk size |
| `CHUNK_OVERLAP` | `100` | Context overlap between chunks |
| `REVIEW_THRESHOLD` | `0.7` | Minimum review score before retry |
| `MAX_RETRIES` | `2` | Translation retry count |
| `ENABLE_REVIEW` | `false` | Enable review by default |
| `ENABLE_SUMMARY` | `false` | Enable summary by default |

## Project Layout

```text
novel-ai-trans/
├── configs/              crawler site profiles
├── rules/                source-language rules per target language
├── src/
│   ├── cli/              command entry points
│   ├── domain/           chunking, glossary, language, quality logic
│   ├── graph/            LangGraph translation workflow
│   ├── prompts/          prompt templates
│   ├── services/         crawler, importer, metadata, LLM providers
│   └── utils/            display, logging, text, JSON, HTML helpers
├── tests/                pytest suite
├── translated/           local generated books and chapters
└── runtime/              progress, reports, crawler state, logs
```

`translated/` and `runtime/` are local runtime data. They are intentionally
separate from source code.

## Development

Run the full validation pipeline:

```bash
uv run test
```

Run individual checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/
```

Forward extra pytest arguments through the unified test command:

```bash
uv run test -- tests/services/test_crawler.py -v
```

## License

MIT. See [LICENSE](LICENSE).
