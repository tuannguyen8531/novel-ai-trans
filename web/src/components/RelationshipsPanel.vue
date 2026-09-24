<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Search, Edit2, Trash2, Save, X, ArrowRight, GitFork } from '@lucide/vue'
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
      <div class="flex items-center gap-2">
        <GitFork :size="18" class="text-indigo-400 shrink-0" />
        <div>
          <h3>{{ $t("relationships") }}</h3>
          <p class="muted">{{ $t("character_relationships", { count: relationships.length }) }}</p>
        </div>
      </div>
      <div class="gloss-controls">
        <div class="relative flex items-center">
          <Search :size="14" class="absolute left-2.5 text-zinc-500 pointer-events-none" />
          <input
            v-model="filter"
            :placeholder="$t('filter_relationships')"
            class="gloss-filter !pl-8"
          />
        </div>
        <button
          type="button"
          class="secondary flex items-center gap-1.5"
          @click="showAdd = !showAdd"
        >
          <component :is="showAdd ? X : Plus" :size="14" />
          {{ showAdd ? $t('cancel') : $t('add_relationship') }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add p-3 bg-zinc-900/60 dark:bg-zinc-900/80 rounded-lg border border-indigo-500/30">
      <input v-model="newRelationship.from" :placeholder="$t('from_character_original')" class="flex-1" />
      <input v-model="newRelationship.to" :placeholder="$t('to_character_original')" class="flex-1" />
      <input v-model="newRelationship.relationship" :placeholder="$t('relationship_e_g_friend')" class="flex-1" />
      <input
        v-model.number="newRelationship.since"
        type="number"
        min="0"
        :placeholder="$t('since_ch_opt')"
        class="since-input !max-w-32"
      />
      <button
        type="button"
        class="flex items-center gap-1.5"
        :disabled="!newRelationship.from || !newRelationship.to || !newRelationship.relationship"
        @click="add"
      >
        <Save :size="14" />
        {{ $t("save") }}
      </button>
    </div>

    <div class="gloss-table-wrap">
      <table v-if="filteredRelationships.length">
        <thead>
          <tr>
            <th>{{ $t("from") }}</th>
            <th class="w-8"></th>
            <th>{{ $t("to") }}</th>
            <th>{{ $t("relationship") }}</th>
            <th>{{ $t("since") }}</th>
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
              <td class="arrow text-center"><ArrowRight :size="14" class="text-zinc-500 inline" /></td>
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
                  <button
                    type="button"
                    class="flex items-center gap-1"
                    :disabled="!editing.relationship"
                    @click="saveEdit"
                  >
                    <Save :size="13" />
                    {{ $t("save") }}
                  </button>
                  <button class="secondary flex items-center gap-1" type="button" @click="editing = null">
                    <X :size="13" />
                    {{ $t("cancel") }}
                  </button>
                </div>
              </td>
            </template>
            <template v-else>
              <td class="gloss-original font-medium text-zinc-100">{{ edge.from }}</td>
              <td class="arrow text-center"><ArrowRight :size="14" class="text-zinc-500 inline" /></td>
              <td class="gloss-original font-medium text-zinc-100">{{ edge.to }}</td>
              <td><span class="inline-block px-2 py-0.5 text-xs rounded bg-zinc-800 text-zinc-200 border border-zinc-700">{{ edge.relationship }}</span></td>
              <td class="text-zinc-400 text-sm">{{ edge.since !== null ? $t('chapter_number', { number: edge.since }) : '—' }}</td>
              <td class="actions">
                <div class="row gap-1 row-actions">
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2"
                    type="button"
                    @click="startEdit(edge, index)"
                  >
                    <Edit2 :size="12" />
                    {{ $t("edit") }}
                  </button>
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2 text-rose-400 hover:text-rose-300"
                    type="button"
                    @click="removeRelationship(edge.from, edge.to)"
                  >
                    <Trash2 :size="12" />
                    {{ $t("remove") }}
                  </button>
                </div>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted gloss-empty">
        {{ filter ? $t('no_relationships_match_the_filter') : $t('no_relationships_yet') }}
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
