<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useNovelsStore } from '@/stores/novels'
import { useSettingsStore } from '@/stores/settings'
import type { NovelSummary, NovelTargetProgress } from '@/api/types'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const novels = useNovelsStore()
const settings = useSettingsStore()
const deletingNovel = ref<string | null>(null)
const deleteError = ref<string | null>(null)
const showDeleteDialog = ref(false)
const novelToDelete = ref<NovelSummary | null>(null)

// Add novel modal state
const showAddModal = ref(false)
const newSlug = ref('')
const newTitle = ref('')
const newAuthor = ref('')
const newSourceLang = ref('ko')
const newIllustrationUrl = ref('')
const addError = ref<string | null>(null)
const adding = ref(false)

function closeAddModal() {
  showAddModal.value = false
  newSlug.value = ''
  newTitle.value = ''
  newAuthor.value = ''
  newSourceLang.value = 'ko'
  newIllustrationUrl.value = ''
  addError.value = null
}

async function submitAddNovel() {
  if (!newSlug.value.trim()) return
  adding.value = true
  addError.value = null
  try {
    await novels.create({
      name: newSlug.value.trim(),
      title: newTitle.value.trim() || undefined,
      author: newAuthor.value.trim() || undefined,
      source_language: newSourceLang.value.trim() || undefined,
      illustration_url: newIllustrationUrl.value.trim() || undefined
    })
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
    <div class="row gap-3" style="margin-bottom: 1rem; justify-content: space-between;">
      <h2 style="margin: 0; font-size: 1.2rem;">All Novels</h2>
      <button type="button" @click="showAddModal = true">Add Novel</button>
    </div>
    <div v-if="deleteError" class="error delete-error">{{ deleteError }}</div>
    <div v-if="novels.error" class="error">{{ novels.error }}</div>
    <div v-else-if="!novels.novels.length" class="card">
      <p class="muted">No novels yet. Crawl a site or import an EPUB to get started.</p>
    </div>
    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Author</th>
            <th>Total</th>
            <th>Translated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="novel in novels.novels" :key="novel.name">
            <td><code>{{ novel.name }}</code></td>
            <td>{{ novel.title ?? '—' }}</td>
            <td>{{ novel.author?.trim() || '—' }}</td>
            <td>{{ novel.total_input_chapters }}</td>
            <td>
              {{ translatedProgress(novel)?.completed ?? 0 }} / {{ translatedProgress(novel)?.total ?? novel.total_input_chapters }}
              <span v-if="(translatedProgress(novel)?.failed ?? 0) > 0" class="badge danger">
                {{ translatedProgress(novel)?.failed }} failed
              </span>
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
                <RouterLink class="action-link" :to="`/novels/${novel.name}`">Open →</RouterLink>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top: 0.5rem;">{{ totalNovels }} novels in your library.</p>

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
            <label for="new-slug">Slug/Directory Name <span class="danger">*</span></label>
            <input id="new-slug" v-model="newSlug" placeholder="e.g. my-awesome-novel (only letters, numbers, dashes, underscores)" />
          </div>
          <div>
            <label for="new-title">Title</label>
            <input id="new-title" v-model="newTitle" placeholder="e.g. My Awesome Novel" />
          </div>
          <div>
            <label for="new-author">Author</label>
            <input id="new-author" v-model="newAuthor" placeholder="e.g. Author Name" />
          </div>
          <div>
            <label for="new-lang">Language</label>
            <select id="new-lang" v-model="newSourceLang">
              <option value="ko">Korean</option>
              <option value="ja">Japanese</option>
              <option value="zh">Chinese</option>
            </select>
          </div>
          <div>
            <label for="new-illustration">Illustration URL</label>
            <input id="new-illustration" v-model="newIllustrationUrl" placeholder="e.g. https://example.com/cover.jpg" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="secondary" type="button" :disabled="adding" @click="closeAddModal">Cancel</button>
          <button type="button" :disabled="adding || !newSlug.trim()" @click="submitAddNovel">
            {{ adding ? 'Creating...' : 'Create Novel' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.delete-error {
  margin-bottom: 0.75rem;
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
</style>
