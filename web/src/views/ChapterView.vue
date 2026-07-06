<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { NovelChapterStatus } from '@/api/types'
import { useSettingsStore } from '@/stores/settings'
import ChapterContent from '@/components/ChapterContent.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'

const props = defineProps<{ name: string; chapter: number }>()
const router = useRouter()
const settings = useSettingsStore()

// ── Data ──────────────────────────────────────────────────────────────────────
const chapters = ref<NovelChapterStatus[]>([])
const metadata = ref<any>(null)
const content = ref('')
const editContent = ref('')
const editing = ref(false)
const saving = ref(false)
const loading = ref(true)
const error = ref<string | null>(null)

const viewMode = ref<'source' | 'vi' | 'en'>('source')
const viewLoading = ref(false)

const showDeleteDialog = ref(false)
const deleteLoading = ref(false)

const showMenu = ref(false)

// ── Computed ──────────────────────────────────────────────────────────────────
const chapterNumbers = computed(() => {
  const sources = new Set<number>()
  for (const s of chapters.value) {
    if (s.has_source) sources.add(s.number)
  }
  return [...sources].sort((a, b) => a - b)
})

const currentIndex = computed(() => chapterNumbers.value.indexOf(props.chapter))

const prevChapter = computed(() =>
  currentIndex.value > 0 ? chapterNumbers.value[currentIndex.value - 1] : null
)
const nextChapter = computed(() =>
  currentIndex.value < chapterNumbers.value.length - 1
    ? chapterNumbers.value[currentIndex.value + 1]
    : null
)

const hasVi = computed(() =>
  chapters.value.some(
    (s) => s.number === props.chapter && s.target === 'vi' && s.has_translation
  )
)
const hasEn = computed(() =>
  chapters.value.some(
    (s) => s.number === props.chapter && s.target === 'en' && s.has_translation
  )
)

const chapterCount = computed(() => chapterNumbers.value.length)

const displayTitle = computed(() => {
  if (!metadata.value) return props.name
  const title = metadata.value.title || props.name
  const translated = metadata.value.translated || {}
  
  if (viewMode.value === 'vi' && translated.vi) {
    return translated.vi
  }
  if (viewMode.value === 'en' && translated.en) {
    return translated.en
  }
  return title
})

const chapterLabel = computed(() => {
  return viewMode.value === 'vi' ? 'Chương' : 'Chapter'
})

const targetLanguage = computed(() => {
  return settings.settings?.target_language as 'vi' | 'en' | undefined
})

const defaultViewMode = computed<'source' | 'vi' | 'en'>(() => {
  const lang = targetLanguage.value
  if (lang) {
    const hasTranslation = chapters.value.some(
      (s) => s.number === props.chapter && s.target === lang && s.has_translation
    )
    if (hasTranslation) {
      return lang
    }
  }
  return 'source'
})

// ── Load ──────────────────────────────────────────────────────────────────────
async function loadChapters() {
  try {
    chapters.value = await api.listChapters(props.name)
  } catch {
    // non-fatal; nav still works from URL
  }
}

async function loadMetadata() {
  try {
    const response = await api.getNovelMetadata(props.name)
    metadata.value = response.data ?? null
  } catch {
    // non-fatal
  }
}

