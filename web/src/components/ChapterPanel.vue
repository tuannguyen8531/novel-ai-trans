<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from 'vue'
import {
  ArrowUpDown,
  Plus,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  AlertCircle,
  Check,
  CircleDashed,
  CheckCheck,
  RotateCw
} from '@lucide/vue'
import { useJobsStore } from '@/composables/jobs'
import { useChapters } from '@/composables/chapters'
import ChapterDialog from '@/components/ChapterDialog.vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'
import type { NovelTranslationProgress } from '@/api/types'

const props = withDefaults(
  defineProps<{
    novel: string
    active: boolean
    translationProgress?: NovelTranslationProgress | null
    initialFilter?: 'all' | 'issues' | 'completed' | 'untranslated'
  }>(),
  {
    translationProgress: null,
    initialFilter: 'all'
  }
)

const emit = defineEmits<{
  openChapter: [chapter: number]
  jobStarted: [jobId: string]
  'update:filter': [filter: 'all' | 'issues' | 'completed' | 'untranslated']
  ignoreWarnings: []
  retranslate: []
}>()

const jobs = useJobsStore()

const {
  addSaving,
  addError,
  page,
  ascending,
  containerRef,
  numbers,
  columns,
  perPage,
  nextNumber,
  formatNumber,
  load,
  add
} = useChapters(toRef(props, 'novel'))

const failedSet = computed(() => new Set(props.translationProgress?.failed ?? []))
const warningSet = computed(() => new Set(props.translationProgress?.warnings ?? []))
const importantWarningSet = computed(() => new Set(props.translationProgress?.important_warnings ?? []))
const completedSet = computed(() => new Set(props.translationProgress?.completed ?? []))

const activeFilter = ref<'all' | 'issues' | 'completed' | 'untranslated'>(props.initialFilter)

watch(() => props.initialFilter, (newFilter) => {
  if (newFilter) activeFilter.value = newFilter
})

function setFilter(f: 'all' | 'issues' | 'completed' | 'untranslated') {
  activeFilter.value = f
  page.value = 1
  emit('update:filter', f)
}

const allCount = computed(() => numbers.value.length)
const issuesCount = computed(() => numbers.value.filter((n) => failedSet.value.has(n) || warningSet.value.has(n)).length)
const completedCount = computed(() => numbers.value.filter((n) => completedSet.value.has(n) && !failedSet.value.has(n) && !warningSet.value.has(n)).length)
const untranslatedCount = computed(() => numbers.value.filter((n) => !completedSet.value.has(n) && !failedSet.value.has(n)).length)

const filteredNumbers = computed(() => {
  const all = numbers.value
  if (activeFilter.value === 'issues') {
    return all.filter((n) => failedSet.value.has(n) || warningSet.value.has(n))
  }
  if (activeFilter.value === 'completed') {
    return all.filter((n) => completedSet.value.has(n) && !failedSet.value.has(n) && !warningSet.value.has(n))
  }
  if (activeFilter.value === 'untranslated') {
    return all.filter((n) => !completedSet.value.has(n) && !failedSet.value.has(n))
  }
  return all
})

const displayTotalPages = computed(() => Math.max(1, Math.ceil(filteredNumbers.value.length / perPage.value)))

const displayPagedNumbers = computed(() => {
  const start = (page.value - 1) * perPage.value
  return filteredNumbers.value.slice(start, start + perPage.value)
})

watch([filteredNumbers, displayTotalPages], () => {
  if (page.value > displayTotalPages.value) page.value = displayTotalPages.value
})

function getChapterStatusTitle(number: number): string {
  if (failedSet.value.has(number)) return `Chapter ${number}: Translation Failed - click to inspect`
  if (importantWarningSet.value.has(number)) return `Chapter ${number}: Critical Translation Warning - click to review`
  if (warningSet.value.has(number)) return `Chapter ${number}: Quality Warning - click to review`
  if (completedSet.value.has(number)) return `Chapter ${number}: Translated`
  return `Chapter ${number}: Untranslated (Source only)`
}

const showAddDialog = ref(false)
const insertJobId = ref<string | null>(null)
const pendingChapter = ref<number | null>(null)
const insertJobStatus = computed(() => (
  insertJobId.value ? jobs.findJob(insertJobId.value)?.status ?? null : null
))

onMounted(load)

