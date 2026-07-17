<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import type { NovelChapterStatus } from '@/api/types'
import type { ReaderLanguage } from '@/composables/reader'

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
const modal = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null

const filteredChapters = computed(() => {
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
    return [...unique.values()].sort((left, right) => left.number - right.number)
  }
  return props.chapters
    .filter((chapter) => chapter.target === language.value && chapter.has_translation)
    .sort((left, right) => left.number - right.number)
})

function close() {
  emit('update:open', false)
}

function select(chapter: number) {
  close()
  emit('select', chapter)
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    language.value = props.viewMode
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    document.body.style.overflow = 'hidden'
    void nextTick(() => modal.value?.focus())
  } else {
    document.body.style.overflow = ''
    previousFocus?.focus()
    previousFocus = null
  }
})

onUnmounted(() => {
  document.body.style.overflow = ''
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
        <h3 id="toc-title">Table of Contents</h3>
        <button type="button" class="modal-close" aria-label="Close" @click="close">&times;</button>
      </header>
      <div class="modal-body toc-body">
        <div class="toc-controls">
          <label for="toc-lang-select">Language:</label>
          <select id="toc-lang-select" v-model="language" class="view-select">
            <option value="source">Origin</option>
            <option :value="targetLanguage">{{ targetLanguageLabel }}</option>
          </select>
        </div>
        <div class="toc-list">
          <div v-if="filteredChapters.length === 0" class="muted empty-toc">
            No chapters available for this language.
          </div>
          <button
            v-for="chapter in filteredChapters"
            :key="chapter.number"
            type="button"
            class="toc-item"
            :class="{ active: chapter.number === currentChapter }"
            @click="select(chapter.number)"
          >
            {{ language === 'source' ? chapter.source_title : chapter.title }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.toc-modal {
  max-width: 36rem;
}

.toc-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-height: 70vh;
}

.toc-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.toc-controls label {
  font-weight: 600;
}

.view-select {
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-elev);
  color: var(--fg);
  cursor: pointer;
  height: 2rem;
}

.toc-list {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  flex: 1;
}

.toc-item {
  padding: 0.65rem 1.25rem;
  font-size: 0.9rem;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  cursor: pointer;
  border-radius: 0;
  transition: background 0.15s ease;
}

.toc-item:last-child {
  border-bottom: 0;
}

.toc-item:nth-child(odd) {
  background: var(--bg-elev-2);
}

.toc-item:nth-child(even) {
  background: var(--bg-elev);
}

.toc-item:hover:not(.active) {
  background: var(--bg-hover, rgba(255, 255, 255, 0.05));
}

.toc-item.active {
  background: var(--primary, #007bff);
  color: #fff;
}

.empty-toc {
  text-align: center;
  padding: 2.5rem 0;
  font-size: 0.9rem;
}
</style>
