<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNovelsStore } from '@/composables/novels'
import { useSettingsStore } from '@/composables/settings'
import type { NovelSummary, NovelTargetProgress } from '@/api/types'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const novels = useNovelsStore()
const settings = useSettingsStore()
const router = useRouter()
const deletingNovel = ref<string | null>(null)
const deleteError = ref<string | null>(null)
const showDeleteDialog = ref(false)
const novelToDelete = ref<NovelSummary | null>(null)
const showFailedDialog = ref(false)
const failedNovel = ref<NovelSummary | null>(null)
const failedChapters = ref<number[]>([])
const failedChaptersLoading = ref(false)
const failedChaptersError = ref<string | null>(null)
const showWarningDialog = ref(false)
const warningNovel = ref<NovelSummary | null>(null)
const warningChapters = ref<number[]>([])
const sourceWarningChapters = ref<Set<number>>(new Set())
const warningChaptersLoading = ref(false)
const warningChaptersError = ref<string | null>(null)
const showIgnoreWarningsDialog = ref(false)
const ignoringWarnings = ref(false)
const ignoreWarningsError = ref<string | null>(null)

// Add novel modal state
const showAddModal = ref(false)
const newSlug = ref('')
const newTitle = ref('')
const newAuthor = ref('')
const newSourceLang = ref('ko')
const newIllustrationUrl = ref('')
const newCoverFile = ref<File | null>(null)
const newCoverPreview = ref<string | null>(null)
const createdSlug = ref<string | null>(null)
const addError = ref<string | null>(null)
const adding = ref(false)

function closeAddModal() {
  showAddModal.value = false
  newSlug.value = ''
  newTitle.value = ''
  newAuthor.value = ''
  newSourceLang.value = 'ko'
  newIllustrationUrl.value = ''
  setNewCoverFile(null)
  createdSlug.value = null
  addError.value = null
}

function setNewCoverFile(file: File | null) {
  if (newCoverPreview.value) URL.revokeObjectURL(newCoverPreview.value)
  newCoverFile.value = file
  newCoverPreview.value = file ? URL.createObjectURL(file) : null
}

function selectNewCover(event: Event) {
  const input = event.target as HTMLInputElement
  setNewCoverFile(input.files?.[0] ?? null)
}

async function submitAddNovel() {
  if (!newSlug.value.trim()) return
  adding.value = true
  addError.value = null
  try {
    const slug = createdSlug.value ?? newSlug.value.trim()
    if (!createdSlug.value) {
      await novels.create({
        name: slug,
        title: newTitle.value.trim() || undefined,
        author: newAuthor.value.trim() || undefined,
        source_language: newSourceLang.value.trim() || undefined,
        illustration_url: newCoverFile.value ? undefined : (newIllustrationUrl.value.trim() || undefined)
      })
      createdSlug.value = slug
    }
    if (newCoverFile.value) {
      try {
        await novels.uploadCover(slug, newCoverFile.value)
      } catch (err) {
        addError.value = `Novel was created, but the cover could not be saved: ${(err as Error).message}`
        return
      }
    }
    closeAddModal()
  } catch (err) {
    addError.value = (err as Error).message
  } finally {
    adding.value = false
  }
}

onMounted(() => {
  void Promise.all([novels.refresh(), settings.refresh()])
})

onUnmounted(() => setNewCoverFile(null))

const totalNovels = computed(() => novels.novels.length)
const defaultTarget = computed(() => settings.settings?.target_language ?? 'vi')

function translatedProgress(novel: NovelSummary): NovelTargetProgress | undefined {
  return novel.targets.find((progress) => progress.target === defaultTarget.value)
}

function deleteNovel(novel: NovelSummary) {
  novelToDelete.value = novel
  showDeleteDialog.value = true
}

async function confirmDelete() {
  if (!novelToDelete.value) return
  deletingNovel.value = novelToDelete.value.name
  deleteError.value = null
  try {
    await novels.remove(novelToDelete.value.name)
    showDeleteDialog.value = false
  } catch (err) {
    deleteError.value = (err as Error).message
    showDeleteDialog.value = false
  } finally {
    deletingNovel.value = null
    novelToDelete.value = null
  }
}

function cancelDelete() {
  showDeleteDialog.value = false
  novelToDelete.value = null
}

