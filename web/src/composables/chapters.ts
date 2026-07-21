import { computed, onUnmounted, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'
import type { NovelChapterStatus } from '@/api/types'

export function useChapters(novel: MaybeRefOrGetter<string>) {
  const chapters = ref<NovelChapterStatus[]>([])
  const loading = ref(false)
  const addSaving = ref(false)
  const addError = ref<string | null>(null)
  const page = ref(1)
  const ascending = ref(true)
  const containerWidth = ref(600)
  const containerRef = ref<HTMLElement | null>(null)
  let resizeObserver: ResizeObserver | null = null

  const columns = computed(() => {
    const minWidth = 128
    const gap = 6.4
    return Math.max(1, Math.floor((containerWidth.value + gap) / (minWidth + gap)))
  })
  const perPage = computed(() => columns.value * 5)
  const numbers = computed(() => {
    const sources = new Set<number>()
    for (const status of chapters.value) {
      if (status.has_source) sources.add(status.number)
    }
    const sorted = [...sources].sort((a, b) => a - b)
    return ascending.value ? sorted : sorted.reverse()
  })
  const totalPages = computed(() => Math.max(1, Math.ceil(numbers.value.length / perPage.value)))
  const pagedNumbers = computed(() => {
    const start = (page.value - 1) * perPage.value
    return numbers.value.slice(start, start + perPage.value)
  })
  const padWidth = computed(() => String(numbers.value.reduce((maximum, number) => Math.max(maximum, number), 0)).length)
  const nextNumber = computed(() => numbers.value.length > 0 ? Math.max(...numbers.value) + 1 : 1)

  watch([numbers, totalPages], () => {
    if (page.value > totalPages.value) page.value = totalPages.value
  })

  watch(containerRef, (element) => {
    resizeObserver?.disconnect()
    resizeObserver = null
    if (!element) return
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) containerWidth.value = entry.contentRect.width
    })
    resizeObserver.observe(element)
  })

  onUnmounted(() => resizeObserver?.disconnect())

  function formatNumber(number: number): string {
    return String(number).padStart(padWidth.value, '\u2007')
  }

  async function load() {
    loading.value = true
    try {
      chapters.value = await api.listChapters(toValue(novel))
    } finally {
      loading.value = false
    }
  }

  async function add(number: number, content: string): Promise<string | null> {
    addError.value = null
    addSaving.value = true
    try {
      return (await api.insertChapter(toValue(novel), number, content)).job_id
    } catch (err) {
      addError.value = (err as Error).message
      return null
    } finally {
      addSaving.value = false
    }
  }

  return {
    loading,
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
  }
}
