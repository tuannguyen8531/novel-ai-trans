# Providers

`novel-ai-trans` supports three LLM providers. Pick one in `.env` via
`LLM_PROVIDER`, and optionally pair it with a different `FALLBACK_PROVIDER` for
automatic failover.

| Provider    | Type   | Get started                                         |
| ----------- | ------ | --------------------------------------------------- |
| **Ollama**  | Local  | [ollama.com](https://ollama.com/)                   |
| **Gemini**  | Cloud  | [Google AI Studio](https://aistudio.google.com/apikey) |
| **OpenRouter** | Cloud (200+ models) | [openrouter.ai/keys](https://openrouter.ai/keys) |

You can also override the provider per run with `translate --provider <name>` or
`generate --provider <name>`.

## Table of contents

- [Ollama](#ollama)
- [Gemini](#gemini)
- [OpenRouter](#openrouter)
- [Fallback provider](#fallback-provider)
- [Choosing a model](#choosing-a-model)
- [Tuning generation](#tuning-generation)

## Ollama

Local, free, nothing leaves your machine. Best for privacy and for testing.

1. Install [Ollama](https://ollama.com/).
2. Pull a model:

   ```bash
   ollama pull qwen3:8b
   ```

3. Configure `.env`:

   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen3:8b
   ```

4. Verify it is running:

   ```bash
   curl http://localhost:11434/api/tags
   ```

### Remote Ollama

Point `OLLAMA_BASE_URL` at any reachable Ollama instance (e.g. a GPU server on
your LAN):

```env
OLLAMA_BASE_URL=http://192.168.1.10:11434
OLLAMA_MODEL=qwen3:14b
```

### Recommended models

| Model | Notes |
| --- | --- |
| `qwen3:8b` | Default. Good balance, fits modest GPUs. |
| `qwen3:14b` | Higher quality, needs more VRAM. |
| `qwen3:32b` | Best local quality, needs a large GPU. |
| `gemma3:12b` | Solid alternative for Chinese → Vietnamese. |

Structured-JSON calls (glossary growth, language detection) are sent with
`format: json` and `think: false`, so reasoning models behave as direct
generators for those calls.

## Gemini

Google's cloud API. Generous free tier, fast, good multilingual quality.

1. Create a key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Configure `.env`:

   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-2.5-flash
   ```

### Recommended models

| Model | Notes |
| --- | --- |
| `gemini-2.5-flash` | Default. Fast and cheap, strong quality. |
| `gemini-2.5-pro` | Higher quality, slower, higher cost/quota use. |
| `gemini-2.0-flash` | Cheaper fallback option. |

### Safety settings

The provider sets `BLOCK_NONE` for all four safety categories
(hate speech, dangerous content, harassment, sexually explicit) so novel content
is not filtered. If Gemini still blocks a chunk, the run reports
`Gemini blocked: <reason>` for that chapter.

### Endpoint

Calls go to
`https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`.
No custom endpoint override is supported.

## OpenRouter

Access 200+ models (Anthropic, OpenAI, Qwen, DeepSeek, Mistral, etc.) through
one API key.

1. Create a key at [openrouter.ai/keys](https://openrouter.ai/keys).
2. Configure `.env`:

   ```env
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-v1-...
   OPENROUTER_MODEL=qwen/qwen3-8b
   ```

### Recommended models

| Model | Notes |
| --- | --- |
| `qwen/qwen3-8b` | Default. Cheap, good multilingual. |
| `qwen/qwen3-14b` | Higher quality Qwen. |
| `anthropic/claude-sonnet-4` | Top literary quality, higher cost. |
| `google/gemini-2.5-flash` | Same as Gemini, routed through OpenRouter. |
| `deepseek/deepseek-chat` | Cost-effective for long books. |

The model id must match OpenRouter's exact slug. Browse the full catalog at
[openrouter.ai/models](https://openrouter.ai/models).

### Endpoint

Calls go to `https://openrouter.ai/api/v1/chat/completions` with a
`Authorization: Bearer <key>` header (OpenAI-compatible). No custom endpoint
override is supported.

## Fallback provider

Pair a primary provider with a different fallback. If the primary raises an
error, the fallback provider handles that call automatically.

```env
LLM_PROVIDER=ollama
FALLBACK_PROVIDER=gemini

GEMINI_API_KEY=your-key-here
```

Typical setups:

- **Local-first with cloud backup**: `LLM_PROVIDER=ollama`,
  `FALLBACK_PROVIDER=gemini`. Runs free on local hardware, falls back to Gemini
  if Ollama is down or a model errors.
- **Cloud-first with local backup**: `LLM_PROVIDER=gemini`,
  `FALLBACK_PROVIDER=ollama`. Useful if you want to keep going offline.

`FALLBACK_PROVIDER` must differ from `LLM_PROVIDER`; setting them equal is
ignored. Make sure the fallback provider's credentials are set in `.env`.

## Choosing a model

For Chinese/Korean/Japanese → Vietnamese:

1. **Quality first, cost flexible** — `anthropic/claude-sonnet-4` via
   OpenRouter, or `gemini-2.5-pro`.
2. **Best free/local** — `qwen3:14b` via Ollama (needs ~16GB VRAM), or
   `qwen3:8b` on smaller GPUs.
3. **Best price/quality on cloud** — `gemini-2.5-flash` or
   `qwen/qwen3-14b` via OpenRouter.

For Chinese/Korean/Japanese → English, the same models work well; English
output tends to be slightly more robust on smaller models.

## Tuning generation

Two temperature/max-token pairs are used:

- **Crawler / config generator** — `LLM_TEMPERATURE` (default `0.0`) and
  `LLM_MAX_TOKENS` (default `4096`). Keep temperature low for deterministic
  selector generation.
- **Translator** — `TRANSLATION_TEMPERATURE` (default `0.3`) and
  `TRANSLATION_MAX_TOKENS` (default `4096`). Slightly higher temperature gives
  more natural prose; lower is more literal.

Chunking is controlled by `CHUNK_SIZE` (default `1500` chars) and
`CHUNK_OVERLAP` (default `100` chars). Larger chunks give the model more context
but cost more tokens and increase the chance of truncation; overlap keeps
context between chunks. `CHUNK_OVERLAP` must be less than `CHUNK_SIZE`.

Quality-control knobs:

- `REVIEW_THRESHOLD` (default `0.7`) — minimum review score before a chunk is
  retried. Lower = more retries, higher cost, tighter quality.
- `MAX_RETRIES` (default `2`) — retry count per chunk when review is on.
- `ENABLE_REVIEW` / `ENABLE_SUMMARY` (default `false`) — turn on the optional
  review and summary steps globally, or use `--review` / `--summary` per run.
