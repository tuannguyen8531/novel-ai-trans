# Web GUI and API Implementation Plan

This document is the single implementation plan for adding a FastAPI API and
a Vue 3 web interface to novel-ai-trans.

The implementation must preserve the existing CLI behavior while moving shared
workflow logic out of CLI modules so both CLI and API use the same code paths.

## Goals

- Manage the complete crawl -> import -> translate -> pack workflow in a browser.
- Keep the existing CLI commands and output behavior working.
- Run long operations in a background worker and stream progress with SSE.
- Use one repository with independent Python and JavaScript toolchains.
- Serve the built frontend and API from one FastAPI process for normal use.
- Remain lightweight: no Redis, Celery, WebSocket, SSR framework, or database.
- Be safe by default on localhost and support an explicitly enabled remote mode.

## Non-goals

- Multi-user accounts, permissions, or shared job scheduling.
- Replacing the CLI.
- Persisting the in-memory job history across server restarts.
- Editing secrets or writing back to the .env file from the browser.
- Running multiple top-level long jobs concurrently.
- Interrupting an in-flight HTTP or LLM request; cancellation is cooperative.

## Decisions

| Area | Decision |
| --- | --- |
| Repository | Keep backend and frontend in this repository; frontend lives in web/. |
| Backend | FastAPI with Pydantic request and response schemas. |
| Frontend | Vue 3 + Vite + TypeScript. |
| State | Vue Router + Pinia; native fetch for ordinary requests. |
| Long work | One active long-running job at a time; conflicting starts return 409. |
| Execution | Run synchronous workflows in one background worker thread. |
| Progress | REST for state and SSE for live one-way events. No WebSocket. |
| Job storage | In-memory current job plus a bounded recent-history list. |
| Deployment | FastAPI serves /api and web/dist from the same origin. |
| Local security | Bind to 127.0.0.1 by default; authentication may be disabled. |
| Remote security | Require an API key, explicit CORS origins, and HTTPS at a reverse proxy. |
| UI language | English labels and messages. |

The single-job rule applies to top-level operations such as crawl, generate
config, validate config, import, translate, and pack. Internal crawler workers
may still fetch multiple chapters concurrently.

## Current Code Constraints

The design must account for the current repository rather than treating the CLI
as an API-ready service layer:

- src/cli/translate.py owns argument parsing, the batch translation loop,
  progress printing, signal handling, progress persistence, and notifications.
- src/cli/pack.py contains reusable EPUB and PDF builders mixed with CLI code.
- src/cli/crawl.py contains orchestration and an interactive confirmation in the
  config-generation flow.
- NovelCrawler.crawl already accepts a progress callback, but has no
  cancellation event.
- Translation progress is written to the terminal and has no callback.
- The LLM providers and graph nodes import the mutable global config singleton.
- Provider calls, graph invocation, crawling, EPUB import, and packaging are
  synchronous.

The API must not invoke argparse entry points, replace sys.argv, install signal
handlers in a worker thread, or depend on captured terminal output.

## Architecture

~~~text
 Browser
 Vue 3 + Vite
      |
      | REST + SSE
      v
 FastAPI                          src/api/
 routes, schemas, auth, static serving
      |
      v
 JobManager                      src/api/jobs.py
 one worker, job state, events, cancellation
      |
      v
 Application workflows           src/application/
 crawl, import, translate, pack, config generation
      |
      v
 Domain / services / graph        src/domain/, src/services/, src/graph/

 CLI                              src/cli/
      |
      +-------------------------> same application workflows
~~~

The API and CLI are adapters. Workflow orchestration belongs in
src/application/, while domain logic and external integrations remain under
src/domain/, src/services/, and src/graph/.

## Proposed File Layout

