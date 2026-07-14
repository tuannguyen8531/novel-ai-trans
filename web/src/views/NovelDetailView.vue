<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'
import { useSettingsStore } from '@/stores/settings'
import { useJobsStore } from '@/stores/jobs'
import { api } from '@/api/client'
import type { NovelChapterStatus, ArtifactInfo } from '@/api/types'
import GlossaryEditor from '@/components/GlossaryEditor.vue'
import JobMonitor from '@/components/JobMonitor.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import placeholderCover from '@/assets/placeholder-cover.png'

const props = defineProps<{ name: string }>()
const route = useRoute()
const router = useRouter()
const novels = useNovelsStore()
const settings = useSettingsStore()
const jobs = useJobsStore()
const tab = ref<'chapters' | 'glossary' | 'artifacts' | 'rules'>('chapters')
const chapters = ref<NovelChapterStatus[]>([])
const target = ref<'vi' | 'en'>('vi')
const jobId = ref<string | null>(null)

const packFormats = ref<{ epub: boolean; pdf: boolean }>({ epub: true, pdf: true })
const packDarkMode = ref<boolean>(false)
const packTitle = ref<string>('')
const packAuthor = ref<string>('')
const packError = ref<string | null>(null)
const artifactError = ref<string | null>(null)
const showPackForm = ref<boolean>(false)

const metadata = ref<Record<string, unknown> | null>(null)
const metadataLoading = ref<boolean>(false)
const metadataError = ref<string | null>(null)
const metaTitle = ref<string>('')
const metaAuthor = ref<string>('')
const metaSourceUrl = ref<string>('')
const metaIllustrationUrl = ref<string>('')
const metaSummary = ref<string>('')
const metaSourceLang = ref<string>('')
const metaTranslatedVi = ref<string>('')
const metaTranslatedEn = ref<string>('')
const metaSummaryVi = ref<string>('')
const metaSummaryEn = ref<string>('')
const metadataForce = ref<boolean>(false)
const metaError = ref<string | null>(null)
const showMetaForm = ref<boolean>(false)
const coverBroken = ref<boolean>(false)

const novelRules = ref<string>('')
const rulesLoading = ref<boolean>(false)
const rulesSaving = ref<boolean>(false)
const rulesError = ref<string | null>(null)
const rulesSuccessMessage = ref<string | null>(null)

const inputPage = ref(1)
const containerWidth = ref(600)
const containerRef = ref<HTMLElement | null>(null)
let resizeObserver: ResizeObserver | null = null

const columnsCount = computed(() => {
  const width = containerWidth.value
  const minWidth = 128 // 8rem * 16px
  const gap = 6.4      // 0.4rem * 16px
  const cols = Math.floor((width + gap) / (minWidth + gap))
  return Math.max(1, cols)
})

const inputRows = 5
const inputPerPage = computed(() => columnsCount.value * inputRows)
const inputAscending = ref(true)

const showAddModal = ref(false)
const addChapterNumber = ref<number | null>(null)
const addChapterContent = ref('')
const addChapterSaving = ref(false)
const addChapterError = ref<string | null>(null)
const addModalCard = ref<HTMLElement | null>(null)
let addPreviousFocus: HTMLElement | null = null

const showDeleteDialog = ref(false)
const deleteChapterSaving = ref(false)
const inputReading = ref<{ chapter: number; content: string; editing: boolean; editContent: string } | null>(null)
const inputSaving = ref(false)
const inputError = ref<string | null>(null)

const novelName = computed(() => props.name || String(route.params.name || ''))

const inputChapterNumbers = computed(() => {
  const sources = new Set<number>()
  for (const status of chapters.value) {
    if (status.has_source) sources.add(status.number)
  }
  const sorted = [...sources].sort((a, b) => a - b)
  return inputAscending.value ? sorted : sorted.reverse()
})

const inputTotalPages = computed(() => Math.max(1, Math.ceil(inputChapterNumbers.value.length / inputPerPage.value)))

const pagedInputChapters = computed(() => {
  const start = (inputPage.value - 1) * inputPerPage.value
  return inputChapterNumbers.value.slice(start, start + inputPerPage.value)
})

const chapterPadWidth = computed(() => {
  const max = inputChapterNumbers.value.reduce((m, n) => Math.max(m, n), 0)
  return String(max).length
})

function formatChapterNum(num: number): string {
  return String(num).padStart(chapterPadWidth.value, '\u2007')
}

const lastInputChapter = computed(() => {
  const nums = inputChapterNumbers.value
  return nums.length > 0 ? Math.max(...nums) : 0
})

watch([inputChapterNumbers, inputTotalPages], () => {
  if (inputPage.value > inputTotalPages.value) {
    inputPage.value = inputTotalPages.value
  }
})

