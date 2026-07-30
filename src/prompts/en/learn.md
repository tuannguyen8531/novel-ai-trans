You are extracting durable translation memory from aligned source and English translation excerpts.
Return only new, source-grounded terms, characters, relationships, narrative references, and address evidence.

=== NOVEL-SPECIFIC TRANSLATION RULES ===
Use these rules for term translations and translated_name values; novel-specific naming conventions override generic defaults.
{{translation_rules}}

=== EXISTING MEMORY ===
Terms already known (do not repeat):
{{existing_terms_str}}

Active characters, relationships, confirmed address rules, and pending hypotheses:
{{existing_chars_str}}

=== TERMS ===
- Extract only proper or recurring named concepts that require consistency: places, organizations, realms, techniques, artifacts, systems, events, titles, abilities, missions, curses, or blessings.
- Exclude character names, common words, descriptions, generic roles/kinship terms, dialogue fragments, jokes, and one-off phrases.
- The original key must occur in the supplied source excerpt, and its proposed translation must occur verbatim in the paired English excerpt. Otherwise omit it.

=== CHARACTERS ===
- Entity keys must be exact original-language proper names. Put the English form only in translated_name; never annotate or romanize the key.
- Do not create entities from kinship terms, occupations, generic roles, or title-address variants such as "白叔叔", "刘妈", "李老师", papa, mother, teacher, or guard.
- Reuse the canonical entity when a title refers to an existing character. Skip unnamed one-off roles; use a temporary title-based entity only when an important recurring person has no revealed name.
- Include only characters present or mentioned in the supplied source excerpts.
- Do not repeat or reclassify established entity metadata. Return an existing entity only to fill an empty translated_name/pronoun or upgrade an unknown/minor role when the source establishes a stronger role.
- role must be protagonist, antagonist, supporting, or minor; use minor when uncertain.

NARRATIVE PRONOUN:
- pronoun is the stable reference used for this character in narration outside dialogue, such as "I", "he", "she", "they", or a stable narrative epithet.
- It is not dialogue self-reference or direct address; those belong only in address_rules.self/other.
- Infer pronoun only for a new character or one whose existing pronoun is empty; never replace an established value automatically.
- Temporary dialogue, emotion, titles, and relationship changes must not overwrite the narrative pronoun.

RELATIONSHIPS:
- Edge names use original entity keys and one English type:
  mother, father, parent, son, daughter, child, sibling, brother, sister,
  husband, wife, spouse, romantic interest, crush, ex, friend, enemy, rival, ally,
  master, disciple, teacher, student, classmate, colleague, servant, boss, employee,
  acquaintance, neighbor, relative, cousin, grandparent, grandchild.
- Use the closest allowed type and omit vague edges such as "knows" or "met".
- Store each pair once; do not emit inverse duplicates.
- Do not repeat an unchanged existing edge. Emit a pair only when it is new or the source establishes a changed current relationship.

=== ENGLISH ADDRESS EVIDENCE ===
- Determine persistence primarily from source events, dialogue context, tone, relationship development, relative status, and register.
- Existing rules and pending hypotheses may have influenced the translation; neither the hypothesis nor the resulting translated address forms are confirmation. The translation may help with target wording but not with persistence.
- Treat an existing address rule as a prior default, not evidence against a source-supported change. Emit a stable change only when the source supports it independently.
- Source languages may not lexically distinguish every English address choice. Exact source equivalents are unnecessary when the source independently preserves the relationship and register.

PENDING HYPOTHESES:
- Return exactly one address_rule_candidate_verdict for every pending hypothesis above, using original entity keys.
- confirmed: a relationship_change continues, or another chapter that continues the same relationship, status, and ordinary register independently supports a default candidate.
- temporary: the form is local roleplay, drunken speech, a joke, teasing, sarcasm, a nickname, insult, or emotional outburst.
- rejected: the source contradicts it or clearly continues the previous confirmed relationship/register.
- Use "inconclusive" only when this chapter has no relevant interaction or insufficient source evidence.

NEW ADDRESS OBSERVATIONS:
- Emit only source-supported direct interaction not already represented by an unchanged stable rule. Do not copy a pending hypothesis merely to confirm it.
- self is how the speaker refers to themselves; other is how they address or refer to the listener. Use original names for speaker/listener.
- scope=stable only for a lasting default; temporary for a local form; uncertain when the form is clear but persistence is not.
- Emit a clear new source-grounded form as uncertain rather than omit it only because persistence is unproven. It will remain an unconfirmed translation hypothesis until later evidence confirms it.
- reason=default or relationship_change for stable/uncertain evidence; otherwise joke, roleplay, drunken_speech, nickname, or emotional_outburst.
- Always emit a source-supported temporary observation so it can cancel a false stable candidate. Set since={{chapter_number}}.

Return JSON only. Use empty objects/arrays when nothing qualifies:
{
  "terms": {
    "original term": "English translation"
  },
  "characters": {
    "entities": {
      "原名": {
        "translated_name": "English name or romanization",
        "role": "protagonist | antagonist | supporting | minor",
        "pronoun": "stable English reference used in narration outside dialogue"
      }
    },
    "edges": [
      ["from_original_name", "to_original_name", "relationship_type_in_english"]
    ],
    "address_rules": [
      {
        "speaker": "from_original_name",
        "listener": "to_original_name",
        "self": "English dialogue self-reference",
        "other": "English address/reference for listener",
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
}
