# Guide

End-to-end walkthrough of the `novel-ai-trans` pipeline: crawl a site (or import
an EPUB), translate chapters, manage the glossary, and package the result as
EPUB.

For provider setup, see [PROVIDERS.md](PROVIDERS.md).
Use `uv run <command> --help` for the complete, current option list.

## Table of contents

- [Pipeline overview](#pipeline-overview)
- [1. Get source chapters](#1-get-source-chapters)
  - [Crawl a configured site](#crawl-a-configured-site)
  - [Generate a novel config](#generate-a-novel-config)
  - [Validate a config](#validate-a-config)
  - [Import an EPUB](#import-an-epub)
  - [Insert a missing chapter](#insert-a-missing-chapter)
- [2. Translate](#2-translate)
  - [Translation rules](#translation-rules)
  - [Localize title and novel summary](#localize-title-and-novel-summary)
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
                          pack ──> EPUB
```

Source chapters live as zero-padded `chapter_NNN.txt` files under
`translated/<novel>/input/`. Translation output is written to
`translated/<novel>/output/` (Vietnamese) or `translated/<novel>/output/en/`
(English). Packaging reads the output directory and writes
`translated/<novel>/artifacts/<novel>.<target>.epub`.

## 1. Get source chapters

You have two ways to fill `translated/<novel>/input/`: crawl a public site, or
import an existing EPUB.

### Crawl a configured site

Each novel owns its crawl config at `translated/<name>/config.json`. Common
variants are:

```bash
uv run crawl my-novel
```

Limit chapters:

```bash
uv run crawl my-novel --max 10
```

Use Playwright browser mode for JavaScript-heavy pages:

```bash
uv run crawl my-novel --browser --workers 1
```

Preview discovered chapters without writing files:

```bash
uv run crawl my-novel --dry-run
```

Re-download chapter files even if they already exist:

```bash
uv run crawl my-novel --overwrite
```

Ignore `robots.txt` only when you have permission:

```bash
uv run crawl my-novel --ignore-robots
```

Stop on the first chapter error instead of writing partial output:

```bash
uv run crawl my-novel --fail-fast
```

#### Crawl flags

| Flag | Description | Default |
| --- | --- | --- |
| `novel` | Novel slug from `translated/{novel}/config.json` | required |
| `--translated-output` | Per-novel translated root | `TRANSLATED_DIR` |
| `-m, --max` | Stop after this many new chapters | unlimited |
| `--fail-fast` | Stop on first chapter error | off |
| `--ignore-robots` | Skip `robots.txt` check | off |
| `--dry-run` | Only discover and print chapter links | off |
| `--overwrite` | Re-download existing `chapter_NNN.txt` | off |
| `--help` | Show crawl command help | off |
| `-b, --browser` | Use an ephemeral headless browser for JS challenges | off |
| `-h, --headed` | Use a visible browser with a persistent per-domain profile | off |
| `-w, --workers` | Concurrent chapter downloads | `1` |

The two browser modes are intentionally separate and cannot be combined. `-b`
uses a temporary profile on every run. `-h` reuses state per source domain under
`runtime/cache/browser/`. If a site fingerprints headless and headed
sessions differently, use `-h` for the entire crawl instead of expecting its
profile to unblock later `-b` runs.

### Generate a novel config

If no config exists for a novel, let the LLM build one from the novel's main
information/detail URL:

```bash
uv run generate https://example.com/novel --name my-novel
uv run validate my-novel
uv run crawl my-novel
```

The generator first extracts the title, author, cover, summary, and TOC URL from
the novel page. It then inspects the TOC and a sample chapter and proposes a JSON
config with CSS selectors. Review the printed JSON and confirm to save the crawl
settings to `translated/<name>/config.json` and the extracted novel information
to `translated/<name>/metadata.json`. The config keeps only `source_url` so the
crawler can distinguish the main novel page from its `toc_url` TOC page.

Use `generate --help` for provider, browser, cache, template, and output-root
options.

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

Skip crawling by importing an EPUB. Use `--keep-existing` when importing into
an existing novel:

```bash
uv run import ./book.epub --name my-novel
uv run import ./book.epub --name my-novel --keep-existing
uv run import ./book.epub --name my-novel --translated-output ./translated
```

The importer creates chapter files, extracts illustrations, and reads available
title, author, and summary metadata. Re-import preserves manually edited
metadata and, with `--keep-existing`, existing source chapters.

### Insert a missing chapter

Insert an empty source chapter before an existing chapter number:

```bash
uv run insert my-novel 301
```

The command moves that chapter and every later source chapter, translation,
report, progress entry, and chapter-indexed glossary record forward by one. It
then creates an empty `chapter_301.txt` and stores a recovery backup under
`runtime/backups/insertions/`. Fill the new source chapter in the GUI or edit the
file, then translate that chapter explicitly. If a translation already exists,
use `--force`:

```bash
uv run translate my-novel --start 301 --to 301 --force
```

#### Novel config schema

Novel configs live at `translated/<name>/config.json` and use CSS selectors.
Reusable examples remain directly under `configs/`:

```json
{
  "name": "example-public-site",
  "toc_url": "https://example.com/novel/table-of-contents",
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

Required: `name`, `toc_url`, `chapter_link_selector`,
`chapter_content_selector`. Everything else is optional.

## 2. Translate

Translate all untranslated chapters with `uv run translate my-novel`. Common
selections are:

```bash
uv run translate my-novel --lang chinese --provider gemini
uv run translate my-novel --start 20 --to 30
uv run translate my-novel --start 20 --to 20 --force
uv run translate my-novel --resume
uv run translate my-novel --failed-only
uv run translate my-novel --limit 10
uv run translate my-novel --target en
uv run translate my-novel --dry-run
uv run translate my-novel --review --summary
uv run translate my-novel --verbose
```

### Translation rules

The translator builds its rule context from separate Markdown fragments; they
are not merged into the prompt templates:

```text
src/prompts/rules/<target>/common.md
src/prompts/rules/<target>/<source>.md
src/prompts/rules/<target>/<source>/<genre>.md
translated/<novel>/rules.md
```

`<target>` is `vi` or `en`, and `<source>` is `chinese`, `korean`, or
`japanese`. Common rules always apply. Source-language rules are selected from
the detected or requested source language, and genre rules are selected from
the novel metadata. The optional per-novel file is applied last and is the
place for book-specific naming, tone, address, or terminology instructions.

The files under `src/prompts/rules/` are bundled application defaults. Edit
`translated/<novel>/rules.md`—directly or through the GUI Rules editor—for
novel-specific customization. Rule contents are snapshotted at the start of a
translation job, so changes take effect on the next job.

### Localize title and novel summary

Novel title and summary localization is available through the GUI. Open the
novel's **Metadata** dialog and use **Save and translate**, or enable metadata
translation when starting a chapter translation job.

AI-generated values refresh when their source changes. Manually edited values
are preserved; clear one first if it should be regenerated by AI.

### Progress and reports

Chapter-level progress is stored in `runtime/progress/{novel}.json` (Vietnamese)
or `runtime/progress/en/{novel}.json` (English):

```json
{
  "completed": [1, 2, 3],
  "failed": [4]
}
```

Chapter output files are authoritative for completion. The `failed` list is
retry and diagnostic state, so a failed retranslation can leave a chapter in
both lists until it succeeds.

Per-chapter quality state is written to
`runtime/reports/{target}/{novel}/chapter_NNN.json`. One report contains current
output warning codes, ignore decisions, and the latest complete rejected
candidate when one exists.

Token-free checks run on every translated chunk, even when `--review` is off.
Blocking issues such as empty output, substantial untranslated source text,
severe truncation, code fences, or missing illustration markers are retried up
to `MAX_RETRIES`; if they still fail, the chapter is recorded as failed instead
of saving a known-bad translation.

The chapter reader can accept a complete rejected candidate. Acceptance checks
that the browser still refers to the current candidate, asks before replacing
existing output, and clears the chapter's failed state. Partial or empty
candidates cannot be accepted.

Chapter output and its report are published through a recoverable journal under
`runtime/transactions/{target}/{novel}/`. The next translation run recovers an
interrupted publication before selecting chapters.

Press `Ctrl+C` once for graceful cancellation. If the provider remains blocked,
press it again to exit immediately with code `130`. The cancelled chapter is not
published; resume later with `--resume`.

## 3. Glossary

Each novel has its own target-aware glossary at
`translated/{novel}/glossary.json` or `translated/{novel}/glossary.{target}.json`.
It stores:

- `terms` — source term → target translation
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
uv run glossary apply my-novel
uv run glossary apply my-novel --write
uv run glossary dismiss my-novel
uv run glossary rollback my-novel BACKUP_ID
```

`validate` checks the glossary JSON for structural issues. `audit` scans the
translated output for obvious glossary-consistency problems (a term in the
source rendered inconsistently in the target) and prints per-chapter issues.
When a term translation or character `translated_name` changes, `apply`
previews exact old-to-new replacements in existing translated chapters whose
source contains that term/name. Add `--write` to update those chapter files
atomically. Only exact, unambiguous chapter matches are written; missing,
ambiguous, or conflicting matches remain pending for manual review. A successful
write prints a backup ID that can be passed to `rollback`. Use `dismiss` only to
discard pending replacements without changing chapter files. Terms are
capitalized at sentence starts; character names preserve the casing stored in
the glossary. Rebuild EPUB artifacts afterward.

The translator automatically grows the glossary while translating — new terms
and characters detected in each chapter are merged in and reused for later
chapters, keeping names consistent across the whole book.

## 4. Package

Build an EPUB, optionally overriding its metadata or output directory:

```bash
uv run pack my-novel --target vi
uv run pack my-novel --title "My Novel" --author "Author Name" --output ./dist
```

### Metadata and cover

`pack` reads `translated/<novel>/metadata.json` for the title, author, and
cover image. Unless `--title` is supplied, it prefers
`localized.<target>.title`, then the source `title`, then the novel directory
name. The cover can be a local path or a URL (`illustration_url`) — URL covers
are downloaded to a temp file and embedded. Illustrations referenced by markers
in the translated text are pulled from
`translated/<novel>/illustrations/` and embedded in the EPUB.

## Review and summary steps

The deterministic checks described above are always enabled. Two additional,
token-heavier steps are optional:

- **Review** (`--review`): a second pass scores each
  chunk against the source. Chunks below `REVIEW_THRESHOLD` (default `0.7`) are
  retried up to `MAX_RETRIES` times.
- **Summary** (`--summary`): generates a short chapter
  summary stored in the glossary's `chapter_summaries`, used as extra context
  for later chapters.

The LLM review and summary calls are off by default to keep cost down. Turn them
on for higher-quality literary output, especially with cloud providers.
This chapter-summary step is separate from translating the novel-level
`metadata.json` summary described above.

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

A GUI/API translation with failed chapters uses terminal status `degraded`,
but its Telegram notification remains `Status: Failed` and includes the chapter
counts.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `Config not found for novel '...'` | Create `translated/{name}/config.json`, then pass `{name}` to `crawl` or `validate` |
| Ollama won't connect | Check Ollama is running, test `curl http://localhost:11434/api/tags` |
| Model not found | Run `ollama list`, then `ollama pull <model-name>` |
| Crawler gets 0 chapters | Run `validate` to check selectors; try `--browser` for JS sites |
| Content extracted too short | Check `chapter_content_selector` and `remove_selectors` with `validate` |
| Gemini blocked content | Provider sets `BLOCK_NONE` for all safety categories by default |
| Translation stops mid-run | Press `Ctrl+C` once for graceful cancellation, twice for immediate exit `130`, then use `--resume` |
| Names inconsistent across chapters | Check `glossary list` and `glossary audit`; add fixed terms with `glossary add` |
| Imported novel has no summary | The EPUB has no `dc:description` or clearly labelled synopsis page; enter the source summary in the GUI Metadata dialog |
| Old translated title is ignored | Move `translated.<language>` to `localized.<language>.title` in `metadata.json` |