~~~text
novel-ai-trans/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── __main__.py
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── events.py
│   │   ├── jobs.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── system.py
│   │       ├── novels.py
│   │       ├── configs.py
│   │       ├── crawl.py
│   │       ├── translate.py
│   │       ├── pack.py
│   │       ├── glossary.py
│   │       └── jobs.py
│   ├── application/
│   │   ├── __init__.py
│   │   ├── config_context.py
│   │   ├── crawl.py
│   │   ├── errors.py
│   │   ├── import_book.py
│   │   ├── pack.py
│   │   └── translate.py
│   ├── cli/
│   ├── domain/
│   ├── graph/
│   └── services/
├── web/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── src/
│   └── dist/                  generated; ignored by Git
├── runtime/
│   └── config-drafts/         generated config drafts; ignored by Git
├── pyproject.toml
└── uv.lock
~~~

Packaging helpers currently located in src/cli/pack.py should move to an
application or service module. CLI imports may be retained temporarily for
compatibility, but the API must not import CLI entry points.

## Runtime Configuration

### Problem

Config is currently created once from the environment and imported directly by
providers and graph nodes. Creating a cloned Config object in an API dependency
does not isolate a job if downstream code continues reading the global object.

### Design

1. Add Config.clone(**overrides), implemented with dataclasses.replace so normal
   validation still runs.
2. Add get_config() and config_scope(snapshot) under
   src/application/config_context.py using ContextVar.
3. Update worker-reachable services and graph nodes to resolve configuration at
   execution time through get_config(), instead of capturing the global object.
4. Enter config_scope inside the actual worker thread before building providers
   or the translation graph.
5. Worker dispatch uses an explicit copied context so the ContextVar crosses
   the ThreadPoolExecutor boundary:
   `ctx = copy_context(); future = executor.submit(ctx.run, work_fn)`.
   A ContextVar set in the request thread does NOT propagate into a raw
   ThreadPoolExecutor worker without `ctx.run`. For child threads spawned by
   the workflow, pass them through the same copied context.
6. Refactor CLI flags to create a snapshot and call the same application
   workflow. CLI behavior and flags remain unchanged.

Each job receives an immutable configuration snapshot. Missing request fields
fall back to the current server settings, which initially come from .env.

PATCH /api/settings changes only the defaults used by future jobs in the
current process. It does not edit .env and does not affect an already running
job.

Secrets are never returned. Settings responses expose only booleans such as
gemini_api_key_configured and openrouter_api_key_configured.

## Application Errors

The application layer exposes a small exception hierarchy from
src/application/errors.py. CLI and API adapters translate these exceptions into
their own output formats; workflows do not raise HTTPException or call
sys.exit.

~~~python
class ApplicationError(Exception):
    code: str
    public_message: str


class ApplicationValidationError(ApplicationError):
    pass


class ResourceNotFoundError(ApplicationError):
    pass


class ResourceConflictError(ApplicationError):
    pass


class ExternalServiceError(ApplicationError):
    pass


class PersistenceError(ApplicationError):
    pass


class OperationCancelledError(ApplicationError):
    pass
~~~

Each expected exception has a stable machine-readable code and a safe public
message. Internal exception details and tracebacks are attached only to server
logs.

| Application exception | Synchronous API behavior | Background job behavior |
| --- | --- | --- |
| ApplicationValidationError | 422 | failed with a validation error code |
| ResourceNotFoundError | 404 | failed with a not-found error code |
| ResourceConflictError | 409 | failed with a conflict error code |
| ExternalServiceError | 502 or 503 | failed with a provider error code |
| PersistenceError | 500 with a generic message | failed with a storage error code |
| OperationCancelledError | Not used for normal requests | cancelled |
| Unexpected exception | 500 with a generic message | failed with internal_error |

Authentication failures remain API-layer concerns and map to 401 or 403.
Central FastAPI exception handlers perform synchronous mappings. Once an
endpoint has accepted a background job and returned its id, later exceptions
are serialized into Job.error instead of being mapped to a new HTTP response.

## Application Workflows

Application functions use typed request objects and return typed results. They
do not parse arguments, print, call sys.exit, or install signal handlers.

All long workflows accept:

~~~python
progress_callback: Callable[[ProgressEvent], None] | None
cancel_event: threading.Event | None
~~~

### Translation

Extract the chapter-selection and batch loop from translate_main into
run_translation().

