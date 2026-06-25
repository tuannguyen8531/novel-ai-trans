# novel-ai-trans

End-to-end pipeline that **crawls** public novel websites, **translates** chapters
with LLMs (Ollama, Gemini, OpenRouter), and **packages** the result as EPUB / PDF.

```text
crawl ─▶ translated/<novel>/input/ ─▶ translate ─▶ translated/<novel>/output/ ─▶ pack ─▶ EPUB / PDF
```

Per-novel data, LLM prompts, quality reports, and run state all live under
`translated/` and `runtime/` inside the project — one repo, one tree, one
command (`uv run novel-ai-trans <command>`) to do everything.

---

## Features

### Crawler

- Per-site JSON profiles with CSS selectors.
- AI-assisted site-config generation (Ollama / Gemini).
- EPUB import — extracts chapters + illustrations, emits `[[ILLUSTRATION:…]]`
  markers in source text.
- Auto-resume, atomic writes, incremental `manifest.json`.
- Headless browser mode (Playwright) for JS-heavy sites, with concurrent pages
  and system-Chromium fallback.
- `robots.txt` respected by default.

### Translator

- Multi-provider LLM with **automatic fallback** on rate limits / failures.
- Source language auto-detection (heuristic + LLM fallback) — Chinese, Korean,
  Japanese.
- Target languages: **Vietnamese** (default) and English.
- Context-aware translation: per-novel glossary, character graph, chapter
  summaries.
- Quality review loop (LLM score + deterministic checks + retry below threshold).
- Language-specific rules (honorifics, xianxia, murim, isekai, regression) per
  `rules/<target>/<source>.md`.
- Paragraph-aware chunking with configurable overlap.
- Illustration marker detach / restore so images are never garbled by
  translation.

### Packager

- EPUB and PDF output with CJK-safe text normalisation.
- Cover image resolution (local file or URL → temp download).
- Embeds illustrations at their `[[ILLUSTRATION:…]]` marker positions.
- Target-specific output paths (Vietnamese / English).

---

## Installation

```bash
git clone <repo>
cd novel-ai-trans
uv sync                                # creates .venv + installs deps
uv run playwright install chromium      # optional, for browser mode
cp .env.example .env                    # then edit credentials
```

Requires **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/).

---

## Configuration

All settings come from `.env` (loaded automatically). The full key list:

| Key | Default | Used by |
|---|---|---|
| `TRANSLATED_DIR` | `translated` | both |
| `MAX_CHAPTERS` | `0` (no cap) | crawler |
| `USE_BROWSER` | `false` | crawler |
| `LLM_TEMPERATURE` | `0.0` | crawler (config gen) |
| `LLM_MAX_TOKENS` | `4096` | crawler (config gen) |
| `LLM_PROVIDER` | `ollama` | both |
| `FALLBACK_PROVIDER` | `""` | translator |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | both |
| `OLLAMA_MODEL` | `qwen3:8b` | both |
| `GEMINI_API_KEY` | (empty) | both |
| `GEMINI_MODEL` | `gemini-2.5-flash` | both |
| `OPENROUTER_API_KEY` | (empty) | both |
| `OPENROUTER_MODEL` | `qwen/qwen3-8b` | both |
| `TARGET_LANGUAGE` | `vi` | translator |
| `TRANSLATION_TEMPERATURE` | `0.3` | translator |
| `TRANSLATION_MAX_TOKENS` | `4096` | translator |
| `CHUNK_SIZE` | `1500` | translator |
| `CHUNK_OVERLAP` | `100` | translator |
| `REVIEW_THRESHOLD` | `0.7` | translator |
| `MAX_RETRIES` | `2` | translator |
| `ENABLE_REVIEW` | `false` | translator |
| `ENABLE_SUMMARY` | `false` | translator |

`TRANSLATED_DIR` is the project root for per-novel artefacts
(`input/`, `output/`, `glossary.json`, `metadata.json`, `illustrations/`).
The default value is `translated/`, which is where per-novel files live when you
run the project from a fresh clone.

---

## Usage

`main.py` is the single CLI entry point. Every command below routes through it.

```bash
python main.py --help
python main.py <command> --help
```

### Crawl a site

```bash
# Use an existing config
uv run crawl example

# Limit output
uv run crawl example -m 5

# Parallel workers + browser
uv run crawl example -w 3 -b

# Put chapters in a custom location
uv run crawl example --translated-output /tmp/translated
```

### Generate a site config with AI

```bash
uv run generate https://example.com/novel/toc --name my-novel
```

### Validate a config against live HTML

```bash
uv run validate my-novel
```

### Import an EPUB

```bash
uv run import book.epub -n my-novel
```

Chapters land in `translated/my-novel/input/`, illustrations in
`translated/my-novel/illustrations/`.

### Translate chapters

