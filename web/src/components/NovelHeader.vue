<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Sparkles, Package, FileEdit } from '@lucide/vue'
import type { NovelDetail } from '@/api/types'
import type { MetadataDisplay, TargetLanguage } from '@/composables/metadata'
import { formatLanguage } from '@/language'
import placeholderCover from '@/assets/placeholder-cover.png'
import { t } from '@/i18n'

const props = defineProps<{
  novel: NovelDetail
  metadata: MetadataDisplay
  targetLanguage: TargetLanguage
  translatedCount: number
}>()

const emit = defineEmits<{
  translate: []
  pack: []
  metadata: []
}>()

const coverBroken = ref(false)

const displayTitle = computed(() => (
  props.metadata.targetTitle.trim() ||
  props.metadata.title.trim() ||
  props.novel.title ||
  props.novel.name
))

const displayAuthor = computed(() => (
  props.metadata.author.trim() || props.novel.author?.trim() || t('not_specified')
))

const displayGenres = computed(() => (
  props.metadata.genres
    .map((genre) => genre
      .split('-')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' '))
    .join(', ')
))

const displaySummary = computed(() => (
  props.metadata.targetSummary.trim() || props.metadata.summary.trim()
))

const coverSrc = computed(() => (
  coverBroken.value ? placeholderCover : props.metadata.illustrationSrc || placeholderCover
))

const progressPct = computed(() => {
  const total = props.novel.total_input_chapters
  if (!total) return 0
  return Math.min(100, Math.round((props.translatedCount / total) * 100))
})

watch(() => props.metadata.illustrationSrc, () => {
  coverBroken.value = false
})

function metaDisplayValue(current: string, fallback: string | null | undefined): string {
  return current.trim() || (fallback ? String(fallback) : '') || '—'
}
</script>

<template>
  <div class="novel-header-card card-panel">
    <div class="header-main-layout">
      <!-- Cover Column -->
      <div class="cover-wrapper">
        <img
          class="novel-cover-image"
          :src="coverSrc"
          :alt="$t('cover_for', { title: displayTitle })"
          referrerpolicy="no-referrer"
          @error="coverBroken = true"
        />
        <div class="cover-lang-chip">
          {{ formatLanguage(props.novel.source_language, 'korean') }} &rarr; {{ formatLanguage(props.targetLanguage, 'vietnamese') }}
        </div>
      </div>

      <!-- Info Column -->
      <div class="info-wrapper">
        <div class="title-section">
          <div class="badge-row">
            <span class="novel-slug-pill">
              <code>{{ props.novel.name }}</code>
            </span>
            <span v-if="props.novel.has_illustrations" class="illus-badge">
              {{ $t("illustrated") }}
            </span>
          </div>

          <h2 class="novel-main-title" :title="displayTitle">{{ displayTitle }}</h2>

          <div class="novel-subinfo">
            <span class="subinfo-item">
              <strong class="subinfo-label">{{ $t("author") }}:</strong> {{ displayAuthor }}
            </span>
            <span v-if="displayGenres" class="subinfo-item">
              <strong class="subinfo-label">{{ $t("genres") }}:</strong> {{ displayGenres }}
            </span>
          </div>
        </div>

        <!-- Summary if exists -->
        <div v-if="displaySummary" class="novel-summary-box">
          <span class="summary-label">{{ $t("summary") }}</span>
          <div class="summary-text">{{ displaySummary }}</div>
        </div>

        <!-- Quick Progress Bar -->
        <div class="header-progress-box">
          <div class="progress-details">
            <span class="progress-title">{{ $t("translation_progress") }}</span>
            <span class="progress-ratio">
              {{ $t("chapters_translated_of_total", { completed: translatedCount, total: props.novel.total_input_chapters }) }}
              <span class="pct-badge">({{ progressPct }}%)</span>
            </span>
          </div>
          <div class="progress">
            <div class="fill" :style="{ width: `${progressPct}%` }" />
          </div>
        </div>

        <!-- Action Bar -->
        <div class="actions-wrapper">
          <button type="button" class="btn-primary" @click="emit('translate')">
            <Sparkles :size="16" />
            <span>{{ $t("translate_chapters") }}</span>
          </button>
          <button type="button" class="secondary" @click="emit('pack')">
            <Package :size="16" />
            <span>{{ $t("pack_epub") }}</span>
          </button>
          <button type="button" class="secondary" @click="emit('metadata')">
            <FileEdit :size="16" />
            <span>{{ $t("edit_metadata") }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Metadata Details Strip (if loaded) -->
    <div v-if="metadata.exists || metadata.loadError" class="meta-details-strip">
      <div v-if="metadata.title || novel.title" class="meta-pill">
        <span class="meta-label">{{ $t("original_title") }}</span>
        <span class="meta-val">{{ metaDisplayValue(metadata.title, novel.title) }}</span>
      </div>
      <div v-if="metadata.targetTitle" class="meta-pill">
        <span class="meta-label">{{ $t("target_title_language", { language: formatLanguage(targetLanguage) }) }}</span>
        <span class="meta-val">{{ metadata.targetTitle }}</span>
      </div>
      <div v-if="metadata.author || novel.author" class="meta-pill">
        <span class="meta-label">{{ $t("author") }}</span>
        <span class="meta-val">{{ metaDisplayValue(metadata.author, novel.author) }}</span>
      </div>
      <div class="meta-pill">
        <span class="meta-label">{{ $t("glossary") }}</span>
        <span class="meta-val">{{ $t("terms_characters_count", { terms: novel.glossary_terms, characters: novel.glossary_entities }) }}</span>
      </div>

      <p v-if="metadata.loadError" class="error meta-empty">
        {{ $t("failed_to_load_metadata", { error: metadata.loadError }) }}
      </p>
      <p v-else-if="!metadata.hasAny" class="muted meta-empty">
        {{ $t("metadata_missing_action", { action: $t("edit_metadata") }) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.novel-header-card {
  padding: 1.5rem 1.75rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-card);
}

.header-main-layout {
  display: grid;
  grid-template-columns: clamp(9rem, 20vw, 13rem) minmax(0, 1fr);
  gap: 1.75rem;
}

/* Cover */
.cover-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 2 / 3;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  box-shadow: var(--shadow-floating);
}

.novel-cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s var(--ease-spring);
}