The workflow:

- Applies start, end, force, resume, failed-only, and limit selection.
- Builds the graph after entering the job config scope.
- Emits started, chapter_started, chapter_completed, and progress events.
- Saves completed or failed chapter state after every chapter.
- Checks cancel_event before starting each chapter.
- Finishes the current graph invocation before honoring cancellation.
- Returns structured totals and failure details.

ProgressTracker and terminal output stay in the CLI adapter. The API supplies an
event callback instead.

### Crawl

Keep NovelCrawler.crawl as the main service entry point.

- Continue using its existing progress callback.
- Add an optional cancel_event.
- Stop scheduling new chapters when cancellation is requested.
- Allow in-flight fetches to finish or time out.
- Persist the manifest with cancelled status.
- Preserve the existing internal workers option.

### Config generation and validation

Do not call the interactive CLI generation function.

- ConfigGenerator.generate creates a draft but never writes into configs/.
- Store each draft atomically at runtime/config-drafts/{draft_id}.json.
- The draft contains its id, creation and expiry timestamps, source URL,
  suggested name, and generated config document.
- The generation job result returns draft_id and suggested_name, not the only
  copy of the generated JSON.
- The browser loads the draft, lets the user edit it, and sends the complete
  edited JSON to PUT /api/configs/{name}.
- A successful save optionally consumes and removes the associated draft.
- Keep drafts for seven days by default and remove expired drafts during server
  startup and draft listing.
- Validation runs as a job because browser and network validation may be slow.

Draft persistence is intentionally separate from job history. A server restart
may discard jobs, but it must not discard a generated config draft that has not
yet been reviewed.

### EPUB import

- Stream an uploaded EPUB into a temporary file.
- Enforce a configurable maximum upload size; default 100 MB.
- Run import_epub in the background worker.
- Delete the temporary upload in a finally block.
- Emit chapter and illustration counts as the result.

### Pack

Extract reusable packaging orchestration from the CLI.

- Support EPUB, PDF, or both.
- Emit phase-level progress.
- Return generated artifact names and sizes.
- Never accept an unrestricted output filesystem path from the API. API pack
  has no output parameter; artifacts always write to the novel root. CLI keeps
  --output.
- Cancellation is best-effort: checked between EPUB and PDF phases only. A
  running PDF generation completes before honoring cancel.

## Job Manager

### Job model

~~~python
@dataclass
class JobError:
    code: str
    message: str
    details: dict | None = None


@dataclass
class Job:
    id: str
    kind: str
    novel: str | None
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    progress: dict
    result: dict | None
    error: JobError | None
    logs: deque[str]
    cancel_event: threading.Event
~~~

Status values:

~~~text
queued -> running -> completed
                  -> failed
                  -> cancelling -> cancelled
~~~

### Concurrency

- One dedicated executor with max_workers=1 executes top-level jobs.
- Starting a job while one is queued, running, or cancelling returns 409.
- The response includes the active job id so the GUI can navigate to it.
- Read-only endpoints remain available while a job runs.
- Keep only the latest configurable number of finished jobs, default 50.

### Events and thread safety

Worker callbacks run outside the API event-loop thread. They must not write
directly to asyncio.Queue.

The event publisher captures the server loop and uses:

~~~python
loop.call_soon_threadsafe(queue.put_nowait, event)
~~~

The REST job state is authoritative. SSE supplies live updates; after a reload
or reconnect, the frontend first fetches GET /api/jobs/{id} and then resumes
the stream. The stream is forward-only; no Last-Event-ID replay is attempted.
Missed events are reconciled via REST. Terminal status (completed, failed,
cancelled) is always observable via GET /api/jobs/{id} so no terminal event is
lost on disconnect.

### SSE event contract

~~~text
event: started
data: {"job_id":"...","kind":"translate","novel":"book","total":42}

event: progress
data: {"job_id":"...","current":7,"total":42,"chapter":12,"pct":16.67}

event: chapter
data: {"job_id":"...","chapter":12,"ok":true,"elapsed":3.4,"chars_out":18234,"new_terms":2}

