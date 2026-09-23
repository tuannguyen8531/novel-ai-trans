<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertCircle } from '@lucide/vue'
import type { NovelSummary, NovelTargetProgress } from '@/api/types'
import { getNovelCoverUrl } from '@/composables/novels'
import placeholderCover from '@/assets/placeholder-cover.png'
import StatusBadge from '@/components/common/StatusBadge.vue'

const props = withDefaults(
  defineProps<{
    novel: NovelSummary
    targetLanguage?: string
  }>(),
  {
    targetLanguage: 'vi'
  }
)

const coverError = ref(false)

const coverUrl = computed(() => {
  if (coverError.value) return placeholderCover
  return getNovelCoverUrl(props.novel.name, props.novel.illustration_url)
})

const targetProgress = computed<NovelTargetProgress | undefined>(() => {
  return props.novel.targets.find((p) => p.target === props.targetLanguage)
})

const completedChapters = computed(() => targetProgress.value?.completed ?? 0)
const totalChapters = computed(() => targetProgress.value?.total ?? props.novel.total_input_chapters)
const failedChapters = computed(() => targetProgress.value?.failed ?? 0)
const warningChapters = computed(() => targetProgress.value?.warnings ?? 0)

const percent = computed(() => {
  if (!totalChapters.value) return 0
  return Math.min(100, Math.round((completedChapters.value / totalChapters.value) * 100))
})

const languageLabel = computed(() => {
  const lang = (props.novel.source_language || '').toLowerCase()
  if (lang === 'ko' || lang === 'korean') return 'Korean'
  if (lang === 'ja' || lang === 'japanese') return 'Japanese'
  if (lang === 'zh' || lang === 'chinese') return 'Chinese'
  if (lang) return lang.toUpperCase()
  return 'Auto'
})
</script>

<template>
  <div class="novel-card-root">
    <RouterLink :to="`/novels/${novel.name}`" class="card-cover-container" :title="novel.title || novel.name">
      <img
        :src="coverUrl"
        :alt="novel.title || novel.name"
        class="card-cover-img"
        loading="lazy"
        referrerpolicy="no-referrer"
        @error="coverError = true"
      />
      <div class="cover-overlay">
        <span class="lang-tag">{{ languageLabel }}</span>
        <div v-if="failedChapters > 0 || warningChapters > 0" class="issues-tag">
          <AlertCircle :size="12" />
          <span>{{ failedChapters > 0 ? `${failedChapters} failed` : `${warningChapters} warn` }}</span>
        </div>
      </div>
    </RouterLink>

    <div class="card-content">
      <div class="card-header">
        <RouterLink :to="`/novels/${novel.name}`" class="card-title" :title="novel.title || novel.name">
          {{ novel.title || novel.name }}
        </RouterLink>
        <div class="card-meta">
          <span class="card-author" :title="novel.author || 'Unknown Author'">
            {{ novel.author || 'Unknown author' }}
          </span>
          <span class="card-slug" :title="novel.name">
            <code>{{ novel.name }}</code>
          </span>
        </div>
      </div>

      <div class="progress-section">
        <div class="progress-meta">
          <span class="progress-label">Chapters</span>
          <span class="progress-count">
            <strong>{{ completedChapters }}</strong> / {{ totalChapters }}
            <span class="progress-pct">({{ percent }}%)</span>
          </span>
        </div>
        <div class="progress-bar-track">
          <div class="progress-bar-fill" :style="{ width: `${percent}%` }" />
        </div>
      </div>

      <div class="card-footer">
        <div class="card-status">
          <StatusBadge
            v-if="failedChapters > 0"
            status="failed"
            :label="`${failedChapters} failed`"
            size="sm"
          />
          <StatusBadge
            v-else-if="warningChapters > 0"
            status="warn"
            :label="`${warningChapters} warnings`"
            size="sm"
          />
          <StatusBadge
            v-else-if="completedChapters > 0 && completedChapters === totalChapters"
            status="completed"
            label="Translated"
            size="sm"
          />
          <StatusBadge
            v-else-if="completedChapters > 0"
            status="running"
            label="In Progress"
            size="sm"
          />
          <StatusBadge
            v-else
            status="normal"
            label="Untranslated"
            size="sm"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.novel-card-root {
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-card);
  transition: all var(--transition-normal);
}

.novel-card-root:hover {
  border-color: var(--border-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow-floating);
}

.card-cover-container {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--bg-surface-elevated);
  overflow: hidden;
}

.card-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 20%;
  transition: transform 0.4s var(--ease-spring);
}

.novel-card-root:hover .card-cover-img {
  transform: scale(1.04);
}

.cover-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 0.75rem;
  background: linear-gradient(180deg, rgba(11, 14, 20, 0.75) 0%, rgba(11, 14, 20, 0) 100%);
  pointer-events: none;
}

.lang-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-xs);
  background: rgba(11, 14, 20, 0.7);
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #ffffff;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.issues-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-xs);
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--danger);
  font-size: 0.7rem;
  font-weight: 600;
}

.card-content {
  display: flex;
  flex-direction: column;
  padding: 1rem;
  gap: 0.875rem;
  flex: 1;
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--fg-primary);
  text-decoration: none;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  transition: color var(--transition-fast);
}

.card-title:hover {
  color: var(--accent);
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--fg-secondary);
}

.card-author {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-slug {
  flex-shrink: 0;
}

.progress-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.75rem;
}

.progress-label {
  color: var(--fg-muted);
}

.progress-count {
  color: var(--fg-secondary);
}

.progress-pct {
  color: var(--fg-muted);
  font-weight: 400;
}

.progress-bar-track {
  height: 6px;
  background: var(--bg-surface-elevated);
  border-radius: var(--radius-pill);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent) 0%, var(--accent-light) 100%);
  border-radius: var(--radius-pill);
  transition: width 0.4s var(--ease-spring);
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin-top: auto;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.card-status {
  display: flex;
  align-items: center;
}
</style>
