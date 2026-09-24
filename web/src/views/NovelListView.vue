<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  Library,
  Plus,
  Search,
  LayoutGrid,
  List,
  AlertCircle,
  Sparkles,
  Trash2,
  FolderDown,
  X,
  Upload
} from '@lucide/vue'
import { useNovelsStore, getNovelCoverUrl } from '@/composables/novels'
import { useSettingsStore } from '@/composables/settings'
import type { NovelSummary, NovelTargetProgress } from '@/api/types'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { useBodyScrollLock } from '@/composables/scrolllock'
import EmptyState from '@/components/common/EmptyState.vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { formatLanguage, normalizeLanguage } from '@/language'
import placeholderCover from '@/assets/placeholder-cover.png'
import { t } from '@/i18n'

const novels = useNovelsStore()
const settings = useSettingsStore()
const router = useRouter()

// View layout & filters
const viewMode = ref<'grid' | 'table'>('grid')
const searchQuery = ref('')
const filterLanguage = ref<string>('all')
const filterStatus = ref<string>('all')

const languageFilterOptions = computed(() => [
  { value: 'all', label: t('all_languages') },
  { value: 'korean', label: t('korean') },
  { value: 'japanese', label: t('japanese') },
  { value: 'chinese', label: t('chinese') }
])

const sourceLanguageOptions = computed(() => [
  { value: 'ko', label: t('korean') },
  { value: 'ja', label: t('japanese') },
  { value: 'zh', label: t('chinese') }
])

const statusFilterOptions = computed(() => [
  { value: 'all', label: t('all_statuses') },
  { value: 'in_progress', label: t('in_progress') },
  { value: 'completed', label: t('translated') },
  { value: 'issues', label: t('needs_attention') }
])

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
const importantWarningChapters = ref<Set<number>>(new Set())
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

useBodyScrollLock(() => (
  showFailedDialog.value ||
  showWarningDialog.value ||
  showAddModal.value ||
  showDeleteDialog.value ||
  showIgnoreWarningsDialog.value
))

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

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (showIgnoreWarningsDialog.value) cancelIgnoreWarnings()
    else if (showDeleteDialog.value) cancelDelete()
    else if (showWarningDialog.value) closeWarningDialog()
    else if (showFailedDialog.value) closeFailedDialog()
    else if (showAddModal.value) closeAddModal()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown)
  void Promise.all([novels.refresh(), settings.refresh()])
  const savedView = localStorage.getItem('novel_view_mode') as 'grid' | 'table' | null
  if (savedView) viewMode.value = savedView
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  setNewCoverFile(null)
})

function setViewMode(mode: 'grid' | 'table') {
  viewMode.value = mode
  localStorage.setItem('novel_view_mode', mode)
}

const defaultTarget = computed(() => settings.settings?.target_language ?? 'vi')

function translatedProgress(novel: NovelSummary): NovelTargetProgress | undefined {
  return novel.targets.find((progress) => progress.target === defaultTarget.value)
}

function progressPercent(novel: NovelSummary): number {
  const prog = translatedProgress(novel)
  const total = prog?.total ?? novel.total_input_chapters
  if (!total) return 0
  return Math.min(100, Math.round(((prog?.completed ?? 0) / total) * 100))
}

const filteredNovels = computed(() => {
  let list = novels.novels

  // Search filter
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((n) =>
      n.name.toLowerCase().includes(q) ||
      (n.title && n.title.toLowerCase().includes(q)) ||
      (n.author && n.author.toLowerCase().includes(q))
    )
  }

  // Language filter
  if (filterLanguage.value !== 'all') {
    list = list.filter((n) => normalizeLanguage(n.source_language) === filterLanguage.value)
  }

  // Status filter
  if (filterStatus.value === 'completed') {
    list = list.filter((n) => {
      const p = translatedProgress(n)
      const total = p?.total ?? n.total_input_chapters
      return (p?.completed ?? 0) > 0 && (p?.completed ?? 0) === total
    })
  } else if (filterStatus.value === 'issues') {
    list = list.filter((n) => {
      const p = translatedProgress(n)
      return (p?.failed ?? 0) > 0 || (p?.warnings ?? 0) > 0
    })
  } else if (filterStatus.value === 'in_progress') {
    list = list.filter((n) => {
      const p = translatedProgress(n)
      const total = p?.total ?? n.total_input_chapters
      const completed = p?.completed ?? 0
      return completed > 0 && completed < total
    })
  }

  return list
})

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
    failedChapters.value = [...(progress.failed ?? [])].sort((a, b) => a - b)
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
  importantWarningChapters.value = new Set()
  warningChaptersError.value = null
  ignoreWarningsError.value = null
  warningChaptersLoading.value = true
  showWarningDialog.value = true
  try {
    const progress = await novels.progress(novel.name, defaultTarget.value)
    warningChapters.value = [...(progress.warnings ?? [])].sort((a, b) => a - b)
    importantWarningChapters.value = new Set(progress.important_warnings ?? [])
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
  importantWarningChapters.value = new Set()
  warningChaptersError.value = null
  ignoreWarningsError.value = null
}

