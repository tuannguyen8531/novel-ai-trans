<script setup lang="ts">
import { computed } from 'vue'
import { useIllustrations } from '@/composables/illustrations'

const props = defineProps<{
  content: string
  novel: string
}>()

// Parse content into segments: plain text blocks and illustration filenames
type Segment = { type: 'text'; text: string } | { type: 'illustration'; filename: string }

const ILLUSTRATION_RE = /\[\[ILLUSTRATION:([A-Za-z0-9][A-Za-z0-9._-]*)\]\]/g

const segments = computed<Segment[]>(() => {
  const result: Segment[] = []
  let lastIndex = 0
  const text = props.content
  ILLUSTRATION_RE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = ILLUSTRATION_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push({ type: 'text', text: text.slice(lastIndex, match.index) })
    }
    result.push({ type: 'illustration', filename: match[1] })
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    result.push({ type: 'text', text: text.slice(lastIndex) })
  }
  return result
})

const hasIllustrations = computed(() => segments.value.some((s) => s.type === 'illustration'))

const illustrationFilenames = computed(() => segments.value
  .filter((segment): segment is Extract<Segment, { type: 'illustration' }> => segment.type === 'illustration')
  .map((segment) => segment.filename))
const { authenticated, src: illustrationSrc } = useIllustrations(() => props.novel, illustrationFilenames)
</script>

<template>
  <div class="reader-container">
    <div class="reader-prose">
      <template v-if="!hasIllustrations">
        <pre class="chapter-content-text">{{ content || 'This chapter has no content.' }}</pre>
      </template>
      <template v-else>
        <template v-for="(seg, i) in segments" :key="i">
          <pre v-if="seg.type === 'text'" class="chapter-content-text">{{ seg.text }}</pre>
          <figure v-else class="chapter-illustration">
            <img
              v-if="seg.type === 'illustration' && (illustrationSrc(seg.filename) || !authenticated())"
              :src="illustrationSrc(seg.filename)"
              :alt="`Illustration: ${seg.filename}`"
              class="chapter-illustration-img"
              loading="lazy"
            />
            <div v-else class="chapter-illustration-loading muted">
              Loading illustration…
            </div>
            <figcaption class="illustration-caption">{{ seg.filename }}</figcaption>
          </figure>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.reader-container {
  display: flex;
  justify-content: center;
  width: 100%;
  padding: 1.5rem 0.5rem;
}

.reader-prose {
  width: 100%;
  max-width: 52rem;
  margin: 0 auto;
}

.chapter-content-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  font-family: var(--font-serif);
  font-size: 1.15rem;
  line-height: 1.85;
  color: var(--fg-primary);
  text-align: justify;
  letter-spacing: 0.01em;
}

.chapter-illustration {
  margin: 2rem 0;
  text-align: center;
}

.chapter-illustration-img {
  max-width: 100%;
  max-height: 38rem;
  height: auto;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  display: block;
  margin: 0 auto;
  border: 1px solid var(--border-base);
}

.illustration-caption {
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: var(--fg-muted);
  font-family: var(--font-sans);
}

.chapter-illustration-loading {
  padding: 2rem;
  font-size: 0.875rem;
  background: var(--bg-surface-elevated);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-base);
}
</style>
