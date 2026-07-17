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
`services/rules.py`, `services/drafts.py`, and the feature packages under
`services/`. Application modules resolve use-case inputs and coordinate those
collaborators.

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

## Cohesive large modules

The Phase 9 review intentionally keeps these modules together:

- `src/domain/characters.py` contains character normalization and relationship
  policies, one domain concern.
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
