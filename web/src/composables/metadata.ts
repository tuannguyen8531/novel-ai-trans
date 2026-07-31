import { computed, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'
import { useNovelsStore } from '@/composables/novels'

export type TargetLanguage = 'vi' | 'en'

export interface MetadataDisplay {
  exists: boolean
  loadError: string | null
  title: string
  author: string
  sourceLanguage: string
  genres: string[]
  summary: string
  targetTitle: string
  targetSummary: string
  illustrationSrc: string | null
  hasAny: boolean
}

export function useMetadata(
  novel: MaybeRefOrGetter<string>,
  targetLanguage: MaybeRefOrGetter<TargetLanguage>
) {
  const novels = useNovelsStore()
  const metadata = ref<Record<string, unknown> | null>(null)
  const loading = ref(false)
  const loadError = ref<string | null>(null)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const title = ref('')
  const author = ref('')
  const sourceUrl = ref('')
  const illustrationUrl = ref('')
  const summary = ref('')
  const sourceLanguage = ref('')
  const genreCatalog = ref<Record<string, string[]>>({})
  const genreLoading = ref(false)
  const genreLoadError = ref<string | null>(null)
  const genres = ref<string[]>([])
  const translatedVi = ref('')
  const translatedEn = ref('')
  const summaryVi = ref('')
  const summaryEn = ref('')
  const force = ref(false)
  const coverFile = ref<File | null>(null)
  const coverPreviewUrl = ref<string | null>(null)

  function setCoverFile(file: File | null) {
    if (coverPreviewUrl.value) URL.revokeObjectURL(coverPreviewUrl.value)
    coverFile.value = file
    coverPreviewUrl.value = file ? URL.createObjectURL(file) : null
  }

  onScopeDispose(() => setCoverFile(null))

  const targetTitle = computed({
    get: () => toValue(targetLanguage) === 'vi' ? translatedVi.value : translatedEn.value,
    set: (value: string) => {
      if (toValue(targetLanguage) === 'vi') translatedVi.value = value
      else translatedEn.value = value
    }
  })

  const targetSummary = computed({
    get: () => toValue(targetLanguage) === 'vi' ? summaryVi.value : summaryEn.value,
    set: (value: string) => {
      if (toValue(targetLanguage) === 'vi') summaryVi.value = value
      else summaryEn.value = value
    }
  })

  const availableGenres = computed(() => genreCatalog.value[sourceLanguage.value] ?? [])

  watch([sourceLanguage, genreCatalog, genreLoading, genreLoadError], () => {
    if (genreLoading.value || genreLoadError.value || !Object.keys(genreCatalog.value).length) return
    const available = new Set(availableGenres.value)
    genres.value = genres.value.filter((genre) => available.has(genre))
  })

  const hasAny = computed(() => Boolean(
    title.value.trim() ||
    author.value.trim() ||
    sourceUrl.value.trim() ||
    illustrationUrl.value.trim() ||
    coverFile.value ||
    summary.value.trim() ||
    sourceLanguage.value.trim() ||
    genres.value.length ||
    translatedVi.value.trim() ||
    translatedEn.value.trim() ||
    summaryVi.value.trim() ||
    summaryEn.value.trim()
  ))

  const illustrationSrc = computed(() => {
    if (coverPreviewUrl.value) return coverPreviewUrl.value
    const value = illustrationUrl.value.trim()
    if (!value) return null
    if (value.startsWith('http://') || value.startsWith('https://') || value.startsWith('data:')) {
      return value
    }
    if (/^(?:illustrations\/)?cover\.(?:gif|jpe?g|png|webp)$/i.test(value)) {
      return api.coverUrl(toValue(novel))
    }
    return api.illustrationUrl(toValue(novel), value)
  })

  const display = computed<MetadataDisplay>(() => ({
    exists: metadata.value !== null,
    loadError: loadError.value,
    title: title.value,
    author: author.value,
    sourceLanguage: sourceLanguage.value,
    genres: [...genres.value],
    summary: summary.value,
    targetTitle: targetTitle.value,
    targetSummary: targetSummary.value,
    illustrationSrc: illustrationSrc.value,
    hasAny: hasAny.value
  }))

  async function loadGenreCatalog() {
    genreLoading.value = true
    genreLoadError.value = null
    try {
      genreCatalog.value = await api.getGenres()
    } catch (err) {
      genreLoadError.value = (err as Error).message
    } finally {
      genreLoading.value = false
    }
  }

  async function load() {
    setCoverFile(null)
    loading.value = true
    loadError.value = null
    const genreRequest = loadGenreCatalog()
    try {
      const response = await api.getNovelMetadata(toValue(novel))
      const inner = (response.data as Record<string, unknown>) ?? {}
      metadata.value = Object.keys(inner).length ? inner : null
      title.value = (inner.title as string) ?? ''
      author.value = (inner.author as string) ?? ''
      sourceUrl.value = (inner.source_url as string) ?? ''
      illustrationUrl.value = (inner.illustration_url as string) ?? ''
      summary.value = (inner.summary as string) ?? ''
      sourceLanguage.value = (inner.source_language as string) ?? ''
      genres.value = Array.isArray(inner.genres)
        ? inner.genres.filter((genre): genre is string => typeof genre === 'string')
        : []
      const localized = (inner.localized as Record<string, Record<string, string | null>> | undefined) ?? {}
      translatedVi.value = localized.vi?.title ?? ''
      translatedEn.value = localized.en?.title ?? ''
      summaryVi.value = localized.vi?.summary ?? ''
      summaryEn.value = localized.en?.summary ?? ''
    } catch (err) {
      metadata.value = null
      loadError.value = (err as Error).message
    } finally {
      loading.value = false
    }
    await genreRequest
  }

  async function save(): Promise<boolean> {
    error.value = null
    saving.value = true
    const patch: Record<string, unknown> = {
      title: title.value.trim(),
      author: author.value.trim(),
      source_url: sourceUrl.value.trim(),
      summary: summary.value.trim(),
      source_language: sourceLanguage.value.trim() || null,
      genres: genres.value
    }
    if (!coverFile.value) patch.illustration_url = illustrationUrl.value.trim()
    const currentLocalized = (
      metadata.value?.localized as Record<string, Record<string, string | null>> | undefined
    ) ?? {}
    const localized: Record<string, Record<string, string | null>> = {}
    for (const [language, localizedTitle, localizedSummary] of [
      ['vi', translatedVi.value.trim(), summaryVi.value.trim()],
      ['en', translatedEn.value.trim(), summaryEn.value.trim()]
    ] as const) {
      const changes: Record<string, string | null> = {}
      const currentTitle = currentLocalized[language]?.title ?? ''
      const currentSummary = currentLocalized[language]?.summary ?? ''
      if (localizedTitle !== currentTitle) changes.title = localizedTitle || null
      if (localizedSummary !== currentSummary) changes.summary = localizedSummary || null
      if (Object.keys(changes).length) localized[language] = changes
    }
    if (Object.keys(localized).length) patch.localized = localized

    try {
      await api.patchNovelMetadata(toValue(novel), patch)
      if (coverFile.value) await api.uploadNovelCover(toValue(novel), coverFile.value)
      setCoverFile(null)
      await load()
      await novels.load(toValue(novel))
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    } finally {
      saving.value = false
    }
  }

  async function localize(): Promise<string | null> {
    error.value = null
    try {
      const result = await api.localizeNovelMetadata(toValue(novel), {
        target_language: toValue(targetLanguage),
        force: force.value
      })
      return result.job_id
    } catch (err) {
      error.value = (err as Error).message
      return null
    }
  }

  return {
    metadata,
    loading,
    loadError,
    error,
    saving,
    title,
    author,
    sourceUrl,
    illustrationUrl,
    summary,
    sourceLanguage,
    genres,
    availableGenres,
    genreLoading,
    genreLoadError,
    force,
    coverFile,
    setCoverFile,
    targetTitle,
    targetSummary,
    display,
    load,
    save,
    localize
  }
}
