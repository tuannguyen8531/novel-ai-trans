<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'
import { api } from '@/api/client'
import type { NovelChapterStatus } from '@/api/types'
import GlossaryEditor from '@/components/GlossaryEditor.vue'
import JobMonitor from '@/components/JobMonitor.vue'
import placeholderCover from '@/assets/placeholder-cover.png'

const props = defineProps<{ name: string }>()
const route = useRoute()
const router = useRouter()
const novels = useNovelsStore()
const tab = ref<'chapters' | 'translated' | 'glossary' | 'artifacts'>('chapters')
const chapters = ref<NovelChapterStatus[]>([])
const reading = ref<{ chapter: number; content: string; view: 'source' | 'translation'; target: 'vi' | 'en' } | null>(null)
const target = ref<'vi' | 'en'>('vi')
const selectedChapters = ref<Record<'vi' | 'en', string>>({ vi: '', en: '' })
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
const metaTranslatedVi = ref<string>('')
const metaTranslatedEn = ref<string>('')
const metaError = ref<string | null>(null)
const showMetaForm = ref<boolean>(false)
const coverBroken = ref<boolean>(false)

const inputReading = ref<{ chapter: number; content: string; editing: boolean; editContent: string } | null>(null)
const inputSaving = ref(false)
const inputError = ref<string | null>(null)

const inputPage = ref(1)
const inputPerPage = 100
const inputAscending = ref(true)

const showAddModal = ref(false)
const addChapterNumber = ref<number | null>(null)
const addChapterContent = ref('')
const addChapterSaving = ref(false)
const addChapterError = ref<string | null>(null)
const addModalCard = ref<HTMLElement | null>(null)
let addPreviousFocus: HTMLElement | null = null

const showDeleteModal = ref(false)
const deleteChapterNumber = ref<number | null>(null)
const deleteChapterSaving = ref(false)
const deleteChapterError = ref<string | null>(null)
const deleteModalCard = ref<HTMLElement | null>(null)
let deletePreviousFocus: HTMLElement | null = null

const novelName = computed(() => props.name || String(route.params.name || ''))

const inputChapterNumbers = computed(() => {
  const sources = new Set<number>()
  for (const status of chapters.value) {
    if (status.has_source) sources.add(status.number)
  }
  const sorted = [...sources].sort((a, b) => a - b)
  return inputAscending.value ? sorted : sorted.reverse()
})

const inputTotalPages = computed(() => Math.max(1, Math.ceil(inputChapterNumbers.value.length / inputPerPage)))