function warningChapterTooltip(chapter: number): string {
  if (importantWarningChapters.value.has(chapter)) {
    return t('source_text_or_missing_title')
  }
  return t('unresolved_quality_warnings')
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
  const name = warningNovel.value?.name ?? t('this_novel')
  return t('confirm_ignore_novel_warnings', { name })
})

const deleteMessage = computed(() => {
  if (!novelToDelete.value) return ''
  const label = novelToDelete.value.title
    ? `"${novelToDelete.value.title}" (${novelToDelete.value.name})`
    : `"${novelToDelete.value.name}"`
  return t('confirm_delete_novel', { label })
})
</script>

<template>
  <div class="novel-list-root">
    <!-- Header Controls Bar -->
    <header class="library-header card-panel">
      <div class="header-left">
        <div class="library-title-group">
          <div class="header-icon-box">
            <Library :size="20" />
          </div>
          <div>
            <h2 class="library-title">{{ $t("novel_library") }}</h2>
            <p class="library-count">
              {{ novels.novels.length === 1 ? $t('single_novel_in_collection') : $t('novels_in_collection_count', { count: novels.novels.length }) }}
            </p>
          </div>
        </div>
      </div>

      <div class="header-right">
        <!-- Search Field -->
        <div class="search-box">
          <Search :size="15" class="search-icon" />
          <input
            v-model="searchQuery"
            type="search"
            :placeholder="$t('search_by_title_author_slug')"
            class="search-input"
          />
          <button
            v-if="searchQuery"
            type="button"
            class="clear-search-btn"
            @click="searchQuery = ''"
          >
            <X :size="14" />
          </button>
        </div>

        <!-- Filter Selects -->
        <CustomSelect
          v-model="filterLanguage"
          :options="languageFilterOptions"
          class="filter-select-wrapper"
        />

        <CustomSelect
          v-model="filterStatus"
          :options="statusFilterOptions"
          class="filter-select-wrapper"
        />

        <!-- View Toggle Buttons -->
        <div class="view-toggle-group">
          <button
            type="button"
            class="toggle-btn"
            :class="{ active: viewMode === 'grid' }"
            :title="$t('bookshelf_grid_view')"
            @click="setViewMode('grid')"
          >
            <LayoutGrid :size="16" />
          </button>
          <button
            type="button"
            class="toggle-btn"
            :class="{ active: viewMode === 'table' }"
            :title="$t('list_table_view')"
            @click="setViewMode('table')"
          >
            <List :size="16" />
          </button>
        </div>

        <!-- Add Novel Button -->
        <button type="button" class="add-novel-btn" @click="showAddModal = true">
          <Plus :size="16" />
          <span>{{ $t("new_novel") }}</span>
        </button>
      </div>
    </header>

    <!-- Error Alerts -->
    <div v-if="deleteError" class="alert-banner error">
      <AlertCircle :size="16" />
      <span>{{ deleteError }}</span>
    </div>
    <div v-if="novels.error" class="alert-banner error">
      <AlertCircle :size="16" />
      <span>{{ novels.error }}</span>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-if="!novels.novels.length"
      :icon="Library"
      :title="$t('no_novels_yet')"
      :description="$t('empty_library_instructions')"
    >
      <template #action>
        <div class="row gap-2">
          <button type="button" @click="showAddModal = true">
            <Plus :size="16" />
            <span>{{ $t("create_empty_novel") }}</span>
          </button>
          <RouterLink to="/sources">
            <button type="button" class="secondary">
              <FolderDown :size="16" />
              <span>{{ $t("import_sources") }}</span>
            </button>
          </RouterLink>
        </div>
      </template>
    </EmptyState>

    <!-- Filtered Empty State -->
    <div v-else-if="!filteredNovels.length" class="empty-filter-state card-panel">
      <p class="muted">{{ $t("no_matching_novels") }}</p>
      <button type="button" class="secondary" @click="searchQuery = ''; filterLanguage = 'all'; filterStatus = 'all'">
        {{ $t("clear_filters") }}
      </button>
    </div>

    <!-- Grid View Mode -->
    <div v-else-if="viewMode === 'grid'" class="library-grid">
      <div
        v-for="novel in filteredNovels"
        :key="novel.name"
        class="grid-novel-item"
      >
        <div class="novel-card-wrap">
          <div class="card-cover-container">
            <img
              :src="getNovelCoverUrl(novel.name, novel.illustration_url)"
              :alt="novel.title || novel.name"
              class="card-cover-img"
              loading="lazy"
              referrerpolicy="no-referrer"
              @error="($event.target as HTMLImageElement).src = placeholderCover"
            />
            <div class="cover-overlay">
              <span class="lang-tag">{{ formatLanguage(novel.source_language, 'auto') }}</span>
              <div v-if="(translatedProgress(novel)?.failed ?? 0) > 0" class="badge-failed">
                {{ $t("failed_count", { count: translatedProgress(novel)?.failed ?? 0 }) }}
              </div>
            </div>
          </div>

          <div class="novel-card-info">
            <RouterLink :to="`/novels/${novel.name}`" class="novel-card-title" :title="novel.title || novel.name">
              {{ novel.title || novel.name }}
            </RouterLink>
              <span class="novel-card-author">{{ novel.author || $t('unknown_author') }}</span>
            <span class="novel-card-slug"><code>{{ novel.name }}</code></span>

            <!-- Progress Bar -->
            <div class="progress-wrap">
              <div class="progress-info">
                <span>{{ $t("chapters_completed_of_total", { completed: translatedProgress(novel)?.completed ?? 0, total: translatedProgress(novel)?.total ?? novel.total_input_chapters }) }}</span>
                <span>{{ progressPercent(novel) }}%</span>
              </div>
              <div class="progress">
                <div class="fill" :style="{ width: `${progressPercent(novel)}%` }" />
              </div>
            </div>

            <!-- Status Buttons / Indicators -->
            <div class="status-row">
              <button
                v-if="(translatedProgress(novel)?.failed ?? 0) > 0"
                type="button"
                class="badge danger status-badge"
                @click="showFailedChapters(novel)"
              >
                {{ $t("failed_count_label", { count: translatedProgress(novel)?.failed ?? 0 }) }}
              </button>
              <button
                v-if="(translatedProgress(novel)?.warnings ?? 0) > 0"
                type="button"
                class="badge warn status-badge"
                :title="$t('chapters_with_quality_warnings')"
                @click="showWarningChapters(novel)"
              >
                {{ $t("warnings_count_label", { count: translatedProgress(novel)?.warnings ?? 0 }) }}
              </button>
              <span
                v-if="(translatedProgress(novel)?.failed ?? 0) === 0 && (translatedProgress(novel)?.warnings ?? 0) === 0"
                class="badge ok"
              >
                {{ $t("normal") }}
              </span>
            </div>

            <!-- Action Buttons -->
            <div class="card-action-bar">
              <RouterLink
                :to="{ name: 'translate', query: { novel: novel.name } }"
                class="btn-action primary"
                :title="$t('translate_this_novel')"
              >
                <Sparkles :size="13" />
                <span>{{ $t("translate") }}</span>
              </RouterLink>
              <RouterLink
                :to="`/novels/${novel.name}`"
                class="btn-action secondary"
                :title="$t('open_workspace')"
              >
                {{ $t("details") }}
              </RouterLink>
              <button
                type="button"
                class="btn-action danger"
                :title="$t('delete_novel')"
                :disabled="deletingNovel !== null"
                @click="deleteNovel(novel)"
              >
                <Trash2 :size="13" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Table View Mode -->
    <div v-else class="library-table-shell card-panel">
      <table class="library-table">
        <thead>
          <tr>
            <th style="width: 50px;">{{ $t("cover") }}</th>
            <th>{{ $t("title_slug") }}</th>
            <th>{{ $t("author") }}</th>
            <th>{{ $t("language") }}</th>
            <th>{{ $t("progress") }}</th>
            <th>{{ $t("status") }}</th>
            <th class="actions-col" style="text-align: right;">{{ $t("actions") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="novel in filteredNovels" :key="novel.name">
            <td>
              <div class="table-cover-frame">
                <img
                  :src="getNovelCoverUrl(novel.name, novel.illustration_url)"
                  :alt="novel.title || novel.name"
                  class="table-cover-img"
                  referrerpolicy="no-referrer"
                  @error="($event.target as HTMLImageElement).src = placeholderCover"
                />
              </div>
            </td>
            <td>
              <div class="table-title-cell">
                <RouterLink :to="`/novels/${novel.name}`" class="table-title-link">
                  {{ novel.title || novel.name }}
                </RouterLink>
                <span class="table-slug"><code>{{ novel.name }}</code></span>
              </div>
            </td>
            <td class="table-author-cell">
              {{ novel.author || '—' }}
            </td>
            <td>
              <span class="badge">{{ formatLanguage(novel.source_language, 'auto') }}</span>
            </td>
            <td style="min-width: 140px;">
              <div class="table-progress-cell">
                <div class="progress-info">
                  <span>{{ $t("chapters_completed_of_total", { completed: translatedProgress(novel)?.completed ?? 0, total: translatedProgress(novel)?.total ?? novel.total_input_chapters }) }}</span>
                  <span>{{ progressPercent(novel) }}%</span>
                </div>
                <div class="progress">
                  <div class="fill" :style="{ width: `${progressPercent(novel)}%` }" />
                </div>
              </div>
            </td>
            <td>
              <div class="status-badges">
                <button
                  v-if="(translatedProgress(novel)?.failed ?? 0) > 0"
                  type="button"
                  class="badge danger status-badge"
                  @click="showFailedChapters(novel)"
                >
                  {{ $t("failed_count_label", { count: translatedProgress(novel)?.failed ?? 0 }) }}
                </button>
                <button
                  v-if="(translatedProgress(novel)?.warnings ?? 0) > 0"
                  type="button"
                  class="badge warn status-badge"
                  :title="$t('chapters_with_quality_warnings')"
                  @click="showWarningChapters(novel)"
                >
                  {{ $t("warnings_count_label", { count: translatedProgress(novel)?.warnings ?? 0 }) }}
                </button>
                <span
                  v-if="(translatedProgress(novel)?.failed ?? 0) === 0 && (translatedProgress(novel)?.warnings ?? 0) === 0"
                  class="badge ok"
                >
                  {{ $t("normal") }}
                </span>
              </div>
            </td>
            <td class="actions-col" style="text-align: right;">
              <div class="table-actions">
                <RouterLink
                  :to="{ name: 'translate', query: { novel: novel.name } }"
                  class="btn-action primary"
                  :title="$t('translate_novel')"
                >
                  <Sparkles :size="13" />
                  <span>{{ $t("translate") }}</span>
                </RouterLink>
                <RouterLink
                  :to="`/novels/${novel.name}`"
                  class="btn-action secondary"
                  :title="$t('open_workspace')"
                >
                  <span>{{ $t("details") }}</span>
                </RouterLink>
                <button
                  type="button"
                  class="btn-action danger"
                  :title="$t('delete_novel')"
                  :disabled="deletingNovel !== null"
                  @click="deleteNovel(novel)"
                >
                  <Trash2 :size="13" />
                  <span>{{ $t("delete") }}</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Confirm Delete Dialog -->
    <ConfirmDialog
      :show="showDeleteDialog"
      :title="$t('delete_novel')"
      :message="deleteMessage"
      :confirm-label="$t('delete_novel')"
      :danger="true"
      :loading="deletingNovel !== null"
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />

    <!-- Failed Chapters Modal -->
    <div v-if="showFailedDialog" class="modal-overlay" @click.self="closeFailedDialog">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="failed-chapters-title">
        <header class="modal-header">
          <h3 id="failed-chapters-title">
            {{ $t("failed_chapters_for", { novel: failedNovel?.name ?? '' }) }}
          </h3>
          <button class="modal-close" type="button" :aria-label="$t('close')" @click="closeFailedDialog">
            <X :size="18" />
          </button>
        </header>
        <div class="modal-body">
          <p v-if="failedChaptersLoading" class="muted">{{ $t("loading_failed_chapters") }}</p>
          <p v-else-if="failedChaptersError" class="error">{{ failedChaptersError }}</p>
          <p v-else-if="!failedChapters.length" class="muted">{{ $t("no_failed_chapters") }}</p>
          <div v-else class="failed-chapter-list">
            <RouterLink
              v-for="chapter in failedChapters"
              :key="chapter"
              class="failed-chapter-link"
              :to="`/novels/${failedNovel?.name}/chapters/${chapter}`"
              @click="closeFailedDialog"
            >
              {{ $t("chapter_number", { number: chapter }) }}
            </RouterLink>
          </div>
        </div>
        <footer class="modal-footer">
          <button
            type="button"
            class="secondary"
            :disabled="failedChaptersLoading || !failedNovel"
            @click="retranslateFailed"
          >
            {{ $t("retranslate") }}
          </button>
        </footer>
      </div>
    </div>

    <!-- Warning Chapters Modal -->
    <div v-if="showWarningDialog" class="modal-overlay" @click.self="closeWarningDialog">
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="warning-chapters-title">
        <header class="modal-header">
          <h3 id="warning-chapters-title">
            {{ $t("warning_chapters_for", { novel: warningNovel?.name ?? '' }) }}
          </h3>
          <button class="modal-close" type="button" :aria-label="$t('close')" @click="closeWarningDialog">
            <X :size="18" />
          </button>
        </header>
        <div class="modal-body">
          <p v-if="ignoreWarningsError" class="error">{{ ignoreWarningsError }}</p>
          <p v-if="warningChaptersLoading" class="muted">{{ $t("loading_warning_chapters") }}</p>
          <p v-else-if="warningChaptersError" class="error">{{ warningChaptersError }}</p>
          <p v-else-if="!warningChapters.length" class="muted">{{ $t("no_warning_chapters") }}</p>
          <div v-else class="failed-chapter-list">
            <RouterLink
              v-for="chapter in warningChapters"
              :key="chapter"
              class="failed-chapter-link"
              :class="{ 'important-warning-chapter': importantWarningChapters.has(chapter) }"
              :title="warningChapterTooltip(chapter)"
              :to="`/novels/${warningNovel?.name}/chapters/${chapter}`"
              @click="closeWarningDialog"
            >
              {{ $t("chapter_number", { number: chapter }) }}
            </RouterLink>
          </div>
        </div>
        <footer class="modal-footer">
          <button
            type="button"
            class="secondary"
            :disabled="warningChaptersLoading || !warningChapters.length || Boolean(warningChaptersError)"
            @click="requestIgnoreWarnings"
          >
            {{ $t("ignore_all_warnings") }}
          </button>
        </footer>
      </div>
    </div>

    <!-- Ignore Warnings Confirm Dialog -->
    <ConfirmDialog
      :show="showIgnoreWarningsDialog"
      :title="$t('ignore_warnings')"
      :message="ignoreWarningsMessage"
      :confirm-label="$t('ignore')"
      :danger="true"
      :loading="ignoringWarnings"
      @confirm="confirmIgnoreWarnings"
      @cancel="cancelIgnoreWarnings"
    />

    <!-- Add Novel Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="closeAddModal">
      <div class="modal-card">
        <header class="modal-header">
          <h3>{{ $t("create_new_novel") }}</h3>
          <button class="modal-close" type="button" @click="closeAddModal">
            <X :size="18" />
          </button>
        </header>
        <div class="modal-body flex-col gap-3">
          <div v-if="addError" class="error">{{ addError }}</div>
          <div>
            <label for="new-slug">{{ $t("short_identifier_slug") }} <span class="danger">*</span></label>
            <input
              id="new-slug"
              v-model="newSlug"
              :disabled="Boolean(createdSlug)"
              :placeholder="$t('slug_placeholder')"
            />
          </div>
          <div>
            <label for="new-title">{{ $t("novel_title") }}</label>
            <input
              id="new-title"
              v-model="newTitle"
              :disabled="Boolean(createdSlug)"
              :placeholder="$t('e_g_shadow_slave')"
            />
          </div>
          <div>
            <label for="new-author">{{ $t("author") }}</label>
            <input
              id="new-author"
              v-model="newAuthor"
              :disabled="Boolean(createdSlug)"
              :placeholder="$t('e_g_guiltythree')"
            />
          </div>
          <div>
            <label for="new-lang">{{ $t("source_language") }}</label>
            <CustomSelect
              id="new-lang"
              v-model="newSourceLang"
              :options="sourceLanguageOptions"
              :disabled="Boolean(createdSlug)"
            />
          </div>
          <div>
            <label for="new-cover">{{ $t("upload_cover") }}</label>
            <div class="cover-upload-area">
              <input
                id="new-cover"
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                class="hidden-file-input"
                @change="selectNewCover"
              />
              <label for="new-cover" class="upload-dropzone">
                <Upload :size="20" class="upload-icon" />
                <span class="upload-label">{{ newCoverFile ? newCoverFile.name : $t('choose_image_file_or_drag_here') }}</span>
                <span class="upload-hint">{{ $t("cover_image_formats_hint") }}</span>
              </label>
            </div>
            <img v-if="newCoverPreview" class="cover-preview" :src="newCoverPreview" :alt="$t('cover_preview')" />
          </div>
          <div>
            <label for="new-illustration">{{ $t("alternative_remote_cover_url") }}</label>
            <input
              id="new-illustration"
              v-model="newIllustrationUrl"
              :disabled="Boolean(newCoverFile) || Boolean(createdSlug)"
              :placeholder="$t('cover_url_placeholder')"
            />
          </div>
        </div>
        <footer class="modal-footer">
          <button class="secondary" type="button" :disabled="adding" @click="closeAddModal">{{ $t("cancel") }}</button>
          <button type="button" :disabled="adding || !newSlug.trim()" @click="submitAddNovel">
            {{ adding ? $t('saving') : (createdSlug ? $t('retry_cover_upload') : $t('create_novel')) }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.novel-list-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Header Controls */
.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
}

.library-title-group {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

.header-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--accent);
}

.library-title {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.library-count {
  margin: 0.15rem 0 0;
  font-size: 0.8125rem;
  color: var(--fg-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

/* Search Box */
.search-box {
  position: relative;
  display: flex;
  align-items: center;
  min-width: 15rem;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  color: var(--fg-muted);
  pointer-events: none;
}

.search-input {
  padding-left: 2.25rem;
  padding-right: 2rem;
  font-size: 0.85rem;
  border-radius: var(--radius-md);
}

.clear-search-btn {
  position: absolute;
  right: 0.5rem;
  background: transparent;
  border: none;
  color: var(--fg-muted);
  padding: 0.25rem;
  cursor: pointer;
}

.clear-search-btn:hover {
  color: var(--fg-primary);
  background: transparent;
}

.filter-select,
.filter-select-wrapper {
  width: 10.5rem;
  font-size: 0.85rem;
}

/* View Toggle Group */
.view-toggle-group {
  display: inline-flex;
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  padding: 2px;
}

.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-secondary);
  border: none;
  cursor: pointer;
  box-shadow: none;
}

.toggle-btn:hover {
  color: var(--fg-primary);
  background: var(--bg-surface-active);
  transform: none;
}

.toggle-btn.active {
  background: var(--accent);
  color: #ffffff;
}

.add-novel-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 600;
}

/* Grid View Layout */
.library-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}

