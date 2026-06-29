# Guide

End-to-end walkthrough of the `novel-ai-trans` pipeline: crawl a site (or import
an EPUB), translate chapters, manage the glossary, and package the result as
EPUB/PDF.

For provider setup, see [PROVIDERS.md](PROVIDERS.md).

## Table of contents

- [Pipeline overview](#pipeline-overview)
- [1. Get source chapters](#1-get-source-chapters)
  - [Crawl a configured site](#crawl-a-configured-site)
  - [Generate a site config](#generate-a-site-config)
  - [Validate a config](#validate-a-config)
  - [Import an EPUB](#import-an-epub)
- [2. Translate](#2-translate)
- [3. Glossary](#3-glossary)
- [4. Package](#4-package)
- [Review and summary steps](#review-and-summary-steps)
- [Notifications](#notifications)
- [Troubleshooting](#troubleshooting)

## Pipeline overview

```text
 Website ──crawl──┐
                  ├──> translated/<novel>/input/chapter_*.txt
 EPUB ──import──┘                │
                                 ▼
                       translate (LangGraph workflow)
                                 │
                                 ▼
                  translated/<novel>/output/chapter_*.txt
                                 │
                                 ▼
                          pack ──> EPUB / PDF
```

Source chapters live as `chapter_N.txt` files under
`translated/<novel>/input/`. Translation output is written to
`translated/<novel>/output/` (Vietnamese) or `translated/<novel>/output/en/`
(English). Packaging reads the output dir and writes `<novel>.<target>.epub`
and `<novel>.<target>.pdf` next to it.

## 1. Get source chapters

You have two ways to fill `translated/<novel>/input/`: crawl a public site, or
import an existing EPUB.

### Crawl a configured site

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

Re-download chapter files even if they already exist:

```bash
uv run crawl example --overwrite
```

Ignore `robots.txt` only when you have permission:

```bash
uv run crawl example --ignore-robots
```

Stop on the first chapter error instead of writing partial output:

```bash
uv run crawl example --fail-fast
```

#### Crawl flags

| Flag | Description | Default |
| --- | --- | --- |
| `target` | Config path or novel name from `configs/{novel}.json` | required |
| `--translated-output` | Per-novel translated root | `TRANSLATED_DIR` |
| `-m, --max` | Stop after this many new chapters | `MAX_CHAPTERS` env or unlimited |
| `--fail-fast` | Stop on first chapter error | off |
| `--ignore-robots` | Skip `robots.txt` check | off |
| `--dry-run` | Only discover and print chapter links | off |
| `--overwrite` | Re-download existing `chapter_N.txt` | off |
| `--help` | Show crawl command help | off |
| `-b, --browser` | Use an ephemeral headless browser for JS challenges | off |
| `-h, --headed` | Use a visible browser with a persistent per-domain profile | off |
| `-w, --workers` | Concurrent chapter downloads | `1` |

The two browser modes are intentionally separate and cannot be combined. `-b`
uses a temporary profile on every run. `-h` reuses state per source domain under
`runtime/crawler/browser-profiles/`. If a site fingerprints headless and headed
sessions differently, use `-h` for the entire crawl instead of expecting its
profile to unblock later `-b` runs.

### Generate a site config

If no config exists for a site, let the LLM build one from the table-of-contents
URL:

```bash
uv run generate https://example.com/novel/table-of-contents --name my-novel
uv run validate my-novel
uv run crawl my-novel
```

The generator fetches the TOC page, inspects the HTML, and proposes a JSON
config with CSS selectors. Review the printed JSON, confirm, and it is saved to
`configs/<name>.json`.

```bash
uv run generate <url> --provider gemini        # override provider for generation
uv run generate <url> --browser                # fetch with headless browser
uv run generate <url> --no-cache               # always re-fetch pages
uv run generate <url> --ignore-sample          # ignore bundled templates
uv run generate <url> --output ./configs       # output directory
```

### Validate a config

Test a config's selectors against live HTML before crawling:

```bash
uv run validate my-novel
uv run validate my-novel --browser
```

The validator prints how many matches each selector gets on the TOC page and on
a sample chapter, plus the extracted content length. Use it to catch broken
selectors before a long crawl.

### Import an EPUB

Skip crawling entirely by importing an EPUB:

```bash
uv run import ./book.epub --name my-novel
```

Keep existing source chapters in the destination:

```bash
uv run import ./book.epub --name my-novel --keep-existing
```

Override the per-novel root:

```bash
uv run import ./book.epub --name my-novel --translated-output ./translated
```

The importer splits the EPUB into `chapter_N.txt` files, extracts illustrations
into `translated/<novel>/illustrations/`, and writes `metadata.json` with the
title, author, and cover URL.

#### Site config schema

Site configs live in `configs/` and use CSS selectors:

```json
{
  "name": "example-public-site",
  "start_url": "https://example.com/novel/table-of-contents",
  "novel_title_selector": "h1",
  "author_selector": ".author",
  "illustration_selector": ".book-cover img",
  "chapter_link_selector": ".chapter-list a",
  "toc_next_selector": "a.next",
  "chapter_title_selector": "h1",
  "chapter_content_selector": ".chapter-content",
  "remove_selectors": ["script", "style", ".ads", ".share", ".chapter-nav"],
  "same_domain": true,
  "reverse_chapter_order": false,
  "filter_non_chapter_links": true,
  "request_delay_seconds": 1.5,
  "timeout_seconds": 30,
  "max_toc_pages": 50,
  "user_agent": "novel-crawler/0.1",
  "version": 1
}
```

Required: `name`, `start_url`, `chapter_link_selector`,
`chapter_content_selector`. Everything else is optional.

## 2. Translate

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

Resume from progress state (skip chapters marked completed):

```bash
uv run translate my-novel --resume
```

Retry only chapters marked failed:

```bash
uv run translate my-novel --failed-only
```

Translate at most N chapters:

```bash
uv run translate my-novel --limit 10
```

Translate to English:

```bash
uv run translate my-novel --target en
```

List chapters that would be translated without translating:

```bash
uv run translate my-novel --dry-run
```

Enable token-heavier review and summary steps:

```bash
uv run translate my-novel --review --summary
```

Print full AI request/response to console:

```bash
uv run translate my-novel --verbose
```

### Translate flags

| Flag | Description | Default |
| --- | --- | --- |
| `novel` | Novel name (directory in `translated/{novel}/input`) | required |
| `-l, --lang` | Source language: `chinese`, `korean`, `japanese` | auto-detect |
| `-t, --target` | Target language: `vi`, `en` | `TARGET_LANGUAGE` env |
| `-p, --provider` | LLM provider: `ollama`, `gemini`, `openrouter` | `LLM_PROVIDER` env |
| `-r, --review` | Enable review step | `ENABLE_REVIEW` env |
| `-s, --summary` | Enable chapter summary generation | `ENABLE_SUMMARY` env |
| `-v, --verbose` | Print full AI request/response | off |
| `-n, --start` | Start from this chapter number | `0` |
| `-e, --to` | Stop at this chapter number (`0` = all) | `0` |
| `-f, --force` | Re-translate already translated chapters | off |
| `-d, --dry-run` | List chapters without translating | off |
| `-R, --resume` | Skip chapters marked completed | off |
| `-F, --failed-only` | Translate only chapters marked failed | off |
| `-m, --limit` | Translate at most N chapters (`0` = no limit) | `0` |

### Progress and reports

Chapter-level progress is stored in `runtime/progress/{novel}.json` (Vietnamese)
or `runtime/progress/en/{novel}.json` (English):

```json
{
  "completed": [1, 2, 3],
  "failed": [4]
}
```

Per-chapter quality reports are written to
`runtime/reports/{novel}/chapter_NNN.json` (or `runtime/reports/en/...`) with
output char count, elapsed seconds, new terms/characters count, and chunk-level
quality reports.

Use `Ctrl+C` to interrupt gracefully — progress is saved and the run can be
resumed with `--resume`.

## 3. Glossary

Each novel has its own glossary at `runtime/glossary/{novel}.json` (copied from
`translated/{novel}/glossary.json` if present). It stores:

- `terms` — source term → target translation
- `source_language` — detected source language
- `entities` — characters with translated name, role, pronoun, aliases
- `edges` — character relationships `[from, to, type, since_chapter]`
- `address_rules` — per-pair direct address/reference timelines
- `chapter_summaries` — generated when `--summary` is on

List and manage terms:

```bash
uv run glossary list my-novel
uv run glossary add my-novel "原名" "Tên dịch"
uv run glossary remove my-novel "原名"
uv run glossary export my-novel
```

Characters and relationships:

```bash
uv run glossary characters my-novel
uv run glossary character my-novel "李明" --translated-name "Lý Minh" --role protagonist
uv run glossary pronoun my-novel "李明" "anh"
uv run glossary relationship my-novel "李明" "张伟" friend --since 3
```

Validate and audit:

```bash
uv run glossary validate my-novel
uv run glossary audit my-novel
```

`validate` checks the glossary JSON for structural issues. `audit` scans the
translated output for obvious glossary-consistency problems (a term in the
source rendered inconsistently in the target) and prints per-chapter issues.

The translator automatically grows the glossary while translating — new terms
and characters detected in each chapter are merged in and reused for later
chapters, keeping names consistent across the whole book.

## 4. Package

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

### Pack flags

| Flag | Description | Default |
| --- | --- | --- |
| `novel` | Novel name (directory in `translated/`) | required |
| `-f, --format` | `epub`, `pdf`, or `all` | `all` |
| `-t, --title` | Custom book title | from `metadata.json` or novel name |
| `-a, --author` | Author name in metadata | `AI Translator` or `metadata.json` |
| `--target` | Target language to package | `TARGET_LANGUAGE` env |
| `-o, --output` | Custom output directory | per-novel root |
| `--dark` | Dark mode PDF | off |

### Metadata and cover

`pack` reads `translated/<novel>/metadata.json` for the title, author, and
cover image. The cover can be a local path or a URL (`illustration_url`) — URL
covers are downloaded to a temp file and embedded. Illustrations referenced by
markers in the translated text are pulled from
`translated/<novel>/illustrations/` and embedded in both EPUB and PDF.

PDF output uses DejaVu Serif fonts for Vietnamese diacritics. On Linux install
`fonts-dejavu` (or `dejavu-serif-fonts`) if missing.

## Review and summary steps

Two optional, token-heavier steps in the translation workflow:

- **Review** (`--review` or `ENABLE_REVIEW=true`): a second pass scores each
  chunk against the source. Chunks below `REVIEW_THRESHOLD` (default `0.7`) are
  retried up to `MAX_RETRIES` times.
- **Summary** (`--summary` or `ENABLE_SUMMARY=true`): generates a short chapter
  summary stored in the glossary's `chapter_summaries`, used as extra context
  for later chapters.

Both are off by default to keep cost down. Turn them on for higher-quality
literary output, especially with cloud providers.

## Notifications

Set Telegram env vars in `.env` to get a message when a crawl or translation run
finishes (success, failure, or interruption with stats):

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

All three values are required. Set `TELEGRAM_ENABLED=false` to disable notifications without removing credentials.
`TELEGRAM_PARSE_MODE` defaults to `HTML` and messages are escaped accordingly.
Set `TELEGRAM_SILENT=true` to send without a notification sound.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `Config not found for '...'` | Put a JSON config in `configs/{name}.json`, or pass a file path |
| Ollama won't connect | Check Ollama is running, test `curl http://localhost:11434/api/tags` |
| Model not found | Run `ollama list`, then `ollama pull <model-name>` |
| Crawler gets 0 chapters | Run `validate` to check selectors; try `--browser` for JS sites |
| Content extracted too short | Check `chapter_content_selector` and `remove_selectors` with `validate` |
| Vietnamese PDF crashes | Install DejaVu Serif fonts: `apt install fonts-dejavu` |
| Gemini blocked content | Provider sets `BLOCK_NONE` for all safety categories by default |
| Translation stops mid-run | Use `Ctrl+C` for graceful stop, then `--resume` to continue |
| Names inconsistent across chapters | Check `glossary list` and `glossary audit`; add fixed terms with `glossary add` |
