# Guide

End-to-end walkthrough of the `novel-ai-trans` pipeline: crawl a site (or import
an EPUB), translate chapters, manage the glossary, and package the result as
EPUB.

For provider setup, see [PROVIDERS.md](PROVIDERS.md).

## Table of contents

- [Pipeline overview](#pipeline-overview)
- [1. Get source chapters](#1-get-source-chapters)
  - [Crawl a configured site](#crawl-a-configured-site)
  - [Generate a novel config](#generate-a-novel-config)
  - [Validate a config](#validate-a-config)
  - [Import an EPUB](#import-an-epub)
- [2. Translate](#2-translate)
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

Each novel owns its crawl config at `translated/<name>/config.json`. Pass only
the novel slug; paths and files outside that location are not accepted:

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
| `-m, --max` | Stop after this many new chapters | `MAX_CHAPTERS` env or unlimited |
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
`runtime/crawler/browser-profiles/`. If a site fingerprints headless and headed
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

```bash
uv run generate <url> --provider gemini        # override provider for generation
uv run generate <url> --browser                # fetch with headless browser
uv run generate <url> --no-cache               # always re-fetch pages
uv run generate <url> --ignore-sample          # ignore bundled templates
uv run generate <url> --translated-output ./translated  # override novel root
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

The importer splits the EPUB into `chapter_NNN.txt` files, extracts illustrations
into `translated/<novel>/illustrations/`, and creates `metadata.json` with the
title, author, and original summary when available. Summary extraction prefers
the OPF `dc:description` value, including escaped HTML descriptions, then falls
back to clearly labelled front matter such as `Synopsis`, `Summary`,
`Description`, `简介`, `あらすじ`, or `줄거리`. A combined
`Author / Tags / Status / Synopsis` information page is also supported. A
summary/front-matter page is not imported as a chapter, and ordinary chapter
text is never treated as the novel summary.

Re-importing the same novel preserves existing metadata. An extracted EPUB
summary fills `summary` only when that field is missing or blank; it never
overwrites an existing or manually edited summary. Import results report
retained chapters, unchanged chapters skipped without rewriting, chapters
overwritten because their content changed, newly added chapters, and chapters
removed when `--keep-existing` is not enabled. Changed overwritten chapters are
listed by number and title.

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

### Localize title and novel summary

Novel-level metadata localization is currently available through the GUI and
HTTP API, not through the `translate` CLI. It translates the source `title`
and/or `summary` stored in `translated/<novel>/metadata.json` into `vi` or `en`.
A missing source field is skipped, so a novel with only an original summary can
still localize that summary.

In the GUI, either:

- Open the novel's **Metadata** dialog and click **Save and translate
  Vietnamese** or **Save and translate English**; or
- Start a translation job with **Translate title and novel summary** enabled.
  This option is on by default and runs before chapter translation.

The localizer filters glossary terms and character memory against only the
title/summary fields being sent. Character aliases are considered, and a
relationship is included only when both characters are active in the source
metadata. This keeps the prompt concise while preserving the same terminology
and character names used by translated chapters.

Each localized field stores provenance in `localization_meta`:

- `origin: "ai"` plus `source_hash` identifies an AI value. It is skipped when
  the normalized source is unchanged and automatically refreshed when the
  source changes.
- `origin: "manual"` identifies a value saved through the Metadata editor. It
  is never overwritten by AI.
- A pre-existing localized value with no provenance is conservatively treated
  like a manual value and skipped.
- **Regenerate AI metadata** ignores a matching source hash for AI values, but
  still preserves manual values. To replace a manual value with AI, clear that
  localized field and use **Save and translate...**.

The persisted schema is:

```json
{
  "title": "Original title",
  "summary": "Original synopsis",
  "localized": {
    "vi": {"title": "Tên truyện", "summary": "Tóm tắt"},
    "en": {"title": "English title", "summary": "English synopsis"}
  },
  "localization_meta": {
    "vi": {
      "summary": {
        "origin": "ai",
        "source_hash": "sha256...",
        "updated_at": "2026-07-14T00:00:00+00:00"
      }
    }
  }
}
```

The old `translated: {"vi": "...", "en": "..."}` title-only structure is
not read and is rejected by the metadata API. Migrate it to
`localized.<language>.title` before relying on the GUI or packager.

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

Token-free checks run on every translated chunk, even when `--review` is off.
Blocking issues such as empty output, substantial untranslated source text,
severe truncation, code fences, or missing illustration markers are retried up
to `MAX_RETRIES`; if they still fail, the chapter is recorded as failed instead
of saving a known-bad translation.

Use `Ctrl+C` to stop gracefully. The chapter currently being processed finishes
and is saved, then the run stops before starting the next chapter. Resume later
with `--resume`.

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

Build an EPUB:

```bash
uv run pack my-novel --target vi
```

Override metadata or output directory:

```bash
uv run pack my-novel --title "My Novel" --author "Author Name" --output ./dist
```

### Pack flags

| Flag | Description | Default |
| --- | --- | --- |
| `novel` | Novel name (directory in `translated/`) | required |
| `-t, --title` | Custom book title | localized target title, source title, or novel name |
| `-a, --author` | Author name in metadata | `AI Translator` or `metadata.json` |
| `--target` | Target language to package | `TARGET_LANGUAGE` env |
| `-o, --output` | Custom output directory | per-novel root |

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

- **Review** (`--review` or `ENABLE_REVIEW=true`): a second pass scores each
  chunk against the source. Chunks below `REVIEW_THRESHOLD` (default `0.7`) are
  retried up to `MAX_RETRIES` times.
- **Summary** (`--summary` or `ENABLE_SUMMARY=true`): generates a short chapter
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

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `Config not found for novel '...'` | Create `translated/{name}/config.json`, then pass `{name}` to `crawl` or `validate` |
| Ollama won't connect | Check Ollama is running, test `curl http://localhost:11434/api/tags` |
| Model not found | Run `ollama list`, then `ollama pull <model-name>` |
| Crawler gets 0 chapters | Run `validate` to check selectors; try `--browser` for JS sites |
| Content extracted too short | Check `chapter_content_selector` and `remove_selectors` with `validate` |
| Gemini blocked content | Provider sets `BLOCK_NONE` for all safety categories by default |
| Translation stops mid-run | Use `Ctrl+C` for graceful stop, then `--resume` to continue |
| Names inconsistent across chapters | Check `glossary list` and `glossary audit`; add fixed terms with `glossary add` |
| Imported novel has no summary | The EPUB has no `dc:description` or clearly labelled synopsis page; enter the source summary in the GUI Metadata dialog |
| Old translated title is ignored | Move `translated.<language>` to `localized.<language>.title` in `metadata.json` |