.novel-cover-image:hover {
  transform: scale(1.03);
}

.cover-lang-chip {
  position: absolute;
  bottom: 0.6rem;
  left: 0.6rem;
  right: 0.6rem;
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
  background: rgba(11, 14, 20, 0.85);
  backdrop-filter: blur(6px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #ffffff;
  font-size: 0.725rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-align: center;
}

/* Info Column */
.info-wrapper {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-width: 0;
}

.title-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.badge-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.novel-slug-pill {
  font-size: 0.8rem;
}

.illus-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-pill);
  font-size: 0.7rem;
  font-weight: 600;
  background: var(--accent-subtle);
  border: 1px solid rgba(79, 125, 249, 0.25);
  color: var(--accent);
}

.novel-main-title {
  margin: 0;
  font-size: 1.625rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.25;
}

.novel-subinfo {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  flex-wrap: wrap;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

.subinfo-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.subinfo-label {
  color: var(--fg-muted);
  font-weight: 500;
}

/* Summary Box */
.novel-summary-box {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  max-height: 7rem;
  overflow-y: auto;
}

.summary-label {
  font-size: 0.725rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--fg-muted);
}

.summary-text {
  font-size: 0.875rem;
  line-height: 1.55;
  color: var(--fg-primary);
  white-space: pre-wrap;
  text-align: justify;
}

/* Progress Box */
.header-progress-box {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.progress-details {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.8rem;
}

.progress-title {
  color: var(--fg-secondary);
  font-weight: 500;
}

.progress-ratio {
  color: var(--fg-primary);
}

.pct-badge {
  color: var(--accent);
  font-weight: 600;
}

/* Action Buttons */
.actions-wrapper {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 0.5rem;
}

/* Meta Details Strip */
.meta-details-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 0.75rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border-subtle);
}

.meta-pill {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  font-size: 0.85rem;
}

.meta-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--fg-muted);
}

.meta-val {
  color: var(--fg-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-empty {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 0.85rem;
}

@media (max-width: 768px) {
  .header-main-layout {
    grid-template-columns: 1fr;
  }

  .cover-wrapper {
    max-width: 10rem;
    margin: 0 auto;
  }
}
</style>
