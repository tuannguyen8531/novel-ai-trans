import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/api/client'
import type { NovelSummary } from '@/api/types'
import { useNovelsStore } from '@/composables/novels'

export function useTranslation() {
  const novels = useNovelsStore()
  const route = useRoute()
  const novel = ref('')
  const target = ref('vi')
  const source = ref('')
  const provider = ref('')
  const start = ref(0)
  const end = ref(0)
  const limit = ref(0)
  const force = ref(false)
  const resume = ref(false)
  const failedOnly = ref(false)
  const review = ref(false)
  const summary = ref(false)
  const translateMetadata = ref(false)
  const jobId = ref<string | null>(null)
  const error = ref<string | null>(null)
  const novelOptions = computed(() => novels.novels)

  function syncSourceLanguage(novelName: string) {
    const language = novels.novels.find((item) => item.name === novelName)?.source_language ?? ''
    source.value = ({ zh: 'chinese', ja: 'japanese', ko: 'korean' } as Record<string, string>)[language] ?? language
  }

  function remainingChapters(item: NovelSummary): number {
    const progress = item.targets.find((entry) => entry.target === target.value)
    return Math.max(0, item.total_input_chapters - (progress?.completed ?? 0))
  }

  async function startTranslation() {
    error.value = null
    if (!novel.value) {
      error.value = 'Choose a novel.'
      return
    }
    const payload: Record<string, unknown> = {
      novel: novel.value,
      target_language: target.value,
      start_chapter: start.value,
      end_chapter: end.value,
      limit: limit.value,
      force: force.value,
      resume: resume.value,
      failed_only: failedOnly.value,
      enable_review: review.value,
      enable_summary: summary.value,
      translate_metadata: translateMetadata.value,
      force_metadata: translateMetadata.value
    }
    if (source.value) payload.source_language = source.value
    if (provider.value) payload.provider = provider.value
    try {
      jobId.value = (await api.startTranslate(payload)).job_id
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  onMounted(async () => {
    if (typeof route.query.novel === 'string') novel.value = route.query.novel
    await novels.refresh()
    syncSourceLanguage(novel.value)
  })
  watch(novel, syncSourceLanguage)

  return {
    novel, target, source, provider, start, end, limit, force, resume, failedOnly, review,
    summary, translateMetadata, jobId, error, novelOptions, remainingChapters,
    startTranslation
  }
}
