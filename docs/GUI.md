# Web GUI

Browser interface for the `novel-ai-trans` pipeline. The Vue app uses the same
workflows and data as the CLI and is served by FastAPI.

For what each pipeline step does, see [GUIDE.md](GUIDE.md). For provider
setup, see [PROVIDERS.md](PROVIDERS.md).

## Table of contents

- [What the GUI does](#what-the-gui-does)
- [Build and start](#build-and-start)
- [Configuration](#configuration)
- [Local and remote mode](#local-and-remote-mode)
- [Pages](#pages)
- [Jobs, progress, and cancellation](#jobs-progress-and-cancellation)
- [Troubleshooting](#troubleshooting)

## What the GUI does

The GUI supports crawl, import, translation, metadata localization, glossary,
and packaging. Development commands such as `build`, `serve`, and `test`
remain CLI-only.

Only one long-running job may target a novel at a time. Jobs for different
novels may run concurrently; global work such as config generation conflicts
with every active job. The GUI links conflicts to the active job.

The GUI does not replace the CLI; the two share the same `runtime/settings.json`, the
same secret values from `.env`, the same `translated/` directory, and the same
progress files. Stop the server, run CLI commands, and the GUI sees the same
state on next refresh.

## Build and start

Build the production bundle once (writes `web/dist/`, ignored by Git).
Node.js 20+ is required for this step:

```bash
cd web && npm install && cd ..
uv run build
```

Start the API and serve the built GUI on the same origin:

```bash
uv run serve
```

Open `http://127.0.0.1:8000`. The interactive OpenAPI docs are at
`http://127.0.0.1:8000/docs`.

For frontend development with hot reload, run the Vite dev server alongside
the API:

```bash
uv run serve                       # terminal 1
cd web && npm run dev              # terminal 2
```

Vite proxies `/api` to FastAPI, so the browser stays same-origin during
development and CORS does not apply.

### Server flags

Environment variables only — there are no CLI flags for `serve`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_HOST` | `127.0.0.1` | Bind address. Non-loopback values enable remote mode. |
| `API_PORT` | `8000` | TCP port |
| `API_LOG_LEVEL` | `info` | Uvicorn log level |
| `API_SECRET_KEY` | _empty_ | Required when `API_HOST` is not loopback |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated exact origins; wildcards rejected in remote mode |

## Configuration

When `runtime/settings.json` does not exist, the server seeds it from values in
`.env` and falls back to code defaults for missing values. Afterwards it reads
normal application settings from the JSON file. Explicit process environment
variables may still override the JSON for deployment and CI. The Settings page
can update runtime, Telegram, and provider options and persist non-secret
fields to `runtime/settings.json`.
Secrets are never displayed; API keys, Telegram credentials, and
`API_SECRET_KEY` must be edited directly in `.env`.

To start from scratch:

```bash
cp .env.example .env
# runtime/settings.json is created automatically; edit it if needed, then:
uv run serve
```

## Local and remote mode

### Local mode

Default. `API_HOST=127.0.0.1` (or `::1`, `localhost`, anything starting with
`127.`). No authentication, no CORS surprises: every request is treated as
authenticated and the Vite proxy keeps the browser same-origin.

### Remote mode

Triggered by any non-loopback `API_HOST` (for example `0.0.0.0`, a LAN IP, or
a public host name). On startup the server checks:

- `API_SECRET_KEY` is non-empty. The server refuses to start otherwise.
- `CORS_ORIGINS` does not contain `*`. The server refuses to start otherwise.

Every protected endpoint requires `Authorization: Bearer <key>`. The key is
held in memory in the browser only — never in `localStorage`, never in a
query string — and the server applies a constant-time comparison.

Native `EventSource` cannot attach `Authorization` headers, so the GUI uses
a fetch-based SSE client when a token is present. Use HTTPS at a reverse
proxy (nginx, Caddy, or equivalent) for transport security and request-size
limits; the FastAPI process itself does not terminate TLS.

## Pages

| Route | View | Purpose |
| --- | --- | --- |
| `/` | Dashboard | Library overview, totals, and the active job monitor |
| `/novels` | Novels | Novel library, translation progress, creation, and deletion |
| `/novels/:name` | Novel detail | Chapters, glossary, artifacts, rules, metadata, translation, and packing |
| `/novels/:name/chapters/:chapter` | Chapter reader | Read or edit a source or translated chapter |
| `/sources` | Sources | Crawl a website or import an EPUB |
| `/translate` | Translate | Chapter range, language, provider, review, summary, and metadata options |
| `/jobs` | Jobs | Current and recent jobs with their status, results, and logs |
| `/settings` | Settings | Runtime defaults, Telegram behavior, providers, and connection checks |

The sidebar contains Dashboard, Novels, Translate, Sources, Jobs, and Settings.

### Dashboard

Shows the count of novels, total input chapters, total translated chapters,
and a live monitor for active jobs. Quick actions open Translate or Sources.

### Novels

Lists every novel under `TRANSLATED_DIR`. Each row shows its short name, title,
translated/total chapter count for the configured target language, and either
normal or failed status. Clicking the name or title opens Novel detail. Clicking
a failed badge lists the failed chapters.

**Add Novel** creates an empty novel from a required short name plus optional
title, author, source language, uploaded cover, or remote cover URL. **Delete**
permanently removes the novel after confirmation. Deletion is rejected while a
job for that novel is active.

### Novel detail

The header shows the cover, localized title and summary when available, author,
chapter totals, and translated count. Its actions open Translate with the novel
selected, open the Pack dialog, or edit Metadata.

Tabs cover:

- **Chapters**: paginated source chapter numbers, ascending/descending order,
  and an Insert chapter action. Inserting moves that chapter and every later
  source, translation, report, and progress record forward before saving the
  new source text. The reader can switch between source and target text, open
  the table of contents, edit the current text, and delete a source chapter.
  The reader's **Review** action shows output warnings and the latest rejected
  candidate. Complete candidates can be accepted; replacing existing output
  requires confirmation. Partial and empty candidates remain view-only.
- **Glossary**: terms, characters, and relationships. Edits are saved through
  their respective inline editors. When glossary changes affect existing
  translations, Preview & Apply shows proposed replacements, conflicts, and a
  restore action for an applied change.
- **Artifacts**: lists generated EPUBs for the configured target language with
  format, language, chapter count, size, and creation time. Artifacts can be
  downloaded or deleted.
- **Rules**: Markdown-capable translation instructions for this novel. Save
  writes the editor contents; Reload restores the currently saved rules.

The Pack dialog uses the configured target language and accepts optional title
and author overrides for that job.

The **Metadata** dialog edits the source title, author, source URL, uploaded or
remote cover, source summary, source language, and localized title/summary for
the configured target language. **Save metadata** writes manual values. **Save
and translate _language_** saves first and then starts an asynchronous metadata
localization job. **Regenerate existing AI translations** refreshes AI values
whose source has not changed, but never overwrites a value marked as manual.
Clear a manual localized field before localizing if AI should replace it.

The configured target language controls the localized title and summary shown
on the novel list and detail header. The chapter reader similarly selects the
localized title for its current `vi` or `en` view, falling back to the source
title when needed.

### Sources

Sources contains **From Website** and **From EPUB** tabs.

#### From Website

**Crawl** selects a crawl setup by short name, optionally edits and reloads its
JSON, chooses direct/background/visible browser mode, and controls robots.txt,
overwrite behavior, simultaneous downloads, and maximum chapters. Starting the
operation creates a crawl job that can be monitored in place or on Jobs.

**Generate** accepts a novel information URL and produces a reviewable crawl
configuration draft that can be saved, reopened, or deleted.

The GUI does not expose the separate live-selector validation operation. Use
`uv run validate <name>` or `POST /api/configs/{name}/validate` when it is
needed.

#### From EPUB

Select an existing novel or provide a new short name, then choose whether to
keep its current chapters. Import runs as a background job and preserves an
existing summary when re-importing.

### Translate

The form selects the novel, languages, provider, chapter range, retry behavior,
review, summary, and optional title/summary localization. These correspond to
the CLI translation options described in the workflow guide.

The metadata option is separate from `--summary`: the latter
generates short per-chapter memory, while metadata localization translates the
novel's existing source synopsis. If the source title or source summary is
blank, that field is skipped. Enabling it regenerates existing AI-localized
title/summary values but preserves manual values. Metadata localization uses
only glossary terms and known characters that occur in the fields being
translated.

Live progress is streamed over SSE. Reloading reconnects to the job without
interrupting it; REST remains the source of truth for current state.

### Jobs

Lists active and recent jobs with status, progress, result, error, and current
server logs. Inactive jobs can be filtered or deleted.

### Settings

Three panels:

- **Runtime settings**: target language, chunk mode (`Characters` or estimated
  `Tokens`), chunk size, review threshold, and translation temperature. Field
  changes update the runtime snapshot; **Save** persists supported non-secret
  values.
- **Telegram**: enabled flag, API base, parse mode, silent flag, and timeout.
  Credentials are represented only by configured/not-configured status.
- **Providers**: primary and fallback provider, Ollama base URL and model,
  Gemini model and key, OpenRouter model and key, Ollama cloud-account status,
  model refresh, and per-provider connection checks. Blank key inputs preserve
  current keys.

## Jobs, progress, and cancellation

### Lifecycle

```text
queued -> running -> completed
                  -> degraded
                  -> failed
                  -> cancelling -> cancelled
```

Translation batches with failed chapters end as `degraded`; uncaught workflow
or worker errors end as `failed`.

### Cancellation

**Cancel** requests a cooperative stop at a safe point. In-flight LLM and HTTP
calls still finish or time out; a translation returned after cancellation is
not published.

Running translations also show **Force stop**. It terminates the worker and
finishes the job as `cancelled` with `forced: true`. Completed updates may
remain, while incomplete chapter output is discarded.

### Persistence

Finished jobs survive server restarts. Interrupted jobs are marked failed, and
in-memory logs are not restored. Generated config drafts expire after seven
days.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `API_SECRET_KEY must be set when API_HOST is not loopback` | Bind to `127.0.0.1` for local use, or set `API_SECRET_KEY` in `.env` |
| `CORS_ORIGINS must not contain '*' in remote mode` | Replace `*` with the exact origin(s), comma-separated |
| `Another long-running job is already active` (409) | Open the Jobs page to inspect or cancel the active job, or wait for it to finish |
| Vite dev server cannot reach the API | Confirm `uv run serve` is running on `127.0.0.1:8000`; Vite's dev proxy assumes that target |
| `web/dist not present; API will run without the SPA bundle` | Run `uv run build`, then restart `uv run serve` |
| Settings change does not survive a restart | Click **Save** on the Settings page after editing; the edit updates the running process, while Save writes non-secret values to `runtime/settings.json` |
| Reload during translation loses live progress | Reopen the job; its persisted status remains available even if live streaming does not reconnect |
| Cancel button does nothing immediately | An in-flight provider call must return or time out; use **Force stop** for a blocked translation |
| Generated draft disappeared | Drafts expire after seven days and are also removed when consumed by a successful `PUT /api/configs/{name}` or by a manual `DELETE /api/config-drafts/{draft_id}` |
| Localized title is not displayed | Migrate the legacy `translated.<language>` value to `localized.<language>.title` |
| Imported novel has no summary | The EPUB has no `dc:description` or clearly labelled synopsis page; enter the source summary in the novel's Metadata dialog |