event: log
data: {"job_id":"...","level":"info","message":"..."}

event: completed
data: {"job_id":"...","result":{"success":40,"failed":2}}

event: failed
data: {"job_id":"...","error":{"code":"provider_unavailable","message":"Translation provider is unavailable."}}

event: cancelling
data: {"job_id":"..."}

event: cancelled
data: {"job_id":"..."}
~~~

Send periodic comment heartbeats so proxies do not close idle streams. Detailed
exceptions stay in server logs; API errors contain a concise safe message.

## API Surface

All application routes use the /api prefix. Use job consistently; do not mix
job and task terminology.

### System and settings

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/health | Server health and current job summary. |
| GET | /api/settings | Non-secret runtime defaults and configured-provider flags. |
| PATCH | /api/settings | Change defaults for future jobs in this process. |
| GET | /api/providers | Configured providers and model names. |
| POST | /api/providers/check | Check one provider. Runs via FastAPI run_in_threadpool, NOT the single job executor; never 409s against an active job. |

### Novels and chapters

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/novels | List novels with per-target input, output, failed, and progress counts. |
| GET | /api/novels/{name} | Metadata, language, progress, glossary stats, and artifacts. |
| GET | /api/novels/{name}/chapters | Chapter list with source and per-target output status. |
| GET | /api/novels/{name}/chapters/{number} | Source or translated content using view and target query parameters. |
| DELETE | /api/novels/{name} | Delete one validated novel directory. |
| GET | /api/novels/{name}/artifacts | List generated EPUB and PDF files. |
| GET | /api/novels/{name}/artifacts/{filename} | Download one validated artifact. |

### Crawler configs

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/configs | List configs under configs/. |
| GET | /api/configs/{name} | Return one config JSON document. |
| PUT | /api/configs/{name} | Validate and atomically save a config JSON document. |
| POST | /api/configs/generate | Start config generation and return a job id. |
| POST | /api/configs/{name}/validate | Start selector validation and return a job id. |
| GET | /api/config-drafts | List non-expired generated drafts. |
| GET | /api/config-drafts/{draft_id} | Return one generated draft for review. |
| DELETE | /api/config-drafts/{draft_id} | Discard one generated draft. |

Generation returns a draft id in the job result and does not save automatically.
PUT /api/configs/{name} accepts the complete edited config plus an optional
draft_id. It validates and atomically saves the config before deleting that
draft.

### Pipeline operations

| Method | Path | Description |
| --- | --- | --- |
| POST | /api/crawl | Start a crawl job. |
| POST | /api/import | Upload an EPUB and start an import job. |
| POST | /api/translate | Start a translation job. |
| GET | /api/novels/{name}/translation-progress | Read durable progress for a target. |
| POST | /api/pack | Start an EPUB or PDF packaging job. |

### Glossary

Glossary endpoints are nested under their novel to keep resource ownership
clear.

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/novels/{name}/glossary | Full normalized glossary. |
| PUT | /api/novels/{name}/glossary/terms | Bulk merge terms. |
| POST | /api/novels/{name}/glossary/terms | Add or update one term. |
| DELETE | /api/novels/{name}/glossary/terms/{original} | Remove one URL-encoded source term. |
| GET | /api/novels/{name}/glossary/characters | List character entities. |
| PUT | /api/novels/{name}/glossary/characters/{original} | Update name, role, or pronoun. |
| POST | /api/novels/{name}/glossary/relationships | Add or update a relationship. |
| POST | /api/novels/{name}/glossary/validate | Validate glossary structure. Returns 202 + job id. |
| POST | /api/novels/{name}/glossary/audit | Audit translated output for one target. Returns 202 + job id; audit scans all output chapters and is too slow for a synchronous response. |

Glossary writes use existing atomic, thread-safe service helpers. Bulk PUT
means merge, not replacement, unless a future endpoint explicitly exposes
replacement semantics.

### Jobs

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/jobs | Current and recent jobs. |
| GET | /api/jobs/{id} | Authoritative job state, result, error, and bounded logs. |
| GET | /api/jobs/{id}/events | SSE progress stream. |
| POST | /api/jobs/{id}/cancel | Request cooperative cancellation. |

