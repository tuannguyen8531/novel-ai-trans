You extract source-grounded dialogue address evidence, separately from translation memory.
Use only the supplied character keys; do not create or modify entities, narrative pronouns, terms, or relationships.
The source may be one contiguous part of a chapter, with overlap from an adjacent part. Assess only evidence visible in this part.
If an interaction is incomplete or ambiguous, use inconclusive for pending hypotheses and uncertain for new observations.
Do not treat missing interaction in this part as rejection. Other parts may contain relevant evidence.

=== NOVEL-SPECIFIC TRANSLATION RULES ===
{{translation_rules}}

=== CHARACTERS AND EXISTING ADDRESS MEMORY ===
{{existing_chars_str}}

=== ADDRESS EVIDENCE ===
- Determine persistence primarily from source events, dialogue context, tone, relationship development, relative status, and register.
- Existing rules and pending hypotheses may have influenced the translation; neither the hypothesis nor the resulting translated pronouns are confirmation. The translation may help with target wording but not with persistence.
- Treat an existing address rule as a prior default, not evidence against a source-supported change. Emit a stable change only when the source supports it independently.
- Source languages may not lexically distinguish Vietnamese forms. Exact source equivalents of "tớ/cậu" or "anh/em" are unnecessary when the source independently preserves the relationship and register.

PENDING HYPOTHESES:
- Return exactly one address_rule_candidate_verdict for every pending hypothesis above, using original entity keys.
- confirmed: a relationship_change continues, or another chapter that continues the same relationship, status, and ordinary register independently supports a default candidate.
- temporary: the form is local roleplay, drunken speech, a joke, teasing, sarcasm, a nickname, insult, or emotional outburst.
- rejected: the source contradicts it or clearly continues the previous confirmed relationship/register.
- Use "inconclusive" only when this source part has no relevant interaction or insufficient source evidence.

NEW ADDRESS OBSERVATIONS:
- Emit only source-supported direct interaction not already represented by an unchanged stable rule. Do not copy a pending hypothesis merely to confirm it.
- self is how the speaker refers to themselves; other is how they address or refer to the listener. Use original names for speaker/listener.
- scope=stable only for a lasting default; temporary for a local form; uncertain when the form is clear but persistence is not.
- Emit a clear new source-grounded form as uncertain rather than omit it only because persistence is unproven. It will remain an unconfirmed translation hypothesis until later evidence confirms it.
- reason=default or relationship_change for stable/uncertain evidence; otherwise joke, roleplay, drunken_speech, nickname, or emotional_outburst.
- Always emit a source-supported temporary observation so it can cancel a false stable candidate. Set since={{chapter_number}}.

Return JSON only. Use empty arrays when nothing qualifies:
{
  "address_rules": [
    {
      "speaker": "from_original_name",
      "listener": "to_original_name",
      "self": "Vietnamese dialogue self-reference",
      "other": "Vietnamese address/reference for listener",
      "since": {{chapter_number}},
      "scope": "stable | temporary | uncertain",
      "reason": "default | relationship_change | joke | roleplay | drunken_speech | nickname | emotional_outburst",
      "notes": "optional concise source-grounded context"
    }
  ],
  "address_rule_candidate_verdicts": [
    {
      "speaker": "pending_candidate_speaker_original_name",
      "listener": "pending_candidate_listener_original_name",
      "verdict": "confirmed | temporary | rejected | inconclusive"
    }
  ]
}
