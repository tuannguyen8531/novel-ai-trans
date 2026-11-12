# Providers

`novel-ai-trans` supports four LLM providers. Pick one in `runtime/settings.json` via
`llm_provider`, and optionally pair it with a different `fallback_provider` for
automatic failover. Environment variables with the old names remain supported
to seed a missing settings file; API keys always come from the environment.

| Provider    | Type   | Get started                                         |
| ----------- | ------ | --------------------------------------------------- |
| **Ollama**  | Local  | [ollama.com](https://ollama.com/)                   |
| **Gemini**  | Cloud  | [Google AI Studio](https://aistudio.google.com/apikey) |
| **OpenRouter** | Cloud (200+ models) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **NVIDIA** | Cloud (NIM) | [build.nvidia.com](https://build.nvidia.com/google/gemma-4-31b-it) |

You can also override the provider per run with `translate --provider <name>` or
`generate --provider <name>`.

## Table of contents

- [Ollama](#ollama)
- [Gemini](#gemini)
- [OpenRouter](#openrouter)
- [NVIDIA](#nvidia)
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

3. Configure `runtime/settings.json`:

   ```json
   {
     "llm_provider": "ollama",
     "ollama_base_url": "http://localhost:11434",
     "ollama_model": "qwen3:8b"
   }
   ```

4. Verify it is running:

   ```bash
   curl http://localhost:11434/api/tags
   ```

### Remote Ollama

Point `ollama_base_url` at any reachable Ollama instance (e.g. a GPU server on
your LAN):

```json
{
  "ollama_base_url": "http://192.168.1.10:11434",
  "ollama_model": "qwen3:14b"
}
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
2. Put the provider and model in `runtime/settings.json`, and the API key in `.env`:

   ```json
   {
     "llm_provider": "gemini",
     "gemini_model": "gemini-2.5-flash"
   }
   ```
   ```env
   GEMINI_API_KEY=your-key-here
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
2. Put the provider and model in `runtime/settings.json`, and the API key in `.env`:

   ```json
   {
     "llm_provider": "openrouter",
     "openrouter_model": "qwen/qwen3-8b"
   }
   ```
   ```env
   OPENROUTER_API_KEY=sk-or-v1-...
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

## NVIDIA

Use NVIDIA's hosted NIM API with `google/gemma-4-31b-it` as the default model.

1. Open the [Gemma 4 model page](https://build.nvidia.com/google/gemma-4-31b-it),
   sign in, and select **Generate API Key**.
2. Add the key to `.env`:

   ```env
   NVIDIA_API_KEY=nvapi-...
   ```

3. Select NVIDIA in the web GUI's provider settings, or update
   `runtime/settings.json`:

   ```json
   {
     "llm_provider": "nvidia",
     "nvidia_model": "google/gemma-4-31b-it"
   }
   ```

Calls use `https://integrate.api.nvidia.com/v1/chat/completions` with Bearer
authentication, following the [NVIDIA API example](https://build.nvidia.com/google/gemma-4-31b-it).
The GUI supports model discovery, manual model entry, and testing an unsaved
key/model. The key test sends a short inference request with `max_tokens: 1`,
because the model catalog is public and cannot verify credentials.

If NVIDIA reports `DEGRADED function cannot be invoked`, the model endpoint is
temporarily unavailable. Choose another model or retry later; changing the API
key does not resolve that service condition. Translation calls can use a
configured fallback provider after retries.

NVIDIA can also be selected per run with `translate --provider nvidia` or used
as `fallback_provider`. API keys stay in `.env` and are excluded from settings
JSON and API responses. Gemma 4 thought-channel wrappers are removed from the
returned text, as described in the
[model documentation](https://docs.api.nvidia.com/nim/reference/google-gemma-4-31b-it).

## Fallback provider

Pair a primary provider with a different fallback. If the primary raises an
error, the fallback provider handles that call automatically.

```json
{
  "llm_provider": "ollama",
  "fallback_provider": "gemini"
}
```
```env

GEMINI_API_KEY=your-key-here
```

Typical setups:

- **Local-first with cloud backup**: `llm_provider=ollama`,
  `fallback_provider=gemini`. Runs free on local hardware, falls back to Gemini
  if Ollama is down or a model errors.
- **Cloud-first with local backup**: `llm_provider=gemini`,
  `fallback_provider=ollama`. Useful if you want to keep going offline.

`fallback_provider` must differ from `llm_provider`; setting them equal is
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

- **Structured / analysis calls** — learning, crawler config generation,
  language detection, and translation review use `LLM_TEMPERATURE` (default
  `0.0`) and `LLM_MAX_TOKENS` (default `4096`). Keep temperature low for
  deterministic structured results. Metadata localization also requests a
  structured JSON response.
- **Translation / summarization / metadata localization calls** — `translate`,
  `summarize`, and `localize` use
  `translation_temperature` (default `0.3`) and
  `translation_max_tokens` (default `8192`) from `runtime/settings.json`.
  Slightly higher temperature gives
  more natural prose; lower is more literal.

Metadata localization translates only an existing novel title or synopsis; it
does not generate a synopsis from chapters. Its prompt contains only glossary
terms and known characters that occur in the metadata fields being sent.

Chunking is controlled by `chunk_mode` (`chars` by default), `chunk_size`
(default `5000`), and `chunk_overlap` (default `100`) in
`runtime/settings.json`. In `chars` mode, size
and overlap use characters and preserve the legacy behaviour. In `tokens` mode,
they use a deterministic local estimate: CJK and other non-whitespace
characters count individually, while ASCII letters and digits are grouped in
runs of up to four. This estimate is consistent and offline, but is not an
exact model-specific token count. `chunk_overlap` must be less than
`chunk_size` in either mode.

Quality-control knobs:

- `REVIEW_THRESHOLD` (default `0.7`) — minimum review score before a chunk is
  retried. Lower = more retries, higher cost, tighter quality.
- `MAX_RETRIES` (default `2`) — retry count per chunk when review is on.
- Review and summary steps are disabled by default and can be enabled per run
  with `--review` / `--summary`.