.grid-novel-item {
  display: flex;
}

.novel-card-wrap {
  display: flex;
  flex-direction: column;
  width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card);
  transition: all var(--transition-normal);
}

.novel-card-wrap:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-floating);
}

.card-cover-container {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--bg-surface-elevated);
  overflow: hidden;
}

.card-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 20%;
  transition: transform 0.4s var(--ease-spring);
}

.novel-card-wrap:hover .card-cover-img {
  transform: scale(1.04);
}

.cover-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 0.75rem;
  background: linear-gradient(180deg, rgba(11, 14, 20, 0.75) 0%, rgba(11, 14, 20, 0) 100%);
  pointer-events: none;
}

.lang-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-xs);
  background: rgba(11, 14, 20, 0.75);
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #ffffff;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.badge-failed {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--danger);
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-xs);
}

.novel-card-info {
  display: flex;
  flex-direction: column;
  padding: 1.15rem;
  gap: 0.75rem;
  flex: 1;
}

.novel-card-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--fg-primary);
  text-decoration: none;
  line-height: 1.3;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color var(--transition-fast);
}

.novel-card-title:hover {
  color: var(--accent);
}

.novel-card-author {
  font-size: 0.825rem;
  color: var(--fg-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-card-slug {
  font-size: 0.8rem;
}

.progress-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-top: 0.25rem;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--fg-secondary);
}

