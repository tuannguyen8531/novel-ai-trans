<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { GlossaryApplyResponse, GlossaryReplacementReport, GlossaryResponse } from '@/api/types'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

interface Edge {
  from: string
  to: string
  relationship: string
  since: number | null
}

const props = defineProps<{ novel: string }>()

const data = ref<GlossaryResponse | null>(null)
const error = ref<string | null>(null)
const actionMessage = ref<string | null>(null)
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

const confirmDialog = ref<{
  show: boolean
  title: string
  message: string
  confirmLabel: string
  danger: boolean
  resolve: ((value: boolean) => void) | null
}>({
  show: false,
  title: '',
  message: '',
  confirmLabel: 'Confirm',
  danger: false,
  resolve: null
})

function askConfirm(
  title: string,
  message: string,
  options: { confirmLabel?: string; danger?: boolean } = {}
): Promise<boolean> {
  return new Promise((resolve) => {
    confirmDialog.value = {
      show: true,
      title,
      message,
      confirmLabel: options.confirmLabel ?? 'Confirm',
      danger: options.danger ?? false,
      resolve
    }
  })
}

function handleConfirmDialogConfirm() {
  confirmDialog.value.resolve?.(true)
  confirmDialog.value.show = false
  confirmDialog.value.resolve = null
}

function handleConfirmDialogCancel() {
  confirmDialog.value.resolve?.(false)
  confirmDialog.value.show = false
  confirmDialog.value.resolve = null
}

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
  if (!await askConfirm('Remove Term', `Remove term "${original}"?`, { confirmLabel: 'Remove', danger: true })) return
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
    if (!await askConfirm('Overwrite Term', `Term "${original}" already exists. Overwrite it?`, { confirmLabel: 'Overwrite', danger: true })) {
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
  if (!await askConfirm('Remove Character', `Remove character "${original}"? This will also remove their relationships.`, { confirmLabel: 'Remove', danger: true })) return
  try {
    data.value = await api.removeCharacter(props.novel, original)
  } catch (err) {
    error.value = (err as Error).message
  }
}

async function removeRelationship(from_char: string, to_char: string) {
  if (!await askConfirm('Remove Relationship', `Remove relationship between "${from_char}" and "${to_char}"?`, { confirmLabel: 'Remove', danger: true })) return
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

// Staged glossary / pending replacements logic
const pendingReplacements = computed<unknown[]>(() => {
  if (!data.value || !data.value.data) return []
  return (data.value.data._pending_replacements as unknown[]) ?? []
})

const showPreviewModal = ref(false)
const previewLoading = ref(false)
const previewData = ref<GlossaryApplyResponse | null>(null)
const applyLoading = ref(false)
const rollbackLoading = ref(false)
const modalCard = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

const unresolvedCount = computed(() =>
  previewData.value?.replacements.filter((replacement) =>
    ['ambiguous', 'conflict', 'missing_output'].includes(replacement.status)
  ).length ?? 0
)

async function handleDismiss() {
  if (!await askConfirm('Dismiss Pending Replacements', 'Dismiss all pending glossary replacements? Glossary values and translated files will remain unchanged; only the pending-change notice will be cleared.', { confirmLabel: 'Dismiss' })) return
  loading.value = true
  error.value = null
  actionMessage.value = null
  try {
    await api.dismissGlossary(props.novel)
    await load()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function openPreview() {
  showPreviewModal.value = true
  previewLoading.value = true
  previewData.value = null
  error.value = null
  actionMessage.value = null
  try {
    const res = await api.applyGlossary(props.novel, { write: false })
    previewData.value = res
  } catch (err) {
    error.value = (err as Error).message
    closePreview()
  } finally {
    previewLoading.value = false
  }
}

async function handleApply() {
  applyLoading.value = true
  error.value = null
  actionMessage.value = null
  try {
    const res = await api.applyGlossary(props.novel, { write: true })
    previewData.value = res
    await load()
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    applyLoading.value = false
  }
}

async function handleRollback() {
  const backupId = previewData.value?.backup_id
  if (!backupId || !await askConfirm('Rollback Glossary', 'Restore every translated chapter changed by this apply operation? Current glossary values will remain unchanged, and pending replacements will be restored.', { confirmLabel: 'Rollback' })) return
  rollbackLoading.value = true
  error.value = null
  actionMessage.value = null
  let restored = false
  try {
    await api.rollbackGlossary(props.novel, backupId)
    await load()
    restored = true
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    rollbackLoading.value = false
  }
  if (restored) {
    closePreview()
    actionMessage.value = `Restored translated chapters from backup ${backupId}.`
  }
}

function closePreview() {
  if (applyLoading.value || rollbackLoading.value) return
  showPreviewModal.value = false
  previousFocus?.focus()
  previousFocus = null
}

function handleModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closePreview()
    return
  }
  if (event.key !== 'Tab' || !modalCard.value) return
  const focusable = Array.from(
    modalCard.value.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])')
  )
  if (!focusable.length) {
    event.preventDefault()
    modalCard.value.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function getStatusClass(status: string) {
  if (status === 'safe' || status === 'applied' || status === 'already_applied') return 'ok'
  if (status === 'ambiguous' || status === 'missing_output') return 'warn'
  if (status === 'conflict') return 'danger'
  return ''
}

function statusLabel(replacement: GlossaryReplacementReport): string {
  if (previewData.value?.write && replacement.status === 'safe') return 'APPLIED'
  return replacement.status.toUpperCase()
}

// Lock background scrolling when modal is open
watch(showPreviewModal, (isOpen) => {
  if (isOpen) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => modalCard.value?.focus())
  } else {
    document.body.style.overflow = ''
  }
})

