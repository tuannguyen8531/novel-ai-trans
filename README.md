# novel-ai-trans

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Node.js 20+](https://img.shields.io/badge/node-20%2B-green.svg)](https://nodejs.org/)
[![uv](https://img.shields.io/badge/package%20manager-uv-2b2b2b.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Turn web novels or EPUB files into translated EPUB books with LLMs. Crawl or
import a novel, translate its chapters with consistent terminology, and package
the result through a CLI or web interface.

```text
Website / EPUB
    -> source chapters
    -> Ollama, Gemini, or OpenRouter
    -> translated chapters
    -> EPUB
```

## Highlights

- Crawl public novel sites with reusable selector configurations.
- Generate and validate crawl configurations with LLM assistance.
- Import EPUB files while preserving metadata and illustrations.
- Translate Chinese, Korean, and Japanese novels into Vietnamese or English.
- Keep names, terms, pronouns, and relationships consistent with per-novel
  glossary memory.
- Detect incomplete, untranslated, or illustration-damaging output and retry
  automatically.
- Resume interrupted runs, retry failed chapters, or retranslate a range.
- Localize novel titles and summaries and package translated chapters as EPUB.
- Use Ollama locally or Gemini and OpenRouter in the cloud, with optional
  provider fallback.
- Run the complete workflow from either the CLI or the web GUI.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- One supported LLM provider: [Ollama](https://ollama.com/),
  [Gemini](https://aistudio.google.com/apikey), or
  [OpenRouter](https://openrouter.ai/keys)
- Node.js 20+ when building the web GUI
- Playwright Chromium when crawling JavaScript-heavy sites

## Quick start

```bash
git clone https://github.com/tuannguyen8531/novel-ai-trans.git
cd novel-ai-trans

uv sync
cp .env.example .env
```

Configure a provider in `.env`. For example, with a local Ollama server:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

See the [provider guide](docs/PROVIDERS.md) for Gemini, OpenRouter, fallback,
and model settings.

### Use the web GUI

```bash
cd web && npm install && cd ..
uv run build
uv run serve
```

Open <http://127.0.0.1:8000>. The GUI supports importing, crawling,
translation, metadata localization, glossary management, packaging, and job
monitoring.

### Use the CLI

Import and translate an EPUB:

```bash
uv run import ./book.epub --name my-novel
uv run translate my-novel --target vi
uv run pack my-novel --target vi
```

Or generate a configuration and crawl a website:

```bash
uv run generate https://example.com/novel --name my-novel
uv run validate my-novel
uv run crawl my-novel --max 5
uv run translate my-novel --target vi
uv run pack my-novel --target vi
```

Install Chromium before using browser-based crawling:

```bash
uv run playwright install chromium
```

Runtime novel data and generated books are kept together:

```text
translated/<novel>/
├── config.json
├── metadata.json
├── glossary.json
├── rules.md                optional per-novel translation rules
├── input/                  source chapters
├── output/                 Vietnamese chapters
├── output/en/              English chapters
├── illustrations/
└── artifacts/
    ├── <novel>.vi.epub
    └── <novel>.en.epub
```

## Commands

| Command | Purpose |
| --- | --- |
| `uv run generate <url>` | Generate novel metadata and a crawl configuration |
| `uv run validate <novel>` | Validate selectors against the source website |
| `uv run crawl <novel>` | Download source chapters |
| `uv run import <book.epub>` | Import an EPUB into the chapter pipeline |
| `uv run insert <novel> <chapter>` | Insert an empty source chapter before an existing chapter |
| `uv run translate <novel>` | Translate chapters |
| `uv run glossary <command> <novel>` | Manage the per-novel glossary |
| `uv run pack <novel>` | Build a translated EPUB |
| `uv run serve` | Start the API and built web GUI |

Run a workflow command such as `uv run translate --help`, or see the
[complete workflow guide](docs/GUIDE.md) for flags and examples.

## Documentation

| Guide | Contents |
| --- | --- |
| [Workflow guide](docs/GUIDE.md) | Crawl, generate, import, translate, glossary, and packaging |
| [Web GUI](docs/GUI.md) | Build, serve, configure, and operate the browser interface and API |
| [Providers](docs/PROVIDERS.md) | Ollama, Gemini, OpenRouter, fallback, and generation settings |
| [Architecture](docs/ARCHITECTURE.md) | Module ownership and backend/frontend dependency direction |

Configuration starts from [.env.example](.env.example). Runtime logs, progress,
jobs, reports, locks, and crawler state are stored under `runtime/`, separately
from the source code and per-novel data. LLM request, response, and error logs
are rotated by daily folder under `runtime/logs/`. See
[runtime data, cleanup, and upgrades](docs/GUIDE.md#runtime-data-cleanup-and-upgrades)
before removing operational state or rolling out the canonical layout.

Bundled prompt templates and translation-rule fragments live under
`src/prompts/`. The default language and genre rules are packaged from
`src/prompts/rules/`; editable novel-specific rules remain in
`translated/<novel>/rules.md`.

## Development

Apply safe formatting and lint fixes, then run the full validation pipeline:

```bash
uv run test --fix
uv run test
```

After changing the frontend, also run:

```bash
uv run build
```

## License

MIT. See [LICENSE](LICENSE).