async function showFailedChapters(novel: NovelSummary) {
  failedNovel.value = novel
  failedChapters.value = []
  failedChaptersError.value = null
  failedChaptersLoading.value = true
  showFailedDialog.value = true
  try {
    const progress = await novels.progress(novel.name, defaultTarget.value)
    failedChapters.value = [...progress.failed].sort((a, b) => a - b)
  } catch (err) {
    failedChaptersError.value = (err as Error).message
  } finally {
    failedChaptersLoading.value = false
  }
}

function closeFailedDialog() {
  showFailedDialog.value = false
  failedNovel.value = null
  failedChapters.value = []
  failedChaptersError.value = null
}

function retranslateFailed() {
  const name = failedNovel.value?.name
  if (!name) return
  closeFailedDialog()
  void router.push({ name: 'translate', query: { novel: name, failed_only: 'true' } })
}

async function showWarningChapters(novel: NovelSummary) {
  warningNovel.value = novel
  warningChapters.value = []
  sourceWarningChapters.value = new Set()
  warningChaptersError.value = null
  ignoreWarningsError.value = null
  warningChaptersLoading.value = true
  showWarningDialog.value = true
  try {
    const progress = await novels.progress(novel.name, defaultTarget.value)
    warningChapters.value = [...progress.warnings].sort((a, b) => a - b)
    sourceWarningChapters.value = new Set(progress.source_warnings ?? [])
  } catch (err) {
    warningChaptersError.value = (err as Error).message
  } finally {
    warningChaptersLoading.value = false
  }
}

function closeWarningDialog() {
  showWarningDialog.value = false
  warningNovel.value = null
  warningChapters.value = []
  sourceWarningChapters.value = new Set()
  warningChaptersError.value = null
  ignoreWarningsError.value = null
}

function requestIgnoreWarnings() {
  ignoreWarningsError.value = null
  showIgnoreWarningsDialog.value = true
}

function cancelIgnoreWarnings() {
  showIgnoreWarningsDialog.value = false
}

async function confirmIgnoreWarnings() {
  const novel = warningNovel.value
  if (!novel) return
  ignoringWarnings.value = true
  ignoreWarningsError.value = null
  try {
    await novels.ignoreWarnings(novel.name, defaultTarget.value)
    showIgnoreWarningsDialog.value = false
    closeWarningDialog()
    await novels.refresh()
  } catch (err) {
    showIgnoreWarningsDialog.value = false
    ignoreWarningsError.value = (err as Error).message
  } finally {
    ignoringWarnings.value = false
  }
}

const ignoreWarningsMessage = computed(() => {
  const name = warningNovel.value?.name ?? 'this novel'
  return `Ignore all current warning chapters for "${name}"? The warning decisions will apply to the current translation content.`
})

const deleteMessage = computed(() => {
  if (!novelToDelete.value) return ''
  const label = novelToDelete.value.title
    ? `"${novelToDelete.value.title}" (${novelToDelete.value.name})`
    : `"${novelToDelete.value.name}"`
  return `Delete ${label}?\n\nThis permanently removes all chapters, translations, glossary data, illustrations, and artifacts. This cannot be undone.`
})
</script>

