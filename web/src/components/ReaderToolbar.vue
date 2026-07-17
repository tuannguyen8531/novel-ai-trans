<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { ReaderLanguage } from '@/composables/reader'

withDefaults(defineProps<{
  showControls?: boolean
  displayTitle: string
  chapterLabel: string
  chapter: number
  editing: boolean
  saving: boolean
  loading: boolean
  viewLoading: boolean
  viewMode: ReaderLanguage
  targetLanguage: 'vi' | 'en'
  targetLanguageLabel: string
  hasTargetTranslation: boolean
  previousChapter: number | null
  nextChapter: number | null
  currentIndex: number
  chapterCount: number
}>(), {
  showControls: true
})

const emit = defineEmits<{
  back: []
  changeView: [mode: ReaderLanguage]
  edit: []
  delete: []
  save: []
  cancel: []
  navigate: [chapter: number]
  openToc: []
}>()

const showMenu = ref(false)

function closeMenu() {
  showMenu.value = false
}

function selectAction(action: 'edit' | 'delete') {
  showMenu.value = false
  if (action === 'edit') emit('edit')
  else emit('delete')
}

onMounted(() => window.addEventListener('click', closeMenu))
onUnmounted(() => window.removeEventListener('click', closeMenu))
</script>

<template>
  <div v-if="showControls" class="chapter-topbar card">
    <div class="chapter-topbar-left">
      <button type="button" class="secondary icon-btn" title="Back to novel" @click="emit('back')">
        ← Back
      </button>
      <span class="chapter-topbar-title">
        <span class="muted">{{ displayTitle }} /</span>
        {{ chapterLabel }} {{ chapter }}
      </span>
    </div>

    <div class="chapter-topbar-controls">
      <template v-if="!editing">
        <select
          class="view-select"
          :value="viewMode"
          :disabled="viewLoading || loading"
          @change="emit(
            'changeView',
            ($event.target as HTMLSelectElement).value as ReaderLanguage
          )"
        >
          <option value="source">Origin</option>
          <option :value="targetLanguage" :disabled="!hasTargetTranslation">
            {{ targetLanguageLabel }}
          </option>
        </select>

        <div class="menu-container">
          <button
            type="button"
            class="secondary icon-btn menu-trigger"
            :disabled="loading"
            @click.stop="showMenu = !showMenu"
          >⋮</button>
          <div v-if="showMenu" class="dropdown-menu">
            <button type="button" class="menu-item" @click="selectAction('edit')">Edit</button>
            <button
              v-if="viewMode === 'source'"
              type="button"
              class="menu-item danger"
              @click="selectAction('delete')"
            >Delete</button>
          </div>
        </div>
      </template>

      <template v-else>
        <button type="button" :disabled="saving" @click="emit('save')">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
        <button type="button" class="secondary" :disabled="saving" @click="emit('cancel')">
          Cancel
        </button>
      </template>
    </div>
  </div>

  <div class="chapter-nav">
    <button
      type="button"
      class="secondary"
      :disabled="previousChapter === null"
      @click="previousChapter !== null && emit('navigate', previousChapter)"
    >← Previous</button>
    <button type="button" class="secondary" title="Open Table of Contents" @click="emit('openToc')">
      {{ currentIndex + 1 }} / {{ chapterCount }}
    </button>
    <button
      type="button"
      class="secondary"
      :disabled="nextChapter === null"
      @click="nextChapter !== null && emit('navigate', nextChapter)"
    >Next →</button>
  </div>
</template>

<style scoped>
.chapter-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
}

.chapter-topbar-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.chapter-topbar-title {
  font-size: 1rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chapter-topbar-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.icon-btn {
  flex-shrink: 0;
}

.menu-container {
  position: relative;
  display: inline-block;
}

.menu-trigger {
  width: 2rem;
  height: 2rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  line-height: 1;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.25rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 100;
  min-width: 8rem;
  display: flex;
  flex-direction: column;
  padding: 0.25rem 0;
}

.menu-item {
  background: transparent;
  color: var(--fg);
  border: 0;
  border-radius: 0;
  padding: 0.5rem 1rem;
  text-align: left;
  font-size: 0.875rem;
  cursor: pointer;
  width: 100%;
  transition: background 0.1s ease;
}

.menu-item:hover:not(:disabled) {
  background: var(--bg-elev);
}

.menu-item.danger {
  color: var(--danger);
  background: transparent;
}

.menu-item.danger:hover:not(:disabled) {
  background: rgba(240, 98, 98, 0.1);
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

.view-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chapter-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.2rem 0;
}
</style>