### Error shape

Use a consistent caller-visible error:

~~~json
{
  "error": {
    "code": "job_conflict",
    "message": "Another job is already running.",
    "details": {"active_job_id": "..."}
  }
}
~~~

Do not return tracebacks, provider secrets, raw environment values, or
unrestricted filesystem paths.

## Filesystem Safety

- Novel and config names are slugs, never arbitrary paths.
- Resolve every target and verify it remains below the configured root.
- Reject absolute paths, path separators, dot segments, and symlink escapes.
- DELETE /api/novels/{name} returns 409 when the active job's novel matches,
  to prevent deleting a directory a running job is writing to.
- Artifact downloads use a filename selected from the server-generated list.
- Writes use temporary files and atomic replacement where practical.
- EPUB upload size is checked while streaming, not after buffering the file.
- Temporary uploads are always cleaned up.
- DELETE affects only one validated novel directory.

## Authentication and Deployment

### Local mode

Defaults:

~~~env
API_HOST=127.0.0.1
API_PORT=8000
API_SECRET_KEY=
CORS_ORIGINS=http://localhost:5173
~~~

The Vite development server proxies /api to FastAPI, so browser requests can
normally stay same-origin and avoid CORS. CORS_ORIGINS applies only when the
frontend origin differs from the API: a split deploy, or accessing the Vite
dev server directly at its own origin while pointing fetch at the API. Same-
origin requests via the Vite proxy or production static serving ignore CORS.
In production, FastAPI serves both the API and built assets from one origin.

### Remote mode

When API_HOST is non-loopback:

- Refuse startup unless API_SECRET_KEY is non-empty.
- Require an exact CORS allowlist; never use a wildcard.
- Put HTTPS and request-size limits at nginx, Caddy, or another reverse proxy.
- Compare keys with a constant-time comparison.
- Protect API and SSE endpoints; health may expose only a minimal status.

The browser sends Authorization: Bearer <key>. Native EventSource cannot attach
that header, so remote mode uses a fetch-based SSE client. Do not put the key in
a query string. Do not persist it in localStorage; keep it in memory for the
browser session.

API responses never return or partially reveal API_SECRET_KEY or provider keys.

## FastAPI Application and Static Frontend

src/api/app.py provides create_app() and the app object used by tests and
Uvicorn. src/api/__main__.py owns host, port, and server startup.

Register /api routes before static frontend handling.

Production behavior:

- Serve hashed Vite assets from web/dist/assets.
- Serve web/dist/index.html at /.
- For non-API browser routes such as /novels/book, return index.html so Vue
  Router can handle the route after a refresh.
- Never let the SPA fallback consume /api, /docs, or /openapi.json.
- If web/dist is absent, keep the API usable and return a clear message at /.

Python dependencies:

~~~toml
"fastapi>=0.115"
"uvicorn>=0.32"
"sse-starlette>=2.2"
"python-multipart>=0.0.18"
~~~

sse-starlette is required. It handles SSE framing, keepalive comments, and
correct Content-Type; do not hand-roll a StreamingResponse for the event
stream.

Add:

~~~toml
[project.scripts]
serve = "src.api.__main__:main"
~~~

Also add serve to the top-level main.py dispatcher for command consistency.

## Vue Frontend

### Setup

Create a TypeScript Vite application under web/:

~~~bash
npm create vite@latest web -- --template vue-ts
~~~

Runtime dependencies:

- vue
- vue-router
- pinia
- a locally bundled Inter variable-font asset

Use native fetch for REST. Implement a small fetch-based SSE wrapper or use one
focused SSE client package if correct parsing and reconnect behavior would
otherwise be duplicated. Do not add a general utility library until the UI
needs it.

### Routes