watch(containerRef, (el) => {
  if (el) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        containerWidth.value = entry.contentRect.width
      }
    })
    resizeObserver.observe(el)
  } else {
    resizeObserver?.disconnect()
    resizeObserver = null
  }
})

const artifactsList = ref<ArtifactInfo[]>([])
const artifactsLoading = ref(false)

async function loadArtifacts() {
  artifactsLoading.value = true
  artifactError.value = null
  try {
    artifactsList.value = await api.listArtifacts(novelName.value)
  } catch (err) {
    artifactError.value = (err as Error).message
  } finally {
    artifactsLoading.value = false
  }
}

watch(tab, (newTab) => {
  if (newTab === 'artifacts') {
    void loadArtifacts()
  } else if (newTab === 'rules') {
    void loadNovelRules()
  }
})

onMounted(async () => {
  await Promise.all([novels.load(novelName.value), settings.refresh()])
  chapters.value = await api.listChapters(novelName.value)
  await loadMetadata()
  if (tab.value === 'artifacts') {
    await loadArtifacts()
  }
  if (route.query.job) {
    jobId.value = String(route.query.job)
  }
})

async function loadMetadata() {
  metadataLoading.value = true
  metadataError.value = null
  try {
    const response = await api.getNovelMetadata(novelName.value)
    const inner = (response.data as Record<string, unknown>) ?? {}
    metadata.value = Object.keys(inner).length ? inner : null
    metaTitle.value = (inner.title as string) ?? ''
    metaAuthor.value = (inner.author as string) ?? ''
    metaSourceUrl.value = (inner.source_url as string) ?? ''
    metaIllustrationUrl.value = (inner.illustration_url as string) ?? ''
    metaSummary.value = (inner.summary as string) ?? ''
    metaSourceLang.value = (inner.source_language as string) ?? ''
    const localized = (inner.localized as Record<string, Record<string, string | null>> | undefined) ?? {}
    metaTranslatedVi.value = localized.vi?.title ?? ''
    metaTranslatedEn.value = localized.en?.title ?? ''
    metaSummaryVi.value = localized.vi?.summary ?? ''
    metaSummaryEn.value = localized.en?.summary ?? ''
  } catch (err) {
    metadata.value = null
    metadataError.value = (err as Error).message
  } finally {
    metadataLoading.value = false
  }
}

async function loadNovelRules() {
  rulesLoading.value = true
  rulesError.value = null
  rulesSuccessMessage.value = null
  try {
    const data = await api.getNovelRules(novelName.value)
    novelRules.value = data.rules || ''
  } catch (err) {
    rulesError.value = (err as Error).message
  } finally {
    rulesLoading.value = false
  }
}

async function saveNovelRules() {
  rulesSaving.value = true
  rulesError.value = null
  rulesSuccessMessage.value = null
  try {
    await api.saveNovelRules(novelName.value, novelRules.value)
    rulesSuccessMessage.value = 'Rules saved successfully.'
    setTimeout(() => {
      if (rulesSuccessMessage.value === 'Rules saved successfully.') {
        rulesSuccessMessage.value = null
      }
    }, 3000)
  } catch (err) {
    rulesError.value = (err as Error).message
  } finally {
    rulesSaving.value = false
  }
}

const displayNovelTitle = computed(() => {
  const targetLanguage = settings.settings?.target_language
  const targetTitle = targetLanguage === 'en' ? metaTranslatedEn.value.trim() : metaTranslatedVi.value.trim()
  return targetTitle || metaTitle.value.trim() || novels.detail?.title || novelName.value
})

const displayNovelSummary = computed(() => {
  const localizedSummary = settings.settings?.target_language === 'en'
    ? metaSummaryEn.value.trim()
    : metaSummaryVi.value.trim()
  return localizedSummary || metaSummary.value.trim()
})

const displayNovelAuthor = computed(
  () => metaAuthor.value.trim() || novels.detail?.author?.trim() || 'Not updated'
)

watch(
  displayNovelTitle,
  (title) => {
    document.title = `${title} — Novel AI Translation`
  },
  { immediate: true }
)

async function saveMetadata() {
  metaError.value = null
  const patch: Record<string, unknown> = {
    title: metaTitle.value.trim(),
    author: metaAuthor.value.trim(),
    source_url: metaSourceUrl.value.trim(),
    illustration_url: metaIllustrationUrl.value.trim(),
    summary: metaSummary.value.trim(),
    source_language: metaSourceLang.value.trim() || null
  }
  const currentLocalized = (
    metadata.value?.localized as Record<string, Record<string, string | null>> | undefined
  ) ?? {}
  const localized: Record<string, Record<string, string | null>> = {}
  for (const [language, title, summary] of [
    ['vi', metaTranslatedVi.value.trim(), metaSummaryVi.value.trim()],
    ['en', metaTranslatedEn.value.trim(), metaSummaryEn.value.trim()]
  ] as const) {
    const changes: Record<string, string | null> = {}
    const currentTitle = currentLocalized[language]?.title ?? ''
    const currentSummary = currentLocalized[language]?.summary ?? ''
    if (title !== currentTitle) changes.title = title || null
    if (summary !== currentSummary) changes.summary = summary || null
    if (Object.keys(changes).length) localized[language] = changes
  }
  if (Object.keys(localized).length) patch.localized = localized
  try {
    await api.patchNovelMetadata(novelName.value, patch)
    await loadMetadata()
    await novels.load(novelName.value)
    showMetaForm.value = false
  } catch (err) {
    metaError.value = (err as Error).message
  }
}