watch(insertJobStatus, async (status, previous) => {
  if (status !== 'completed' || previous === 'completed') return
  const chapter = pendingChapter.value
  await load()
  insertJobId.value = null
  pendingChapter.value = null
  if (chapter !== null) emit('openChapter', chapter)
})

function openAddDialog() {
  addError.value = null
  showAddDialog.value = true
}

async function addChapter(chapter: number, content: string) {
  const jobId = await add(chapter, content)
  if (!jobId) return
  showAddDialog.value = false
  insertJobId.value = jobId
  pendingChapter.value = chapter
  emit('jobStarted', jobId)
}
</script>

<template>
  <div
    v-show="active"
    id="chapters-panel"
    class="detail-tab-panel"
    role="tabpanel"
    aria-labelledby="chapters-tab"
  >
    <DetailPanelHeader title="Chapter List">
      <template #actions>
        <button
          v-if="activeFilter === 'issues' && warningSet.size > 0"
          type="button"
          class="secondary panel-action-button"
          title="Ignore all unresolved warnings"
          @click="emit('ignoreWarnings')"
        >
          <CheckCheck :size="13" />
          <span>Ignore all</span>
        </button>
        <button
          v-if="activeFilter === 'issues'"
          type="button"
          class="secondary panel-action-button"
          title="Retranslate"
          @click="emit('retranslate')"
        >
          <RotateCw :size="13" />
          <span>Retranslate</span>
        </button>
        <button
          type="button"
          class="secondary sort-toggle panel-action-button"
          :title="ascending ? 'Ascending' : 'Descending'"
          @click="ascending = !ascending"
        >
          <ArrowUpDown :size="13" />
          <span>{{ ascending ? 'Asc' : 'Desc' }}</span>
        </button>
        <button type="button" class="secondary panel-action-button" @click="openAddDialog">
          <Plus :size="13" />
          <span>Insert chapter</span>
        </button>
      </template>
    </DetailPanelHeader>
    <!-- Chapter Filter Bar -->
    <div class="chapter-filter-bar">
      <button
        type="button"
        class="filter-tab"
        :class="{ active: activeFilter === 'all' }"
        @click="setFilter('all')"
      >
        <span>All</span>
        <span class="count-pill">{{ allCount }}</span>
      </button>

      <button
        v-if="issuesCount > 0"
        type="button"
        class="filter-tab tab-issues"
        :class="{ active: activeFilter === 'issues' }"
        @click="setFilter('issues')"
      >
        <span>Attention</span>
        <span class="count-pill pill-danger">{{ issuesCount }}</span>
      </button>

      <button
        type="button"
        class="filter-tab"
        :class="{ active: activeFilter === 'completed' }"
        @click="setFilter('completed')"
      >
        <span>Completed</span>
        <span class="count-pill">{{ completedCount }}</span>
      </button>

      <button
        type="button"
        class="filter-tab"
        :class="{ active: activeFilter === 'untranslated' }"
        @click="setFilter('untranslated')"
      >
        <span>Untranslated</span>
        <span class="count-pill">{{ untranslatedCount }}</span>
      </button>
    </div>

    <p v-if="!numbers.length" class="muted empty-message">No chapters yet.</p>
    <div v-else ref="containerRef" class="input-chapter-container">
      <div v-if="!filteredNumbers.length" class="empty-filter-state">
        <p class="muted">No chapters match this filter.</p>
      </div>
      <div v-else class="input-chapter-list">
        <button
          v-for="number in displayPagedNumbers"
          :key="number"
          type="button"
          class="input-chapter-item"
          :class="{
            'item-failed': failedSet.has(number),
            'item-warning': warningSet.has(number) && !failedSet.has(number),
            'item-completed': completedSet.has(number) && !warningSet.has(number) && !failedSet.has(number)
          }"
          :title="getChapterStatusTitle(number)"
          @click="emit('openChapter', number)"
        >
          <div class="chapter-info">
            <span class="chapter-label">Chapter</span>
            <span class="chapter-num">{{ formatNumber(number) }}</span>
          </div>

          <div v-if="failedSet.has(number)" class="chapter-status-badge badge-failed" title="Translation failed">
            <AlertCircle :size="12" />
          </div>
          <div v-else-if="warningSet.has(number)" class="chapter-status-badge badge-warning" title="Quality warning">
            <AlertTriangle :size="12" />
          </div>
          <div v-else-if="completedSet.has(number)" class="chapter-status-badge badge-completed" title="Translated">
            <Check :size="12" />
          </div>
          <div v-else class="chapter-status-badge badge-untranslated" title="Untranslated">
            <CircleDashed :size="12" />
          </div>
        </button>
      </div>
      <div v-if="displayTotalPages > 1" class="input-pagination">
        <button type="button" class="secondary" :disabled="page <= 1" @click="page--">
          <ChevronLeft :size="14" />
          <span>Prev</span>
        </button>
        <span class="muted pagination-label">{{ page }} / {{ displayTotalPages }}</span>
        <button type="button" class="secondary" :disabled="page >= displayTotalPages" @click="page++">
          <span>Next</span>
          <ChevronRight :size="14" />
        </button>
      </div>
    </div>
  </div>

  <ChapterDialog
    :show="showAddDialog"
    :suggested-number="nextNumber"
    :saving="addSaving"
    :error="addError"
    @confirm="addChapter"
    @cancel="showAddDialog = false"
  />
