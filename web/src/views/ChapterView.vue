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
const showScrollToTop = ref(false)

const showToc = ref(false)
const tocLang = ref<'source' | 'vi' | 'en'>('source')
let tocPreviousFocus: HTMLElement | null = null

// ── Computed ──────────────────────────────────────────────────────────────────
const filteredChapters = computed(() => {
  if (tocLang.value === 'source') {
    const uniqueMap = new Map<number, { number: number; source_title?: string | null; title?: string | null }>()
    for (const c of chapters.value) {
      if (c.has_source && !uniqueMap.has(c.number)) {
        uniqueMap.set(c.number, { number: c.number, source_title: c.source_title, title: null })
      }
    }
    return [...uniqueMap.values()].sort((a, b) => a.number - b.number)
  } else {
    return chapters.value
      .filter((c) => c.target === tocLang.value && c.has_translation)
      .sort((a, b) => a.number - b.number)
  }
})

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

function selectChapter(chapterNumber: number) {
  showToc.value = false
  goTo(chapterNumber)
}

function updateScrollToTopVisibility() {
  showScrollToTop.value = window.scrollY > 480
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('click', closeMenu)
  window.addEventListener('scroll', updateScrollToTopVisibility, { passive: true })
  updateScrollToTopVisibility()
  await Promise.all([loadChapters(), loadMetadata(), settings.refresh()])
  await loadContent(props.chapter, defaultViewMode.value)
})

onUnmounted(() => {
  window.removeEventListener('click', closeMenu)
  window.removeEventListener('scroll', updateScrollToTopVisibility)
  document.body.style.overflow = ''
})

watch(showToc, (isOpen) => {
  if (isOpen) {
    tocLang.value = viewMode.value
    tocPreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
    tocPreviousFocus?.focus()
    tocPreviousFocus = null
  }
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

    <!-- ── Prev / Next (Top) ── -->
    <div class="chapter-nav">
      <button
        type="button"
        class="secondary"
        :disabled="prevChapter === null"
        @click="prevChapter !== null && goTo(prevChapter)"
      >
        ← Previous
      </button>

      <button
        type="button"
        class="secondary"
        title="Open Table of Contents"
        @click="showToc = true"
      >
        {{ currentIndex + 1 }} / {{ chapterCount }}
      </button>

      <button
        type="button"
        class="secondary"
        :disabled="nextChapter === null"
        @click="nextChapter !== null && goTo(nextChapter)"
      >
        Next →
      </button>
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

      <button
        type="button"
        class="secondary"
        title="Open Table of Contents"
        @click="showToc = true"
      >
        {{ currentIndex + 1 }} / {{ chapterCount }}
      </button>

      <button
        type="button"
        class="secondary"
        :disabled="nextChapter === null"
        @click="nextChapter !== null && goTo(nextChapter)"
      >
        Next →
      </button>
    </div>

    <!-- ── Table of Contents popup ── -->
    <div v-if="showToc" class="modal-overlay" @click.self="showToc = false">
      <div
        class="modal-card toc-modal"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        @keydown.esc="showToc = false"
      >
        <header class="modal-header">
          <h3>Table of Contents</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="showToc = false"
          >&times;</button>
        </header>
        <div class="modal-body toc-body">
          <div class="toc-controls">
            <label for="toc-lang-select" style="font-weight: 600;">Language:</label>
            <select id="toc-lang-select" v-model="tocLang" class="view-select">
              <option value="source">Origin</option>
              <option value="vi">Vietnamese</option>
              <option value="en">English</option>
            </select>
          </div>
          <div class="toc-list">
            <div v-if="filteredChapters.length === 0" class="muted empty-toc">
              No chapters available for this language.
            </div>
            <button
              v-for="ch in filteredChapters"
              :key="ch.number"
              type="button"
              class="toc-item"
              :class="{ active: ch.number === props.chapter }"
              @click="selectChapter(ch.number)"
            >
              {{ tocLang === 'source' ? ch.source_title : ch.title }}
            </button>
          </div>
        </div>
      </div>
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

    <button
      v-show="showScrollToTop"
      type="button"
      class="secondary scroll-to-top"
      aria-label="Scroll to top"
      title="Scroll to top"
      @click="scrollToTop"
    >
      ↑ Top
    </button>
  </section>
</template>

<style scoped>
.chapter-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
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
  padding: 0.2rem 0;
}

.chapter-nav-pos {
  font-size: 0.875rem;
}

.scroll-to-top {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  z-index: 120;
  min-width: 4rem;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
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

/* ── Table of Contents Modal & Button Styles ── */
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

.toc-modal {
  max-width: 36rem;
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

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
}

.toc-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 70vh;
}

.toc-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.toc-list {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  flex: 1;
}

.toc-item {
  padding: 0.65rem 1.25rem;
  font-size: 0.9rem;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  cursor: pointer;
  border-radius: 0;
  transition: background 0.15s ease;
}

.toc-item:last-child {
  border-bottom: 0;
}

.toc-item:nth-child(odd) {
  background: var(--bg-elev-2);
}

.toc-item:nth-child(even) {
  background: var(--bg-elev);
}

.toc-item:hover:not(.active) {
  background: var(--bg-hover, rgba(255, 255, 255, 0.05));
}

.toc-item.active {
  background: var(--primary, #007bff);
  color: #fff;
}

.empty-toc {
  text-align: center;
  padding: 2.5rem 0;
  font-size: 0.9rem;
}
</style>
