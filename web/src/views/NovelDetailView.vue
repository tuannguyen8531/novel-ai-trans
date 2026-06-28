<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNovelsStore } from '@/stores/novels'
import { api } from '@/api/client'
import type { NovelChapterStatus } from '@/api/types'
import GlossaryEditor from '@/components/GlossaryEditor.vue'
import JobMonitor from '@/components/JobMonitor.vue'

const props = defineProps<{ name: string }>()
const route = useRoute()
const router = useRouter()
const novels = useNovelsStore()
const tab = ref<'chapters' | 'glossary' | 'artifacts'>('chapters')
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

const novelName = computed(() => props.name || String(route.params.name || ''))

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
  return chapters.value.filter((status) => status.target === forTarget)
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

const totalChapters = computed(() => {
  const sources = new Set<number>()
  for (const status of chapters.value) {
    if (status.has_source) sources.add(status.number)
  }
  return sources.size
})

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
</script>

<template>
  <section class="flex-col gap-3">
    <div v-if="novels.error" class="card error">{{ novels.error }}</div>
    <div v-else-if="novels.detail" class="flex-col gap-3">
      <div class="card">
        <h2>{{ novels.detail.title ?? novelName }}</h2>
        <p class="muted">
          <span v-if="novels.detail.author">by {{ novels.detail.author }} · </span>
          <code>{{ novelName }}</code>
        </p>
        <div class="stats-row" style="margin-top: 0.5rem;">
          <span><span class="muted">Total:</span> <strong>{{ novels.detail.total_input_chapters }}</strong></span>
          <template v-for="t in novels.detail.targets" :key="t.target">
            <span>
              <span class="muted">{{ t.target.toUpperCase() }}:</span>&nbsp;
              <strong>{{ t.completed }}<span class="muted">/{{ t.total }}</span></strong>
              <span v-if="t.failed > 0" class="badge danger">{{ t.failed }} failed</span>
            </span>
          </template>
          <span>
            <span class="muted">Glossary:</span>
            {{ novels.detail.glossary_terms }}<span class="muted"> terms,</span> {{ novels.detail.glossary_entities }}<span class="muted"> entities</span>
          </span>
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
          <div class="meta-row" v-if="metaIllustrationUrl">
            <span class="meta-label">Cover</span>
            <span class="muted">{{ metaIllustrationUrl }}</span>
          </div>
          <p v-if="metadataError" class="error meta-empty">Failed to load metadata: {{ metadataError }}</p>
          <p v-else-if="!hasAnyMetadata" class="muted meta-empty">
            No metadata fields filled in yet — click <strong>Edit metadata</strong> to add some.
          </p>
        </div>
        <div class="actions-row">
          <div class="row gap-2" style="align-items: center;">
            <button type="button" class="secondary" @click="showPackForm = !showPackForm">
              {{ showPackForm ? 'Hide pack options' : 'Pack options' }}
            </button>
            <button type="button" class="secondary" @click="showMetaForm = !showMetaForm">
              {{ showMetaForm ? 'Close metadata editor' : 'Edit metadata' }}
            </button>
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
          class="detail-tab-panel chapter-browser"
          role="tabpanel"
          aria-labelledby="chapters-tab"
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
                  :disabled="!status.has_translation"
                >
                  Chapter {{ status.number }} — {{ status.has_translation ? 'Translated' : 'Not translated' }}
                </option>
              </select>
            </section>
          </div>

          <div v-if="reading" class="chapter-reader">
            <h4>Chapter {{ reading.chapter }} — {{ targetLabel(reading.target ?? 'vi') }} translation</h4>
            <pre class="chapter-content">{{ reading.content }}</pre>
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
  </section>
</template>

<style scoped>
.stats-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1.25rem;
  font-size: 0.95rem;
}

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
  padding: 1rem;
  max-height: 24rem;
  overflow: auto;
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.85rem;
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
</style>
