<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GlossaryEdge } from '@/composables/glossary'

const props = defineProps<{
  relationships: GlossaryEdge[]
  addRelationship: (
    from: string,
    to: string,
    relationship: string,
    since: number | null
  ) => Promise<boolean>
  updateRelationship: (
    from: string,
    to: string,
    relationship: string,
    since: number | null
  ) => Promise<boolean>
  removeRelationship: (from: string, to: string) => Promise<boolean>
}>()

const filter = ref('')
const newRelationship = ref({ from: '', to: '', relationship: '', since: null as number | null })
const showAdd = ref(false)
const editing = ref<{
  key: string
  from: string
  to: string
  relationship: string
  since: number | null
} | null>(null)

const filteredRelationships = computed(() => {
  const query = filter.value.trim().toLowerCase()
  const relationships = query
    ? props.relationships.filter((edge) =>
        edge.from.toLowerCase().includes(query) ||
        edge.to.toLowerCase().includes(query) ||
        edge.relationship.toLowerCase().includes(query)
      )
    : [...props.relationships]
  return relationships.sort((left, right) => left.from.localeCompare(right.from))
})

function edgeKey(edge: GlossaryEdge, index: number) {
  return `${edge.from}-${edge.to}-${edge.relationship}-${index}`
}

async function add() {
  const value = newRelationship.value
  if (!value.from || !value.to || !value.relationship) return
  if (!await props.addRelationship(value.from, value.to, value.relationship, value.since)) return
  newRelationship.value = { from: '', to: '', relationship: '', since: null }
  showAdd.value = false
}

function startEdit(edge: GlossaryEdge, index: number) {
  editing.value = {
    key: edgeKey(edge, index),
    from: edge.from,
    to: edge.to,
    relationship: edge.relationship,
    since: edge.since
  }
}

async function saveEdit() {
  if (!editing.value?.relationship) return
  if (!await props.updateRelationship(
    editing.value.from,
    editing.value.to,
    editing.value.relationship,
    editing.value.since
  )) return
  editing.value = null
}
</script>

<template>
  <section class="gloss-section card">
    <header class="gloss-header">
      <div>
        <h3>Relationships</h3>
        <p class="muted">{{ relationships.length }} edges between characters</p>
      </div>
      <div class="gloss-controls">
        <input v-model="filter" placeholder="Filter relationships…" class="gloss-filter" />
        <button type="button" class="secondary" @click="showAdd = !showAdd">
          {{ showAdd ? 'Cancel' : 'Add relationship' }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add">
      <input v-model="newRelationship.from" placeholder="From character (original)" />
      <input v-model="newRelationship.to" placeholder="To character (original)" />
      <input v-model="newRelationship.relationship" placeholder="Relationship (e.g. friend)" />
      <input
        v-model.number="newRelationship.since"
        type="number"
        min="0"
        placeholder="Since chapter (optional)"
        class="since-input"
      />
      <button
        type="button"
        :disabled="!newRelationship.from || !newRelationship.to || !newRelationship.relationship"
        @click="add"
      >Save</button>
    </div>

    <div class="gloss-table-wrap">
      <table v-if="filteredRelationships.length">
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
          <tr
            v-for="(edge, index) in filteredRelationships"
            :key="edgeKey(edge, index)"
          >
            <template v-if="editing?.key === edgeKey(edge, index)">
              <td class="gloss-original">{{ edge.from }}</td>
              <td class="arrow">→</td>
              <td class="gloss-original">{{ edge.to }}</td>
              <td><input v-model="editing.relationship" class="inline-edit-input" /></td>
              <td>
                <input
                  v-model.number="editing.since"
                  type="number"
                  min="0"
                  class="inline-edit-input edit-since-input"
                />
              </td>
              <td class="actions">
                <div class="row gap-1">
                  <button type="button" :disabled="!editing.relationship" @click="saveEdit">Save</button>
                  <button class="secondary" type="button" @click="editing = null">Cancel</button>
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
                <div class="row gap-1 row-actions">
                  <button class="secondary" type="button" @click="startEdit(edge, index)">Edit</button>
                  <button class="secondary" type="button" @click="removeRelationship(edge.from, edge.to)">Remove</button>
                </div>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted gloss-empty">
        {{ filter ? 'No relationships match the filter.' : 'No relationships yet.' }}
      </p>
    </div>
  </section>
</template>

<style scoped src="../assets/glossary.css"></style>
<style scoped>
.since-input {
  max-width: 9rem;
}

.edit-since-input {
  max-width: 6rem;
}

.row-actions {
  display: inline-flex;
}
</style>
