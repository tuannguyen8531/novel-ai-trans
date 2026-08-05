<script setup lang="ts">
import { ref, toRef } from 'vue'
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
</script>

<template>
  <section class="chapter-view">
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

    <p v-if="error" class="error card">{{ error }}</p>
    <p v-if="postCheckError" class="error card">{{ postCheckError }}</p>

    <div class="chapter-body card">
      <ReaderContent
        v-if="loading || viewLoading || !editing"
        :novel="name"
        :content="content"
        :loading="loading"
        :view-loading="viewLoading"
      />
      <ChapterEditor v-else v-model="editContent" />
    </div>

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

    <ChapterToc
      v-model:open="showToc"
      :chapters="chapters"
      :current-chapter="chapter"
      :view-mode="viewMode"
      :target-language="targetLanguage"
      :target-language-label="targetLanguageLabel"
      @select="goTo"
    />

    <PostCheckDialog
      :open="showPostCheckDialog"
      :review="postCheck"
      :loading="postCheckLoading"
      :error="postCheckError"
      @review-item="reviewPostCheckItem"
      @accept-candidate="acceptCandidate"
      @close="showPostCheckDialog = false"
    />

    <ConfirmDialog
      :show="showDeleteDialog"
      title="Delete Chapter"
      :message="`Delete Chapter ${chapter}?\n\nThis permanently deletes the source chapter. Existing translations are kept. This cannot be undone.`"
      confirm-label="Delete"
      :danger="true"
      :loading="deleteLoading"
      @confirm="confirmDelete"
      @cancel="showDeleteDialog = false"
    />

    <button
      v-show="showScrollToTop"
      type="button"
      class="secondary scroll-to-top"
      aria-label="Scroll to top"
      title="Scroll to top"
      @click="scrollToTop"
    >↑ Top</button>
  </section>
</template>

<style scoped>
.chapter-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.chapter-body {
  min-height: 60vh;
}

.scroll-to-top {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  z-index: 120;
  min-width: 4rem;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
}
</style>
