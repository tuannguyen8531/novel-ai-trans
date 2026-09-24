<script setup lang="ts">
import ChapterContent from '@/components/ChapterContent.vue'

defineProps<{
  novel: string
  content: string
  loading: boolean
  viewLoading: boolean
  viewMode?: string
}>()
</script>

<template>
  <div class="reader-content-root">
    <!-- Slim Indeterminate Progress Line when switching views in background -->
    <div v-if="viewLoading" class="view-loading-bar" aria-hidden="true" />

    <!-- Initial Chapter Loading Skeleton -->
    <div v-if="loading && !content" class="chapter-loading-skeleton">
      <div class="skeleton-line title" />
      <div class="skeleton-line" />
      <div class="skeleton-line" />
      <div class="skeleton-line short" />
      <div class="skeleton-line" style="margin-top: 1.5rem;" />
      <div class="skeleton-line" />
      <div class="skeleton-line short" />
    </div>

    <!-- Chapter Content with Smooth Cross-Fade -->
    <div
      v-else
      class="reader-content-display"
      :class="{ 'is-switching': viewLoading }"
    >
      <Transition name="chapter-fade" mode="out-in">
        <ChapterContent
          :key="`${novel}-${viewMode || 'default'}`"
          :content="content"
          :novel="novel"
        />
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.reader-content-root {
  position: relative;
  width: 100%;
}

.view-loading-bar {
  position: absolute;
  top: -2.5rem;
  left: -2rem;
  right: -2rem;
  height: 3px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--accent) 30%,
    var(--accent-light) 60%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: loading-bar-slide 1.1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
  z-index: 10;
}

@keyframes loading-bar-slide {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.reader-content-display {
  width: 100%;
  transition: opacity 0.22s cubic-bezier(0.16, 1, 0.3, 1), filter 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.reader-content-display.is-switching {
  opacity: 0.6;
  filter: blur(0.3px);
  pointer-events: none;
}

/* Fluid, graceful cross-fade transition */
.chapter-fade-enter-active,
.chapter-fade-leave-active {
  transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1), transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.chapter-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.chapter-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Elegant skeleton loader for initial load */
.chapter-loading-skeleton {
  max-width: 52rem;
  margin: 0 auto;
  padding: 2rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.skeleton-line {
  height: 1.15rem;
  background: linear-gradient(90deg, var(--bg-surface-elevated) 25%, var(--bg-surface-active) 50%, var(--bg-surface-elevated) 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.8s ease-in-out infinite;
  border-radius: var(--radius-xs);
  width: 100%;
}

.skeleton-line.title {
  height: 1.6rem;
  width: 45%;
  margin-bottom: 1.25rem;
}

.skeleton-line.short {
  width: 65%;
}

@keyframes skeleton-pulse {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