| Route | View | Purpose |
| --- | --- | --- |
| / | DashboardView | Novel totals, current job, and quick actions. |
| /novels | NovelListView | Novels and translation progress by target. |
| /novels/:name | NovelDetailView | Chapters, glossary, artifacts, and pack actions. |
| /crawl | CrawlView | Config selection, generation, validation, and crawl form. |
| /import | ImportView | EPUB upload and import options. |
| /translate | TranslateView | Translation options and current progress. |
| /jobs | JobListView | Current and recent job history. |
| /settings | SettingsView | Non-secret runtime settings and provider checks. |

### State and composables

~~~text
web/src/
├── api/
│   ├── client.ts
│   └── sse.ts
├── assets/
│   └── fonts/
│       └── InterVariable.woff2
├── router/
├── stores/
│   ├── novels.ts
│   ├── jobs.ts
│   └── settings.ts
├── components/
│   ├── JobMonitor.vue
│   ├── ChapterReader.vue
│   ├── GlossaryEditor.vue
│   ├── CrawlForm.vue
│   ├── ImportForm.vue
│   ├── TranslateForm.vue
│   └── PackForm.vue
└── views/
~~~

The jobs store fetches authoritative state before opening an SSE stream and
re-fetches state after reconnect or terminal events.

### UI scope

MVP UI prioritizes function over visual polish:

- Responsive sidebar and content layout.
- Accessible forms, tables, dialogs, progress bars, errors, and confirmations.
- Dark theme by default with an optional light theme through CSS variables.
- Persist the theme preference in localStorage; it contains no secret data.
- Bundle the Inter variable font locally with a system-font fallback.
- Do not require Google Fonts or any other runtime font request.
- Minimal transitions and no mandatory glassmorphism or animation framework.

Deferred UI features:

- Direct translated-chapter editing.
- CSV glossary import and export.
- Quality score charts.
- Bulk operations across novels.
- Advanced animation and visual themes.

## Implementation Phases

Each phase must keep existing tests, Ruff, and Pyright green.

### Phase -1: Test coverage audit and behavior lock

Do not begin the application-layer extraction until this gate is complete.

1. Add pytest-cov to the development dependency group.
2. Record line and branch coverage for src/cli/translate.py,
   src/cli/crawl.py, and src/cli/pack.py.
3. Build a behavior matrix covering CLI inputs, observable outputs, exit codes,
   filesystem changes, progress files, reports, and notifications.
4. Add characterization tests for uncovered behavior that Phase 0 will move.
5. Run the full test suite and store the baseline commands and results in the
   implementation handoff or pull request.

Required characterization coverage:

- Translation flag mapping and chapter selection for start, to, force, resume,
  failed-only, and limit.
- Success, failure, skip, and cancellation progress persistence.
- Provider, target, review, and summary configuration overrides.
- Crawler option mapping, progress, existing interruption behavior, and
  notification outcomes.
- Config generation accept, reject, and save behavior.
- Pack format, target, title, author, cover, dark mode, output naming, and
  missing-input behavior.
- CLI return codes and caller-visible messages for expected failures.

There is no arbitrary 100 percent target. Phase 0 may start only when every
behavior it will move is represented in the matrix and protected by a test.
Coverage for affected modules must not fall below the recorded baseline during
the refactor.

### Phase 0: Shared application layer

0. Audit every module importing config for top-level attribute binding (module
   constants, default-argument values, class-level attributes). Only call-site
   reads are safe with get_config(); bound values at import time silently keep
   the old global. List and fix offenders before extracting workflows.
1. Add the application exception hierarchy and adapter mappings.
2. Add config cloning, config scope, and execution-time config access.
3. Extract translation orchestration into run_translation().
4. Extract packaging orchestration from CLI code.
5. Add progress and cancellation parameters.
6. Adapt CLI modules to the shared workflows without changing their interface.

This phase removes the largest architectural risk before FastAPI is introduced.
Move one workflow at a time and run its characterization tests after each
extraction.

### Phase 1: API foundation and job infrastructure

1. Add minimal FastAPI dependencies and uv run serve.
2. Add create_app(), health endpoint, schemas, and error handling.
3. Implement the single-active JobManager.
4. Implement thread-safe SSE events and cancellation. Attach a per-job logging
   Handler inside the worker context so log events mirror captured records into
   Job.logs and SSE; remove the handler when the job ends.
