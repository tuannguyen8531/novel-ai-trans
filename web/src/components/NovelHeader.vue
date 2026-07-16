<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { NovelDetail } from '@/api/types'
import type { MetadataDisplay, TargetLanguage } from '@/composables/metadata'
import placeholderCover from '@/assets/placeholder-cover.png'

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
  props.metadata.author.trim() || props.novel.author?.trim() || 'Not updated'
))
const displaySummary = computed(() => (
  props.metadata.targetSummary.trim() || props.metadata.summary.trim()
))
const coverSrc = computed(() => (
  coverBroken.value ? placeholderCover : props.metadata.illustrationSrc || placeholderCover
))

watch(() => props.metadata.illustrationSrc, () => {
  coverBroken.value = false
})

function metaDisplayValue(current: string, fallback: string | null | undefined): string {
  return current.trim() || (fallback ? String(fallback) : '') || '—'
}
</script>

<template>
  <div class="card">
    <div class="novel-cover-row">
      <img
        class="novel-cover"
        :src="coverSrc"
        :alt="`Cover for ${displayTitle}`"
        @error="coverBroken = true"
      />
      <div class="novel-cover-info">
        <h2 :title="displayTitle">{{ displayTitle }}</h2>
        <p class="novel-author" :title="`Author: ${displayAuthor}`">
          <span>Author:</span> {{ displayAuthor }}
        </p>
        <div v-if="displaySummary" class="novel-summary">
          <span class="novel-summary-label">Summary</span>
          <div class="novel-summary-content">{{ displaySummary }}</div>
        </div>
      </div>
    </div>

    <div v-if="metadata.exists || metadata.loadError" class="meta-summary">
      <div v-if="metadata.title || novel.title" class="meta-row">
        <span class="meta-label">Title</span>
        <span>{{ metaDisplayValue(metadata.title, novel.title) }}</span>
      </div>
      <div v-if="metadata.author || novel.author" class="meta-row">
        <span class="meta-label">Author</span>
        <span>{{ metaDisplayValue(metadata.author, novel.author) }}</span>
      </div>
      <div v-if="metadata.sourceLanguage || novel.source_language" class="meta-row">
        <span class="meta-label">Language</span>
        <span class="capitalize">{{ metaDisplayValue(metadata.sourceLanguage, novel.source_language) }}</span>
      </div>
      <div v-if="metadata.targetTitle" class="meta-row">
        <span class="meta-label">Title ({{ targetLanguage }})</span>
        <span>{{ metadata.targetTitle }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Total</span>
        <span>{{ novel.total_input_chapters }} chapter{{ novel.total_input_chapters === 1 ? '' : 's' }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">Translated</span>
        <span>{{ translatedCount }} chapter{{ translatedCount === 1 ? '' : 's' }}</span>
      </div>
      <p v-if="metadata.loadError" class="error meta-empty">
        Failed to load metadata: {{ metadata.loadError }}
      </p>
      <p v-else-if="!metadata.hasAny" class="muted meta-empty">
        No metadata fields filled in yet — click <strong>Edit metadata</strong> to add some.
      </p>
    </div>

    <div class="actions-row">
      <div class="row gap-2 action-buttons">
        <button type="button" @click="emit('translate')">Translate</button>
        <button type="button" class="secondary" @click="emit('pack')">Pack</button>
        <button type="button" class="secondary" @click="emit('metadata')">Metadata</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.actions-row {
  margin-top: 0.75rem;
}

.action-buttons {
  align-items: center;
}

.meta-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: 0.35rem 1rem;
  margin-top: 0.75rem;
  padding: 0.6rem 0.75rem;
  font-size: 0.9rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.meta-row {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.1rem;
}

.meta-row > span:not(.meta-label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-label {
  color: var(--fg-dim);
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.meta-empty {
  grid-column: 1 / -1;
  margin: 0;
  padding-top: 0.25rem;
}

.capitalize {
  text-transform: capitalize;
}

.novel-cover-row {
  display: grid;
  grid-template-columns: clamp(7rem, 24vw, 11.25rem) minmax(0, 1fr);
  height: clamp(10.5rem, 36vw, 16.875rem);
  gap: 1.25rem;
  margin-bottom: 1rem;
}

.novel-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: var(--bg-elev-2);
  border-radius: var(--radius);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
}

.novel-cover-info {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex-direction: column;
}

.novel-cover-info h2 {
  flex-shrink: 0;
  margin: 0;
  overflow: hidden;
  font-size: 1.35rem;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-author {
  flex-shrink: 0;
  margin: 0.25rem 0 0;
  overflow: hidden;
  color: var(--fg-dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.novel-author span {
  color: var(--fg);
  font-weight: 600;
}

.novel-summary {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  margin-top: 0.75rem;
  padding: 0.6rem 0.75rem;
  overflow: hidden;
  font-size: 0.9rem;
  line-height: 1.5;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.novel-summary-label {
  flex-shrink: 0;
  margin-bottom: 0.25rem;
  color: var(--fg-dim);
  font-size: 0.75rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.novel-summary-content {
  min-height: 0;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