.status-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
}

button.status-badge {
  background: var(--bg-surface-elevated);
  cursor: pointer;
  border: 1px solid transparent;
}

button.status-badge.danger {
  color: var(--danger);
  border-color: rgba(244, 63, 94, 0.3);
  background: var(--danger-subtle);
}

button.status-badge.warn {
  color: var(--warn);
  border-color: rgba(245, 158, 11, 0.3);
  background: var(--warn-subtle);
}

button.status-badge:hover {
  text-decoration: underline;
  transform: none;
}

.card-action-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: auto;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.btn-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.4rem 0.65rem;
  border-radius: var(--radius-sm);
  font-size: 0.775rem;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.btn-action.primary {
  background: var(--accent-subtle);
  color: var(--accent);
  border: 1px solid rgba(79, 125, 249, 0.25);
  flex: 1;
}

.btn-action.primary:hover {
  background: var(--accent);
  color: #ffffff;
}

.btn-action.secondary {
  background: var(--bg-surface-elevated);
  color: var(--fg-primary);
  border: 1px solid var(--border-base);
  flex: 1;
}

.btn-action.secondary:hover {
  background: var(--bg-surface-active);
  border-color: var(--border-hover);
}

.btn-action.danger {
  background: var(--danger-subtle);
  color: var(--danger);
  border: 1px solid rgba(244, 63, 94, 0.25);
  padding: 0.4rem 0.65rem;
}