function metaDisplayValue(current: string, fallback: string | null | undefined): string {
  return current.trim() || (fallback ? String(fallback) : '') || '—'
}

const hasAnyMetadata = computed(() =>
  Boolean(
    metaTitle.value.trim() ||
      metaAuthor.value.trim() ||
      metaSourceUrl.value.trim() ||
      metaIllustrationUrl.value.trim() ||
      metaSummary.value.trim() ||
      metaSourceLang.value.trim() ||
      metaTranslatedVi.value.trim() ||
      metaTranslatedEn.value.trim() ||
      metaSummaryVi.value.trim() ||
      metaSummaryEn.value.trim()
  )
)

async function translateMetadata(language: 'vi' | 'en') {
  metaError.value = null
  await saveMetadata()
  if (metaError.value) {
    showMetaForm.value = true
    return
  }
  try {
    const result = await api.localizeNovelMetadata(novelName.value, {
      target_language: language,
      force: metadataForce.value
    })
    jobId.value = result.job_id
    showMetaForm.value = false
  } catch (err) {
    metaError.value = (err as Error).message
  }
}

const metadataJobStatus = computed(() => jobId.value ? jobs.findJob(jobId.value)?.status : null)

watch(metadataJobStatus, (status, previous) => {
  if (status === 'completed' && previous !== 'completed') {
    void loadMetadata()
    void novels.load(novelName.value)
  }
})

const coverSrc = computed(() => {
  if (coverBroken.value) return placeholderCover
  const url = metaIllustrationUrl.value.trim()
  if (!url) return placeholderCover
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url
  }
  return api.illustrationUrl(novelName.value, url)
})

watch(metaIllustrationUrl, () => {
  coverBroken.value = false
})

function onCoverError() {
  coverBroken.value = true
}

async function downloadArtifact(name: string) {
  artifactError.value = null
  try {
    const blob = await api.downloadArtifact(novelName.value, name)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    artifactError.value = (err as Error).message
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  const YYYY = date.getFullYear()
  const MM = String(date.getMonth() + 1).padStart(2, '0')
  const DD = String(date.getDate()).padStart(2, '0')
  const HH = String(date.getHours()).padStart(2, '0')
  const MIN = String(date.getMinutes()).padStart(2, '0')
  const SS = String(date.getSeconds()).padStart(2, '0')
  return `${YYYY}/${MM}/${DD} ${HH}:${MIN}:${SS}`
}

const showDeleteArtifactDialog = ref(false)
const deleteArtifactName = ref<string | null>(null)
const deleteArtifactSaving = ref(false)

function confirmDeleteArtifact(name: string) {
  deleteArtifactName.value = name
  showDeleteArtifactDialog.value = true
}

async function handleDeleteArtifact() {
  if (!deleteArtifactName.value) return
  deleteArtifactSaving.value = true
  artifactError.value = null
  try {
    await api.deleteArtifact(novelName.value, deleteArtifactName.value)
    showDeleteArtifactDialog.value = false
    await loadArtifacts()
  } catch (err) {
    artifactError.value = (err as Error).message
  } finally {
    deleteArtifactSaving.value = false
    deleteArtifactName.value = null
  }
}

function cancelDeleteArtifact() {
  showDeleteArtifactDialog.value = false
  deleteArtifactName.value = null
}

async function startPack() {
  packError.value = null
  const formats: string[] = []
  if (packFormats.value.epub) formats.push('epub')
  if (packFormats.value.pdf) formats.push('pdf')
  if (!formats.length) {
    packError.value = 'Pick at least one format.'
    return
  }
  const payload: Record<string, unknown> = {
    novel: novelName.value,
    target_language: target.value,
    formats
  }
  if (packFormats.value.pdf) {
    payload.dark_mode = packDarkMode.value
  }
  if (packTitle.value.trim()) payload.title = packTitle.value.trim()
  if (packAuthor.value.trim()) payload.author = packAuthor.value.trim()
  try {
    const result = await api.startPack(payload)
    jobId.value = result.job_id
    router.replace({ query: { job: result.job_id } })
    showPackForm.value = false
  } catch (err) {
    packError.value = (err as Error).message
  }
}


async function addNewChapter() {
  addChapterError.value = null
  addChapterNumber.value = lastInputChapter.value + 1
  addChapterContent.value = ''
  showAddModal.value = true
}

function closeAddModal() {
  if (addChapterSaving.value) return
  showAddModal.value = false
  addPreviousFocus?.focus()
  addPreviousFocus = null
}

function handleAddModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeAddModal()
    return
  }
  if (event.key !== 'Tab' || !addModalCard.value) return
  const focusable = Array.from(
    addModalCard.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
  )
  if (!focusable.length) {
    event.preventDefault()
    addModalCard.value.focus()
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

watch(showAddModal, (isOpen) => {
  if (isOpen) {
    addPreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => addModalCard.value?.focus())
  } else {
    document.body.style.overflow = ''
  }
})

