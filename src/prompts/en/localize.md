Translate the supplied novel metadata into English.

Output
- Return ONLY one JSON object whose keys exactly match the keys inside the supplied `fields` object.
- Do not return `source_language`, `target_language`, or `fields`.
- Every returned value must be a non-empty string. Do not wrap the JSON in a Markdown code fence.

General rules
- Translate directly from the supplied source metadata. If `source_language` is `auto`, infer it from the text.
- Do not invent, omit, or alter information.
- Preserve the author's intent, tone, and genre.
- Apply the supplied glossary consistently.
- Use the supplied active character names consistently.

Title
- Treat the title as a published novel title, not a literal sentence.
- Use fluent, readable wording natural for a published novel title in the target language.
- Preserve the original meaning, tone, and hook.
- Recreate the title's stylistic effect—such as mystery, humor, romance, irony, or drama—rather than preserving the source word order.
- Preserve rhetorical questions, exclamations, and dramatic phrasing when they are part of the original.
- Preserve wordplay, metaphor, ambiguity, and cultural flavor when possible. If they cannot be carried over literally, use a natural target-language equivalent that creates a similar effect.
- Adapt naturally when a literal translation would sound awkward, but do not add information not implied by the original.
- Treat glossary entries as terminology references, not fixed sentence fragments; adapt grammar and word order naturally while preserving their intended meaning.
- Render common genre terms using established target-language equivalents when available; otherwise translate them naturally from context.

Summary
- Translate faithfully.
- Do not rewrite into a new synopsis.
- Do not summarize, expand, or embellish.
- Preserve paragraph breaks when practical.
