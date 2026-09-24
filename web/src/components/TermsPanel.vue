<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Search, Edit2, Trash2, Save, X, BookA } from '@lucide/vue'

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
      <div class="flex items-center gap-2">
        <BookA :size="18" class="text-indigo-400 shrink-0" />
        <div>
          <h3>{{ $t("terms") }}</h3>
          <p class="muted">{{ $t("glossary_entries", { count: Object.keys(terms).length }) }}</p>
        </div>
      </div>
      <div class="gloss-controls">
        <div class="relative flex items-center">
          <Search :size="14" class="absolute left-2.5 text-zinc-500 pointer-events-none" />
          <input
            v-model="filter"
            :placeholder="$t('filter_terms')"
            class="gloss-filter !pl-8"
          />
        </div>
        <button
          type="button"
          class="secondary flex items-center gap-1.5"
          @click="showAdd = !showAdd"
        >
          <component :is="showAdd ? X : Plus" :size="14" />
          {{ showAdd ? $t('cancel') : $t('add_term') }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add p-3 bg-zinc-900/60 dark:bg-zinc-900/80 rounded-lg border border-indigo-500/30">
      <input v-model="newTerm.original" :placeholder="$t('original_source_language')" class="flex-1" />
      <input v-model="newTerm.translated" :placeholder="$t('translated')" class="flex-1" />
      <button
        type="button"
        class="flex items-center gap-1.5"
        :disabled="!newTerm.original || !newTerm.translated"
        @click="add"
      >
        <Save :size="14" />
        {{ $t("save") }}
      </button>
    </div>

    <div class="gloss-table-wrap">
      <table v-if="filteredTerms.length">
        <thead>
          <tr>
            <th>{{ $t("original") }}</th>
            <th>{{ $t("translated") }}</th>
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
                    class="flex items-center gap-1"
                    :disabled="!editing.original || !editing.translated"
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
              <td class="gloss-original font-medium text-zinc-100">{{ original }}</td>
              <td class="text-zinc-300">{{ translated }}</td>
              <td class="actions">
                <div class="row gap-1 row-actions">
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2"
                    type="button"
                    @click="startEdit(original, translated)"
                  >
                    <Edit2 :size="12" />
                    {{ $t("edit") }}
                  </button>
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2 text-rose-400 hover:text-rose-300"
                    type="button"
                    @click="removeTerm(original)"
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
        {{ filter ? $t('no_terms_match_the_filter') : $t('no_terms_yet') }}
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