5. Prove the job lifecycle with a deterministic test job.

### Phase 2: Translation vertical slice and minimal GUI

1. Add novel listing and translation-progress endpoints.
2. Add POST /api/translate and all job endpoints.
3. Scaffold Vue 3 + Vite + TypeScript.
4. Add the locally bundled Inter font and default dark theme.
5. Build a minimal novel selector, translate form, and JobMonitor.
6. Verify start, live progress, reload recovery, failure, and cancellation.

This produces a useful GUI early and validates the hardest integration.

### Phase 3: Crawl, config, and import

1. Add durable config-draft storage, expiry cleanup, and draft endpoints.
2. Add config list, detail, save, generation, and validation.
3. Add crawl jobs with progress and cooperative cancellation.
4. Add streamed EPUB upload and import jobs.
5. Add CrawlView and ImportView.

### Phase 4: Chapters, glossary, pack, and artifacts

1. Add chapter listing and source/translated reading.
2. Add glossary CRUD, validation, and audit.
3. Add pack jobs, artifact listing, and safe downloads.
4. Complete NovelDetailView and its tabs.

### Phase 5: Deployment and polish

1. Add remote-mode auth enforcement and fetch-based authenticated SSE.
2. Add production Vue build serving and SPA fallback.
3. Add explicit CORS configuration and deployment documentation.
4. Improve accessibility, responsive layout, and error presentation.

## Verification Plan

### Automated backend checks

~~~bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest tests/
uv run pytest --cov=src.cli --cov-branch --cov-report=term-missing tests/cli/
~~~

Add tests for:

- The Phase -1 behavior matrix and recorded CLI coverage baseline.
- Existing CLI behavior after application-layer extraction.
- Application exception types, stable error codes, and adapter mappings.
- Config snapshot isolation and restoration after failures.
- API lifespan startup through a TestClient context manager.
- Single-job 409 response and active job id.
- Job state transitions and bounded history.
- Cross-thread progress publication and SSE event ordering.
- Cooperative cancellation and durable translation progress.
- Crawler cancellation without scheduling new work.
- Secrets omitted from every settings response.
- Remote-mode startup rejection without a key.
- Path traversal, absolute path, and symlink escape attempts.
- Upload size enforcement and temporary-file cleanup.
- Generated config draft persistence, reload recovery, expiry, cleanup, and
  explicit save.
- Artifact allowlisting and downloads.
- SPA fallback without shadowing API or documentation routes.

### Frontend checks

~~~bash
cd web
npm run build
~~~

Add focused component or store tests when behavior becomes non-trivial,
especially for job reconnect, terminal events, forms, and glossary editing.

### Manual smoke test

1. Start the API with uv run serve and check /api/health and /docs.
2. Start Vite and verify the /api proxy.
3. Import an EPUB through the GUI.
4. Translate a small chapter range and observe SSE progress.
5. Reload during translation and verify state recovery.
6. Request cancellation and verify it stops before the next chapter.
7. Edit a glossary term and verify the stored JSON.
8. Pack EPUB and PDF and download both artifacts.
9. Build web/dist and verify FastAPI serves direct and refreshed Vue routes.
10. Stop every temporary server started for verification.

## Acceptance Criteria

- One uv run serve command serves API and the built GUI.
- Existing crawl, generate, validate, import, translate, glossary, and pack CLI
  commands retain their behavior.
- The GUI completes import -> translate -> pack without shell access.
- Only one top-level long job runs at a time.
- Live progress, reconnect, failure, and cooperative cancellation work.
- Phase 0 workflow behavior is protected by characterization tests and does not
  regress the recorded CLI coverage baseline.
- Per-job provider and target overrides do not leak into later jobs.
- Generated config drafts survive a server restart until saved, discarded, or
  expired.
- No API response exposes provider keys or the server API key.
- Filesystem endpoints cannot escape their configured roots.
- No Redis, Celery, database, WebSocket, or SSR runtime is required.
