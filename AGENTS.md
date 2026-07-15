# Project instructions

## Project

`novel-ai-trans` crawls or imports novels, translates them with Ollama, Gemini,
or OpenRouter, and packages translated chapters as EPUB files. Python code lives
under `src/`, the Vue frontend under `web/`, and tests mirror the Python layers
under `tests/`.

Runtime novel data belongs under `translated/<novel>/`. Generated books belong
under `translated/<novel>/artifacts/<novel>.<target>.epub`. Progress, jobs,
reports, locks, and crawler state belong under `runtime/`.

## Implementation conventions

- Target Python 3.14 and keep code compatible with the configured Ruff and
  Pyright versions in `pyproject.toml`.
- Use `src.application.config.get_config()` in application workflows and
  worker-reachable code so per-job configuration snapshots are respected.
- Use helpers from `src/paths.py` instead of constructing runtime paths ad hoc.
- Raise application exceptions from `src/application/errors.py`; CLI and API
  adapters own user-facing error responses.
- API request and response models use Pydantic. Domain and application value
  objects may use dataclasses where appropriate.
- Python module filenames must be one descriptive word.
- Put tests in the directory matching the source layer. Mock LLM, HTTP, and
  browser integrations; use `tmp_path` for filesystem behavior.

## Validation

Run the standard validation pipeline:

```bash
uv run test
```

Apply safe Ruff fixes and formatting before validation:

```bash
uv run test --fix
```

Build and type-check the frontend after changes under `web/`:

```bash
uv run build
```

### API tests in the sandbox

Tests under `tests/api/` may hang when run in the sandbox. Start with the normal
validation command. If it stalls during the API tests, after 30 seconds, terminate it and rerun:

```bash
uv run test -- --ignore=tests/api
```

Do not retry to run API tests when it stalls. Report that `tests/api/` was skipped because of the sandbox hang. Do not report
the hang itself as an application failure unless it is reproduced outside the
sandbox. Do not skip other tests unless they independently require unavailable
external services.
