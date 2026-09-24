<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Search, Edit2, Trash2, Save, X, Users, User } from '@lucide/vue'
import type { GlossaryCharacter } from '@/composables/glossary'
import CustomSelect from '@/components/common/CustomSelect.vue'

const roleOptions = [
  { value: '', label: '(role unchanged)' },
  { value: 'protagonist', label: 'Protagonist' },
  { value: 'antagonist', label: 'Antagonist' },
  { value: 'supporting', label: 'Supporting' },
  { value: 'minor', label: 'Minor' }
]

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

function roleBadgeClass(role?: string) {
  switch (role) {
    case 'protagonist':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
    case 'antagonist':
      return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
    case 'supporting':
      return 'bg-sky-500/15 text-sky-300 border-sky-500/30'
    case 'minor':
      return 'bg-zinc-700/30 text-zinc-400 border-zinc-700/50'
    default:
      return 'text-zinc-500'
  }
}
</script>

<template>
  <section class="gloss-section card">
    <header class="gloss-header">
      <div class="flex items-center gap-2">
        <Users :size="18" class="text-indigo-400 shrink-0" />
        <div>
          <h3>Characters</h3>
          <p class="muted">{{ Object.keys(characters).length }} character entities</p>
        </div>
      </div>
      <div class="gloss-controls">
        <div class="relative flex items-center">
          <Search :size="14" class="absolute left-2.5 text-zinc-500 pointer-events-none" />
          <input
            v-model="filter"
            placeholder="Filter characters…"
            class="gloss-filter !pl-8"
          />
        </div>
        <button
          type="button"
          class="secondary flex items-center gap-1.5"
          @click="showAdd = !showAdd"
        >
          <component :is="showAdd ? X : Plus" :size="14" />
          {{ showAdd ? 'Cancel' : 'Add character' }}
        </button>
      </div>
    </header>

    <div v-if="showAdd" class="gloss-add p-3 bg-zinc-900/60 dark:bg-zinc-900/80 rounded-lg border border-indigo-500/30">
      <input v-model="newCharacter.original" placeholder="Original name" class="flex-1" />
      <input v-model="newCharacter.translatedName" placeholder="Translated name" class="flex-1" />
      <CustomSelect
        v-model="newCharacter.role"
        :options="roleOptions"
        placeholder="Role (optional)"
      />
      <input v-model="newCharacter.pronoun" placeholder="Pronoun / reference style" class="flex-1" />
      <button
        type="button"
        class="flex items-center gap-1.5"
        :disabled="!newCharacter.original"
        @click="add"
      >
        <Save :size="14" />
        Save
      </button>
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
                <CustomSelect
                  v-model="editing.role"
                  :options="roleOptions"
                  class="role-select-inline"
                />
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
                  <button type="button" class="flex items-center gap-1" @click="saveEdit">
                    <Save :size="13" />
                    Save
                  </button>
                  <button class="secondary flex items-center gap-1" type="button" @click="editing = null">
                    <X :size="13" />
                    Cancel
                  </button>
                </div>
              </td>
            </template>
            <template v-else>
              <td class="gloss-original font-medium text-zinc-100">{{ original }}</td>
              <td class="text-zinc-300">{{ info.translated_name ?? '—' }}</td>
              <td>
                <span
                  v-if="info.role"
                  class="inline-block px-2 py-0.5 text-xs rounded border capitalize font-medium"
                  :class="roleBadgeClass(info.role)"
                >
                  {{ info.role }}
                </span>
                <span v-else class="text-zinc-600">—</span>
              </td>
              <td class="text-zinc-400 text-sm">{{ info.pronoun || '—' }}</td>
              <td class="actions">
                <div class="row gap-1 row-actions">
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2"
                    type="button"
                    @click="startEdit(original, info)"
                  >
                    <Edit2 :size="12" />
                    Edit
                  </button>
                  <button
                    class="secondary flex items-center gap-1 text-xs py-1 px-2 text-rose-400 hover:text-rose-300"
                    type="button"
                    @click="removeCharacter(original)"
                  >
                    <Trash2 :size="12" />
                    Remove
                  </button>
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

.role-select-inline {
  min-width: 9rem;
}
</style>
