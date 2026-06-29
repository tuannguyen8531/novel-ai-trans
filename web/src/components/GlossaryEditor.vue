<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { GlossaryResponse } from '@/api/types'

interface Edge {
  from: string
  to: string
  relationship: string
  since: number | null
}

const props = defineProps<{ novel: string }>()

const data = ref<GlossaryResponse | null>(null)
const error = ref<string | null>(null)
const loading = ref(false)

const termFilter = ref('')
const characterFilter = ref('')
const edgeFilter = ref('')

const newTerm = ref({ original: '', translated: '' })
const newCharacter = ref({ original: '', translated_name: '', role: '' })
const newRelationship = ref({ from: '', to: '', relationship: '', since: null as number | null })

const showAddTerm = ref(false)
const showAddCharacter = ref(false)
const showAddRelationship = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    data.value = await api.getGlossary(props.novel)
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.novel, load)

const terms = computed<Record<string, string>>(() => {
  if (!data.value || !data.value.data) return {}
  return (data.value.data.terms as Record<string, string>) ?? {}
})

const entities = computed<Record<string, { translated_name?: string; role?: string; pronoun?: string }>>(() => {
  if (!data.value || !data.value.data) return {}
  return (data.value.data.entities as Record<string, { translated_name?: string; role?: string; pronoun?: string }>) ?? {}
})

const edges = computed<Edge[]>(() => {
  if (!data.value || !data.value.data) return []
  const raw = (data.value.data.edges as unknown[]) ?? []
  const out: Edge[] = []
  for (const entry of raw) {
    if (!Array.isArray(entry) || entry.length < 3) continue
    const [from, to, relationship, since] = entry
    if (typeof from !== 'string' || typeof to !== 'string' || typeof relationship !== 'string') continue
    out.push({
      from,
      to,
      relationship,
      since: typeof since === 'number' ? since : null,
    })
  }
  return out
})

const filteredTerms = computed<[string, string][]>(() => {
  const q = termFilter.value.trim().toLowerCase()
  const entries = Object.entries(terms.value)
  if (!q) return entries.sort(([a], [b]) => a.localeCompare(b))
  return entries
    .filter(([k, v]) => k.toLowerCase().includes(q) || v.toLowerCase().includes(q))
    .sort(([a], [b]) => a.localeCompare(b))
})

const filteredCharacters = computed<[string, { translated_name?: string; role?: string; pronoun?: string }][]>(() => {
  const q = characterFilter.value.trim().toLowerCase()
  const entries = Object.entries(entities.value)
  if (!q) return entries.sort(([a], [b]) => a.localeCompare(b))
  return entries.filter(([k, v]) => {
    if (k.toLowerCase().includes(q)) return true
    const fields = [v.translated_name, v.role, v.pronoun].filter(Boolean) as string[]
    return fields.some((f) => f.toLowerCase().includes(q))
  }).sort(([a], [b]) => a.localeCompare(b))
})

const filteredEdges = computed<Edge[]>(() => {
  const q = edgeFilter.value.trim().toLowerCase()
  if (!q) return [...edges.value].sort((a, b) => a.from.localeCompare(b.from))
  return edges.value.filter((e) => {
    return (
      e.from.toLowerCase().includes(q) ||
      e.to.toLowerCase().includes(q) ||
      e.relationship.toLowerCase().includes(q)
    )
  }).sort((a, b) => a.from.localeCompare(b.from))
})

