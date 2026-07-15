# Web GUI

Browser interface and HTTP API for the `novel-ai-trans` pipeline. Crawl,
import, translate, glossary, and pack workflows share the same application
layer as the CLI; metadata localization is currently exposed by the GUI/API.
The Vue 3 single-page app is served by FastAPI.

For what each pipeline step does, see [GUIDE.md](GUIDE.md). For provider
setup, see [PROVIDERS.md](PROVIDERS.md).

## Table of contents

- [What the GUI does](#what-the-gui-does)
- [Build and start](#build-and-start)
- [Configuration](#configuration)
- [Local and remote mode](#local-and-remote-mode)
- [Pages](#pages)
- [Jobs, progress, and cancellation](#jobs-progress-and-cancellation)
- [Metadata localization API](#metadata-localization-api)
- [Settings in the browser](#settings-in-the-browser)
- [File and upload safety](#file-and-upload-safety)
- [Troubleshooting](#troubleshooting)

## What the GUI does

The GUI is a thin Vue 3 frontend over a FastAPI service. Pipeline operations
exposed by both adapters call the same application workflows, so a chapter
translated through the GUI is identical to one translated with
`uv run translate`. Metadata localization is the current exception: its
application workflow is started by the GUI/API but has no CLI adapter yet.
Development commands such as `build`, `serve`, and `test` are CLI-only.

```text
 Browser (Vue 3 + Vite)
        |
        | REST + Server-Sent Events
        v
 FastAPI (uvicorn)               src/api/
   /api/...  routes, auth, jobs
        |
        v
 Application workflows           src/application/
   crawl, import, translate, pack, glossary, config
        |
        v
 Domain / services / graph        src/domain/, src/services/, src/graph/
```

Only one top-level long job runs at a time (crawl, config generation, import,
translate, metadata localization, pack, glossary validate, glossary audit).
Read-only endpoints stay available while a job is running. Starting a second
job while one is active returns HTTP 409 with the active job id. The current GUI
displays the conflict; open the Jobs page to inspect or cancel the active job.

The GUI does not replace the CLI; the two share the same `.env`, the same
`translated/` directory, and the same progress files. Stop the server, run
CLI commands, and the GUI sees the same state on next refresh.

## Build and start

Build the production bundle once (writes `web/dist/`, ignored by Git):

```bash
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

The server reads `.env` on startup, the same way the CLI does. Settings
exposed through `GET /api/settings` are split into three groups: general
runtime settings, Telegram notifications, and providers. The Settings page
reads and updates all three. Each group has an explicit save action that writes
its supported fields back to `.env`.

Provider keys, Telegram tokens, and `API_SECRET_KEY` are read from `.env` and
are never returned by the API. The `/api/settings` response only shows
booleans such as `gemini_api_key_configured`. New Gemini and OpenRouter keys
can be entered in the Providers panel; leaving those inputs blank preserves the
current values. Telegram bot credentials and `API_SECRET_KEY` must be edited
directly in `.env`.

To start from scratch:

```bash
cp .env.example .env
# Edit .env, then:
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
| `/novels` | Novels | Per-novel translation progress by target |
| `/novels/:name` | Novel detail | Metadata localization, chapter reader, glossary editor, pack, artifacts |
| `/crawl` | Crawl | Pick or generate a config, then start a crawl |
| `/import` | Import | Upload an EPUB and start an import job |
| `/translate` | Translate | Metadata localization, chapter range, force / failed-only / limit, optional review |
| `/jobs` | Jobs | Current and recent jobs with their status, results, and logs |
| `/settings` | Settings | Read runtime defaults, edit and persist non-secret fields, run provider checks |

### Dashboard

Shows the count of novels, total input chapters, total translated chapters,
and a live monitor for the active job (if any). Quick links jump to Translate,
Import, or Crawl.

### Novels

Lists every novel under `TRANSLATED_DIR`. Each row shows its total input
chapters and translation progress for the configured default target language.
Use **Open** to view its details or **Delete** to permanently remove the novel
directory after confirmation. Deletion is rejected while a job is active.

### Novel detail

The workhorse page. Tabs cover:

- **Chapters**: per-chapter source and per-target output status, with a
  reader for any single chapter.
- **Glossary**: terms, characters, and relationships. Edits are saved through
  the same atomic helpers the CLI uses; bulk term PUT is a merge, not a
  replace. Validation and audit are available through the API and CLI, but are
  not exposed as buttons in the current GUI.
- **Artifacts**: list and download generated EPUB and PDF files for the
  novel.

Pack options are displayed above the tabs rather than as a fourth tab. They can
start an EPUB, PDF, or combined pack job; title, author, target language, and
dark-mode PDF can be overridden per job. The **Translate** action opens the
Translate page with the current novel selected.

The **Metadata** action edits the source title, author, source URL, cover URL,
source novel summary, source language, and localized title/summary values for
Vietnamese and English. Use **Save metadata** for manual values. Use **Save and
translate Vietnamese** or **Save and translate English** to save the form and
start an asynchronous localization job. **Regenerate existing AI translations**
refreshes AI-generated values even when their source has not changed, but never
overwrites a value marked as manual. Clear a manual localized field before
starting localization if AI should replace it.

The configured target language controls the localized title and summary shown
on the novel list and detail header. The chapter reader similarly selects the
localized title for its current `vi` or `en` view, falling back to the source
title when needed.

### Crawl

The Crawl page keeps both config workflows in one place:

1. Pick an existing `translated/<name>/config.json` by novel name.
2. Generate a new one with `POST /api/configs/generate` from the novel's main
   information URL. The job returns a draft id; the draft is loaded into the
   editor for review, and `PUT /api/configs/{name}` writes it to that novel
   directory and consumes the draft.
3. Start a crawl by novel slug. Explicit config paths are not accepted.

The current Crawl page does not expose config validation. Use
`uv run validate <name>` or `POST /api/configs/{name}/validate` when selectors
need to be checked against live HTML. The site config field is named
`chapter_link_selector`, alongside `chapter_content_selector` and
`remove_selectors`.

A successful config save (or a `DELETE /api/config-drafts/{draft_id}`) ends
the draft; unconsumed drafts survive a server restart and expire after
seven days, with cleanup at startup and on each draft listing.

### Import

Streams an EPUB to a temp file (default cap 100 MB), then runs the import
in the background worker. Chapter and illustration counts are reported
when the job finishes. The importer also captures the original novel summary
from OPF `dc:description` or clearly labelled synopsis front matter when
available. Re-import fills only a missing/blank summary and preserves an
existing value. The temp file is deleted even on failure.

### Translate

Includes the CLI chapter flags plus GUI/API-only metadata controls:

| Field | CLI flag | Notes |
| --- | --- | --- |
| Novel | `<novel>` | Required; novel name in `translated/` |
| Source language | `--lang` | Defaults to Auto detect; detected from the glossary when blank |
| Target | `--target` | Defaults to `TARGET_LANGUAGE` |
| Provider | `--provider` | Optional per-run override |
| Start / end | `--start`, `--to` | Inclusive range |
| Force | `--force` | Re-translate even if an output chapter exists |
| Resume | `--resume` | Skip chapters recorded as completed |
| Failed only | `--failed-only` | Retry only chapters that previously failed |
| Limit | `--limit` | Cap the number of chapters this run |
| Review | `--review` | Optional second pass; off by default |
| Summary | `--summary` | Optional per-chapter summary; off by default |
| Translate title and novel summary | GUI/API only | On by default; runs before chapter translation |
| Regenerate AI metadata | GUI/API only | Rebuild AI metadata without overwriting manual values |

The metadata options are intentionally separate from `--summary`: the latter
generates short per-chapter memory, while metadata localization translates the
novel's existing source synopsis. If the source title or source summary is
blank, only that field is skipped. Metadata localization uses only glossary
terms and known characters that occur in the fields being translated.

Live progress is streamed over SSE. Reloading the page does not interrupt
the job — the GUI fetches the authoritative job state, then resumes the
event stream from the current point. On reconnect, any missed events are
reconciled from REST; terminal status (`completed`, `failed`, `cancelled`)
is always observable from `GET /api/jobs/{id}`.

### Jobs

Lists the current job (if any) and the most recent 50 finished jobs from
on-disk history (`runtime/jobs/`). Open any job to see its kind, novel,
timestamps, progress, result, error, and a bounded log tail from the current
server process. Logs are deliberately omitted when jobs are restored from disk
after a restart. The endpoint is the source of truth for terminal state; the
SSE stream is the live view.

### Settings

Three panels:

- **General**: target language, chunk mode (`Characters` or estimated `Tokens`),
  chunk size, chunk overlap, review
  threshold, max retries, review / summary toggles. Changes are sent with
  `PATCH /api/settings`; the persist button calls `POST /api/settings/persist`
  and writes the in-memory values back to `.env` (non-secret fields only).
- **Telegram**: enabled flag, API base, parse mode, silent flag, and timeout.
  Bot token and chat id are only read from `.env` and are represented in the
  GUI by a configured/not-configured status.
- **Providers**: primary and fallback provider, Ollama base URL and model,
  Gemini model and key, OpenRouter model and key. Provider check calls
  `POST /api/providers/check`, which uses a thread pool and is not gated
  by the single-job rule — checks can run while a translate job is in
  flight.

## Jobs, progress, and cancellation

### Lifecycle

```text
queued -> running -> completed
                  -> failed
                  -> cancelling -> cancelled
```

The status diagram is observable in both `GET /api/jobs/{id}` (the source
of truth) and the SSE event stream (the live view).

### Cancellation

`POST /api/jobs/{id}/cancel` sets a cooperative flag. The worker checks
the flag between translation chapters and at safe points in crawl and pack
workflows. In-flight LLM and HTTP calls are not interrupted — they finish or
time out on their own. A translation chapter already in progress finishes
processing before the job stops: successful output is saved, while a quality
or provider failure is recorded in progress.

### Persistence

Job snapshots are written to `runtime/jobs/{job_id}.json`; finished jobs
survive a server restart up to the on-disk retention window. A queued or
running job found after a restart is marked failed because its worker cannot be
resumed. Logs are not restored. Expired files are removed at startup. Generated
config drafts are stored separately under `runtime/config-drafts/` and are kept
for seven days.

### Event contract

Every stream starts with an authoritative `snapshot`. Later event names depend
on the workflow. A translation stream commonly contains:

```text
event: snapshot          data: {"id":"...","status":"running","progress":{...}}
event: started           data: {"job_id":"...","current":0,"total":42}
event: chapter_started   data: {"job_id":"...","chapter":12,"current":7,"total":42}
event: chapter_completed data: {"job_id":"...","chapter":12,"ok":true,"elapsed":3.4,"chars_out":18234}
event: chapter_failed    data: {"job_id":"...","chapter":13,"error":"..."}
event: log          data: {"job_id":"...","level":"info","message":"..."}
event: completed    data: {"job_id":"...","result":{"success":40,"failed":2}}
event: failed       data: {"job_id":"...","error":{"code":"...","message":"..."}}
event: cancelling   data: {"job_id":"..."}
event: cancelled    data: {"job_id":"..."}
```

Tracebacks stay in server logs. Top-level failure events carry the available
error code and message; chapter events may carry the underlying failure text.

## Metadata localization API

Start a standalone metadata localization job with:

```http
POST /api/novels/{name}/metadata/localize
Content-Type: application/json

{
  "target_language": "vi",
  "fields": ["title", "summary"],
  "provider": "ollama",
  "force": false
}
```

`target_language` is required and accepts `vi` or `en`. `fields` defaults to
both fields and may select only `title` or `summary`; a selected field with no
source value is skipped. `provider` is optional. `force` regenerates existing
AI values but does not overwrite manual values. The endpoint returns HTTP 202:

```json
{"job_id": "..."}
```

Track it with `GET /api/jobs/{job_id}` or
`GET /api/jobs/{job_id}/events`. The job result contains `localized` fields
written in this call and a `skipped` list.

`POST /api/translate` accepts two additional optional fields:

```json
{
  "translate_metadata": true,
  "force_metadata": false
}
```

Metadata localization runs before chapter translation. Omitting
`translate_metadata` enables it; explicitly send `false` to retain the old
chapter-only API behavior. A localization failure fails the translation job
before chapter processing begins.

Manual localized values can be written with
`PATCH /api/novels/{name}/metadata`:

```json
{
  "localized": {
    "vi": {"title": "Tên truyện", "summary": "Tóm tắt"}
  }
}
```

These values are recorded with `origin: "manual"`. Send `null` for one nested
field to clear its value and provenance before asking AI to recreate it. The
legacy top-level `translated` field is rejected; migrate legacy values to
`localized.<language>.title`.

## Settings in the browser

General runtime settings use a two-step workflow:

1. **Edit**: `PATCH /api/settings` updates the in-process config snapshot.
   Future jobs in this server use the new values; the running job, if any,
   is unaffected.
2. **Persist**: `POST /api/settings/persist` writes the current snapshot
   back to `.env`. Only general non-secret fields are written by this endpoint.
   `POST /api/settings/providers/persist` writes provider settings and any
   non-empty key entered in the GUI; a blank key preserves its existing value.
   `POST /api/settings/telegram/persist` writes non-secret Telegram behavior
   settings but does not accept the bot token or chat id.

The Provider and Telegram forms apply their runtime changes and persist them in
one save request rather than using the general `PATCH`-then-persist sequence.

Removing provider keys, changing Telegram credentials, or changing
`API_SECRET_KEY` requires editing `.env` and restarting the server.

## File and upload safety

- Novel names and config names used by resource endpoints are validated as
  slugs. Absolute paths, `..`, symlink escapes, and embedded separators are
  rejected by those endpoints.
- Crawl and validation requests accept only a novel slug and resolve its config
  as `translated/<slug>/config.json`.
- Artifact downloads use a filename selected from the server-generated
  list; the client cannot ask for an arbitrary path.
- DELETE for a novel returns 409 while the active job's novel matches,
  to prevent deleting a directory a running job is writing to.
- EPUB uploads stream to a temp file with the configured size cap (default
  100 MB) enforced while reading, not after buffering. The temp file is
  deleted in a `finally` block on success or failure.
- Generated config drafts live outside the job history; restarting the
  server never discards an unsaved draft.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `API_SECRET_KEY must be set when API_HOST is not loopback` | Bind to `127.0.0.1` for local use, or set `API_SECRET_KEY` in `.env` |
| `CORS_ORIGINS must not contain '*' in remote mode` | Replace `*` with the exact origin(s), comma-separated |
| `Another long-running job is already active` (409) | Open the Jobs page to inspect or cancel the active job, or wait for it to finish |
| Vite dev server cannot reach the API | Confirm `uv run serve` is running on `127.0.0.1:8000`; Vite's dev proxy assumes that target |
| `web/dist not present; API will run without the SPA bundle` | Run `uv run build`, then restart `uv run serve` |
| Settings change does not survive a restart | Click **Persist** on the Settings page after editing; the edit updates the running process, persist writes to `.env` |
| Reload during translation loses live progress | The progress bar is restored from `GET /api/jobs/{id}` and the SSE stream is reopened; terminal status is always available even if the stream never reconnects |
| Cancel button does nothing immediately | The job enters `cancelling` immediately; the running translation chapter finishes before it becomes `cancelled` |
| Generated draft disappeared | Drafts expire after seven days and are also removed when consumed by a successful `PUT /api/configs/{name}` or by a manual `DELETE /api/config-drafts/{draft_id}` |
| Localized title is not displayed | Migrate the legacy `translated.<language>` value to `localized.<language>.title` |
| Imported novel has no summary | The EPUB has no `dc:description` or clearly labelled synopsis page; enter the source summary in the novel's Metadata dialog |