const pagedInputChapters = computed(() => {
  const start = (inputPage.value - 1) * inputPerPage
  return inputChapterNumbers.value.slice(start, start + inputPerPage)
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

watch(inputChapterNumbers, () => {
  if (inputPage.value > inputTotalPages.value) {
    inputPage.value = inputTotalPages.value
  }
})

onMounted(async () => {
  await novels.load(novelName.value)
  chapters.value = await api.listChapters(novelName.value)
  await loadMetadata()
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
    const translated = (inner.translated as Record<string, string | null> | undefined) ?? {}
    metaTranslatedVi.value = translated.vi ?? ''
    metaTranslatedEn.value = translated.en ?? ''
  } catch (err) {
    metadata.value = null
    metadataError.value = (err as Error).message
  } finally {
    metadataLoading.value = false
  }
}

watch(
  [metaTitle, () => novels.detail?.title],
  ([meta, detail]) => {
    const original = meta.trim() || (detail ? String(detail) : '') || novelName.value
    document.title = `${original} — Novel AI Translation`
  },
  { immediate: true }
)

async function saveMetadata() {
  metaError.value = null
  const patch: Record<string, unknown> = {
    title: metaTitle.value.trim(),
    author: metaAuthor.value.trim(),
    source_url: metaSourceUrl.value.trim(),
    illustration_url: metaIllustrationUrl.value.trim()
  }
  const translated: Record<string, string | null> = {}
  const currentTranslated = (metadata.value?.translated as Record<string, string | null> | undefined) ?? {}
  const viValue = metaTranslatedVi.value.trim()
  const enValue = metaTranslatedEn.value.trim()
  if (viValue) translated.vi = viValue
  else if (viValue === '' && currentTranslated.vi) translated.vi = null
  if (enValue) translated.en = enValue
  else if (enValue === '' && currentTranslated.en) translated.en = null
  if (Object.keys(translated).length) patch.translated = translated
  try {
    await api.patchNovelMetadata(novelName.value, patch)
    await loadMetadata()
    await novels.load(novelName.value)
    showMetaForm.value = false
  } catch (err) {
    metaError.value = (err as Error).message
  }
}

async function openChapter(chapter: number, view: 'source' | 'translation', openTarget: 'vi' | 'en' = target.value) {
  const response = await api.getChapterContent(novelName.value, chapter, view, openTarget)
  reading.value = { chapter, content: response.content, view, target: openTarget }
}

function translatedChapters(forTarget: 'vi' | 'en'): NovelChapterStatus[] {
  return chapters.value.filter(
    (status) => status.target === forTarget && status.has_translation
  )
}

function chaptersForTarget(forTarget: 'vi' | 'en'): NovelChapterStatus[] {
  return chapters.value.filter(
    (status) => status.target === forTarget && status.has_translation
  )
}

async function selectChapter(forTarget: 'vi' | 'en', event: Event) {
  const value = (event.target as HTMLSelectElement).value
  selectedChapters.value[forTarget] = value
  if (!value) return

  const status = chaptersForTarget(forTarget).find((chapter) => chapter.number === Number(value))
  if (status?.has_translation) {
    await openChapter(status.number, 'translation', forTarget)
  }
}

const totalChapters = computed(() => inputChapterNumbers.value.length)

function targetLabel(forTarget: 'vi' | 'en'): string {
  return forTarget === 'vi' ? 'Vietnamese (vi)' : 'English (en)'
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
      metaTranslatedVi.value.trim() ||
      metaTranslatedEn.value.trim()
  )
)

const coverSrc = computed(() => {
  if (coverBroken.value) return placeholderCover
  const url = metaIllustrationUrl.value.trim()
  return url || placeholderCover
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
  } catch (err) {
    packError.value = (err as Error).message
  }
}

const showSource = ref(false)
const sourceContent = ref('')
const sourceLoading = ref(false)
const sourceError = ref<string | null>(null)
let sourceRequestId = 0

async function fetchSourceContent() {
  if (!reading.value) return
  const chapter = reading.value.chapter
  const requestId = ++sourceRequestId
  sourceLoading.value = true
  sourceError.value = null
  try {
    const response = await api.getChapterContent(novelName.value, chapter, 'source')
    if (requestId === sourceRequestId && reading.value?.chapter === chapter) {
      sourceContent.value = response.content
    }
  } catch (err) {
    if (requestId === sourceRequestId) {
      sourceError.value = (err as Error).message
    }
  } finally {
    if (requestId === sourceRequestId) {
      sourceLoading.value = false
    }
  }
}

watch(() => reading.value?.chapter, async (newCh) => {
  sourceRequestId += 1
  sourceContent.value = ''
  sourceError.value = null
  sourceLoading.value = false
  if (newCh && showSource.value) {
    await fetchSourceContent()
  }
})

watch(showSource, async (val) => {
  if (val && !sourceContent.value && reading.value) {
    await fetchSourceContent()
  } else if (!val) {
    sourceRequestId += 1
    sourceLoading.value = false
  }
})

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

onUnmounted(() => {
  document.body.style.overflow = ''
})

async function confirmAddChapter() {
  if (addChapterNumber.value === null) return
  addChapterError.value = null
  addChapterSaving.value = true
  try {
    await api.putChapterContent(novelName.value, addChapterNumber.value, addChapterContent.value)
    chapters.value = await api.listChapters(novelName.value)
    const newPage = Math.ceil(
      inputChapterNumbers.value.indexOf(addChapterNumber.value) / inputPerPage + 1
    )
    if (newPage > 0) inputPage.value = newPage
    closeAddModal()
    await openInputChapter(addChapterNumber.value)
    if (inputReading.value) {
      inputReading.value.editing = true
      inputReading.value.editContent = addChapterContent.value
    }
  } catch (err) {
    addChapterError.value = (err as Error).message
  } finally {
    addChapterSaving.value = false
  }
}

function openDeleteModal() {
  if (!inputReading.value) return
  deleteChapterError.value = null
  deleteChapterNumber.value = inputReading.value.chapter
  showDeleteModal.value = true
}

function closeDeleteModal() {
  if (deleteChapterSaving.value) return
  showDeleteModal.value = false
  deletePreviousFocus?.focus()
  deletePreviousFocus = null
}

function handleDeleteModalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeDeleteModal()
    return
  }
  if (event.key !== 'Tab' || !deleteModalCard.value) return
  const focusable = Array.from(
    deleteModalCard.value.querySelectorAll<HTMLElement>(
      'button:not(:disabled), [href], input:not(:disabled), [tabindex]:not([tabindex="-1"])'
    )
  )
  if (!focusable.length) {
    event.preventDefault()
    deleteModalCard.value.focus()
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

watch(showDeleteModal, (isOpen) => {
  if (isOpen) {
    deletePreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => deleteModalCard.value?.focus())
  } else {
    document.body.style.overflow = ''
  }
})

