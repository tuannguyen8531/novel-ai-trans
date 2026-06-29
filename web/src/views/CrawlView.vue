<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { useJobsStore } from '@/stores/jobs'
import type { ConfigSummary, DraftDetail } from '@/api/types'
import JobMonitor from '@/components/JobMonitor.vue'

const router = useRouter()
const jobs = useJobsStore()

const configs = ref<ConfigSummary[]>([])
const configsError = ref<string | null>(null)
const loadingConfigs = ref(false)

// --- Crawl form ---
const configMode = ref<'existing' | 'custom'>('existing')
const selectedConfig = ref<string>('')
const customTarget = ref<string>('')
const browser = ref<boolean>(false)
const headed = ref<boolean>(false)
const ignoreRobots = ref<boolean>(false)
const overwrite = ref<boolean>(false)

function selectBrowserMode(mode: 'headless' | 'headed') {
  if (mode === 'headless') {
    browser.value = true
    headed.value = false
  } else {
    browser.value = false
    headed.value = true
  }
}
const workers = ref<number>(1)
const maxChapters = ref<number | null>(null)
const crawlError = ref<string | null>(null)
const crawlJobId = ref<string | null>(null)

const crawlTarget = computed<string>(() =>
  configMode.value === 'existing' ? selectedConfig.value : customTarget.value.trim()
)

// --- Generate form ---
const generateUrl = ref<string>('')
const generateName = ref<string>('')
const generateProvider = ref<string>('')
const generateUseBrowser = ref<boolean>(false)
const generateHeaded = ref<boolean>(false)
const generateNoCache = ref<boolean>(false)
const generateIgnoreSample = ref<boolean>(false)
const generateError = ref<string | null>(null)
const generateJobId = ref<string | null>(null)
const generatedDraft = ref<DraftDetail | null>(null)
const draftConfigText = ref<string>('')

function selectGenerateBrowserMode(mode: 'headless' | 'headed') {
  if (mode === 'headless') {
    generateUseBrowser.value = true
    generateHeaded.value = false
  } else {
    generateUseBrowser.value = false
    generateHeaded.value = true
  }
}

async function loadConfigs() {
  loadingConfigs.value = true
  configsError.value = null
  try {
    configs.value = await api.listConfigs()
    if (configs.value.length && !selectedConfig.value) {
      selectedConfig.value = configs.value[0].name
    }
  } catch (err) {
    configsError.value = (err as Error).message
  } finally {
    loadingConfigs.value = false
  }
}

onMounted(loadConfigs)

async function startCrawl() {
  crawlError.value = null
  const target = crawlTarget.value
  if (!target) {
    crawlError.value = 'Choose an existing config or enter a custom target.'
    return
  }
  try {
    const payload: Record<string, unknown> = {
      target,
      browser: browser.value,
      headed: headed.value,
      ignore_robots: ignoreRobots.value,
      overwrite: overwrite.value,
      workers: workers.value
    }
    if (maxChapters.value !== null && maxChapters.value > 0) {
      payload.max_chapters = maxChapters.value
    }
    const result = await api.startCrawl(payload)
    crawlJobId.value = result.job_id
  } catch (err) {
    crawlError.value = (err as Error).message
  }
}

async function startGenerate() {
  generateError.value = null
  generatedDraft.value = null
  if (!generateUrl.value.trim()) {
    generateError.value = 'A URL is required.'
    return
  }
  const payload: Record<string, unknown> = {
    url: generateUrl.value.trim(),
    browser: generateUseBrowser.value,
    headed: generateHeaded.value,
    no_cache: generateNoCache.value,
    ignore_sample: generateIgnoreSample.value
  }
  if (generateName.value.trim()) payload.name = generateName.value.trim()
  if (generateProvider.value) payload.provider = generateProvider.value
  try {
    const result = await api.generateConfig(payload)
    generateJobId.value = result.job_id
    jobs.follow(result.job_id)
  } catch (err) {
    generateError.value = (err as Error).message
  }
}

async function loadDraft(draftId: string) {
  try {
    const detail = await api.getDraft(draftId)
    generatedDraft.value = detail
    draftConfigText.value = JSON.stringify(detail.config, null, 2)
  } catch (err) {
    generateError.value = (err as Error).message
  }
}

watch(
  () => {
    if (!generateJobId.value) return null
    return jobs.findJob(generateJobId.value)
  },
  (job) => {
    const draftId = job?.result?.draft_id
    if (job?.status === 'completed' && typeof draftId === 'string' && generatedDraft.value?.draft_id !== draftId) {
      void loadDraft(draftId)
    }
  },
  { deep: true }
)

async function saveGeneratedDraft() {
  if (!generatedDraft.value) return
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(draftConfigText.value)
  } catch (err) {
    generateError.value = `Invalid JSON: ${(err as Error).message}`
    return
  }
  try {
    await api.saveConfig(generatedDraft.value.name, parsed, generatedDraft.value.draft_id)
    generateError.value = null
    generatedDraft.value = null
    draftConfigText.value = ''
    await loadConfigs()
  } catch (err) {
    generateError.value = (err as Error).message
  }
}

function discardDraft() {
  if (generatedDraft.value) {
    api.deleteDraft(generatedDraft.value.draft_id).catch(() => undefined)
  }
  generatedDraft.value = null
  draftConfigText.value = ''
}
</script>

