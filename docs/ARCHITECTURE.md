# Architecture and ownership

This document defines the final module ownership rules for contributors. The
rules are enforced where possible by `tests/architecture/test_dependencies.py`.

## Backend dependency direction

```text
CLI / API adapters -> application workflows -> infrastructure services
                              |
                              v
                         domain rules
```

- `src/domain/` owns pure policies and imports only domain modules.
- `src/application/` owns use-case coordination and application errors. It may
  depend on domain rules and infrastructure collaborators, but does not perform
  raw filesystem persistence or depend on API/CLI adapters.
- `src/services/` owns HTTP, browser, filesystem, provider, logging, packaging,
  import, crawl, and repository implementations. It may depend on domain types,
  but not on application, graph, API, or CLI modules.
- `src/graph/` is translation infrastructure. It may use domain rules and
  services, but never application, API, or CLI modules.
- `src/api/routes/` and ordinary `src/cli/` commands translate transport input
  and output and enter the system through application workflows.

The two presentation-owned CLI modules `src/cli/logging.py` and
`src/cli/notifications.py` are the only adapter modules allowed to call their
corresponding console/notification infrastructure directly. Keeping those
side effects in explicit presentation owners avoids leaking them into use-case
workflows.

Raw persistence is implemented by focused repositories and services such as
`services/documents.py`, `services/catalog.py`, `services/artifacts.py`,
`services/rules.py`, and the capability packages under `services/`.
Translation storage, checkpoints, and reports live under
`services/translation/`; glossary persistence, memory, and backups live under
`services/glossary/`; generated config drafts live with the other config
generation collaborators under `services/generation/`. Application modules
resolve use-case inputs and coordinate those collaborators. Operational LLM
request, response, and error logs live under `runtime/logs/`; their writer and
daily retention policy remain owned by `services/logger.py`.

Runtime state uses one canonical layout:

```text
runtime/
├── backups/
│   ├── insertions/
│   └── replacements/
├── cache/
│   ├── browser/
│   └── discovery/
├── drafts/
├── jobs/
├── locks/
├── logs/
├── manifests/
├── progress/
├── reports/
└── transactions/
    ├── en/
    └── vi/
```

Crawler manifests belong to `manifests/`; browser profiles and fetched pages
are disposable cache. Translation warnings deliberately depend on `reports/`
and may disappear when runtime state is cleaned. Glossaries and translated
chapter output are durable novel data and therefore stay under
`translated/<novel>/`.

Recoverable chapter-publication journals use
`transactions/<target>/<novel>/<transaction-id>.json`. Output and report stage
files remain beside their destinations so each final replacement is atomic on
its own filesystem. Each transaction writes its journal once; recovery infers
the commit state from content hashes. Progress has no staged copy because its
completed set is reconstructed from published output and saved atomically.

## Prompt assets and translation rules

All bundled text sent to an LLM lives under `src/prompts/` so it is anchored to
the installed package instead of the process working directory:

```text
src/prompts/
├── detect.md
├── en/                         English-target prompt templates
├── vi/                         Vietnamese-target prompt templates
└── rules/
    ├── en/
    │   ├── common.md
    │   ├── <source>.md
    │   └── <source>/<genre>.md
    └── vi/
        ├── common.md
        ├── <source>.md
        └── <source>/<genre>.md
```

Prompt templates and translation rules remain separate assets. The prompt
renderer owns `{{variable}}` substitution, while `services/rules.py` loads a
static rule snapshot and `services/genres.py` discovers and validates genre
profiles. A translation job assembles rules in this order:

1. target-language common rules;
2. source-language rules for that target;
3. selected source-language genre profiles;
4. optional `translated/<novel>/rules.md`.

Bundled rules are version-controlled application resources and are included in
the Python wheel. Per-novel `rules.md` is mutable user data and must remain
under the novel root. Both prompt templates and rule files are snapshotted
within a translation job so edits affect the next job, not a job already in
progress.

## Frontend dependency direction

```text
route views -> feature components
     |
     v
composables -> API client -> REST / SSE
```

- Route views coordinate routing, tabs, dialogs, and form intent.
- Feature components render one interaction and emit user intent.
- `web/src/composables/` owns asynchronous state, REST/SSE calls, and shared
  Pinia state. Components and views never import the API transports directly.
- `web/src/api/` owns transport primitives and API types.
- `App.vue` may configure the authentication token, but does not execute an
  asynchronous use case.

## Background job semantics

`src/api/background/registry.py` is the single owner of job conflicts:

- only one active job may target a given novel;
- jobs for different novels may run concurrently;
- a job without a novel is global and conflicts with every active job in both
  directions.

The runner owns worker threads and configuration context, streaming owns SSE
fan-out, the filesystem `JobStore` owns persistence, and the manager only
coordinates those collaborators.

Callbacks normally return a public result dictionary. A callback that needs a
non-default successful terminal state returns a typed `JobOutcome` containing
that result and its terminal status. Translation uses this contract for
`degraded`; the runner, rather than inspecting arbitrary result
keys, owns the final status, terminal SSE event, and persisted snapshot.

## Cohesive modules

Character policies are separated by independently changing domain concern:

- `src/domain/entities.py` owns character identity, aliases, and name matching;
- `src/domain/relationships.py` owns directed relationship rules;
- `src/domain/addressing.py` owns stable direct-address timelines;
- `src/domain/candidates.py` owns provisional address-rule confirmation;
- `src/domain/context.py` composes persisted and active character context;
- `src/domain/formatting.py` serializes that context for LLM prompts.

Other intentionally cohesive modules include:

- `src/graph/nodes/learner.py` owns the learner graph step: extracting and
  normalizing learned terms, entities, relationships, and summaries.
- `src/api/schemas.py` owns API request and response contracts.

They should be split only when independently changing policies emerge, not to
meet a line-count target.

## Enforcement

The standard `uv run test` pipeline runs static architecture tests that reject:

- forbidden backend layer imports and import cycles;
- direct raw persistence in application modules;
- `print()` calls in domain, graph, and service infrastructure;
- API/SSE imports outside frontend composables and the API transport;
- reintroduction of superseded pre-refactor modules.

Architecture checks complement review. They cannot prove that an adapter is
semantically thin or that a module has only one reason to change, so new use
cases still require ownership review.