.btn-action.danger:hover:not(:disabled) {
  background: var(--danger);
  color: #ffffff;
  border-color: var(--danger);
}

/* Table View Layout */
.library-table-shell {
  padding: 0;
  overflow-x: auto;
}

.library-table {
  width: 100%;
}

.library-table th.actions-col,
.library-table td.actions-col {
  text-align: right;
  white-space: nowrap;
  position: sticky;
  right: 0;
}

.library-table th.actions-col {
  background: var(--bg-surface-elevated);
  z-index: 2;
}

.library-table td.actions-col {
  background: var(--bg-surface);
  z-index: 1;
}

tbody tr:hover td.actions-col {
  background: var(--bg-surface-elevated);
}

.table-cover-frame {
  width: 36px;
  height: 48px;
  border-radius: var(--radius-xs);
  overflow: hidden;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
}

.table-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.table-title-cell {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  max-width: 20rem;
}

.table-title-link {
  font-weight: 600;
  color: var(--fg-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-title-link:hover {
  color: var(--accent);
}

.table-author-cell {
  color: var(--fg-secondary);
  font-size: 0.85rem;
}

.table-progress-cell {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.status-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.table-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.45rem;
}

.btn-icon-subtle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--fg-secondary);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-icon-subtle:hover:not(:disabled) {
  background: var(--bg-surface-elevated);
  color: var(--accent);
  border-color: var(--border-base);
}

.btn-icon-subtle.danger:hover:not(:disabled) {
  background: var(--danger-subtle);
  color: var(--danger);
  border-color: rgba(244, 63, 94, 0.3);
}

/* Modals & Dialogs */
.failed-chapter-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(7.5rem, 1fr));
  gap: 0.6rem;
}

