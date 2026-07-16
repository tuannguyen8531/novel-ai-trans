import { computed, onMounted, onUnmounted, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import type { NovelChapterStatus } from '@/api/types'
import { useSettingsStore } from '@/stores/settings'

export type ReaderLanguage = 'source' | 'vi' | 'en'

export function useReader(
  novel: MaybeRefOrGetter<string>,
  chapter: MaybeRefOrGetter<number>
) {
  const router = useRouter()
  const settings = useSettingsStore()

  const chapters = ref<NovelChapterStatus[]>([])
  const metadata = ref<Record<string, unknown> | null>(null)
  const content = ref('')
  const editContent = ref('')
  const editing = ref(false)
  const saving = ref(false)
  const loading = ref(true)
  const error = ref<string | null>(null)
  const viewMode = ref<ReaderLanguage>('source')
  const viewLoading = ref(false)
  const showDeleteDialog = ref(false)
  const deleteLoading = ref(false)
  const showScrollToTop = ref(false)

  const chapterNumbers = computed(() => {
    const available = new Set<number>()
    for (const status of chapters.value) {
      const canRead = viewMode.value === 'source'
        ? status.has_source
        : status.target === viewMode.value && status.has_translation
      if (canRead) available.add(status.number)
    }
    return [...available].sort((left, right) => left - right)
  })

  const currentIndex = computed(() => chapterNumbers.value.indexOf(toValue(chapter)))
  const previousChapter = computed(() =>
    currentIndex.value > 0 ? chapterNumbers.value[currentIndex.value - 1] : null
  )
  const nextChapter = computed(() =>
    currentIndex.value < chapterNumbers.value.length - 1
      ? chapterNumbers.value[currentIndex.value + 1]
      : null
  )
  const chapterCount = computed(() => chapterNumbers.value.length)

  const targetLanguage = computed<'vi' | 'en'>(() =>
    settings.settings?.target_language === 'en' ? 'en' : 'vi'
  )
  const targetLanguageLabel = computed(() =>
    targetLanguage.value === 'vi' ? 'Vietnamese' : 'English'
  )
  const hasTargetTranslation = computed(() =>
    chapters.value.some((status) =>
      status.number === toValue(chapter) &&
      status.target === targetLanguage.value &&
      status.has_translation
    )
  )
  const defaultViewMode = computed<ReaderLanguage>(() =>
    hasTargetTranslation.value ? targetLanguage.value : 'source'
  )

  const displayTitle = computed(() => {
    if (!metadata.value) return toValue(novel)
    const title = typeof metadata.value.title === 'string' ? metadata.value.title : toValue(novel)
    const localized = (
      metadata.value.localized as Record<string, { title?: string | null }> | undefined
    ) ?? {}
    if (viewMode.value !== 'source' && localized[targetLanguage.value]?.title) {
      return localized[targetLanguage.value].title as string
    }
    return title
  })

  const chapterLabel = computed(() => viewMode.value === 'vi' ? 'Chương' : 'Chapter')

  async function loadChapters() {
    try {
      chapters.value = await api.listChapters(toValue(novel))
    } catch {
      // Chapter navigation remains usable from the current URL.
    }
  }

  async function loadMetadata() {
    try {
      const response = await api.getNovelMetadata(toValue(novel))
      metadata.value = response.data ?? null
    } catch {
      // Metadata is optional for the reader title.
    }
  }

  async function loadContent(number: number, mode: ReaderLanguage = 'source') {
    loading.value = true
    error.value = null
    content.value = ''
    viewMode.value = mode
    try {
      const view = mode === 'source' ? 'source' : 'translation'
      const target = mode === 'source' ? undefined : mode
      const response = await api.getChapterContent(toValue(novel), number, view, target)
      content.value = response.content
      editContent.value = response.content
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function changeView(mode: ReaderLanguage) {
    if (viewLoading.value || mode === viewMode.value) return
    viewLoading.value = true
    error.value = null
    try {
      const view = mode === 'source' ? 'source' : 'translation'
      const target = mode === 'source' ? undefined : mode
      const response = await api.getChapterContent(
        toValue(novel),
        toValue(chapter),
        view,
        target
      )
      content.value = response.content
      editContent.value = response.content
      viewMode.value = mode
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      viewLoading.value = false
    }
  }

  function startEdit() {
    editContent.value = content.value
    editing.value = true
  }

  function cancelEdit() {
    editing.value = false
    editContent.value = content.value
  }

  async function saveEdit() {
    saving.value = true
    error.value = null
    try {
      const view = viewMode.value === 'source' ? 'source' : 'translation'
      const target = viewMode.value === 'source' ? undefined : viewMode.value
      const response = await api.putChapterContent(
        toValue(novel),
        toValue(chapter),
        editContent.value,
        view,
        target
      )
      content.value = response.content
      editContent.value = response.content
      editing.value = false
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      saving.value = false
    }
  }

  async function confirmDelete() {
    deleteLoading.value = true
    try {
      await api.deleteChapter(toValue(novel), toValue(chapter))
      const destination = previousChapter.value ?? nextChapter.value
      if (destination !== null) {
        await router.replace({
          name: 'chapter-reader',
          params: { name: toValue(novel), chapter: destination }
        })
      } else {
        await router.replace({ name: 'novel-detail', params: { name: toValue(novel) } })
      }
      showDeleteDialog.value = false
    } catch (err) {
      error.value = (err as Error).message
      showDeleteDialog.value = false
    } finally {
      deleteLoading.value = false
    }
  }

  function goTo(number: number) {
    void router.push({
      name: 'chapter-reader',
      params: { name: toValue(novel), chapter: number }
    })
  }

  function goBack() {
    void router.push({ name: 'novel-detail', params: { name: toValue(novel) } })
  }

  function updateScrollToTopVisibility() {
    showScrollToTop.value = window.scrollY > 480
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  onMounted(async () => {
    window.addEventListener('scroll', updateScrollToTopVisibility, { passive: true })
    updateScrollToTopVisibility()
    await Promise.all([loadChapters(), loadMetadata(), settings.refresh()])
    await loadContent(toValue(chapter), defaultViewMode.value)
  })

  onUnmounted(() => {
    window.removeEventListener('scroll', updateScrollToTopVisibility)
  })

  watch(() => toValue(chapter), async (number) => {
    editing.value = false
    await loadContent(number, defaultViewMode.value)
  })

  watch(
    [() => toValue(chapter), displayTitle, chapterLabel],
    ([number, title, label]) => {
      document.title = `${title} - ${label} ${number} - Novel AI Translation`
    },
    { immediate: true }
  )

  return {
    chapters,
    content,
    editContent,
    editing,
    saving,
    loading,
    error,
    viewMode,
    viewLoading,
    showDeleteDialog,
    deleteLoading,
    showScrollToTop,
    currentIndex,
    previousChapter,
    nextChapter,
    chapterCount,
    targetLanguage,
    targetLanguageLabel,
    hasTargetTranslation,
    displayTitle,
    chapterLabel,
    changeView,
    startEdit,
    cancelEdit,
    saveEdit,
    confirmDelete,
    goTo,
    goBack,
    scrollToTop
  }
}
