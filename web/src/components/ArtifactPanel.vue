<script setup lang="ts">
import { onUnmounted, ref, toRef, watch } from 'vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'
import { useArtifacts } from '@/composables/artifacts'
import type { TargetLanguage } from '@/composables/metadata'
import { formatDateTime } from '@/datetime'

const props = defineProps<{
  novel: string
  targetLanguage: TargetLanguage
  targetLanguageLabel: string
  active: boolean
  packOpen: boolean
}>()

const emit = defineEmits<{
  'update:packOpen': [value: boolean]
  jobStarted: [jobId: string]
}>()

const {
  error,
  packError,
  deleteSaving,
  visible,
  load,
  download,
  remove,
  startPack
} = useArtifacts(toRef(props, 'novel'), toRef(props, 'targetLanguage'))
const packTitle = ref('')
const packAuthor = ref('')
const showDeleteDialog = ref(false)
const deleteName = ref<string | null>(null)

watch(() => props.active, (active) => {
  if (active) void load()
}, { immediate: true })

watch(() => props.packOpen, (isOpen) => {
  document.body.style.overflow = isOpen ? 'hidden' : ''
})

onUnmounted(() => {
  document.body.style.overflow = ''
})

function closePack() {
  emit('update:packOpen', false)
}

async function submitPack() {
  const jobId = await startPack(packTitle.value, packAuthor.value)
  if (!jobId) return
  emit('jobStarted', jobId)
  closePack()
}

function confirmDelete(name: string) {
  deleteName.value = name
  showDeleteDialog.value = true
}

async function deleteArtifact() {
  if (!deleteName.value) return
  const removed = await remove(deleteName.value)
  if (removed) showDeleteDialog.value = false
  deleteName.value = null
}

function cancelDelete() {
  showDeleteDialog.value = false
  deleteName.value = null
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

</script>

<template>
  <div
    v-show="active"
    id="artifacts-panel"
    class="detail-tab-panel"
    role="tabpanel"
    aria-labelledby="artifacts-tab"
  >
    <DetailPanelHeader title="Artifacts" />
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="!visible.length" class="muted">No {{ targetLanguage.toUpperCase() }} artifacts yet.</p>
    <div v-else class="artifact-list">
      <div v-for="artifact in visible" :key="artifact.name" class="artifact-item">
        <div class="artifact-info">
          <div class="artifact-name">{{ artifact.name }}</div>
          <div class="artifact-meta">
            <span class="artifact-badge">{{ artifact.format.toUpperCase() }}</span>
            <span class="artifact-badge">{{ artifact.target_language.toUpperCase() }}</span>
            <span v-if="artifact.metadata_status === 'inferred'" class="artifact-badge artifact-badge-warning">
              Metadata inferred
            </span>
            <span class="muted">{{ artifact.chapter_count }} chapters</span>
            <span class="muted">—</span>
            <span class="muted">{{ formatFileSize(artifact.size) }}</span>
            <span class="muted">—</span>
            <span class="muted">{{ formatDateTime(artifact.created_at) }}</span>
          </div>
        </div>
        <div class="artifact-actions">
          <button class="secondary" type="button" @click="download(artifact.name)">Download</button>
          <button class="secondary danger" type="button" @click="confirmDelete(artifact.name)">Delete</button>
        </div>
      </div>
    </div>
  </div>

  <div v-if="packOpen" class="modal-overlay">
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="pack-title" tabindex="-1">
      <header class="modal-header">
        <h3 id="pack-title">Pack Novel</h3>
        <button type="button" class="modal-close" aria-label="Close" @click="closePack">&times;</button>
      </header>
      <div class="modal-body">
        <div class="pack-target">
          <label>Target language</label>
          <div>{{ targetLanguageLabel }} ({{ targetLanguage }})</div>
        </div>
        <div class="pack-meta">
          <div>
            <label>Custom title (optional)</label>
            <input v-model="packTitle" placeholder="defaults to metadata title" />
          </div>
          <div>
            <label>Custom author (optional)</label>
            <input v-model="packAuthor" placeholder="defaults to metadata author" />
          </div>
        </div>
        <p v-if="packError" class="error pack-error">{{ packError }}</p>
      </div>
      <footer class="modal-footer">
        <button type="button" class="secondary" @click="closePack">Cancel</button>
        <button type="button" @click="submitPack">Start pack</button>
      </footer>
    </div>
  </div>

  <ConfirmDialog
    :show="showDeleteDialog"
    title="Delete Artifact"
    :message="`Delete artifact '${deleteName}'?\n\nThis permanently removes the exported file. This cannot be undone.`"
    confirm-label="Delete"
    :danger="true"
    :loading="deleteSaving"
    @confirm="deleteArtifact"
    @cancel="cancelDelete"
  />
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.detail-tab-panel {
  padding: 1rem;
}

.detail-tab-panel > .error,
.detail-tab-panel > .muted {
  margin: 0;
}

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.artifact-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.artifact-info {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 0.25rem;
}

.artifact-name {
  font-weight: 500;
  word-break: break-all;
}

.artifact-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.artifact-badge {
  padding: 0.15rem 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.artifact-badge-warning {
  color: var(--warning, #b7791f);
}

.artifact-actions {
  display: flex;
  flex-shrink: 0;
  gap: 0.5rem;
}

button.secondary.danger {
  color: var(--danger, #dc3545);
  background: transparent;
  border-color: var(--danger, #dc3545);
}

button.secondary.danger:hover:not(:disabled) {
  color: #fff;
  background: var(--danger, #dc3545);
}

.pack-target {
  max-width: 14rem;
}

.pack-meta {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.pack-meta input {
  width: 100%;
}

.pack-error {
  margin-top: 0.5rem;
}
</style>
