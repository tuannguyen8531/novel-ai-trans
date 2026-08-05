# Test layout

Tests mirror the source layer they protect:

- `api/`: routes, background jobs, and process workers.
- `application/`: use-case workflows.
- `cli/`: command-line entry points and batch workflow helpers.
- `config/`: environment and runtime configuration.
- `domain/`: pure domain logic.
- `graph/`: LangGraph routing and graph node behavior.
- `models/`: shared state/data model behavior.
- `services/`: providers, persistence, crawling, and packaging.
- `utils/`: small reusable helpers.

Run the standard validation pipeline from the project root:

```bash
uv run test
```

For a focused pytest run:

```bash
uv run pytest tests/domain/ -q
uv run pytest tests/services/test_crawler.py -q
```

When adding tests, put the file in the folder matching the `src/` layer first.
If a test crosses several layers, prefer `cli/` for user-facing workflows or the
highest-level layer that owns the behavior being asserted.
