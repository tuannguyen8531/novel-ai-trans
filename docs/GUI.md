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

At most one top-level long job may run for a given novel (crawl, import,
translate, metadata localization, pack, glossary validate, glossary audit).
Jobs for different novels may run concurrently. A job without a novel, such as
config generation, is global: it conflicts with every active job, and every job
conflicts while it is active. A conflicting submission returns HTTP 409 with
the active job id. Read-only endpoints stay available while jobs are running.
The GUI displays conflicts; open the Jobs page to inspect or cancel the active
job.

Background job ownership lives under `src/api/background/`: the registry owns
active/history state and conflict rules, the runner owns worker threads and log
capture, streaming owns SSE fan-out, and the manager coordinates those pieces
with the filesystem-backed `JobStore`.

The GUI does not replace the CLI; the two share the same `.env`, the same
`translated/` directory, and the same progress files. Stop the server, run
CLI commands, and the GUI sees the same state on next refresh.

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
| `/novels` | Novels | Novel library, translation progress, creation, and deletion |
| `/novels/:name` | Novel detail | Chapters, glossary, artifacts, rules, metadata, translation, and packing |
| `/novels/:name/chapters/:chapter` | Chapter reader | Read or edit a source or translated chapter |
| `/sources` | Sources | Crawl a website or import an EPUB |
| `/translate` | Translate | Chapter range, language, provider, review, summary, and metadata options |
| `/jobs` | Jobs | Current and recent jobs with their status, results, and logs |
| `/settings` | Settings | Runtime defaults, Telegram behavior, providers, and connection checks |

The sidebar contains Dashboard, Novels, Translate, Sources, Jobs, and Settings.
`/crawl` and `/import` are not GUI routes; both source workflows live under
`/sources`.

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
  In the chapter reader, the **Review** item in the `⋮` menu opens current-output
  warnings and the latest rejected candidate; it is not a separate tab. A
  complete, non-empty candidate can be accepted from this dialog; replacing an
  existing translation requires a second explicit confirmation. Acceptance
  publishes atomically, clears the chapter failure, and leaves remaining
  post-check issues as warnings that support Ignore/Restore. Partial and empty
  candidates remain view-only.
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

Sources is one page with **From Website** and **From EPUB** tabs. The selected
tab is local UI state, so the URL remains `/sources` and opening the page starts
on From Website.

#### From Website

A compact **Crawl / Generate** switch changes the website workflow without
changing routes.

**Crawl** selects a crawl setup by short name, optionally edits and reloads its
JSON, chooses direct/background/visible browser mode, and controls robots.txt,
overwrite behavior, simultaneous downloads, and maximum chapters. Starting the
operation creates a crawl job that can be monitored in place or on Jobs.

**Generate** accepts the novel information URL, optional config name and
provider, browser mode, fresh-fetch option, and from-scratch option. Generation
produces a reviewable draft. Drafts can be reopened or deleted and show their
expiry time in `YYYY/MM/DD HH:mm:ss` format. Saving a draft refreshes the setup
list, selects the saved setup, and returns the switch to Crawl.

The GUI does not expose the separate live-selector validation operation. Use
`uv run validate <name>` or `POST /api/configs/{name}/validate` when it is
needed.

#### From EPUB

The EPUB picker and **Keep chapters already in the novel** option share the
first row. An existing novel can be selected by short name, or an optional new
short name can be supplied; when blank, it is derived from the EPUB filename.
The existing-novel selector uses the same `short-name — chapter count` display
style as the other novel selectors.

The upload streams to a temporary file (default cap 100 MB) and then runs as a
background import job. It imports chapters and illustrations and captures an
available source summary from OPF `dc:description` or clearly labelled synopsis
front matter. Re-import fills only a missing source summary and preserves an
existing one. The temporary file is deleted on success or failure.

### Translate

The novel selector uses short names and shows the remaining chapter count.
Source and target language share one 50/50 row, source first. The six options
form a 3-by-2 grid on wide screens and collapse responsively.

The form includes the CLI chapter flags plus a GUI/API metadata option:

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
| Translate title and summary | GUI/API only | Off by default; when enabled, force-localizes AI metadata before chapters |

The metadata option is separate from `--summary`: the latter
generates short per-chapter memory, while metadata localization translates the
novel's existing source synopsis. If the source title or source summary is
blank, that field is skipped. Enabling it regenerates existing AI-localized
title/summary values but preserves manual values. Metadata localization uses
only glossary terms and known characters that occur in the fields being
translated.

Live progress is streamed over SSE. Reloading the page does not interrupt
the job — the GUI fetches the authoritative job state, then resumes the
event stream from the current point. On reconnect, any missed events are
reconciled from REST; terminal status (`completed`, `degraded`,
`failed`, or `cancelled`) is always observable from `GET /api/jobs/{id}`.

### Jobs

Lists active jobs and the most recent 50 finished jobs from on-disk history
(`runtime/jobs/`). Rows show the short job id, kind, novel, status, progress,
and creation time in `YYYY/MM/DD HH:mm:ss` format. The status selector filters
the list, and `degraded` uses an error badge while remaining a
distinct terminal state. Inactive jobs can be deleted individually or together.
Open a job to see progress, result, error, and a bounded log tail from the
current server process. Logs are omitted when jobs are restored from disk after
a restart. The endpoint is the source of truth for terminal state; the SSE
stream is the live view.

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

The status diagram is observable in both `GET /api/jobs/{id}` (the source
of truth) and the SSE event stream (the live view).

Translation batches that return normally but contain one or more failed
chapters end as `degraded`. An uncaught workflow or worker error
ends as `failed`. Telegram keeps the existing user-facing policy and reports a
`degraded` translation as `Failed`, including translated and
failed chapter counts.

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
config drafts are stored separately under `runtime/drafts/` and are kept
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
chapter-only API behavior. The current GUI always sends this field: the
**Translate title and summary** option is off by default, and enabling it sends
both `translate_metadata` and `force_metadata` as `true`. This regenerates
existing AI-localized title and summary values while preserving manual values.
A localization failure fails the translation job before chapter processing
begins.

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

Editing a general runtime field calls `PATCH /api/settings` and updates the
in-process config snapshot. Future jobs use the new value; a running job, if
any, is unaffected. Clicking **Save** calls `POST /api/settings/persist` and
writes that snapshot back to `.env`. Only general non-secret fields are written
by this endpoint.

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
| Settings change does not survive a restart | Click **Save** on the Settings page after editing; the edit updates the running process, while Save writes it to `.env` |
| Reload during translation loses live progress | The progress bar is restored from `GET /api/jobs/{id}` and the SSE stream is reopened; terminal status is always available even if the stream never reconnects |
| Cancel button does nothing immediately | The job enters `cancelling` immediately; the running translation chapter finishes before it becomes `cancelled` |
| Generated draft disappeared | Drafts expire after seven days and are also removed when consumed by a successful `PUT /api/configs/{name}` or by a manual `DELETE /api/config-drafts/{draft_id}` |
| Localized title is not displayed | Migrate the legacy `translated.<language>` value to `localized.<language>.title` |
| Imported novel has no summary | The EPUB has no `dc:description` or clearly labelled synopsis page; enter the source summary in the novel's Metadata dialog |