async function addTerm() {
  if (!newTerm.value.original || !newTerm.value.translated) return
  try {
    data.value = await api.addTerm(props.novel, newTerm.value.original, newTerm.value.translated)
    newTerm.value = { original: '', translated: '' }
    showAddTerm.value = false
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function removeTerm(original: string) {
  if (!confirm(`Remove term "${original}"?`)) return
  try {
    data.value = await api.removeTerm(props.novel, original)
  } catch (err) {
    error.value = (err as Error).message
  }
}

const editingTerm = ref<{ oldOriginal: string; original: string; translated: string } | null>(null)

function startEditTerm(original: string, translated: string) {
  editingTerm.value = { oldOriginal: original, original, translated }
}

function cancelEditTerm() {
  editingTerm.value = null
}

async function saveEditTerm() {
  if (!editingTerm.value || !editingTerm.value.original || !editingTerm.value.translated) return
  const { oldOriginal, original, translated } = editingTerm.value
  let overwrite = false

  if (oldOriginal !== original && terms.value[original]) {
    if (!confirm(`Term "${original}" already exists. Overwrite it?`)) {
      return
    }
    overwrite = true
  }

  error.value = null
  try {
    data.value = await api.updateTerm(props.novel, oldOriginal, { original, translated, overwrite })
    editingTerm.value = null
  } catch (err) {
    error.value = (err as Error).message
  }
}

const editingCharacter = ref<{ original: string; translated_name: string; role: string } | null>(null)

function startEditCharacter(original: string, translated_name: string, role: string) {
  editingCharacter.value = { original, translated_name, role }
}

function cancelEditCharacter() {
  editingCharacter.value = null
}

async function saveEditCharacter() {
  if (!editingCharacter.value || !editingCharacter.value.original) return
  const { original, translated_name, role } = editingCharacter.value
  error.value = null
  try {
    data.value = await api.updateCharacter(
      props.novel,
      original,
      {
        translated_name: translated_name || undefined,
        role: role || undefined
      }
    )
    editingCharacter.value = null
  } catch (err) {
    error.value = (err as Error).message
  }
}

const editingRelationship = ref<{ index: number; from: string; to: string; relationship: string; since: number | null } | null>(null)

function startEditRelationship(index: number, edge: Edge) {
  editingRelationship.value = {
    index,
    from: edge.from,
    to: edge.to,
    relationship: edge.relationship,
    since: edge.since
  }
}

function cancelEditRelationship() {
  editingRelationship.value = null
}

async function saveEditRelationship() {
  if (!editingRelationship.value) return
  const { from, to, relationship, since } = editingRelationship.value
  error.value = null
  try {
    data.value = await api.addRelationship(props.novel, {
      from_char: from,
      to_char: to,
      relationship,
      since: typeof since === 'number' ? since : null
    })
    editingRelationship.value = null
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function removeCharacter(original: string) {
  if (!confirm(`Remove character "${original}"? This will also remove their relationships.`)) return
  try {
    data.value = await api.removeCharacter(props.novel, original)
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function removeRelationship(from_char: string, to_char: string) {
  if (!confirm(`Remove relationship between "${from_char}" and "${to_char}"?`)) return
  try {
    data.value = await api.removeRelationship(props.novel, from_char, to_char)
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function saveCharacter() {
  if (!newCharacter.value.original) return
  try {
    data.value = await api.updateCharacter(
      props.novel,
      newCharacter.value.original,
      {
        translated_name: newCharacter.value.translated_name || undefined,
        role: newCharacter.value.role || undefined
      }
    )
    newCharacter.value = { original: '', translated_name: '', role: '' }
    showAddCharacter.value = false
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function addRelationship() {
  if (!newRelationship.value.from || !newRelationship.value.to || !newRelationship.value.relationship) return
  try {
    const sinceVal = newRelationship.value.since
    data.value = await api.addRelationship(props.novel, {
      from_char: newRelationship.value.from,
      to_char: newRelationship.value.to,
      relationship: newRelationship.value.relationship,
      since: (typeof sinceVal !== 'number') ? undefined : sinceVal
    })
    newRelationship.value = { from: '', to: '', relationship: '', since: null }
    showAddRelationship.value = false
  } catch (err) {
    error.value = (err as Error).message
  }
}
</script>

<template>
  <div class="glossary">
    <p v-if="error" class="error">{{ error }}</p>

    <!-- Terms -->
    <section class="gloss-section card">
      <header class="gloss-header">
        <div>
          <h3>Terms</h3>
          <p class="muted">{{ Object.keys(terms).length }} glossary entries</p>
        </div>
        <div class="gloss-controls">
          <input v-model="termFilter" placeholder="Filter terms…" class="gloss-filter" />
          <button type="button" class="secondary" @click="showAddTerm = !showAddTerm">
            {{ showAddTerm ? 'Cancel' : 'Add term' }}
          </button>
        </div>
      </header>

      <div v-if="showAddTerm" class="gloss-add">
        <input v-model="newTerm.original" placeholder="Original (source language)" />
        <input v-model="newTerm.translated" placeholder="Translated" />
        <button type="button" @click="addTerm" :disabled="!newTerm.original || !newTerm.translated">Save</button>
      </div>

      <div class="gloss-table-wrap">
        <table v-if="filteredTerms.length">
          <thead>
            <tr>
              <th>Original</th>
              <th>Translated</th>
              <th class="actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[original, translated] in filteredTerms" :key="original">
              <template v-if="editingTerm && editingTerm.oldOriginal === original">
                <td>
                  <input v-model="editingTerm.original" class="inline-edit-input" />
                </td>
                <td>
                  <input v-model="editingTerm.translated" class="inline-edit-input" />
                </td>
                <td class="actions">
                  <div class="row gap-1">
                    <button type="button" @click="saveEditTerm" :disabled="!editingTerm.original || !editingTerm.translated">Save</button>
                    <button class="secondary" type="button" @click="cancelEditTerm">Cancel</button>
                  </div>
                </td>
              </template>
              <template v-else>
                <td class="gloss-original">{{ original }}</td>
                <td>{{ translated }}</td>
                <td class="actions">
                  <div class="row gap-1" style="display: inline-flex;">
                    <button class="secondary" type="button" @click="startEditTerm(original, translated)">Edit</button>
                    <button class="secondary" type="button" @click="removeTerm(original)">Remove</button>
                  </div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted gloss-empty">
          {{ termFilter ? 'No terms match the filter.' : 'No terms yet.' }}
        </p>
      </div>
    </section>

    <!-- Characters -->
    <section class="gloss-section card">
      <header class="gloss-header">
        <div>
          <h3>Characters</h3>
          <p class="muted">{{ Object.keys(entities).length }} character entities</p>
        </div>
        <div class="gloss-controls">
          <input v-model="characterFilter" placeholder="Filter characters…" class="gloss-filter" />
          <button type="button" class="secondary" @click="showAddCharacter = !showAddCharacter">
            {{ showAddCharacter ? 'Cancel' : 'Add / update' }}
          </button>
        </div>
      </header>

      <div v-if="showAddCharacter" class="gloss-add">
        <input v-model="newCharacter.original" placeholder="Original name" />
        <input v-model="newCharacter.translated_name" placeholder="Translated name" />
        <select v-model="newCharacter.role">
          <option value="">(role unchanged)</option>
          <option value="protagonist">protagonist</option>
          <option value="antagonist">antagonist</option>
          <option value="supporting">supporting</option>
          <option value="minor">minor</option>
        </select>
        <button type="button" @click="saveCharacter" :disabled="!newCharacter.original">Save</button>
      </div>

      <div class="gloss-table-wrap">
        <table v-if="filteredCharacters.length">
          <thead>
            <tr>
              <th>Original</th>
              <th>Translated</th>
              <th>Role</th>
              <th>Pronoun</th>
              <th class="actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[original, info] in filteredCharacters" :key="original">
              <template v-if="editingCharacter && editingCharacter.original === original">
                <td class="gloss-original">{{ original }}</td>
                <td>
                  <input v-model="editingCharacter.translated_name" class="inline-edit-input" />
                </td>
                <td>
                  <select v-model="editingCharacter.role" class="inline-edit-input">
                    <option value="">(role unchanged)</option>
                    <option value="protagonist">protagonist</option>
                    <option value="antagonist">antagonist</option>
                    <option value="supporting">supporting</option>
                    <option value="minor">minor</option>
                  </select>
                </td>
                <td>{{ info.pronoun ?? '—' }}</td>
                <td class="actions">
                  <div class="row gap-1">
                    <button type="button" @click="saveEditCharacter">Save</button>
                    <button class="secondary" type="button" @click="cancelEditCharacter">Cancel</button>
                  </div>
                </td>
              </template>
              <template v-else>
                <td class="gloss-original">{{ original }}</td>
                <td>{{ info.translated_name ?? '—' }}</td>
                <td>{{ info.role ?? '—' }}</td>
                <td>{{ info.pronoun ?? '—' }}</td>
                <td class="actions">
                  <div class="row gap-1" style="display: inline-flex;">
                    <button class="secondary" type="button" @click="startEditCharacter(original, info.translated_name ?? '', info.role ?? '')">Edit</button>
                    <button class="secondary" type="button" @click="removeCharacter(original)">Remove</button>
                  </div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted gloss-empty">
          {{ characterFilter ? 'No characters match the filter.' : 'No characters yet.' }}
        </p>
      </div>
    </section>

    <!-- Relationships -->
    <section class="gloss-section card">
      <header class="gloss-header">
        <div>
          <h3>Relationships</h3>
          <p class="muted">{{ edges.length }} edges between characters</p>
        </div>
        <div class="gloss-controls">
          <input v-model="edgeFilter" placeholder="Filter relationships…" class="gloss-filter" />
          <button type="button" class="secondary" @click="showAddRelationship = !showAddRelationship">
            {{ showAddRelationship ? 'Cancel' : 'Add relationship' }}
          </button>
        </div>
      </header>

      <div v-if="showAddRelationship" class="gloss-add">
        <input v-model="newRelationship.from" placeholder="From character (original)" />
        <input v-model="newRelationship.to" placeholder="To character (original)" />
        <input v-model="newRelationship.relationship" placeholder="Relationship (e.g. friend)" />
        <input
          v-model.number="newRelationship.since"
          type="number"
          min="0"
          placeholder="Since chapter (optional)"
          style="max-width: 9rem;"
        />
        <button
          type="button"
          @click="addRelationship"
          :disabled="!newRelationship.from || !newRelationship.to || !newRelationship.relationship"
        >
          Save
        </button>
      </div>

      <div class="gloss-table-wrap">
        <table v-if="filteredEdges.length">
          <thead>
            <tr>
              <th>From</th>
              <th></th>
              <th>To</th>
              <th>Relationship</th>
              <th>Since</th>
              <th class="actions"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(edge, index) in filteredEdges" :key="`${edge.from}-${edge.to}-${edge.relationship}-${index}`">
              <template v-if="editingRelationship && editingRelationship.index === index">
                <td class="gloss-original">{{ edge.from }}</td>
                <td class="arrow">→</td>
                <td class="gloss-original">{{ edge.to }}</td>
                <td>
                  <input v-model="editingRelationship.relationship" class="inline-edit-input" />
                </td>
                <td>
                  <input
                    v-model.number="editingRelationship.since"
                    type="number"
                    min="0"
                    class="inline-edit-input"
                    style="max-width: 6rem;"
                  />
                </td>
                <td class="actions">
                  <div class="row gap-1">
                    <button type="button" @click="saveEditRelationship" :disabled="!editingRelationship.relationship">Save</button>
                    <button class="secondary" type="button" @click="cancelEditRelationship">Cancel</button>
                  </div>
                </td>
              </template>
              <template v-else>
                <td class="gloss-original">{{ edge.from }}</td>
                <td class="arrow">→</td>
                <td class="gloss-original">{{ edge.to }}</td>
                <td>{{ edge.relationship }}</td>
                <td>{{ edge.since ?? '—' }}</td>
                <td class="actions">
                  <div class="row gap-1" style="display: inline-flex;">
                    <button class="secondary" type="button" @click="startEditRelationship(index, edge)">Edit</button>
                    <button class="secondary" type="button" @click="removeRelationship(edge.from, edge.to)">Remove</button>
                  </div>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted gloss-empty">
          {{ edgeFilter ? 'No relationships match the filter.' : 'No relationships yet.' }}
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.glossary {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.gloss-section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.gloss-section h3 {
  margin: 0;
}

.gloss-section p.muted {
  margin: 0;
  font-size: 0.8rem;
}

.gloss-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.gloss-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 0 1 auto;
}

.gloss-filter {
  width: 14rem;
}

.gloss-add {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.5rem;
  padding: 0.6rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.gloss-add button {
  align-self: end;
}

.gloss-table-wrap {
  max-height: 22rem;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.gloss-section table {
  margin: 0;
}

.gloss-section thead th {
  position: sticky;
  top: 0;
  background: var(--bg-elev-2);
  z-index: 1;
}

.gloss-section tbody tr:hover {
  background: var(--bg-elev-2);
}

.gloss-original {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.85rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 18rem;
}

.gloss-section .actions {
  text-align: right;
  width: 1%;
  white-space: nowrap;
}

.arrow {
  text-align: center;
  color: var(--fg-dim);
  font-family: ui-monospace, SFMono-Regular, monospace;
}

.gloss-empty {
  padding: 1rem;
  text-align: center;
}

.inline-edit-input {
  font-size: 0.85rem;
  padding: 0.25rem 0.45rem;
  background: var(--bg-elev-2);
}
</style>
