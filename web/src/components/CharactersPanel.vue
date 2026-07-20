<script setup lang="ts">
import { computed, ref } from 'vue'
import type { GlossaryCharacter } from '@/composables/glossary'

const props = defineProps<{
  characters: Record<string, GlossaryCharacter>
  saveCharacter: (original: string, translatedName: string, role: string, pronoun?: string) => Promise<boolean>
  removeCharacter: (original: string) => Promise<boolean>
}>()

const filter = ref('')
const newCharacter = ref({ original: '', translatedName: '', role: '', pronoun: '' })
const showAdd = ref(false)
const editing = ref<{ original: string; translatedName: string; role: string; pronoun: string } | null>(null)

const filteredCharacters = computed<[string, GlossaryCharacter][]>(() => {
  const query = filter.value.trim().toLowerCase()
  const entries = Object.entries(props.characters)
  if (!query) return entries.sort(([left], [right]) => left.localeCompare(right))
  return entries
    .filter(([original, info]) => {
      if (original.toLowerCase().includes(query)) return true
      return [info.translated_name, info.role, info.pronoun]
        .filter((value): value is string => Boolean(value))
        .some((value) => value.toLowerCase().includes(query))
    })
    .sort(([left], [right]) => left.localeCompare(right))
})

async function add() {
  if (!newCharacter.value.original) return
  if (!await props.saveCharacter(
    newCharacter.value.original,
    newCharacter.value.translatedName,
    newCharacter.value.role,
    newCharacter.value.pronoun || undefined
  )) return
  newCharacter.value = { original: '', translatedName: '', role: '', pronoun: '' }
  showAdd.value = false
}

function startEdit(original: string, info: GlossaryCharacter) {
  editing.value = {
    original,
    translatedName: info.translated_name ?? '',
    role: info.role ?? '',
    pronoun: info.pronoun ?? ''
  }
}

async function saveEdit() {
  if (!editing.value) return
  if (!await props.saveCharacter(
    editing.value.original,
    editing.value.translatedName,
    editing.value.role,
    editing.value.pronoun
  )) return
  editing.value = null
}
</script>

<template>
  <section class="gloss-section card">
    <header class="gloss-header">
      <div>
        <h3>Characters</h3>
        <p class="muted">{{ Object.keys(characters).length }} character entities</p>
      </div>
      <div class="gloss-controls">
        <input v-model="filter" placeholder="Filter characters…" class="gloss-filter" />
        <button type="button" class="secondary" @click="showAdd = !showAdd">
          {{ showAdd ? 'Cancel' : 'Add / update' }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add">
      <input v-model="newCharacter.original" placeholder="Original name" />
      <input v-model="newCharacter.translatedName" placeholder="Translated name" />
      <select v-model="newCharacter.role">
        <option value="">(role unchanged)</option>
        <option value="protagonist">protagonist</option>
        <option value="antagonist">antagonist</option>
        <option value="supporting">supporting</option>
        <option value="minor">minor</option>
      </select>
      <input v-model="newCharacter.pronoun" placeholder="Pronoun / reference style" />
      <button type="button" :disabled="!newCharacter.original" @click="add">Save</button>
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
            <template v-if="editing?.original === original">
              <td class="gloss-original">{{ original }}</td>
              <td><input v-model="editing.translatedName" class="inline-edit-input" /></td>
              <td>
                <select v-model="editing.role" class="inline-edit-input">
                  <option value="">(role unchanged)</option>
                  <option value="protagonist">protagonist</option>
                  <option value="antagonist">antagonist</option>
                  <option value="supporting">supporting</option>
                  <option value="minor">minor</option>
                </select>
              </td>
              <td>
                <input
                  v-model="editing.pronoun"
                  class="inline-edit-input"
                  placeholder="Pronoun / reference style"
                />
              </td>
              <td class="actions">
                <div class="row gap-1">
                  <button type="button" @click="saveEdit">Save</button>
                  <button class="secondary" type="button" @click="editing = null">Cancel</button>
                </div>
              </td>
            </template>
            <template v-else>
              <td class="gloss-original">{{ original }}</td>
              <td>{{ info.translated_name ?? '—' }}</td>
              <td>{{ info.role ?? '—' }}</td>
              <td>{{ info.pronoun || '—' }}</td>
              <td class="actions">
                <div class="row gap-1 row-actions">
                  <button class="secondary" type="button" @click="startEdit(original, info)">Edit</button>
                  <button class="secondary" type="button" @click="removeCharacter(original)">Remove</button>
                </div>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted gloss-empty">
        {{ filter ? 'No characters match the filter.' : 'No characters yet.' }}
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
