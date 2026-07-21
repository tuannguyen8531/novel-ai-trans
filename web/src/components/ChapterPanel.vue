<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from 'vue'
import { useJobsStore } from '@/composables/jobs'
import { useChapters } from '@/composables/chapters'
import ChapterDialog from '@/components/ChapterDialog.vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'

const props = defineProps<{
  novel: string
  active: boolean
}>()

const emit = defineEmits<{
  openChapter: [chapter: number]
  jobStarted: [jobId: string]
}>()

const jobs = useJobsStore()

const {
  addSaving,
  addError,
  page,
  ascending,
  containerRef,
  numbers,
  totalPages,
  pagedNumbers,
  nextNumber,
  formatNumber,
  load,
  add
} = useChapters(toRef(props, 'novel'))
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
          type="button"
          class="secondary sort-toggle panel-action-button"
          :title="ascending ? 'Ascending' : 'Descending'"
          @click="ascending = !ascending"
        >
          {{ ascending ? '\u2191 Asc' : '\u2193 Desc' }}
        </button>
        <button type="button" class="secondary panel-action-button" @click="openAddDialog">Insert chapter</button>
      </template>
    </DetailPanelHeader>
    <p v-if="!numbers.length" class="muted empty-message">No chapters yet.</p>
    <div v-else ref="containerRef" class="input-chapter-container">
      <div class="input-chapter-list">
        <button
          v-for="number in pagedNumbers"
          :key="number"
          type="button"
          class="input-chapter-item"
          @click="emit('openChapter', number)"
        >
          <span class="chapter-label">Chapter</span>
          <span class="chapter-num">{{ formatNumber(number) }}</span>
        </button>
      </div>
      <div v-if="totalPages > 1" class="input-pagination">
        <button type="button" class="secondary" :disabled="page <= 1" @click="page--">Prev</button>
        <span class="muted">{{ page }} / {{ totalPages }}</span>
        <button type="button" class="secondary" :disabled="page >= totalPages" @click="page++">Next</button>
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

.empty-message {
  margin: 0;
}

.panel-action-button {
  padding: 0.25rem 0.65rem;
}

.input-chapter-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  grid-auto-rows: 2.1rem;
  gap: 0.4rem;
}

.input-chapter-container {
  padding: 0.75rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.input-chapter-container .input-chapter-list {
  height: 12.1rem;
  overflow: hidden;
}

.input-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.sort-toggle {
  min-width: 5rem;
  font-variant-numeric: tabular-nums;
}

.input-chapter-item {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  color: var(--fg-dim);
  font-size: 0.85rem;
  cursor: pointer;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.chapter-label {
  color: var(--fg-dim);
}

.chapter-num {
  color: var(--fg);
  font-family: var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
}

.input-chapter-item:hover {
  color: var(--fg);
  border-color: var(--accent);
}
</style>