```bash
# Batch translate all untranslated chapters (default target = vi)
uv run translate my-novel

# Explicit source language + provider
uv run translate my-novel -l chinese -p gemini

# Enable review + summary
uv run translate my-novel -r -s

# Dry run
uv run translate my-novel -d

# Resume from a checkpoint
uv run translate my-novel -R

# Translate only failed chapters
uv run translate my-novel -F

# Translate to English
uv run translate my-novel -t en
```

### Manage glossary

```bash
uv run glossary list my-novel
uv run glossary add my-novel "原名" "Bản dịch"
uv run glossary remove my-novel "原名"
uv run glossary characters my-novel
uv run glossary character my-novel 李明 --role protagonist --translated-name "Lý Minh"
uv run glossary relationship my-novel 李明 张伟 friend --since 3
uv run glossary validate my-novel
uv run glossary audit my-novel
```

### Pack into EPUB / PDF

```bash
uv run pack my-novel                # default target (vi) → EPUB + PDF
uv run pack my-novel -f epub
uv run pack my-novel -f pdf --dark
uv run pack my-novel -t en           # English pack
```

Default output directory: `translated/<novel>/`. Final files:
`<novel>.{vi|en}.epub` and `<novel>.{vi|en}.pdf`.

---

## Project layout

```text
novel-ai-trans/
├── main.py                    Single CLI dispatcher (≈95 lines)
├── pyproject.toml             Project + dependency manifest
├── .env / .env.example        Local configuration
│
├── configs/                   Per-site crawler profiles
│
├── translated/                Per-novel artefacts
│   └── <novel>/
│       ├── input/chapter_*.txt          ← crawler writes, translator reads
│       ├── output/chapter_NNN.txt       ← translator writes, packager reads
│       ├── metadata.json
│       ├── glossary.json
│       └── illustrations/…              ← EPUB images
│
├── runtime/                   Global runtime state
│   ├── crawler/<novel>/                 ← manifest, config snapshot, html cache
│   ├── input/<novel>/                   ← local-only input fallback
│   ├── output/<novel>/                  ← local-only output fallback
│   ├── reports/<novel>/                 ← per-chapter quality reports
│   ├── progress/                        ← batch translator progress
│   └── glossary/<novel>.json            ← local glossary mirror
│
├── rules/{en,vi}/<lang>.md    Translation rules per source language
├── logs/                      LLM request/response + error logs
│
├── src/
│   ├── config.py              Config + SiteConfig
│   ├── models/                Crawler dataclasses + TranslationState
│   ├── domain/                Pure-domain logic (chunking, glossary, language, quality, …)
│   ├── graph/                 LangGraph state machine + nodes
│   ├── prompts/               Markdown prompt templates
│   ├── services/              Business services
│   │   ├── crawler.py
│   │   ├── epub_importer.py
│   │   ├── config_generator.py
│   │   ├── browser.py
│   │   ├── http.py
│   │   ├── glossary.py
│   │   ├── metadata.py
│   │   ├── logger.py
│   │   └── llm/               Ollama, Gemini, OpenRouter + FallbackProvider
│   ├── utils/                 Text, HTML, JSON, progress, display, logging, chapters
│   └── cli/                   Per-command CLI entry points
│       ├── crawl.py
│       ├── translate.py
│       ├── pack.py
│       └── test.py
│
└── tests/                     Pytest suite
```

---

## Console scripts

After `uv sync`, the following are on `PATH` (and runnable as `uv run <name>`):

```bash
novel-ai-trans <command>    # catch-all dispatcher (same as `python main.py <command>`)
uv run crawl <novel>         # crawler shortcut
uv run generate <url>        # AI config generator
uv run validate <novel>      # config validator
uv run import <epub>         # EPUB importer
uv run translate <novel>     # batch translator
uv run pack <novel>          # EPUB / PDF packager
uv run glossary <sub> <novel># per-novel glossary manager
uv run test                  # ruff + ruff format + pytest
```

Each shortcut also works from the project root without `uv run` once the
virtualenv is activated (`source .venv/bin/activate`).

---

## Development

The single `test` command runs the full validation pipeline:

1. `ruff check` (lint)
2. `ruff format --check` (formatting)
3. `pytest tests/` (the full test suite)

```bash
uv run test
```

Skip any step with `--no-lint`, `--no-format`, or `--no-pytest`. Forward extra
arguments to pytest after `--`:

```bash
uv run test -- tests/services/test_crawler.py -v
```

You can also run individual tools directly:

```bash
uv run ruff check .             # lint only
uv run ruff format .            # apply formatting
uv run pytest tests/ -v         # tests only
```

### Test layout

Tests are grouped by the application layer they protect. The layout mirrors
`src/`, with each test file living next to the layer it exercises.

```text
tests/
├── cli/        # command-line behaviour (translator, packager, crawler CLI)
├── config/     # Config + SiteConfig
├── domain/     # pure-domain logic
├── graph/      # LangGraph routing + nodes
├── models/     # shared state/data model
├── prompts/    # markdown prompt templates
├── services/   # external-facing services (crawler, glossary, LLM, logger)
└── utils/      # small helpers
```

---

## License

MIT — see [LICENSE](LICENSE).