async function loadContent(chapter: number, mode: 'source' | 'vi' | 'en' = 'source') {
  loading.value = true
  error.value = null
  content.value = ''
  viewMode.value = mode
  try {
    const view = mode === 'source' ? 'source' : 'translation'
    const tgt = mode === 'source' ? undefined : mode
    const resp = await api.getChapterContent(props.name, chapter, view, tgt)
    content.value = resp.content
    editContent.value = resp.content
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

// ── View switch ───────────────────────────────────────────────────────────────
async function changeView(mode: 'source' | 'vi' | 'en') {
  if (viewLoading.value || mode === viewMode.value) return
  viewLoading.value = true
  error.value = null
  try {
    const view = mode === 'source' ? 'source' : 'translation'
    const tgt = mode === 'source' ? undefined : mode
    const resp = await api.getChapterContent(props.name, props.chapter, view, tgt)
    content.value = resp.content
    if (mode === 'source') editContent.value = resp.content
    viewMode.value = mode
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    viewLoading.value = false
  }
}

// ── Edit ──────────────────────────────────────────────────────────────────────
function startEdit() {
  editContent.value = content.value
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  editContent.value = content.value
}

async function saveEdit() {
  saving.value = true
  error.value = null
  try {
    const resp = await api.putChapterContent(props.name, props.chapter, editContent.value)
    content.value = resp.content
    editContent.value = resp.content
    editing.value = false
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────
async function confirmDelete() {
  deleteLoading.value = true
  try {
    await api.deleteChapter(props.name, props.chapter)
    const dest = prevChapter.value ?? nextChapter.value
    if (dest !== null) {
      await router.replace({
        name: 'chapter-reader',
        params: { name: props.name, chapter: dest }
      })
    } else {
      await router.replace({ name: 'novel-detail', params: { name: props.name } })
    }
    showDeleteDialog.value = false
  } catch (err) {
    error.value = (err as Error).message
    showDeleteDialog.value = false
  } finally {
    deleteLoading.value = false
  }
}

// ── Dropdown Menu ─────────────────────────────────────────────────────────────
function closeMenu() {
  showMenu.value = false
}

function handleMenuAction(action: () => void) {
  showMenu.value = false
  action()
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goTo(chapter: number) {
  void router.push({ name: 'chapter-reader', params: { name: props.name, chapter } })
}

function goBack() {
  void router.push({ name: 'novel-detail', params: { name: props.name } })
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('click', closeMenu)
  await Promise.all([loadChapters(), loadMetadata(), settings.refresh()])
  await loadContent(props.chapter, defaultViewMode.value)
})

onUnmounted(() => {
  window.removeEventListener('click', closeMenu)
})

// Reload when navigating between chapters (same component, different prop)
watch(
  () => props.chapter,
  async (ch) => {
    editing.value = false
    await loadContent(ch, defaultViewMode.value)
  }
)

// Update page title
watch(
  [() => props.chapter, displayTitle, chapterLabel],
  ([ch, title, label]) => {
    document.title = `${title} - ${label} ${ch} - Novel AI Translation`
  },
  { immediate: true }
)
</script>

<template>
  <section class="chapter-view">
    <!-- ── Top bar ── -->
    <div class="chapter-topbar card">
      <div class="chapter-topbar-left">
        <button type="button" class="secondary icon-btn" title="Back to novel" @click="goBack">
          ← Back
        </button>
        <span class="chapter-topbar-title">
          <span class="muted">{{ displayTitle }} /</span>
          {{ chapterLabel }} {{ chapter }}
          <span v-if="chapterCount" class="muted"> of {{ chapterCount }}</span>
        </span>
      </div>

      <div class="chapter-topbar-controls">
        <template v-if="!editing">
          <!-- View mode -->
          <select
            class="view-select"
            :value="viewMode"
            :disabled="viewLoading || loading"
            @change="changeView(($event.target as HTMLSelectElement).value as 'source' | 'vi' | 'en')"
          >
            <option value="source">Origin</option>
            <option value="vi" :disabled="!hasVi">Vietnamese</option>
            <option value="en" :disabled="!hasEn">English</option>
          </select>

          <!-- Action Menu -->
          <div class="menu-container">
            <button
              type="button"
              class="secondary icon-btn menu-trigger"
              :disabled="viewMode !== 'source' || loading"
              @click.stop="showMenu = !showMenu"
            >
              ⋮
            </button>
            <div v-if="showMenu" class="dropdown-menu">
              <button
                type="button"
                class="menu-item"
                @click="handleMenuAction(startEdit)"
              >
                Edit
              </button>
              <button
                type="button"
                class="menu-item danger"
                @click="handleMenuAction(() => showDeleteDialog = true)"
              >
                Delete
              </button>
            </div>
          </div>
        </template>

        <template v-else>
          <button
            type="button"
            :disabled="saving"
            @click="saveEdit"
          >{{ saving ? 'Saving…' : 'Save' }}</button>
          <button
            type="button"
            class="secondary"
            :disabled="saving"
            @click="cancelEdit"
          >Cancel</button>
        </template>
      </div>
    </div>

    <!-- ── Error ── -->
    <p v-if="error" class="error card">{{ error }}</p>

    <!-- ── Content ── -->
    <div class="chapter-body card">
      <div v-if="loading" class="chapter-loading muted">Loading…</div>
      <div v-else-if="viewLoading" class="chapter-loading muted">Loading translation…</div>
      <textarea
        v-else-if="editing"
        v-model="editContent"
        class="chapter-edit-area"
      ></textarea>
      <ChapterContent v-else :content="content" :novel="name" />
    </div>

    <!-- ── Prev / Next ── -->
    <div class="chapter-nav">
      <button
        type="button"
        class="secondary"
        :disabled="prevChapter === null"
        @click="prevChapter !== null && goTo(prevChapter)"
      >
        ← Previous
      </button>

      <span class="muted chapter-nav-pos">
        {{ currentIndex + 1 }} / {{ chapterCount }}
      </span>

      <button
        type="button"
        class="secondary"
        :disabled="nextChapter === null"
        @click="nextChapter !== null && goTo(nextChapter)"
      >
        Next →
      </button>
    </div>

    <!-- ── Delete confirmation ── -->
    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Chapter"
      :message="`Delete Chapter ${chapter}?\n\nThis permanently deletes the source chapter file. Translated chapters will not be deleted but may become orphaned. This cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @cancel="showDeleteDialog = false"
    />
  </section>
</template>

<style scoped>
.chapter-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ── Top bar ── */
.chapter-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
}

.chapter-topbar-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.chapter-topbar-title {
  font-size: 1rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chapter-topbar-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.icon-btn {
  flex-shrink: 0;
}

/* ── Dropdown Menu ── */
.menu-container {
  position: relative;
  display: inline-block;
}

.menu-trigger {
  width: 2rem;
  height: 2rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  line-height: 1;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.25rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 100;
  min-width: 8rem;
  display: flex;
  flex-direction: column;
  padding: 0.25rem 0;
}

.menu-item {
  background: transparent;
  color: var(--fg);
  border: 0;
  border-radius: 0;
  padding: 0.5rem 1rem;
  text-align: left;
  font-size: 0.875rem;
  cursor: pointer;
  width: 100%;
  transition: background 0.1s ease;
}

.menu-item:hover:not(:disabled) {
  background: var(--bg-elev);
}

.menu-item.danger {
  color: var(--danger);
  background: transparent;
}

.menu-item.danger:hover:not(:disabled) {
  background: rgba(240, 98, 98, 0.1);
}

/* ── View select ── */
.view-select {
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-elev);
  color: var(--fg);
  cursor: pointer;
  height: 2rem;
}

.view-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── Content body ── */
.chapter-body {
  min-height: 60vh;
}

.chapter-loading {
  text-align: center;
  padding: 3rem 1rem;
}

.chapter-edit-area {
  width: 100%;
  min-height: 60vh;
  box-sizing: border-box;
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.7;
  resize: vertical;
  background: var(--bg-elev-2);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
}

/* ── Prev / Next ── */
.chapter-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem 0;
}

.chapter-nav-pos {
  font-size: 0.875rem;
}

/* ── Danger button variants ── */
button.danger {
  background: var(--danger, #dc3545);
  color: #fff;
  border-color: var(--danger, #dc3545);
}

button.danger:hover:not(:disabled) {
  background: #c82333;
  border-color: #bd2130;
}

button.secondary.danger {
  background: transparent;
  color: var(--danger, #dc3545);
  border-color: var(--danger, #dc3545);
}

button.secondary.danger:hover:not(:disabled) {
  background: var(--danger, #dc3545);
  color: #fff;
}
</style>
