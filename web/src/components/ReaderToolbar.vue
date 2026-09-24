<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  ChevronLeft,
  ChevronRight,
  List,
  MoreVertical,
  Edit3,
  AlertTriangle,
  Trash2,
  Save,
  X
} from '@lucide/vue'
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
  hasPostCheckReview?: boolean
  previousChapter: number | null
  nextChapter: number | null
  currentIndex: number
  chapterCount: number
}>(), {
  showControls: true,
  hasPostCheckReview: false
})

const emit = defineEmits<{
  back: []
  changeView: [mode: ReaderLanguage]
  edit: []
  delete: []
  reviewPostCheck: []
  save: []
  cancel: []
  navigate: [chapter: number]
  openToc: []
}>()

const showMenu = ref(false)

function closeMenu() {
  showMenu.value = false
}

function selectAction(action: 'edit' | 'delete' | 'review-warning') {
  showMenu.value = false
  if (action === 'edit') emit('edit')
  else if (action === 'review-warning') emit('reviewPostCheck')
  else emit('delete')
}

onMounted(() => window.addEventListener('click', closeMenu))
onUnmounted(() => window.removeEventListener('click', closeMenu))
</script>

<template>
  <div v-if="showControls" class="chapter-topbar card-panel">
    <div class="chapter-topbar-left">
      <div class="title-crumb-wrap">
        <span
          class="novel-name-crumb"
          role="button"
          tabindex="0"
          :title="`Back to novel: ${displayTitle}`"
          @click="emit('back')"
          @keydown.enter="emit('back')"
        >
          {{ displayTitle }}
        </span>
        <span class="crumb-slash">/</span>
        <span class="chapter-name-crumb">{{ chapterLabel }} {{ chapter }}</span>
      </div>
    </div>

    <div class="chapter-topbar-controls">
      <template v-if="!editing">
        <!-- Segmented Origin / Target Mode Toggle Switch -->
        <div class="segmented-control" role="group" aria-label="Reading language">
          <span
            class="segmented-glider"
            :class="{ 'is-right': viewMode === targetLanguage }"
            aria-hidden="true"
          />
          <button
            type="button"
            class="segment-btn"
            :class="{ active: viewMode === 'source' }"
            :disabled="loading"
            @click="emit('changeView', 'source')"
          >
            <span>Source</span>
          </button>
          <button
            type="button"
            class="segment-btn"
            :class="{ active: viewMode === targetLanguage }"
            :disabled="loading || !hasTargetTranslation"
            :title="!hasTargetTranslation ? 'No translation available for this chapter' : ''"
            @click="emit('changeView', targetLanguage)"
          >
            <span>{{ targetLanguageLabel }}</span>
          </button>
        </div>

        <!-- Post Check Review Warning Indicator Button -->
        <button
          v-if="hasPostCheckReview"
          type="button"
          class="review-warning-btn"
          title="Review translation quality issues"
          @click="emit('reviewPostCheck')"
        >
          <AlertTriangle :size="14" />
          <span>Review</span>
        </button>

        <!-- Dropdown Menu -->
        <div class="menu-container">
          <button
            type="button"
            class="btn-icon-subtle menu-trigger"
            aria-label="Chapter actions"
            :disabled="loading"
            @click.stop="showMenu = !showMenu"
          >
            <MoreVertical :size="18" />
          </button>

          <div v-if="showMenu" class="dropdown-menu">
            <button type="button" class="menu-item" @click="selectAction('edit')">
              <Edit3 :size="14" />
              <span>Edit content</span>
            </button>
            <button
              v-if="hasPostCheckReview"
              type="button"
              class="menu-item"
              @click="selectAction('review-warning')"
            >
              <AlertTriangle :size="14" />
              <span>Review warnings</span>
            </button>
            <button
              v-if="viewMode === 'source'"
              type="button"
              class="menu-item danger"
              @click="selectAction('delete')"
            >
              <Trash2 :size="14" />
              <span>Delete chapter</span>
            </button>
          </div>
        </div>
      </template>

      <!-- Editing actions -->
      <template v-else>
        <button
          type="button"
          class="btn-save"
          :disabled="saving"
          @click="emit('save')"
        >
          <Save :size="15" />
          <span>{{ saving ? 'Saving…' : 'Save Changes' }}</span>
        </button>
        <button
          type="button"
          class="secondary"
          :disabled="saving"
          @click="emit('cancel')"
        >
          <X :size="15" />
          <span>Cancel</span>
        </button>
      </template>
    </div>
  </div>

  <!-- Navigation Bar (Previous, TOC, Next) -->
  <div class="chapter-nav-bar">
    <button
      type="button"
      class="nav-btn prev-btn"
      :disabled="previousChapter === null"
      @click="previousChapter !== null && emit('navigate', previousChapter)"
    >
      <ChevronLeft :size="16" />
      <span>Previous</span>
    </button>

    <button
      type="button"
      class="toc-btn"
      title="Open Table of Contents"
      @click="emit('openToc')"
    >
      <List :size="15" />
      <span>Chapter {{ currentIndex + 1 }} of {{ chapterCount }}</span>
    </button>

    <button
      type="button"
      class="nav-btn next-btn"
      :disabled="nextChapter === null"
      @click="nextChapter !== null && emit('navigate', nextChapter)"
    >
      <span>Next</span>
      <ChevronRight :size="16" />
    </button>
  </div>