<template>
  <section>
    <div class="card">
      <div class="row gap-3" style="margin-bottom: 1rem; justify-content: space-between;">
        <h2 style="margin: 0; font-size: 1.2rem;">All Novels</h2>
        <button type="button" @click="showAddModal = true">Add Novel</button>
      </div>
      <div v-if="deleteError" class="error delete-error">{{ deleteError }}</div>
      <div v-if="novels.error" class="error">{{ novels.error }}</div>
      <p v-else-if="!novels.novels.length" class="muted">
        No novels yet. Crawl a site or import an EPUB to get started.
      </p>
      <div v-else class="novel-table-card">
        <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Chapter</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="novel in novels.novels" :key="novel.name">
            <td class="novel-name-cell">
              <RouterLink
                class="novel-cell-link truncate-cell-text"
                :to="`/novels/${novel.name}`"
                :title="novel.name"
              >
                <code>{{ novel.name }}</code>
              </RouterLink>
            </td>
            <td class="novel-title-cell">
              <RouterLink
                class="novel-cell-link truncate-cell-text"
                :to="`/novels/${novel.name}`"
                :title="novel.title ?? undefined"
              >
                {{ novel.title ?? '—' }}
              </RouterLink>
            </td>
            <td>
              {{ translatedProgress(novel)?.completed ?? 0 }} / {{ translatedProgress(novel)?.total ?? novel.total_input_chapters }}
            </td>
            <td>
              <div class="status-badges">
                <button
                  v-if="(translatedProgress(novel)?.failed ?? 0) > 0"
                  type="button"
                  class="badge danger status-badge"
                  @click="showFailedChapters(novel)"
                >
                  failed: {{ translatedProgress(novel)?.failed }}
                </button>
                <button
                  v-if="(translatedProgress(novel)?.warnings ?? 0) > 0"
                  type="button"
                  class="badge warn status-badge"
                  title="Chapters that still contain source-language characters"
                  @click="showWarningChapters(novel)"
                >
                  warning: {{ translatedProgress(novel)?.warnings }}
                </button>
                <span
                  v-if="(translatedProgress(novel)?.failed ?? 0) === 0 && (translatedProgress(novel)?.warnings ?? 0) === 0"
                  class="badge ok"
                >
                  normal
                </span>
              </div>
            </td>
            <td class="novel-actions">
              <div class="novel-actions-inner">
                <button
                  class="action-link delete-link"
                  type="button"
                  :disabled="deletingNovel !== null"
                  @click="deleteNovel(novel)"
                >
                  {{ deletingNovel === novel.name ? 'Deleting…' : 'Delete' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
        </table>
      </div>
      <p class="muted" style="margin-top: 0.5rem; margin-bottom: 0;">
        {{ totalNovels }} novels in your library.
      </p>
    </div>

    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Novel"
      :message="deleteMessage"
      confirm-label="Delete"
      :danger="true"
      :loading="deletingNovel !== null"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <div v-if="showFailedDialog" class="modal-overlay" @click.self="closeFailedDialog">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="failed-chapters-title">
        <div class="modal-header">
          <h3 id="failed-chapters-title">
            Failed chapters — {{ failedNovel?.name }}
          </h3>
          <button class="modal-close" type="button" aria-label="Close" @click="closeFailedDialog">
            &times;
          </button>
        </div>
        <div class="modal-body">
          <p v-if="failedChaptersLoading" class="muted">Loading failed chapters...</p>
          <p v-else-if="failedChaptersError" class="error">{{ failedChaptersError }}</p>
          <p v-else-if="!failedChapters.length" class="muted">No failed chapters.</p>
          <div v-else class="failed-chapter-list">
            <RouterLink
              v-for="chapter in failedChapters"
              :key="chapter"
              class="failed-chapter-link"
              :to="`/novels/${failedNovel?.name}/chapters/${chapter}`"
              @click="closeFailedDialog"
            >
              Chapter {{ chapter }}
            </RouterLink>
          </div>
        </div>
        <div class="modal-footer">
          <button
            type="button"
            class="secondary"
            :disabled="failedChaptersLoading || !failedNovel"
            @click="retranslateFailed"
          >
            Retranslate
          </button>
        </div>
      </div>
    </div>

    <div v-if="showWarningDialog" class="modal-overlay" @click.self="closeWarningDialog">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="warning-chapters-title">
        <div class="modal-header">
          <h3 id="warning-chapters-title">
            Warning chapters — {{ warningNovel?.name }}
          </h3>
          <button class="modal-close" type="button" aria-label="Close" @click="closeWarningDialog">
            &times;
          </button>
        </div>
        <div class="modal-body">
          <p v-if="ignoreWarningsError" class="error">{{ ignoreWarningsError }}</p>
          <p v-if="warningChaptersLoading" class="muted">Loading warning chapters...</p>
          <p v-else-if="warningChaptersError" class="error">{{ warningChaptersError }}</p>
          <p v-else-if="!warningChapters.length" class="muted">No warning chapters.</p>
          <div v-else class="failed-chapter-list">
            <RouterLink
              v-for="chapter in warningChapters"
              :key="chapter"
              class="failed-chapter-link"
              :class="{ 'source-warning-chapter': sourceWarningChapters.has(chapter) }"
              :to="`/novels/${warningNovel?.name}/chapters/${chapter}`"
              @click="closeWarningDialog"
            >
              Chapter {{ chapter }}
            </RouterLink>
          </div>
        </div>
        <div class="modal-footer">
          <button
            type="button"
            class="secondary"
            :disabled="warningChaptersLoading || !warningChapters.length || Boolean(warningChaptersError)"
            @click="requestIgnoreWarnings"
          >
            Ignore
          </button>
        </div>
      </div>
    </div>

    <ConfirmDialog
      :show="showIgnoreWarningsDialog"
      title="Ignore Warnings"
      :message="ignoreWarningsMessage"
      confirm-label="Ignore"
      :danger="true"
      :loading="ignoringWarnings"
      @confirm="confirmIgnoreWarnings"
      @cancel="cancelIgnoreWarnings"
    />

    <!-- Add Novel Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="closeAddModal">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Create New Novel</h3>
          <button class="modal-close" type="button" @click="closeAddModal">&times;</button>
        </div>
        <div class="modal-body flex-col gap-3">
          <div v-if="addError" class="error">{{ addError }}</div>
          <div>
            <label for="new-slug">Short name <span class="danger">*</span></label>
            <input id="new-slug" v-model="newSlug" :disabled="Boolean(createdSlug)" placeholder="e.g. my-awesome-novel (only letters, numbers, dashes, underscores)" />
          </div>
          <div>
            <label for="new-title">Title</label>
            <input id="new-title" v-model="newTitle" :disabled="Boolean(createdSlug)" placeholder="e.g. My Awesome Novel" />
          </div>
          <div>
            <label for="new-author">Author</label>
            <input id="new-author" v-model="newAuthor" :disabled="Boolean(createdSlug)" placeholder="e.g. Author Name" />
          </div>
          <div>
            <label for="new-lang">Language</label>
            <select id="new-lang" v-model="newSourceLang" :disabled="Boolean(createdSlug)">
              <option value="ko">Korean</option>
              <option value="ja">Japanese</option>
              <option value="zh">Chinese</option>
            </select>
          </div>
          <div>
            <label for="new-cover">Upload cover</label>
            <input
              id="new-cover"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              @change="selectNewCover"
            />
            <p class="muted cover-help">JPEG, PNG, WebP, or GIF; up to 10 MiB.</p>
            <img v-if="newCoverPreview" class="cover-preview" :src="newCoverPreview" alt="Cover preview" />
          </div>
          <div>
            <label for="new-illustration">Remote cover URL</label>
            <input
              id="new-illustration"
              v-model="newIllustrationUrl"
              :disabled="Boolean(newCoverFile) || Boolean(createdSlug)"
              placeholder="https://example.com/cover.jpg (alternative to upload)"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="secondary" type="button" :disabled="adding" @click="closeAddModal">Cancel</button>
          <button type="button" :disabled="adding || !newSlug.trim()" @click="submitAddNovel">
            {{ adding ? 'Saving…' : (createdSlug ? 'Retry cover upload' : 'Create Novel') }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.novel-table-card {
  overflow-x: auto;
}

.novel-table-card :deep(th),
.novel-table-card :deep(td) {
  white-space: nowrap;
}

.delete-error {
  margin-bottom: 0.75rem;
}

.novel-name-cell {
  max-width: clamp(8rem, 18vw, 18rem);
}

.novel-title-cell {
  max-width: clamp(10rem, 32vw, 30rem);
}

.truncate-cell-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-title-cell .truncate-cell-text {
  padding-block: 0.08em;
  line-height: 1.4;
}

.novel-cell-link {
  color: var(--fg);
}

button.status-badge {
  background: var(--bg-elev-2);
}

button.status-badge.danger,
button.status-badge.danger:hover:not(:disabled) {
  color: var(--danger);
  border-color: var(--danger);
}

button.status-badge.warn,
button.status-badge.warn:hover:not(:disabled) {
  color: var(--warn);
  border-color: var(--warn);
}

button.status-badge:hover:not(:disabled) {
  text-decoration: underline;
}

.status-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.failed-chapter-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));
  gap: 0.5rem;
}

.failed-chapter-link {
  padding: 0.45rem 0.6rem;
  color: var(--fg);
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-align: center;
}

.failed-chapter-link.source-warning-chapter {
  border-color: var(--danger);
}

.novel-actions {
  text-align: right;
  vertical-align: middle;
  white-space: nowrap;
}

.novel-actions-inner {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}

.action-link {
  padding: 0;
  background: transparent;
  color: var(--accent);
  border: 0;
  border-radius: 0;
}

.delete-link {
  color: var(--danger);
}

button.action-link:hover:not(:disabled) {
  background: transparent;
  text-decoration: underline;
}

/* Modal Styles */
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
  max-width: 32rem;
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

.modal-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.danger {
  color: var(--danger);
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