</template>

<style scoped>
.detail-tab-panel {
  padding: 1rem;
}

.empty-message,
.empty-filter-state {
  margin: 0;
  padding: 1.5rem 0;
  text-align: center;
}

.panel-action-button {
  padding: 0.25rem 0.65rem;
}

/* Chapter Filter Bar */
.chapter-filter-bar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.85rem;
  flex-wrap: wrap;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.65rem;
  border-radius: var(--radius-md);
  font-size: 0.775rem;
  font-weight: 500;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--fg-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.filter-tab:hover:not(:disabled):not(.active) {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
  border-color: var(--border-hover);
}

.filter-tab.active {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(79, 125, 249, 0.3);
}

.filter-tab.tab-issues:not(.active) {
  border-color: rgba(245, 158, 11, 0.45);
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
}

.filter-tab.tab-issues.active {
  background: #f59e0b;
  border-color: #f59e0b;
  color: #0b0e14;
}

.count-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-pill);
  font-size: 0.7rem;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.1);
  color: inherit;
}

.filter-tab.active .count-pill {
  background: rgba(255, 255, 255, 0.25);
  color: #ffffff;
}

.filter-tab.tab-issues.active .count-pill {
  background: rgba(0, 0, 0, 0.25);
  color: #0b0e14;
}

.count-pill.pill-danger {
  background: rgba(244, 63, 94, 0.2);
  color: var(--danger);
}

.filter-tab.tab-issues.active .count-pill.pill-danger {
  background: rgba(0, 0, 0, 0.2);
  color: #0b0e14;
}

.input-chapter-container {
  padding: 0.75rem;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
}

.input-chapter-list {
  display: grid;
  grid-template-columns: repeat(v-bind(columns), minmax(0, 1fr));
  grid-auto-rows: 2.35rem;
  gap: 0.45rem;
  min-height: calc(13.55rem + 6px);
  padding: 3px;
}

.input-chapter-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
  padding: 0.35rem 0.65rem;
  color: var(--fg-secondary);
  font-size: 0.825rem;
  cursor: pointer;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.input-chapter-item:hover {
  color: var(--fg-primary);
  border-color: var(--border-hover);
  background: var(--bg-surface-active);
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  z-index: 2;
}

.input-chapter-item.item-completed {
  border-color: rgba(34, 197, 94, 0.25);
}

.input-chapter-item.item-warning {
  border-color: rgba(245, 158, 11, 0.35);
}

.input-chapter-item.item-warning:hover {
  border-color: #f59e0b;
}

.input-chapter-item.item-failed {
  border-color: rgba(244, 63, 94, 0.35);
}

.input-chapter-item.item-failed:hover {
  border-color: var(--danger);
}

.chapter-info {
  display: flex;
  align-items: baseline;
  gap: 0.3rem;
  min-width: 0;
}

.chapter-label {
  font-size: 0.75rem;
  color: var(--fg-muted);
}

.chapter-num {
  font-weight: 600;
  color: var(--fg-primary);
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
}

.chapter-status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.badge-failed {
  color: var(--danger);
}

.badge-warning {
  color: #f59e0b;
}

.badge-completed {
  color: #22c55e;
}

.badge-untranslated {
  color: var(--fg-muted);
  opacity: 0.55;
}

.input-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-base);
}

.sort-toggle {
  min-width: 5rem;
  font-variant-numeric: tabular-nums;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.panel-action-button {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.pagination-label {
  font-size: 0.825rem;
  font-family: var(--font-mono);
}
</style>