watch(showPackForm, (isOpen) => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'
  } else if (!showAddModal.value && !showMetaForm.value) {
    document.body.style.overflow = ''
  }
})

watch(showMetaForm, (isOpen) => {
  if (isOpen) {
    document.body.style.overflow = 'hidden'
  } else if (!showAddModal.value && !showPackForm.value) {
    document.body.style.overflow = ''
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
  resizeObserver?.disconnect()
})

async function confirmAddChapter() {
  if (addChapterNumber.value === null) return
  addChapterError.value = null
  addChapterSaving.value = true
  try {
    await api.putChapterContent(novelName.value, addChapterNumber.value, addChapterContent.value)
    chapters.value = await api.listChapters(novelName.value)
    const newPage = Math.ceil(
      inputChapterNumbers.value.indexOf(addChapterNumber.value) / inputPerPage.value + 1
    )
    if (newPage > 0) inputPage.value = newPage
    closeAddModal()
    void router.push({
      name: 'chapter-reader',
      params: { name: novelName.value, chapter: addChapterNumber.value }
    })
  } catch (err) {
    addChapterError.value = (err as Error).message
  } finally {
    addChapterSaving.value = false
  }
}

async function openInputChapter(chapter: number) {
  inputError.value = null
  try {
    const response = await api.getChapterContent(novelName.value, chapter, 'source')
    inputReading.value = { chapter, content: response.content, editing: false, editContent: response.content }
  } catch (err) {
    inputError.value = (err as Error).message
  }
}

function startEditInput() {
  if (!inputReading.value) return
  inputReading.value.editContent = inputReading.value.content
  inputReading.value.editing = true
}

function cancelEditInput() {
  if (!inputReading.value) return
  inputReading.value.editing = false
  inputReading.value.editContent = inputReading.value.content
}

async function saveInputChapter() {
  if (!inputReading.value) return
  inputError.value = null
  inputSaving.value = true
  try {
    const response = await api.putChapterContent(novelName.value, inputReading.value.chapter, inputReading.value.editContent)
    inputReading.value.content = response.content
    inputReading.value.editing = false
  } catch (err) {
    inputError.value = (err as Error).message
  } finally {
    inputSaving.value = false
  }
}

function openDeleteDialog() {
  if (!inputReading.value) return
  showDeleteDialog.value = true
}

async function confirmDeleteChapter() {
  if (!inputReading.value) return
  showDeleteDialog.value = false
  deleteChapterSaving.value = true
  try {
    await api.deleteChapter(novelName.value, inputReading.value.chapter)
    inputReading.value = null
    chapters.value = await api.listChapters(novelName.value)
  } catch (err) {
    inputError.value = (err as Error).message
  } finally {
    deleteChapterSaving.value = false
  }
}

function cancelDeleteChapter() {
  showDeleteDialog.value = false
}

</script>

<template>
  <section class="flex-col gap-3">
    <div v-if="novels.error" class="card error">{{ novels.error }}</div>
    <div v-else-if="novels.detail" class="flex-col gap-3">
      <div class="card">
        <div class="novel-cover-row">
          <img class="novel-cover" :src="coverSrc" :alt="`Cover for ${displayNovelTitle}`" @error="onCoverError" />
          <div class="novel-cover-info">
            <h2 :title="displayNovelTitle">{{ displayNovelTitle }}</h2>
            <p class="novel-author" :title="`Author: ${displayNovelAuthor}`">
              <span>Author:</span> {{ displayNovelAuthor }}
            </p>
            <div v-if="displayNovelSummary" class="novel-summary">
              <span class="novel-summary-label">Summary</span>
              <div class="novel-summary-content">{{ displayNovelSummary }}</div>
            </div>
          </div>
        </div>

        <div class="meta-summary" v-if="metadata || metadataError">
          <div class="meta-row" v-if="metaTitle || novels.detail?.title">
            <span class="meta-label">Title</span>
            <span>{{ metaDisplayValue(metaTitle, novels.detail?.title) }}</span>
          </div>
          <div class="meta-row" v-if="metaAuthor || novels.detail?.author">
            <span class="meta-label">Author</span>
            <span>{{ metaDisplayValue(metaAuthor, novels.detail?.author) }}</span>
          </div>
          <div class="meta-row" v-if="metaSourceLang || novels.detail?.source_language">
            <span class="meta-label">Language</span>
            <span style="text-transform: capitalize;">{{ metaDisplayValue(metaSourceLang, novels.detail?.source_language) }}</span>
          </div>
          <div class="meta-row" v-if="metaTranslatedVi">
            <span class="meta-label">Title (vi)</span>
            <span>{{ metaTranslatedVi }}</span>
          </div>
          <div class="meta-row" v-if="metaTranslatedEn">
            <span class="meta-label">Title (en)</span>
            <span>{{ metaTranslatedEn }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Total</span>
            <span>{{ novels.detail.total_input_chapters }} chapter{{ novels.detail.total_input_chapters === 1 ? '' : 's' }}</span>
          </div>
          <p v-if="metadataError" class="error meta-empty">Failed to load metadata: {{ metadataError }}</p>
          <p v-else-if="!hasAnyMetadata" class="muted meta-empty">
            No metadata fields filled in yet — click <strong>Edit metadata</strong> to add some.
          </p>
        </div>
        <div class="actions-row">
          <div class="row gap-2" style="align-items: center;">
            <button type="button" @click="router.push({ name: 'translate', query: { novel: novelName } })">
              Translate
            </button>
            <button type="button" class="secondary" @click="showPackForm = !showPackForm">Pack</button>
            <button type="button" class="secondary" @click="showMetaForm = !showMetaForm">Metadata</button>
          </div>

        </div>
      </div>

      <div v-if="jobId" class="card">
        <h3>Latest job</h3>
        <JobMonitor :job-id="jobId" />
      </div>

      <div class="detail-tabs-shell">
        <nav class="detail-tabs" aria-label="Novel details" role="tablist">
          <button
            id="chapters-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'chapters'"
            aria-controls="chapters-panel"
            @click="tab = 'chapters'"
          >
            Chapters
          </button>



          <button
            id="glossary-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'glossary'"
            aria-controls="glossary-panel"
            @click="tab = 'glossary'"
          >
            Glossary
          </button>
          <button
            id="artifacts-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'artifacts'"
            aria-controls="artifacts-panel"
            @click="tab = 'artifacts'"
          >
            Artifacts
          </button>
          <button
            id="rules-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'rules'"
            aria-controls="rules-panel"
            @click="tab = 'rules'"
          >
            Rules
          </button>
        </nav>

        <div
          v-if="tab === 'chapters'"
          id="chapters-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="chapters-tab"
        >
          <div class="row gap-2" style="justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <h3 style="margin: 0;">Chapter List</h3>
            <div class="row gap-2" style="align-items: center;">
              <button
                type="button"
                class="secondary sort-toggle"
                :title="inputAscending ? 'Ascending' : 'Descending'"
                @click="inputAscending = !inputAscending"
              >
                {{ inputAscending ? '\u2191 Asc' : '\u2193 Desc' }}
              </button>
              <button type="button" class="secondary" @click="addNewChapter">Add chapter</button>
            </div>
          </div>
          <p v-if="!inputChapterNumbers.length" class="muted" style="margin-top: 0.5rem;">No chapters yet.</p>
          <div v-else class="input-chapter-container" ref="containerRef">
            <div class="input-chapter-list">
              <button
                v-for="num in pagedInputChapters"
                :key="num"
                type="button"
                class="input-chapter-item"
                @click="router.push({ name: 'chapter-reader', params: { name: novelName, chapter: num } })"
              >
                <span class="chapter-label">Chapter</span>
                <span class="chapter-num">{{ formatChapterNum(num) }}</span>
              </button>
            </div>
            <div v-if="inputTotalPages > 1" class="input-pagination">
              <button
                type="button"
                class="secondary"
                :disabled="inputPage <= 1"
                @click="inputPage--"
              >Prev</button>
              <span class="muted">{{ inputPage }} / {{ inputTotalPages }}</span>
              <button
                type="button"
                class="secondary"
                :disabled="inputPage >= inputTotalPages"
                @click="inputPage++"
              >Next</button>
            </div>
          </div>

        </div>



        <div
          v-else-if="tab === 'glossary'"
          id="glossary-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="glossary-tab"
        >
          <GlossaryEditor :novel="novelName" />
        </div>

        <div
          v-else-if="tab === 'artifacts' && novels.detail"
          id="artifacts-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="artifacts-tab"
        >
          <h3>Artifacts</h3>
          <p v-if="artifactError" class="error">{{ artifactError }}</p>
          <p v-if="!artifactsList.length" class="muted">No artifacts yet.</p>
          <div v-else class="artifact-list">
            <div v-for="artifact in artifactsList" :key="artifact.name" class="artifact-item">
              <div class="artifact-info">
                <div class="artifact-name">{{ artifact.name }}</div>
                <div class="artifact-meta">
                  <span class="artifact-badge">{{ artifact.format.toUpperCase() }}</span>
                  <span class="artifact-badge">{{ artifact.target_language.toUpperCase() }}</span>
                  <span class="muted">{{ artifact.chapter_count }} chapters</span>
                  <span class="muted">—</span>
                  <span class="muted">{{ formatFileSize(artifact.size) }}</span>
                  <span class="muted">—</span>
                  <span class="muted">{{ formatDate(artifact.created_at) }}</span>
                </div>
              </div>
              <div class="artifact-actions">
                <button class="secondary" type="button" @click="downloadArtifact(artifact.name)">Download</button>
                <button class="secondary danger" type="button" @click="confirmDeleteArtifact(artifact.name)">Delete</button>
              </div>
            </div>
          </div>
        </div>

        <div
          v-else-if="tab === 'rules'"
          id="rules-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="rules-tab"
        >
          <div class="rules-editor">
            <div class="rules-editor-header">
              <div class="rules-editor-copy">
                <h3>Novel Translation Rules</h3>
                <p class="muted">
                  These instructions will be appended to the translation rules for this novel only. You can use Markdown.
                </p>
              </div>
              <button
                type="button"
                :disabled="rulesSaving || rulesLoading"
                @click="saveNovelRules"
              >
                {{ rulesSaving ? 'Saving...' : 'Save Rules' }}
              </button>
            </div>
            <textarea
              v-model="novelRules"
              placeholder="e.g.
- Xưng hô 'ta' - 'ngươi' giữa hai nhân vật chính.
- Giữ nguyên tên chiêu thức bằng Hán-Việt."
              style="width: 100%; min-height: 400px; font-family: monospace; padding: 0.75rem; border-radius: 4px; border: 1px solid var(--border-color); background-color: var(--bg-card); color: var(--text-color); resize: vertical;"
              :disabled="rulesLoading"
            ></textarea>
            <div v-if="rulesError" class="error">{{ rulesError }}</div>
            <div v-if="rulesSuccessMessage" class="success-message" style="color: var(--color-success, #4caf50); font-weight: bold;">
              {{ rulesSuccessMessage }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showAddModal" class="modal-overlay">
      <div
        ref="addModalCard"
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-chapter-title"
        tabindex="-1"
        @keydown="handleAddModalKeydown"
      >
        <header class="modal-header">
          <h3 id="add-chapter-title">Add Chapter</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            :disabled="addChapterSaving"
            @click="closeAddModal"
          >&times;</button>
        </header>
        <div class="modal-body">
          <p v-if="addChapterError" class="error">{{ addChapterError }}</p>
          <div>
            <label>Chapter number</label>
            <input v-model.number="addChapterNumber" type="number" min="1" />
          </div>
          <div style="margin-top: 0.75rem;">
            <label>Content (optional)</label>
            <textarea v-model="addChapterContent" class="chapter-edit-area" style="min-height: 12rem;"></textarea>
          </div>
        </div>
        <footer class="modal-footer">
          <button type="button" class="secondary" :disabled="addChapterSaving" @click="closeAddModal">Cancel</button>
          <button
            type="button"
            :disabled="addChapterSaving || addChapterNumber === null || addChapterNumber < 1"
            @click="confirmAddChapter"
          >{{ addChapterSaving ? 'Adding...' : 'Add' }}</button>
        </footer>
      </div>
    </div>

    <!-- ── Pack Modal ── -->
    <div v-if="showPackForm" class="modal-overlay">
      <div
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pack-title"
        tabindex="-1"
      >
        <header class="modal-header">
          <h3 id="pack-title">Pack Novel</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="showPackForm = false"
          >&times;</button>
        </header>
        <div class="modal-body">
          <div class="pack-target">
            <label for="pack-target-language">Target language</label>
            <select id="pack-target-language" v-model="target" style="width: 100%;">
              <option value="vi">Vietnamese (vi)</option>
              <option value="en">English (en)</option>
            </select>
          </div>
          <div style="margin-top: 0.75rem;">
            <label>Output formats</label>
            <div class="check-row">
              <label class="check">
                <input v-model="packFormats.epub" type="checkbox" />
                <span>EPUB</span>
              </label>
              <label class="check">
                <input v-model="packFormats.pdf" type="checkbox" />
                <span>PDF</span>
              </label>
            </div>
          </div>
          <div v-if="packFormats.pdf" style="margin-top: 0.75rem;">
            <label>PDF options</label>
            <div class="check-row">
              <label class="check">
                <input v-model="packDarkMode" type="checkbox" />
                <span>Dark mode (dark background, light text)</span>
              </label>
            </div>
          </div>
          <div class="pack-meta" style="margin-top: 0.75rem; display: flex; flex-direction: column; gap: 0.75rem;">
            <div>
              <label>Custom title (optional)</label>
              <input v-model="packTitle" placeholder="defaults to metadata title" style="width: 100%;" />
            </div>
            <div>
              <label>Custom author (optional)</label>
              <input v-model="packAuthor" placeholder="defaults to metadata author" style="width: 100%;" />
            </div>
          </div>
          <p v-if="packError" class="error" style="margin-top: 0.5rem;">{{ packError }}</p>
        </div>
        <footer class="modal-footer">
          <button type="button" class="secondary" @click="showPackForm = false">Cancel</button>
          <button type="button" @click="startPack">Start pack</button>
        </footer>
      </div>
    </div>

    <!-- ── Metadata Modal ── -->
    <div v-if="showMetaForm" class="modal-overlay">
      <div
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="metadata-title"
        tabindex="-1"
      >
        <header class="modal-header">
          <h3 id="metadata-title">Edit Metadata</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            @click="showMetaForm = false"
          >&times;</button>
        </header>
        <div class="modal-body">
          <p v-if="metadataLoading" class="muted">Loading metadata…</p>
          <p v-else-if="metadataError" class="error">Failed to load metadata: {{ metadataError }}</p>
          <p v-else-if="!metadata" class="muted">No metadata.json yet. Fill in the fields below and save to create one.</p>
          
          <div v-if="!metadataLoading" style="display: flex; flex-direction: column; gap: 0.75rem;">
            <div>
              <label>Original title</label>
              <input v-model="metaTitle" placeholder="원제목 / タイトル / title" style="width: 100%;" />
            </div>
            <div>
              <label>Author</label>
              <input v-model="metaAuthor" placeholder="author name" style="width: 100%;" />
            </div>
            <div>
              <label>Source URL</label>
              <input v-model="metaSourceUrl" placeholder="https://..." style="width: 100%;" />
            </div>
            <div>
              <label>Cover image URL</label>
              <input v-model="metaIllustrationUrl" placeholder="https://... (optional)" style="width: 100%;" />
            </div>
            <div>
              <label>Summary</label>
              <textarea
                v-model="metaSummary"
                class="metadata-summary-input"
                placeholder="novel synopsis (optional)"
              ></textarea>
            </div>
            <div>
              <label>Source language</label>
              <select v-model="metaSourceLang" style="width: 100%;">
                <option value="">(Auto-detect)</option>
                <option value="korean">Korean</option>
                <option value="japanese">Japanese</option>
                <option value="chinese">Chinese</option>
              </select>
            </div>
            <div class="pack-meta" style="display: flex; flex-direction: column; gap: 0.75rem;">
              <div>
                <label>Translated title — vi</label>
                <input v-model="metaTranslatedVi" placeholder="Tiêu đề tiếng Việt" style="width: 100%;" />
              </div>
              <div>
                <label>Translated summary — vi</label>
                <textarea v-model="metaSummaryVi" class="metadata-summary-input" placeholder="Tóm tắt tiếng Việt"></textarea>
              </div>
              <div>
                <label>Translated title — en</label>
                <input v-model="metaTranslatedEn" placeholder="English title" style="width: 100%;" />
              </div>
              <div>
                <label>Translated summary — en</label>
                <textarea v-model="metaSummaryEn" class="metadata-summary-input" placeholder="English summary"></textarea>
              </div>
              <label class="check">
                <input v-model="metadataForce" type="checkbox" />
                <span>Regenerate existing AI translations</span>
              </label>
              <div class="row gap-2">
                <button class="secondary" type="button" @click="translateMetadata('vi')">Save and translate Vietnamese</button>
                <button class="secondary" type="button" @click="translateMetadata('en')">Save and translate English</button>
              </div>
            </div>
          </div>
          <p v-if="metaError" class="error" style="margin-top: 0.5rem;">{{ metaError }}</p>
        </div>
        <footer class="modal-footer">
          <button class="secondary" type="button" @click="showMetaForm = false">Cancel</button>
          <button class="secondary" type="button" @click="loadMetadata">Revert</button>
          <button type="button" @click="saveMetadata">Save metadata</button>
        </footer>
      </div>
    </div>

    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Chapter"
      :message="`Delete Chapter ${inputReading?.chapter} from the input chapters?\n\nThis permanently deletes the source chapter file. Translated chapters will not be deleted but may become orphaned. This cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      :loading="deleteChapterSaving"
      @confirm="confirmDeleteChapter"
      @cancel="cancelDeleteChapter"
    />

    <ConfirmDialog
      :show="showDeleteArtifactDialog"
      title="Delete Artifact"
      :message="`Delete artifact '${deleteArtifactName}'?\n\nThis permanently removes the exported file. This cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      :loading="deleteArtifactSaving"
      @confirm="handleDeleteArtifact"
      @cancel="cancelDeleteArtifact"
    />

  </section>
</template>

<style scoped>
.actions-row {
  margin-top: 0.75rem;
}

.detail-tabs-shell {
  overflow: hidden;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.detail-tabs {
  display: flex;
  gap: 1.5rem;
  padding: 0 1rem;
  background: var(--bg-elev-2);
  border-bottom: 1px solid var(--border);
}

.detail-tab {
  position: relative;
  padding: 0.65rem 0.1rem 0.75rem;
  background: transparent;
  color: var(--fg-dim);
  border: 0;
  border-radius: 0;
  font-weight: 600;
}

.detail-tab:hover:not(:disabled) {
  background: transparent;
  color: var(--fg);
}

.detail-tab[aria-selected='true'] {
  color: var(--accent);
}

.detail-tab[aria-selected='true']::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: var(--accent);
  content: '';
}

.detail-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.detail-tab-panel {
  padding: 1rem;
}

.meta-summary {
  margin-top: 0.75rem;
  padding: 0.6rem 0.75rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 0.35rem 1rem;
  font-size: 0.9rem;
}

.meta-row {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 0;
}

.meta-row > span:not(.meta-label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-label {
  color: var(--fg-dim);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.meta-empty {
  grid-column: 1 / -1;
  margin: 0;
  padding-top: 0.25rem;
}

.metadata-summary-input {
  height: 10rem;
  resize: none;
}

.rules-editor {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.rules-editor-header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: flex-end;
  justify-content: space-between;
}

.rules-editor-copy {
  flex: 1 1 24rem;
  min-width: 0;
}

.rules-editor-copy h3,
.rules-editor-copy p {
  margin: 0;
}

.rules-editor-copy h3 {
  margin-bottom: 0.35rem;
}

.rules-editor-header button {
  flex: 0 0 auto;
  margin-bottom: 0.1rem;
}

@media (max-width: 640px) {
  .rules-editor-header {
    align-items: flex-start;
  }

  .rules-editor-header button {
    margin-bottom: 0;
  }
}

.novel-cover-row {
  display: grid;
  grid-template-columns: clamp(7rem, 24vw, 11.25rem) minmax(0, 1fr);
  height: clamp(10.5rem, 36vw, 16.875rem);
  gap: 1.25rem;
  margin-bottom: 1rem;
}

.novel-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: var(--radius);
  background: var(--bg-elev-2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

.novel-cover-info {
  display: flex;
  height: 100%;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.novel-cover-info h2 {
  flex-shrink: 0;
  margin: 0;
  overflow: hidden;
  font-size: 1.35rem;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-author {
  flex-shrink: 0;
  margin: 0.25rem 0 0;
  overflow: hidden;
  color: var(--fg-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-author span {
  color: var(--fg);
  font-weight: 600;
}

.novel-summary {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  margin-top: 0.75rem;
  overflow: hidden;
  padding: 0.6rem 0.75rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 0.9rem;
  line-height: 1.5;
}

.novel-summary-label {
  flex-shrink: 0;
  margin-bottom: 0.25rem;
  color: var(--fg-dim);
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.novel-summary-content {
  min-height: 0;
  overflow: auto;
  white-space: pre-wrap;
}

.pack-form {
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.pack-form .pack-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.5rem;
}

.pack-target {
  max-width: 14rem;
}



.chapter-edit-area {
  width: 100%;
  min-height: 20rem;
  max-height: 36rem;
  background: var(--bg-elev-2);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  font-family: var(--font);
  font-size: 1rem;
  line-height: 1.6;
  resize: vertical;
}

.input-chapter-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  grid-auto-rows: 2.1rem;
  gap: 0.4rem;
}

.input-chapter-container {
  margin-top: 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-elev-2);
  padding: 0.75rem;
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
  padding: 0.35rem 0.75rem;
  font-size: 0.85rem;
  border-radius: var(--radius);
  background: var(--bg-elev);
  border: 1px solid var(--border);
  color: var(--fg-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.chapter-label {
  color: var(--fg-dim);
}

.chapter-num {
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono, monospace);
  color: var(--fg);
}

.input-chapter-item:hover {
  color: var(--fg);
  border-color: var(--accent);
}

.input-chapter-item.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--bg-elev);
}

button.active {
  border-color: var(--accent);
  color: var(--accent);
}



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

.modal-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

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

.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.artifact-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  gap: 1rem;
  flex-wrap: wrap;
}

.artifact-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  flex: 1;
}

.artifact-name {
  font-weight: 500;
  word-break: break-all;
}

.artifact-meta {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
  font-size: 0.85rem;
}

.artifact-badge {
  padding: 0.15rem 0.4rem;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.artifact-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

</style>