async function confirmDeleteChapter() {
  if (deleteChapterNumber.value === null) return
  deleteChapterError.value = null
  deleteChapterSaving.value = true
  try {
    await api.deleteChapter(novelName.value, deleteChapterNumber.value)
    if (inputReading.value?.chapter === deleteChapterNumber.value) {
      inputReading.value = null
    }
    chapters.value = await api.listChapters(novelName.value)
    closeDeleteModal()
  } catch (err) {
    deleteChapterError.value = (err as Error).message
  } finally {
    deleteChapterSaving.value = false
  }
}
</script>

<template>
  <section class="flex-col gap-3">
    <div v-if="novels.error" class="card error">{{ novels.error }}</div>
    <div v-else-if="novels.detail" class="flex-col gap-3">
      <div class="card">
        <div class="novel-cover-row">
          <img class="novel-cover" :src="coverSrc" :alt="`Cover for ${novels.detail.title ?? novelName}`" @error="onCoverError" />
          <div class="novel-cover-info">
            <h2>{{ novels.detail.title ?? novelName }}</h2>
            <p class="muted">
              <span v-if="novels.detail.author">by {{ novels.detail.author }} · </span>
              <code>{{ novelName }}</code>
            </p>
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
          <div class="meta-row">
            <span class="meta-label">Slug</span>
            <span><code>{{ novelName }}</code></span>
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

          <div v-if="showPackForm" class="pack-form">
            <div class="pack-target">
              <label for="pack-target-language">Target language</label>
              <select id="pack-target-language" v-model="target">
                <option value="vi">Vietnamese (vi)</option>
                <option value="en">English (en)</option>
              </select>
            </div>
            <div>
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
            <div v-if="packFormats.pdf">
              <label>PDF options</label>
              <div class="check-row">
                <label class="check">
                  <input v-model="packDarkMode" type="checkbox" />
                  <span>Dark mode (dark background, light text)</span>
                </label>
              </div>
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
            <div class="row gap-2" style="margin-top: 0.5rem;">
              <button type="button" @click="startPack">Start pack</button>
            </div>
          <p v-if="packError" class="error" style="margin-top: 0.5rem;">{{ packError }}</p>
        </div>

        <div v-if="showMetaForm" class="pack-form" style="margin-top: 0.5rem;">
          <p v-if="metadataLoading" class="muted">Loading metadata…</p>
          <p v-else-if="metadataError" class="error">Failed to load metadata: {{ metadataError }}</p>
          <p v-else-if="!metadata" class="muted">No metadata.json yet. Fill in the fields below and save to create one.</p>
          <div>
            <label>Original title</label>
            <input v-model="metaTitle" placeholder="원제목 / タイトル / title" />
          </div>
          <div>
            <label>Author</label>
            <input v-model="metaAuthor" placeholder="author name" />
          </div>
          <div>
            <label>Source URL</label>
            <input v-model="metaSourceUrl" placeholder="https://..." />
          </div>
          <div>
            <label>Cover image URL</label>
            <input v-model="metaIllustrationUrl" placeholder="https://... (optional)" />
          </div>
          <div class="pack-meta">
            <div>
              <label>Translated title — vi</label>
              <input v-model="metaTranslatedVi" placeholder="Tiêu đề tiếng Việt" />
            </div>
            <div>
              <label>Translated title — en</label>
              <input v-model="metaTranslatedEn" placeholder="English title" />
            </div>
          </div>
          <div class="row gap-2" style="margin-top: 0.5rem;">
            <button type="button" @click="saveMetadata">Save metadata</button>
            <button class="secondary" type="button" @click="loadMetadata">Revert</button>
          </div>
          <p v-if="metaError" class="error" style="margin-top: 0.5rem;">{{ metaError }}</p>
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
            id="translated-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'translated'"
            aria-controls="translated-panel"
            @click="tab = 'translated'"
          >
            Translated
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
        </nav>

        <div
          v-if="tab === 'chapters'"
          id="chapters-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="chapters-tab"
        >
          <div class="row gap-2" style="justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <h3 style="margin: 0;">Input Chapters</h3>
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
          <p v-if="inputError" class="error" style="margin-top: 0.5rem;">{{ inputError }}</p>
          <p v-if="!inputChapterNumbers.length" class="muted" style="margin-top: 0.5rem;">No input chapters yet.</p>
          <div v-else class="input-chapter-container">
            <div class="input-chapter-list">
              <button
                v-for="num in pagedInputChapters"
                :key="num"
                type="button"
                class="input-chapter-item"
                :class="{ active: inputReading?.chapter === num }"
                @click="openInputChapter(num)"
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

          <div v-if="inputReading" class="chapter-reader">
            <div class="row gap-3" style="justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap;">
              <h4 style="margin: 0;">Chapter {{ inputReading.chapter }}</h4>
              <div class="row gap-2" style="align-items: center;">
                <template v-if="!inputReading.editing">
                  <button type="button" class="secondary" @click="startEditInput">Edit</button>
                  <button type="button" class="secondary danger" @click="openDeleteModal">Delete</button>
                </template>
                <template v-else>
                  <button type="button" :disabled="inputSaving" @click="saveInputChapter">
                    {{ inputSaving ? 'Saving...' : 'Save' }}
                  </button>
                  <button type="button" class="secondary" :disabled="inputSaving" @click="cancelEditInput">Cancel</button>
                </template>
              </div>
            </div>
            <textarea
              v-if="inputReading.editing"
              v-model="inputReading.editContent"
              class="chapter-edit-area"
            ></textarea>
            <pre v-else class="chapter-content">{{ inputReading.content || 'Empty chapter.' }}</pre>
          </div>
        </div>

        <div
          v-else-if="tab === 'translated'"
          id="translated-panel"
          class="detail-tab-panel chapter-browser"
          role="tabpanel"
          aria-labelledby="translated-tab"
        >
          <div class="chapter-language-grid">
            <section v-for="target in (['vi', 'en'] as const)" :key="target" class="chapter-language-section">
              <header class="chapter-section-header">
                <h3>{{ targetLabel(target) }}</h3>
                <span class="muted">
                  {{ translatedChapters(target).length }} translated
                  <template v-if="totalChapters">
                    · {{ totalChapters }} total
                  </template>
                </span>
              </header>

              <label :for="`chapter-select-${target}`">Chapter</label>
              <select
                :id="`chapter-select-${target}`"
                :value="selectedChapters[target]"
                @change="selectChapter(target, $event)"
              >
                <option value="" disabled>Select a translated chapter</option>
                <option
                  v-for="status in chaptersForTarget(target)"
                  :key="`${status.number}-${status.target}`"
                  :value="status.number"
                >
                  Chapter {{ status.number }}
                </option>
              </select>
            </section>
          </div>

          <div v-if="reading" class="chapter-reader">
            <div class="row gap-3" style="justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap;">
              <h4 style="margin: 0;">Chapter {{ reading.chapter }} — {{ targetLabel(reading.target ?? 'vi') }} translation</h4>
              <label class="check" style="margin: 0; padding: 0.25rem 0.5rem; background: var(--bg-elev-2); border: 1px solid var(--border);">
                <input v-model="showSource" type="checkbox" />
                <span>Show original chapter</span>
              </label>
            </div>
            <pre class="chapter-content">{{ reading.content }}</pre>

            <div v-if="showSource" class="source-comparison" style="margin-top: 1rem; border-top: 1px dashed var(--border); padding-top: 1rem;">
              <h5 style="margin-top: 0; margin-bottom: 0.5rem;">Source Chapter</h5>
              <div v-if="sourceLoading" class="preview-spinner" style="padding: 1.5rem; text-align: center; color: var(--fg-dim);">
                <p>Loading original content...</p>
              </div>
              <p v-else-if="sourceError" class="error">Failed to load original chapter: {{ sourceError }}</p>
              <pre v-else class="chapter-content source-content" style="background: var(--bg-elev-2); opacity: 0.85; border-left: 3px solid var(--accent);">{{ sourceContent || 'Original chapter is empty.' }}</pre>
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
          v-else-if="novels.detail"
          id="artifacts-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="artifacts-tab"
        >
          <h3>Artifacts</h3>
          <p v-if="artifactError" class="error">{{ artifactError }}</p>
          <p v-if="!novels.detail.artifacts.length" class="muted">No artifacts yet.</p>
          <ul v-else>
            <li v-for="name in novels.detail.artifacts" :key="name">
              <button class="secondary" type="button" @click="downloadArtifact(name)">{{ name }}</button>
            </li>
          </ul>
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

    <div v-if="showDeleteModal" class="modal-overlay">
      <div
        ref="deleteModalCard"
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-chapter-title"
        tabindex="-1"
        @keydown="handleDeleteModalKeydown"
      >
        <header class="modal-header">
          <h3 id="delete-chapter-title">Delete Chapter</h3>
          <button
            type="button"
            class="modal-close"
            aria-label="Close"
            :disabled="deleteChapterSaving"
            @click="closeDeleteModal"
          >&times;</button>
        </header>
        <div class="modal-body">
          <p v-if="deleteChapterError" class="error">{{ deleteChapterError }}</p>
          <div class="delete-warning">
            <p><strong>Warning:</strong> You are about to delete <strong>Chapter {{ deleteChapterNumber }}</strong> from the input chapters.</p>
            <p>This action will:</p>
            <ul>
              <li>Permanently delete the source chapter file</li>
              <li>Not delete any translated chapters (they will become orphaned)</li>
              <li>Cannot be undone</li>
            </ul>
            <p>Are you sure you want to continue?</p>
          </div>
        </div>
        <footer class="modal-footer">
          <button type="button" class="secondary" :disabled="deleteChapterSaving" @click="closeDeleteModal">Cancel</button>
          <button
            type="button"
            class="danger"
            :disabled="deleteChapterSaving"
            @click="confirmDeleteChapter"
          >{{ deleteChapterSaving ? 'Deleting...' : 'Delete' }}</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<style scoped>