<template>
  <section class="flex-col gap-3">
    <!-- Crawl -->
    <div class="card">
      <h2>Crawl a site</h2>
      <p class="muted">
        Pick a saved config or enter a custom target. The job fetches chapters, writes them into
        the novel input directory, and streams progress live.
      </p>

      <div class="grid">
        <div>
          <label>Config source</label>
          <div class="row gap-1">
            <label class="check" style="flex: 1 1 auto;">
              <input v-model="configMode" type="radio" value="existing" />
              <span>Use existing</span>
            </label>
            <label class="check" style="flex: 1 1 auto;">
              <input v-model="configMode" type="radio" value="custom" />
              <span>Custom target / path</span>
            </label>
          </div>
        </div>

        <div v-if="configMode === 'existing'">
          <label>Config</label>
          <select v-model="selectedConfig" :disabled="!configs.length">
            <option v-if="!configs.length" disabled value="">
              {{ loadingConfigs ? 'Loading…' : 'No configs in configs/' }}
            </option>
            <option v-for="cfg in configs" :key="cfg.name" :value="cfg.name">
              {{ cfg.name }} — {{ cfg.start_url }}
            </option>
          </select>
          <p v-if="configsError" class="error" style="margin-top: 0.25rem;">{{ configsError }}</p>
        </div>

        <div v-else>
          <label>Target</label>
          <input v-model="customTarget" placeholder="e.g. configs/my-novel.json or /abs/path.json" />
        </div>

        <div>
          <label>Browser mode</label>
          <div class="check-row">
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="browser && !headed"
                @change="selectBrowserMode('headless')"
              />
              <span>Headless browser (for JS challenges)</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="headed"
                @change="selectBrowserMode('headed')"
              />
              <span>Headed browser (visible window)</span>
            </label>
          </div>
        </div>

        <div>
          <label>Options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="ignoreRobots" type="checkbox" />
              <span>Ignore robots.txt (only when you have permission)</span>
            </label>
            <label class="check">
              <input v-model="overwrite" type="checkbox" />
              <span>Overwrite already-downloaded chapters</span>
            </label>
          </div>
        </div>

        <div>
          <label>Concurrency &amp; limit</label>
          <div class="row gap-2" style="align-items: center;">
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Workers</span>
              <input v-model.number="workers" type="number" min="1" max="8" style="max-width: 5rem;" />
            </label>
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Max chapters (0 = unlimited)</span>
              <input
                v-model.number="maxChapters"
                type="number"
                min="0"
                placeholder="unlimited"
                style="max-width: 8rem;"
              />
            </label>
          </div>
        </div>
      </div>

      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!crawlTarget" @click="startCrawl">Start crawl</button>
        <button class="secondary" type="button" @click="router.push('/jobs')">View jobs</button>
      </div>
      <p v-if="crawlError" class="error" style="margin-top: 0.5rem;">{{ crawlError }}</p>
    </div>

    <div v-if="crawlJobId" class="card">
      <h3>Crawl job</h3>
      <JobMonitor :job-id="crawlJobId" />
    </div>

    <!-- Generate config -->
    <div class="card">
      <h2>Generate config</h2>
      <p class="muted">
        Provide a table-of-contents URL and the AI will propose a site config. The result is
        saved as a draft; review and edit it, then save to <code>configs/</code>.
      </p>

      <div class="grid">
        <div>
          <label>Table-of-contents URL</label>
          <input v-model="generateUrl" placeholder="https://example.com/novel/table-of-contents" />
        </div>
        <div>
          <label>Config name (optional)</label>
          <input v-model="generateName" placeholder="derived from the URL if blank" />
        </div>
        <div>
          <label>LLM provider (optional)</label>
          <select v-model="generateProvider">
            <option value="">Use default</option>
            <option value="ollama">ollama</option>
            <option value="gemini">gemini</option>
            <option value="openrouter">openrouter</option>
          </select>
        </div>
        <div>
          <label>Browser mode</label>
          <div class="check-row">
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="generateUseBrowser && !generateHeaded"
                @change="selectGenerateBrowserMode('headless')"
              />
              <span>Headless browser (for JS challenges)</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="generateHeaded"
                @change="selectGenerateBrowserMode('headed')"
              />
              <span>Headed browser (visible window)</span>
            </label>
          </div>
        </div>
        <div>
          <label>Generation options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="generateNoCache" type="checkbox" />
              <span>Bypass the HTML cache</span>
            </label>
            <label class="check">
              <input v-model="generateIgnoreSample" type="checkbox" />
              <span>Ignore samples and known-domain configs</span>
            </label>
          </div>
        </div>
      </div>

      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!generateUrl.trim()" @click="startGenerate">Generate</button>
        <button class="secondary" type="button" @click="router.push('/jobs')">View jobs</button>
      </div>
      <p v-if="generateError" class="error" style="margin-top: 0.5rem;">{{ generateError }}</p>
    </div>

    <div v-if="generateJobId" class="card">
      <h3>Generation job</h3>
      <JobMonitor :job-id="generateJobId" />
    </div>

    <!-- Draft review -->
    <div v-if="generatedDraft" class="card">
      <h3>Review draft — <code>{{ generatedDraft.name }}</code></h3>
      <p class="muted">
        Edit the JSON below, then save it to <code>configs/{{ generatedDraft.name }}.json</code>.
        Expires {{ new Date(generatedDraft.expires_at).toLocaleString() }}.
      </p>
      <textarea v-model="draftConfigText" class="draft-editor" spellcheck="false"></textarea>
      <div class="row gap-2" style="margin-top: 0.75rem;">
        <button type="button" @click="saveGeneratedDraft">Save to configs/</button>
        <button class="danger" type="button" @click="discardDraft">Discard draft</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.draft-editor {
  min-height: 22rem;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.85rem;
  line-height: 1.4;
  background: var(--bg-elev-2);
}
</style>