</template>

<style scoped>
.chapter-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.875rem 1.25rem;
  flex-wrap: wrap;
}

.chapter-topbar-left {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-width: 0;
}

.title-crumb-wrap {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.95rem;
  min-width: 0;
}

.novel-name-crumb {
  color: var(--fg-secondary);
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 18rem;
  transition: color var(--transition-fast);
  user-select: none;
}

.novel-name-crumb:hover {
  color: var(--accent);
  text-decoration: underline;
}

.crumb-slash {
  color: var(--fg-muted);
  user-select: none;
}

.chapter-name-crumb {
  color: var(--fg-primary);
  font-weight: 600;
  white-space: nowrap;
}

.chapter-topbar-controls {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-shrink: 0;
}

/* Segmented Control Switch */
.segmented-control {
  display: inline-grid;
  grid-template-columns: 1fr 1fr;
  position: relative;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
  padding: 3px;
  min-width: 12.5rem;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.2);
  user-select: none;
}

.segmented-glider {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc(50% - 3px);
  background: var(--accent);
  border-radius: var(--radius-sm);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25), 0 0 10px var(--accent-glow);
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
  pointer-events: none;
  z-index: 1;
}

.segmented-glider.is-right {
  transform: translateX(100%);
}

.segment-btn {
  position: relative;
  z-index: 2;
  padding: 0.38rem 0.85rem;
  border-radius: var(--radius-sm);
  font-size: 0.825rem;
  font-weight: 500;
  background: transparent;
  color: var(--fg-secondary);
  border: none;
  cursor: pointer;
  box-shadow: none;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  white-space: nowrap;
  transition: color 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.15s ease;
}

.segment-btn:hover:not(:disabled) {
  color: var(--fg-primary);
  background: transparent;
  transform: none;
}

.segment-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.segment-btn.active {
  color: #ffffff;
  font-weight: 600;
  background: transparent;
}

.segment-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Review Warning Button */
.review-warning-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.4rem 0.65rem;
  border-radius: var(--radius-md);
  background: var(--warn-subtle);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: var(--warn);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.review-warning-btn:hover {
  background: var(--warn);
  color: #ffffff;
}

/* Menu Dropdown */
.menu-container {
  position: relative;
  display: inline-block;
}

.menu-trigger {
  width: 2.25rem;
  height: 2.25rem;
  padding: 0;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--fg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.menu-trigger:hover {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
  border-color: var(--border-hover);
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-floating);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 100;
  min-width: 11rem;
  display: flex;
  flex-direction: column;
  padding: 0.35rem;
  animation: modal-fade-in 0.16s cubic-bezier(0.16, 1, 0.3, 1);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: transparent;
  color: var(--fg-primary);
  border: 0;
  border-radius: var(--radius-sm);
  padding: 0.55rem 0.75rem;
  text-align: left;
  font-size: 0.85rem;
  font-weight: 450;
  cursor: pointer;
  width: 100%;
  transition: all var(--transition-fast);
}

.menu-item:hover:not(:disabled) {
  background: var(--bg-surface-active);
  color: var(--fg-primary);
  transform: none;
}

.menu-item.danger {
  color: var(--danger);
}

.menu-item.danger:hover:not(:disabled) {
  background: var(--danger-subtle);
}

.btn-save {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--ok);
  color: #ffffff;
}

.btn-save:hover:not(:disabled) {
  background: #059669;
}

/* Chapter Navigation Bar */
.chapter-nav-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.4rem 0;
}

.nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.875rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  color: var(--fg-primary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.nav-btn:hover:not(:disabled) {
  background: var(--bg-surface-elevated);
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toc-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  color: var(--fg-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.toc-btn:hover {
  background: var(--bg-surface-elevated);
  color: var(--fg-primary);
  border-color: var(--border-hover);
}
</style>
