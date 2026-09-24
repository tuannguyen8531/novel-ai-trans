<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X, Search } from '@lucide/vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import type { NovelChapterStatus } from '@/api/types'
import type { ReaderLanguage } from '@/composables/reader'
import { useBodyScrollLock } from '@/composables/scrolllock'
import { t } from '@/i18n'

const props = defineProps<{
  open: boolean
  chapters: NovelChapterStatus[]
  currentChapter: number
  viewMode: ReaderLanguage
  targetLanguage: 'vi' | 'en'
  targetLanguageLabel: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [chapter: number]
}>()

const language = ref<ReaderLanguage>('source')
const languageOptions = computed(() => [
  { value: 'source', label: t('original') },
  { value: props.targetLanguage, label: props.targetLanguageLabel }
])
const modal = ref<HTMLElement | null>(null)
const tocList = ref<HTMLElement | null>(null)
const searchQuery = ref('')
let previousFocus: HTMLElement | null = null

useBodyScrollLock(() => props.open)

const filteredChapters = computed(() => {
  let list: Array<{ number: number; title?: string | null; source_title?: string | null }> = []

  if (language.value === 'source') {
    const unique = new Map<number, {
      number: number
      source_title?: string | null
      title?: string | null
    }>()
    for (const chapter of props.chapters) {
      if (chapter.has_source && !unique.has(chapter.number)) {
        unique.set(chapter.number, {
          number: chapter.number,
          source_title: chapter.source_title,
          title: null
        })
      }
    }
    list = [...unique.values()].sort((left, right) => left.number - right.number)
  } else {
    list = props.chapters
      .filter((chapter) => chapter.target === language.value && chapter.has_translation)
      .sort((left, right) => left.number - right.number)
  }

  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((ch) => {
      const title = (language.value === 'source' ? ch.source_title : ch.title) || ''
      return String(ch.number).includes(q) || title.toLowerCase().includes(q)
    })
  }

  return list
})

function close() {
  emit('update:open', false)
}

function select(chapter: number) {
  close()
  emit('select', chapter)
}

function scrollToCurrentChapter() {
  const list = tocList.value
  const currentItem = list?.querySelector<HTMLElement>('.toc-item.active')
  if (!list || !currentItem) return

  const listRect = list.getBoundingClientRect()
  const itemRect = currentItem.getBoundingClientRect()
  list.scrollTop += itemRect.top - listRect.top - (list.clientHeight - itemRect.height) / 2
}

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    language.value = props.viewMode
    searchQuery.value = ''
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    modal.value?.focus()
    scrollToCurrentChapter()
  } else {
    previousFocus?.focus()
    previousFocus = null
  }
})

watch([language, filteredChapters], async () => {
  if (!props.open) return
  await nextTick()
  scrollToCurrentChapter()
})
</script>

<template>
  <div v-if="open" class="modal-overlay" @click.self="close">
    <div
      ref="modal"
      class="modal-card toc-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="toc-title"
      tabindex="-1"
      @keydown.esc="close"
    >
      <header class="modal-header">
        <h3 id="toc-title">{{ $t("table_of_contents") }}</h3>
        <button
          type="button"
          class="modal-close"
          :aria-label="$t('close')"
          @click="close"
        >
          <X :size="18" />
        </button>
      </header>
      <div class="modal-body toc-body">
        <div class="toc-controls">
          <div class="toc-lang-group">
            <span class="toc-label">{{ $t("language") }}:</span>
            <CustomSelect
              id="toc-lang-select"
              v-model="language"
              :options="languageOptions"
              class="toc-custom-select"
            />
          </div>

          <div class="toc-search-box">
            <Search :size="14" class="toc-search-icon" />
            <input
              v-model="searchQuery"
              type="search"
              :placeholder="$t('filter_chapters')"
              class="toc-search-input"
            />
          </div>
        </div>

        <div ref="tocList" class="toc-list">
          <div v-if="filteredChapters.length === 0" class="muted empty-toc">
            {{ $t("no_chapters_found") }}
          </div>
          <button
            v-for="chapter in filteredChapters"
            :key="chapter.number"
            type="button"
            class="toc-item"
            :class="{ active: chapter.number === currentChapter }"
            @click="select(chapter.number)"
          >
            <span class="toc-item-number">{{ $t("chapter_number", { number: chapter.number }) }}</span>
            <span class="toc-item-title">{{ (language === 'source' ? chapter.source_title : chapter.title) || $t('untitled') }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.toc-modal {
  max-width: 38rem;
  max-height: 85vh;
}

.toc-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  max-height: calc(85vh - 5rem);
}

.toc-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.toc-lang-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.toc-label {
  font-size: 0.825rem;
  font-weight: 600;
  color: var(--fg-secondary);
  margin-bottom: 0;
}

.toc-custom-select {
  min-width: 10rem;
}

.toc-search-box {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 10rem;
}

.toc-search-icon {
  position: absolute;
  left: 0.65rem;
  color: var(--fg-muted);
}

.toc-search-input {
  padding-left: 2rem;
  font-size: 0.85rem;
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}

.toc-list {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  background: var(--bg-surface-elevated);
  max-height: 24rem;
}

.toc-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 1rem;
  font-size: 0.875rem;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--fg-primary);
  cursor: pointer;
  border-radius: 0;
  transition: all var(--transition-fast);
}

.toc-item:last-child {
  border-bottom: none;
}

.toc-item:hover:not(.active) {
  background: var(--bg-surface-active);
}

.toc-item.active {
  background: var(--accent);
  color: #ffffff;
  font-weight: 600;
}

.toc-item-number {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  flex-shrink: 0;
  color: inherit;
  opacity: 0.85;
}

.toc-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-toc {
  text-align: center;
  padding: 3rem 1rem;
  font-size: 0.875rem;
}
</style>
