import { onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import type { ConfigSummary, DraftDetail, DraftSummary } from '@/api/types'
import { useJobsStore } from '@/composables/jobs'

export function useCrawl() {
  const jobs = useJobsStore()
  const activeTab = ref<'crawl' | 'generate'>('crawl')
  const configs = ref<ConfigSummary[]>([])
  const configsError = ref<string | null>(null)
  const loadingConfigs = ref(false)
  const selectedConfigText = ref('')
  const selectedConfigError = ref<string | null>(null)
  const loadingSelectedConfig = ref(false)
  const savingSelectedConfig = ref(false)
  const selectedConfigMessage = ref<string | null>(null)
  let selectedConfigRequest = 0

  const selectedConfig = ref('')
  const browser = ref(false)
  const headed = ref(false)
  const ignoreRobots = ref(false)
  const overwrite = ref(false)
  const workers = ref(1)
  const maxChapters = ref<number | null>(null)
  const crawlError = ref<string | null>(null)
  const crawlJobId = ref<string | null>(null)

  const generateUrl = ref('')
  const generateName = ref('')
  const generateProvider = ref('')
  const generateUseBrowser = ref(false)
  const generateHeaded = ref(false)
  const generateNoCache = ref(false)
  const generateIgnoreSample = ref(false)
  const generateError = ref<string | null>(null)
  const generateJobId = ref<string | null>(null)
  const generatedDraft = ref<DraftDetail | null>(null)
  const draftConfigText = ref('')
  const drafts = ref<DraftSummary[]>([])
  const draftsError = ref<string | null>(null)
  const loadingDrafts = ref(false)

  function selectBrowserMode(mode: 'headless' | 'headed') {
    browser.value = mode === 'headless'
    headed.value = mode === 'headed'
  }

  function selectGenerateBrowserMode(mode: 'headless' | 'headed') {
    generateUseBrowser.value = mode === 'headless'
    generateHeaded.value = mode === 'headed'
  }

  async function loadConfigs() {
    loadingConfigs.value = true
    configsError.value = null
    try {
      configs.value = await api.listConfigs()
      if (configs.value.length && !selectedConfig.value) selectedConfig.value = configs.value[0].name
    } catch (err) {
      configsError.value = (err as Error).message
    } finally {
      loadingConfigs.value = false
    }
  }

  async function loadSelectedConfig(name: string) {
    const request = ++selectedConfigRequest
    selectedConfigText.value = ''
    selectedConfigError.value = null
    selectedConfigMessage.value = null
    if (!name) return
    loadingSelectedConfig.value = true
    try {
      const detail = await api.getConfig(name)
      if (request === selectedConfigRequest) selectedConfigText.value = JSON.stringify(detail, null, 2)
    } catch (err) {
      if (request === selectedConfigRequest) selectedConfigError.value = (err as Error).message
    } finally {
      if (request === selectedConfigRequest) loadingSelectedConfig.value = false
    }
  }

  function parseConfigDocument(text: string): Record<string, unknown> {
    const parsed: unknown = JSON.parse(text)
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('Config must be a JSON object.')
    }
    return parsed as Record<string, unknown>
  }

  async function saveSelectedConfig() {
    if (!selectedConfig.value) return
    selectedConfigError.value = null
    selectedConfigMessage.value = null
    let parsed: Record<string, unknown>
    try {
      parsed = parseConfigDocument(selectedConfigText.value)
    } catch (err) {
      selectedConfigError.value = `Invalid JSON: ${(err as Error).message}`
      return
    }
    savingSelectedConfig.value = true
    try {
      await api.saveConfig(selectedConfig.value, parsed)
      selectedConfigMessage.value = 'Config validated and saved.'
      await loadConfigs()
    } catch (err) {
      selectedConfigError.value = (err as Error).message
    } finally {
      savingSelectedConfig.value = false
    }
  }

  async function startCrawl() {
    crawlError.value = null
    if (!selectedConfig.value) {
      crawlError.value = 'Choose a novel config.'
      return
    }
    try {
      const payload: Record<string, unknown> = {
        novel: selectedConfig.value,
        browser: browser.value,
        headed: headed.value,
        ignore_robots: ignoreRobots.value,
        overwrite: overwrite.value,
        workers: workers.value
      }
      if (maxChapters.value !== null && maxChapters.value > 0) payload.max_chapters = maxChapters.value
      crawlJobId.value = (await api.startCrawl(payload)).job_id
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
      generateJobId.value = (await api.generateConfig(payload)).job_id
    } catch (err) {
      generateError.value = (err as Error).message
    }
  }

  async function loadDraft(draftId: string) {
    generateError.value = null
    try {
      const detail = await api.getDraft(draftId)
      generatedDraft.value = detail
      draftConfigText.value = JSON.stringify(detail.config, null, 2)
    } catch (err) {
      generateError.value = (err as Error).message
    }
  }

  async function loadDrafts() {
    loadingDrafts.value = true
    draftsError.value = null
    try {
      drafts.value = await api.listDrafts()
    } catch (err) {
      draftsError.value = (err as Error).message
    } finally {
      loadingDrafts.value = false
    }
  }

  async function saveGeneratedDraft() {
    if (!generatedDraft.value) return
    let parsed: Record<string, unknown>
    try {
      parsed = parseConfigDocument(draftConfigText.value)
    } catch (err) {
      generateError.value = `Invalid JSON: ${(err as Error).message}`
      return
    }
    try {
      await api.saveConfig(generatedDraft.value.name, parsed, generatedDraft.value.draft_id)
      generateError.value = null
      generatedDraft.value = null
      draftConfigText.value = ''
      await Promise.all([loadConfigs(), loadDrafts()])
    } catch (err) {
      generateError.value = (err as Error).message
    }
  }

  async function deleteDraft(draftId: string) {
    draftsError.value = null
    try {
      await api.deleteDraft(draftId)
      if (generatedDraft.value?.draft_id === draftId) {
        generatedDraft.value = null
        draftConfigText.value = ''
      }
      await loadDrafts()
    } catch (err) {
      draftsError.value = (err as Error).message
    }
  }

  async function discardDraft() {
    if (generatedDraft.value) await deleteDraft(generatedDraft.value.draft_id)
  }

  onMounted(() => void Promise.all([loadConfigs(), loadDrafts()]))
  watch(selectedConfig, (name) => void loadSelectedConfig(name))
  watch(
    () => generateJobId.value ? jobs.findJob(generateJobId.value) : null,
    (job) => {
      const draftId = job?.result?.draft_id
      if (job?.status === 'completed' && typeof draftId === 'string' && generatedDraft.value?.draft_id !== draftId) {
        void loadDraft(draftId).then(loadDrafts)
      }
    },
    { deep: true }
  )

  return {
    activeTab, configs, configsError, loadingConfigs, selectedConfigText, selectedConfigError,
    loadingSelectedConfig, savingSelectedConfig, selectedConfigMessage, selectedConfig, browser, headed,
    ignoreRobots, overwrite, workers,
    maxChapters, crawlError, crawlJobId, generateUrl, generateName, generateProvider,
    generateUseBrowser, generateHeaded, generateNoCache, generateIgnoreSample, generateError,
    generateJobId, generatedDraft, draftConfigText, drafts, draftsError, loadingDrafts,
    selectBrowserMode, selectGenerateBrowserMode, startCrawl, startGenerate, saveSelectedConfig,
    loadSelectedConfig, loadDraft, saveGeneratedDraft, deleteDraft, discardDraft
  }
}