.actions-row {
  margin: 1.25rem 0 1rem 0;
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

.novel-cover-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.novel-cover {
  width: 180px;
  height: auto;
  max-height: 270px;
  object-fit: cover;
  border-radius: var(--radius);
  background: var(--bg-elev-2);
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

.novel-cover-info {
  flex: 1 1 18rem;
  min-width: 0;
  font-size: 1.1rem;
}

.novel-cover-info h2 {
  margin-top: 0;
  font-size: 1.6rem;
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

.chapter-section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}

.chapter-section-header h3 {
  margin: 0;
}

.chapter-language-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.chapter-reader {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.chapter-reader h4 {
  margin-top: 0;
}

.chapter-content {
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  max-height: 24rem;
  overflow: auto;
  white-space: pre-wrap;
  font-family: var(--font);
  font-size: 1rem;
  line-height: 1.6;
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
  display: flex;
  flex-wrap: wrap;
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
  max-height: 18rem;
  overflow-y: auto;
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

@media (max-width: 700px) {
  .chapter-language-grid {
    grid-template-columns: 1fr;
  }
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
}

.modal-header h3 {
  margin: 0;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--fg-dim);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.modal-close:hover {
  color: var(--fg);
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

.delete-warning {
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
}

.delete-warning p {
  margin: 0.5rem 0;
}

.delete-warning ul {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.delete-warning li {
  margin: 0.25rem 0;
}
</style>
