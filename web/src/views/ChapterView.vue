<script setup lang="ts">
import { onMounted, onUnmounted, ref, toRef } from 'vue'
import { ArrowUp, AlertCircle } from '@lucide/vue'
import ChapterEditor from '@/components/ChapterEditor.vue'
import ChapterToc from '@/components/ChapterToc.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import PostCheckDialog from '@/components/PostCheckDialog.vue'
import ReaderContent from '@/components/ReaderContent.vue'
import ReaderToolbar from '@/components/ReaderToolbar.vue'
import { useReader } from '@/composables/reader'

const props = defineProps<{ name: string; chapter: number }>()

const {
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
  postCheck,
  postCheckLoading,
  postCheckError,
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
  reviewPostCheckItem,
  acceptCandidate,
  confirmDelete,
  goTo,
  goBack,
  scrollToTop
} = useReader(toRef(props, 'name'), toRef(props, 'chapter'))

const showToc = ref(false)
const showPostCheckDialog = ref(false)
const bottomNavigation = ref<HTMLElement | null>(null)
const bottomNavigationVisible = ref(false)
let navigationObserver: IntersectionObserver | undefined

onMounted(() => {
  navigationObserver = new IntersectionObserver(([entry]) => {
    bottomNavigationVisible.value = entry.isIntersecting
  })
  if (bottomNavigation.value) navigationObserver.observe(bottomNavigation.value)
})

onUnmounted(() => navigationObserver?.disconnect())
</script>

<template>
  <section class="chapter-view-root">
    <!-- Top Reader Toolbar -->
    <ReaderToolbar
      :display-title="displayTitle"
      :chapter-label="chapterLabel"
      :chapter="chapter"
      :editing="editing"
      :saving="saving"
      :loading="loading"
      :view-loading="viewLoading"
      :view-mode="viewMode"
      :target-language="targetLanguage"
      :target-language-label="targetLanguageLabel"
      :has-target-translation="hasTargetTranslation"
      :has-post-check-review="Boolean(postCheck && (postCheck.items.length || postCheck.candidate_translation !== null))"
      :previous-chapter="previousChapter"
      :next-chapter="nextChapter"
      :current-index="currentIndex"
      :chapter-count="chapterCount"
      @back="goBack"
      @change-view="changeView"
      @edit="startEdit"
      @review-post-check="showPostCheckDialog = true"
      @delete="showDeleteDialog = true"
      @save="saveEdit"
      @cancel="cancelEdit"
      @navigate="goTo"
      @open-toc="showToc = true"
    />

    <!-- Errors -->
    <div v-if="error" class="card-panel alert-error">
      <AlertCircle :size="18" />
      <span>{{ error }}</span>
    </div>
    <div v-if="postCheckError" class="card-panel alert-error">
      <AlertCircle :size="18" />
      <span>{{ postCheckError }}</span>
    </div>

    <!-- Reading Canvas Card -->
    <div class="chapter-body-frame card-panel">
      <ReaderContent
        v-if="loading || viewLoading || !editing"
        :novel="name"
        :content="content"
        :loading="loading"
        :view-loading="viewLoading"
        :view-mode="viewMode"
      />
      <ChapterEditor v-else v-model="editContent" />
    </div>

    <!-- Bottom Navigation Bar -->
    <div ref="bottomNavigation">
      <ReaderToolbar
        :show-controls="false"
        :display-title="displayTitle"
        :chapter-label="chapterLabel"
        :chapter="chapter"
        :editing="editing"
        :saving="saving"
        :loading="loading"
        :view-loading="viewLoading"
        :view-mode="viewMode"
        :target-language="targetLanguage"
        :target-language-label="targetLanguageLabel"
        :has-target-translation="hasTargetTranslation"
        :previous-chapter="previousChapter"
        :next-chapter="nextChapter"
        :current-index="currentIndex"
        :chapter-count="chapterCount"
        @navigate="goTo"
        @open-toc="showToc = true"
      />
    </div>

    <!-- Table of Contents Modal -->
    <ChapterToc
      v-model:open="showToc"
      :chapters="chapters"
      :current-chapter="chapter"
      :view-mode="viewMode"
      :target-language="targetLanguage"
      :target-language-label="targetLanguageLabel"
      @select="goTo"
    />

    <!-- Post Check Warning Review Dialog -->
    <PostCheckDialog
      :open="showPostCheckDialog"
      :review="postCheck"
      :loading="postCheckLoading"
      :error="postCheckError"
      @review-item="reviewPostCheckItem"
      @accept-candidate="acceptCandidate"
      @close="showPostCheckDialog = false"
    />

    <!-- Delete Chapter Confirmation Dialog -->
    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Chapter"
      :message="`Delete Chapter ${chapter}?\n\nThis permanently deletes the source chapter. Existing translations are kept. This cannot be undone.`"
      confirm-label="Delete Chapter"
      :danger="true"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @cancel="showDeleteDialog = false"
    />

    <!-- Floating Scroll To Top Button -->
    <button
      v-show="showScrollToTop && !bottomNavigationVisible"
      type="button"
      class="scroll-to-top-btn"
      aria-label="Scroll to top"
      title="Scroll to top"
      @click="scrollToTop"
    >
      <ArrowUp :size="18" />
    </button>
  </section>
</template>

<style scoped>
.chapter-view-root {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  max-width: 64rem;
  margin: 0 auto;
}

.chapter-body-frame {
  position: relative;
  overflow: hidden;
  min-height: 65vh;
  padding: 2.5rem 2rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
}

.alert-error {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--danger);
  padding: 0.875rem 1.25rem;
}

.scroll-to-top-btn {
  position: fixed;
  right: 2rem;
  bottom: 2rem;
  z-index: 120;
  width: 3rem;
  height: 3rem;
  border-radius: 50%;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--fg-primary);
  box-shadow: var(--shadow-floating);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.scroll-to-top-btn:hover {
  background: var(--accent);
  color: #ffffff;
  border-color: transparent;
  transform: translateY(-2px);
}
</style>