watch([applyLoading, rollbackLoading], ([applying, rollingBack]) => {
  if (applying || rollingBack) {
    void nextTick(() => modalCard.value?.focus())
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="glossary">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="notice">{{ actionMessage }}</p>

    <!-- Alert Banner for Pending Glossary Changes -->
    <div v-if="pendingReplacements.length" class="pending-banner">
      <div class="pending-banner-text">
        <span>⚠️ You have <strong>{{ pendingReplacements.length }}</strong> pending glossary changes waiting to be applied to translated chapters.</span>
      </div>
      <div class="pending-banner-actions">
        <button type="button" @click="openPreview" :disabled="loading">Preview & Apply</button>
        <button type="button" class="secondary" @click="handleDismiss" :disabled="loading">Dismiss</button>
      </div>
    </div>

    <!-- Modal Preview & Apply -->
    <div v-if="showPreviewModal" class="modal-overlay">
      <div
        ref="modalCard"
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="glossary-preview-title"
        tabindex="-1"
        @keydown="handleModalKeydown"
      >
        <header class="modal-header">
          <h3 id="glossary-preview-title">Preview & Apply Glossary Changes</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close glossary preview"
            :disabled="applyLoading || rollbackLoading"
            @click="closePreview"
          >&times;</button>
        </header>
        <div class="modal-body">
          <p v-if="error" class="error">{{ error }}</p>
          <div v-if="previewLoading" class="preview-spinner">
            <p>Scanning translated chapters...</p>
          </div>
          <div v-else-if="previewData">
            <div class="preview-summary">
              <p>
                Novel: <strong>{{ previewData.novel }}</strong> | Target language: <strong>{{ previewData.target }}</strong>
              </p>
              <p>
                Files to change: <strong>{{ previewData.changed_files }} file(s)</strong>
              </p>
              <p v-if="previewData.conflicted" class="error">
                ⚠️ Conflict detected. You cannot overwrite the translation while conflicts exist.
              </p>
              <p v-else-if="previewData.write" class="notice">
                Updated {{ previewData.changed_files }} file(s).
                <template v-if="unresolvedCount">{{ unresolvedCount }} issue(s) remain pending.</template>
              </p>
              <p v-if="previewData.backup_id" class="muted">
                Backup: <code>{{ previewData.backup_id }}</code>
              </p>
            </div>

            <div v-if="previewData.replacements.length" class="preview-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Chapter</th>
                    <th>Kind</th>
                    <th>Original</th>
                    <th>Old translation</th>
                    <th>New translation</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(rep, idx) in previewData.replacements" :key="idx">
                    <td>Ch.{{ rep.chapter }}</td>
                    <td>{{ rep.kind }}</td>
                    <td>{{ rep.sources.join('/') }}</td>
                    <td>{{ rep.old }}</td>
                    <td>{{ rep.new }}</td>
                    <td>
                      <span :class="['badge', getStatusClass(rep.status)]">
                        {{ statusLabel(rep) }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="muted">No matching translated chapter occurrences were found in existing output.</p>
          </div>
        </div>
        <footer class="modal-footer">
          <button
            v-if="previewData?.backup_id"
            type="button"
            class="secondary"
            :disabled="applyLoading || rollbackLoading"
            @click="handleRollback"
          >
            {{ rollbackLoading ? 'Restoring...' : 'Rollback' }}
          </button>
          <button type="button" class="secondary" @click="closePreview" :disabled="applyLoading || rollbackLoading">
            {{ previewData?.write ? 'Close' : 'Cancel' }}
          </button>
          <button
            v-if="previewData && !previewLoading && !previewData.write"
            type="button"
            @click="handleApply"
            :disabled="previewData.conflicted || applyLoading"
          >
            {{ applyLoading ? 'Applying...' : 'Confirm & Apply' }}
          </button>
        </footer>
      </div>
    </div>

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

    <ConfirmDialog
      :show="confirmDialog.show"
      :title="confirmDialog.title"
      :message="confirmDialog.message"
      :confirm-label="confirmDialog.confirmLabel"
      :danger="confirmDialog.danger"
      @confirm="handleConfirmDialogConfirm"
      @cancel="handleConfirmDialogCancel"
    />
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

/* Staged glossary alert banner */
.pending-banner {
  background: rgba(240, 184, 106, 0.1);
  border: 1px solid var(--warn);
  border-radius: var(--radius);
  padding: 0.75rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.pending-banner-text {
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.pending-banner-actions {
  display: flex;
  gap: 0.5rem;
}

/* Modal and layout overlay */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.modal-card {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 100%;
  max-width: 44rem;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
}

.modal-header {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.modal-header h3 {
  margin: 0;
  flex: 1;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--fg-dim);
  cursor: pointer;
  padding: 0;
  line-height: 1;
  width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-close:hover:not(:disabled) {
  color: var(--fg);
  background: var(--bg-elev-2);
  border-radius: var(--radius);
}

.modal-close:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
}

.preview-summary {
  margin-bottom: 1.25rem;
  padding: 0.75rem 1rem;
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.preview-summary p {
  margin: 0.25rem 0;
}

.preview-table-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  max-height: 25rem;
  overflow: auto;
}

.preview-spinner {
  padding: 3rem;
  text-align: center;
  color: var(--fg-dim);
}

.modal-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.notice {
  color: var(--ok);
}
</style>
