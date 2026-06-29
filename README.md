# novel-ai-trans

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/package%20manager-uv-2b2b2b.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An end-to-end toolkit for turning web novels or EPUB files into translated EPUB
and PDF books with LLMs. Crawl, translate, package — one pipeline.

`novel-ai-trans` combines a configurable crawler, an LLM translation pipeline
with glossary memory and quality checks, and EPUB/PDF packaging in one
repository.

```text
Website / EPUB
    -> translated/<novel>/input/
    -> translate with Ollama, Gemini, or OpenRouter
    -> translated/<novel>/output/
    -> <novel>.<target>.epub / <novel>.<target>.pdf
```

## Features

- **Crawl public novel sites** with per-site JSON selector configs, or generate
  and validate configs with an LLM-assisted workflow.
- **Import EPUB files** into the same chapter pipeline used by the crawler.
- **Translate** Chinese, Korean, and Japanese source chapters into Vietnamese
  or English.
- **Multiple providers** — Ollama (local), Gemini, or OpenRouter, with optional
  fallback provider support.
- **Per-novel glossary memory** for terms, character names, pronouns, and
  relationships — kept consistent across the whole book.
- **Preserve EPUB illustrations** through source markers and restore them during
  packaging.
- **EPUB and PDF output** from translated chapter text, with cover image and
  dark-mode PDF support.
- **Resume anytime** — chapter-level progress tracking, retry failed chapters,
  retranslate ranges.
- **Optional review and summary steps** when quality is worth the extra tokens.
- **Telegram notifications** when a crawl or translation run finishes.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- One supported LLM provider:
  - local [Ollama](https://ollama.com/) server, or
  - [Gemini](https://aistudio.google.com/apikey) API key, or
  - [OpenRouter](https://openrouter.ai/keys) API key
- Playwright Chromium if you crawl JavaScript-heavy sites

## Quick Start

```bash
git clone https://github.com/tuannguyen8531/novel-ai-trans.git
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

See [docs/GUIDE.md](docs/GUIDE.md) for the full walkthrough.

## Providers

| Provider    | Type   | Get started                                         |
| ----------- | ------ | --------------------------------------------------- |
| **Ollama**  | Local  | [ollama.com](https://ollama.com/)                   |
| **Gemini**  | Cloud  | [Google AI Studio](https://aistudio.google.com/apikey) |
| **OpenRouter** | Cloud (200+ models) | [openrouter.ai/keys](https://openrouter.ai/keys) |

Any provider can be paired with a different `FALLBACK_PROVIDER` for automatic
failover when the primary errors out.

See [docs/PROVIDERS.md](docs/PROVIDERS.md) for detailed setup instructions.

## Commands

The project exposes short console commands through `pyproject.toml`:

```bash
uv run crawl <config-or-name>        # download chapters from a site
uv run generate <toc-url>            # AI-generate a site config
uv run validate <config-or-name>     # test selectors against live HTML
uv run import <book.epub>            # import an EPUB into the pipeline
uv run translate <novel>             # batch translate chapters
uv run glossary <command> <novel>    # manage per-novel glossary
uv run pack <novel>                  # build EPUB / PDF
uv run test                          # ruff + pyright + pytest
uv run build                         # build the web UI
uv run serve                         # start the API + built GUI server
```

`main.py` also provides a single dispatcher for local use:

```bash
uv run python main.py <command> --help
```

See [docs/GUIDE.md](docs/GUIDE.md) for every flag and example.

## Configuration

Settings are loaded from `.env`. Copy `.env.example` to `.env` and edit.

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
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token for notifications |
| `TELEGRAM_CHAT_ID` | empty | Telegram chat id to notify |

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

## Documentation

| Guide | Description |
| --- | --- |
| [docs/GUIDE.md](docs/GUIDE.md) | Full walkthrough: crawl, generate, import, translate, glossary, pack |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Detailed provider setup (Ollama, Gemini, OpenRouter, fallback) |

## Development

Run the full validation pipeline:

```bash
uv run test
```

Run individual checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/
```

Forward extra pytest arguments through the unified test command:

```bash
uv run test -- tests/services/test_crawler.py -v
```

## License

MIT. See [LICENSE](LICENSE).