.failed-chapter-link {
  padding: 0.5rem 0.75rem;
  color: var(--fg-primary);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  text-align: center;
  font-size: 0.85rem;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.failed-chapter-link:hover {
  border-color: var(--accent);
  background: var(--bg-surface-active);
  color: var(--accent);
}

.failed-chapter-link.important-warning-chapter {
  border-color: var(--danger);
  color: var(--danger);
}

.hidden-file-input {
  display: none;
}

.upload-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 1.5rem;
  border: 1px dashed var(--border-base);
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  cursor: pointer;
  text-align: center;
  transition: all var(--transition-fast);
}

.upload-dropzone:hover {
  border-color: var(--accent);
  background: var(--bg-surface-active);
}

.upload-icon {
  color: var(--accent);
}

.upload-label {
  font-weight: 500;
  font-size: 0.875rem;
  color: var(--fg-primary);
}

.upload-hint {
  font-size: 0.75rem;
  color: var(--fg-muted);
}

.cover-preview {
  display: block;
  width: min(9rem, 100%);
  max-height: 12rem;
  margin-top: 0.75rem;
  object-fit: contain;
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
}

.alert-banner {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.875rem 1.25rem;
  border-radius: var(--radius-md);
}

.alert-banner.error {
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--danger);
}

.empty-filter-state {
  text-align: center;
  padding: 3rem 1.5rem;
}
</style>
