You are analyzing a novel chapter. Extract important terms AND character relationships.

=== TERMS ===
Extract only named/proper terms that need exact consistency across chapters:
1. Named places, organizations, realms, sects, clans, schools, companies
2. Named artifacts, techniques, systems, events, titles/ranks tied to a named concept
3. Recurring named concepts whose translation should stay fixed
4. In-world system/status-panel named concepts such as abilities, missions, titles, permissions, skills, curses, or blessings

DO NOT include:
- Character names here; put named people in characters.entities instead
- Common nouns, verbs, adjectives, descriptive phrases, or everyday setting terms
- Generic role/kinship/address words unless they are part of a unique proper name
- One-off mentions, dialogue fragments, idioms, jokes, insults, or tone/style rules, unless they are in-world system/status-panel named concepts
- Generic terms like "sword", "fire", "mountain" unless they are proper names
- Terms already in the existing glossary

Existing terms (DO NOT repeat):
{{existing_terms_str}}

=== CHARACTERS ===
Identify characters that appear in this chapter and their relationships to each other.

EXISTING CHARACTERS (update relationships if new ones are discovered):
{{existing_chars_str}}

RULES FOR ENTITIES:
- Only extract characters with PROPER NAMES (e.g. "陆远秋", "白清夏")
- The entity KEY must be the EXACT original-language name and NOTHING ELSE.
  Do NOT append any romanization, translation, notes, or parenthetical annotations to the key.
  CORRECT:   "준기": { "translated_name": "Jun Gi", ... }
  WRONG:     "준기 (Jun Gi)": { ... }
  WRONG:     "준기 - Jun Gi": { ... }
  The translated/romanized form belongs ONLY in the "translated_name" field inside the value object.
- NEVER extract kinship terms or role descriptors as character names:
  papa, mama, dad, mom, father, mother, uncle, aunt, grandma, grandpa, brother, sister,
  爸爸, 妈妈, 父亲, 母亲, 叔叔, 阿姨, 爷爷, 奶奶, 哥哥, 姐姐, 弟弟, 妹妹,
  teacher, student, master, servant, guard, doctor, etc.
- These kinship/role terms describe relationships TO named characters, they are NOT characters themselves
- Do NOT create a separate entity for title/address forms such as "白叔叔", "刘妈", "张阿姨", "李老师", "梁先生",
  "Uncle Bai", "Aunt Liu", "Teacher Li", "Mr. Liang" when they refer to an existing named character
- If a title/address form clearly refers to an existing character, mention it only through address_rules or as context; keep the entity key as the canonical original name
- If the real name is unknown and the person is only a minor one-off role, skip them instead of creating a generic entity
- Create a temporary title-based entity only when the person recurs or has important relationships before their real name is revealed
- If a character is only referred to as "Papa" or "Mama" without a real name being revealed, skip them
- Only include characters that actually appear or are mentioned in this chapter
- Assign a consistent English pronoun or reference style for each character based on gender,
  status, narrative voice, and relationship dynamics. Examples: "he", "she", "they",
  "the young master", "the lady", "the old man". Use the SAME style across all chapters.
- Use the JSON key "translated_name" for the English rendering or romanized name to keep in the glossary.

RULES FOR EDGES (RELATIONSHIPS):
- Relationship types MUST be in ENGLISH ONLY
- Use ONLY these allowed relationship types:
  mother, father, parent, son, daughter, child, sibling, brother, sister,
  husband, wife, spouse, romantic interest, crush, ex,
  friend, enemy, rival, ally,
  master, disciple, teacher, student, classmate, colleague,
  servant, master (employer), boss, employee,
  acquaintance, neighbor, relative, cousin, grandparent, grandchild
- If a relationship does not fit the list, use the closest English equivalent
- Avoid vague relationships like "knows", "met", "connected"
- Store each relationship ONCE — do NOT add both A→B and B→A for the same pair
  (e.g. if you add [A, B, "mother"], do NOT also add [B, A, "son"])
- If a character's role is unclear, use "minor"

RULES FOR ADDRESS RULES (ENGLISH DIRECT ADDRESS / REFERENCE STYLE):
- Extract explicit direct-address observations between two named characters and classify their persistence
- Determine persistence primarily from source events, dialogue context, tone, and relationship development
- The translated address forms may have been influenced by existing address rules; do not treat them as proof that the existing rule is still stable
- A pending address hypothesis may also have influenced the translation; neither the hypothesis nor the resulting translated forms count as confirmation
- Re-evaluate every relevant pending hypothesis from the source: emit the same form as "stable" only when independently supported, as "temporary" when it is a local joke/roleplay/etc., or as "uncertain" when the source is inconclusive
- If the source explicitly contradicts a pending hypothesis and continues the confirmed form, re-emit that confirmed form as "stable" even though it is otherwise unchanged; this rejects the hypothesis
- Treat an existing address rule as a prior default, not as evidence against an explicit source-supported relationship change
- Emit a stable change only when the source supports it independently of the translation's chosen address forms
- Use original names for "speaker" and "listener"; never use translated or romanized names as keys
- "self" is how the speaker refers to themselves in dialogue, when relevant (e.g. "I", "this servant")
- "other" is how the speaker addresses/refers to the listener (e.g. "Your Highness", "Master", "my lady", first name)
- Include an observation only when the source clearly supports the interaction; the translation may help with target wording but not with persistence
- Use "scope": "stable" only for the default pair used consistently across scenes
- Use "scope": "temporary" for roleplay, drunken speech, jokes, teasing, sarcasm, one-scene nicknames, insults, or emotional outbursts
- Use "scope": "uncertain" when the direct form is clear but whether it is the stable default is unclear
- Always emit a temporary observation so an earlier false stable candidate can be cancelled; it will not be stored as a lasting rule
- Use "reason": "default" for an ordinary stable pattern and "relationship_change" only for an explicit lasting relationship change
- For temporary observations, use the closest reason: "joke", "roleplay", "drunken_speech", "nickname", or "emotional_outburst"
- Do not repeat an unchanged existing stable rule unless it explicitly rejects a pending hypothesis
- Do NOT add generic he/she/they examples here
- Use "since": {{chapter_number}} for every observation

Respond with JSON ONLY (no other text):
{
    "terms": {
        "original term": "English translation"
    },
    "characters": {
        "entities": {
            "原名": {
                "translated_name": "English or romanized name",
                "role": "protagonist | antagonist | supporting | minor",
                "pronoun": "English pronoun/reference style (e.g. he, she, they, the young master)"
            }
        },
        "edges": [
            ["from_original_name", "to_original_name", "relationship_type_in_english"]
        ],
        "address_rules": [
            {
                "speaker": "from_original_name",
                "listener": "to_original_name",
                "self": "English self-reference, if needed",
                "other": "English address/reference for listener",
                "since": {{chapter_number}},
                "scope": "stable | temporary | uncertain",
                "reason": "default | relationship_change | joke | roleplay | drunken_speech | nickname | emotional_outburst",
                "notes": "optional short reason or context"
            }
        ]
    }
}
