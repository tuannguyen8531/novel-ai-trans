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
  <div class="chapter-content-rendered">
    <template v-if="!hasIllustrations">
      <pre class="chapter-content">{{ content || 'Empty chapter.' }}</pre>
    </template>
    <template v-else>
      <template v-for="(seg, i) in segments" :key="i">
        <pre v-if="seg.type === 'text'" class="chapter-content chapter-content-segment">{{ seg.text }}</pre>
        <figure v-else class="chapter-illustration">
          <img
            v-if="seg.type === 'illustration' && (illustrationSrc(seg.filename) || !authenticated())"
            :src="illustrationSrc(seg.filename)"
            :alt="`Illustration: ${seg.filename}`"
            class="chapter-illustration-img"
          />
          <div v-else class="chapter-illustration-loading muted">
            Loading illustration…
          </div>
        </figure>
      </template>
    </template>
  </div>
</template>

<style scoped>
.chapter-content-rendered {
  display: contents;
}

.chapter-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: break-word;
  font-family: var(--font);
  font-size: 1rem;
  line-height: 1.7;
  text-align: justify;
}

.chapter-content-segment {
  margin: 0;
  margin-bottom: 0;
}

.chapter-content-segment + .chapter-illustration,
.chapter-illustration + .chapter-content-segment {
  margin-top: 1rem;
}

.chapter-illustration {
  margin: 1rem 0;
  text-align: center;
}

.chapter-illustration-img {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius);
  display: block;
  margin: 0 auto;
}

.chapter-illustration-loading {
  padding: 1rem;
  font-size: 0.875rem;
}
</style>
