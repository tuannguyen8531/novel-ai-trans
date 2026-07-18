<script setup lang="ts">
import { onMounted, onUnmounted, toRef, watch } from 'vue'
import { useMetadata, type MetadataDisplay, type TargetLanguage } from '@/composables/metadata'

const props = defineProps<{
  novel: string
  targetLanguage: TargetLanguage
  targetLanguageLabel: string
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  display: [value: MetadataDisplay]
  jobStarted: [jobId: string]
}>()

const {
  metadata,
  loading,
  loadError,
  error,
  saving,
  title,
  author,
  sourceUrl,
  illustrationUrl,
  summary,
  sourceLanguage,
  force,
  coverFile,
  setCoverFile,
  targetTitle,
  targetSummary,
  display,
  load,
  save,
  localize
} = useMetadata(
  toRef(props, 'novel'),
  toRef(props, 'targetLanguage')
)

watch(display, (value) => emit('display', value), { immediate: true })
watch(() => props.open, (isOpen) => {
  document.body.style.overflow = isOpen ? 'hidden' : ''
})

onMounted(load)
onUnmounted(() => {
  document.body.style.overflow = ''
})

function close() {
  setCoverFile(null)
  emit('update:open', false)
}

function selectCover(event: Event) {
  const input = event.target as HTMLInputElement
  setCoverFile(input.files?.[0] ?? null)
}

async function saveAndClose() {
  if (await save()) close()
}

async function saveAndLocalize() {
  if (!await save()) return
  close()
  const jobId = await localize()
  if (jobId) emit('jobStarted', jobId)
}

defineExpose({ load })
</script>

<template>
  <div v-if="open" class="modal-overlay">
    <div
      class="modal-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="metadata-title"
      tabindex="-1"
    >
      <header class="modal-header">
        <h3 id="metadata-title">Edit Metadata</h3>
        <button type="button" class="modal-close" aria-label="Close" @click="close">&times;</button>
      </header>
      <div class="modal-body">
        <p v-if="loading" class="muted">Loading metadata…</p>
        <p v-else-if="loadError" class="error">Failed to load metadata: {{ loadError }}</p>
        <p v-else-if="!metadata" class="muted">
          No metadata.json yet. Fill in the fields below and save to create one.
        </p>

        <div v-if="!loading" class="metadata-fields">
          <div>
            <label>Original title</label>
            <input v-model="title" placeholder="원제목 / タイトル / title" />
          </div>
          <div>
            <label>Author</label>
            <input v-model="author" placeholder="author name" />
          </div>
          <div>
            <label>Source URL</label>
            <input v-model="sourceUrl" placeholder="https://..." />
          </div>
          <div>
            <label for="metadata-cover-file">Upload cover</label>
            <input
              id="metadata-cover-file"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              @change="selectCover"
            />
            <p class="muted cover-help">JPEG, PNG, WebP, or GIF; up to 10 MiB. Saved as optimized cover.jpg.</p>
            <img v-if="display.illustrationSrc" class="cover-preview" :src="display.illustrationSrc" alt="Cover preview" />
          </div>
          <div>
            <label>Remote cover URL</label>
            <input
              v-model="illustrationUrl"
              :disabled="Boolean(coverFile)"
              placeholder="https://... (alternative to upload)"
            />
          </div>
          <div>
            <label>Summary</label>
            <textarea v-model="summary" class="metadata-summary-input" placeholder="novel synopsis (optional)"></textarea>
          </div>
          <div>
            <label>Source language</label>
            <select v-model="sourceLanguage">
              <option value="">(Auto-detect)</option>
              <option value="korean">Korean</option>
              <option value="japanese">Japanese</option>
              <option value="chinese">Chinese</option>
            </select>
          </div>
          <div class="localization-fields">
            <div>
              <label>Translated title — {{ targetLanguage }}</label>
              <input v-model="targetTitle" :placeholder="`${targetLanguageLabel} title`" />
            </div>
            <div>
              <label>Translated summary — {{ targetLanguage }}</label>
              <textarea
                v-model="targetSummary"
                class="metadata-summary-input"
                :placeholder="`${targetLanguageLabel} summary`"
              ></textarea>
            </div>
            <label class="check">
              <input v-model="force" type="checkbox" />
              <span>Regenerate existing AI translations</span>
            </label>
            <div class="row gap-2">
              <button class="secondary" type="button" :disabled="saving" @click="saveAndLocalize">
                Save and translate {{ targetLanguageLabel }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="error" class="error operation-error">{{ error }}</p>
      </div>
      <footer class="modal-footer">
        <button class="secondary" type="button" :disabled="saving" @click="close">Cancel</button>
        <button class="secondary" type="button" :disabled="saving" @click="load">Revert</button>
        <button type="button" :disabled="saving" @click="saveAndClose">
          {{ saving ? 'Saving…' : 'Save metadata' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.metadata-fields,
.localization-fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.localization-fields {
  margin-top: 0.25rem;
}

.metadata-fields input:not([type='checkbox']),
.metadata-fields select {
  width: 100%;
}

.metadata-summary-input {
  width: 100%;
  height: 10rem;
  resize: none;
}

.operation-error {
  margin-top: 0.5rem;
}

.cover-help {
  margin: 0.35rem 0 0;
  font-size: 0.85rem;
}

.cover-preview {
  display: block;
  width: min(10rem, 100%);
  max-height: 14rem;
  margin-top: 0.65rem;
  object-fit: contain;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
</style>
