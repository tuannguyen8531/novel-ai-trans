<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  terms: Record<string, string>
  addTerm: (original: string, translated: string) => Promise<boolean>
  updateTerm: (oldOriginal: string, original: string, translated: string) => Promise<boolean>
  removeTerm: (original: string) => Promise<boolean>
}>()

const filter = ref('')
const newTerm = ref({ original: '', translated: '' })
const showAdd = ref(false)
const editing = ref<{ oldOriginal: string; original: string; translated: string } | null>(null)

const filteredTerms = computed<[string, string][]>(() => {
  const query = filter.value.trim().toLowerCase()
  const entries = Object.entries(props.terms)
  if (!query) return entries.sort(([left], [right]) => left.localeCompare(right))
  return entries
    .filter(([original, translated]) =>
      original.toLowerCase().includes(query) || translated.toLowerCase().includes(query)
    )
    .sort(([left], [right]) => left.localeCompare(right))
})

async function add() {
  if (!newTerm.value.original || !newTerm.value.translated) return
  if (!await props.addTerm(newTerm.value.original, newTerm.value.translated)) return
  newTerm.value = { original: '', translated: '' }
  showAdd.value = false
}

function startEdit(original: string, translated: string) {
  editing.value = { oldOriginal: original, original, translated }
}

async function saveEdit() {
  if (!editing.value?.original || !editing.value.translated) return
  if (!await props.updateTerm(
    editing.value.oldOriginal,
    editing.value.original,
    editing.value.translated
  )) return
  editing.value = null
}
</script>

<template>
  <section class="gloss-section card">
    <header class="gloss-header">
      <div>
        <h3>Terms</h3>
        <p class="muted">{{ Object.keys(terms).length }} glossary entries</p>
      </div>
      <div class="gloss-controls">
        <input v-model="filter" placeholder="Filter terms…" class="gloss-filter" />
        <button type="button" class="secondary" @click="showAdd = !showAdd">
          {{ showAdd ? 'Cancel' : 'Add term' }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add">
      <input v-model="newTerm.original" placeholder="Original (source language)" />
      <input v-model="newTerm.translated" placeholder="Translated" />
      <button
        type="button"
        :disabled="!newTerm.original || !newTerm.translated"
        @click="add"
      >Save</button>
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
            <template v-if="editing?.oldOriginal === original">
              <td><input v-model="editing.original" class="inline-edit-input" /></td>
              <td><input v-model="editing.translated" class="inline-edit-input" /></td>
              <td class="actions">
                <div class="row gap-1">
                  <button
                    type="button"
                    :disabled="!editing.original || !editing.translated"
                    @click="saveEdit"
                  >Save</button>
                  <button class="secondary" type="button" @click="editing = null">Cancel</button>
                </div>
              </td>
            </template>
            <template v-else>
              <td class="gloss-original">{{ original }}</td>
              <td>{{ translated }}</td>
              <td class="actions">
                <div class="row gap-1 row-actions">
                  <button class="secondary" type="button" @click="startEdit(original, translated)">Edit</button>
                  <button class="secondary" type="button" @click="removeTerm(original)">Remove</button>
                </div>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted gloss-empty">
        {{ filter ? 'No terms match the filter.' : 'No terms yet.' }}
      </p>
    </div>
  </section>
</template>

<style scoped src="../assets/glossary.css"></style>
<style scoped>
.row-actions {
  display: inline-flex;
}
</style>
