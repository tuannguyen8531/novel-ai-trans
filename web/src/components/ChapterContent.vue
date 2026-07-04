<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { api, getAuthToken } from '@/api/client'

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

// For remote mode: map filename → objectURL (to attach Bearer token via fetch)
const objectUrls = ref<Map<string, string>>(new Map())
const loadingImages = ref<Set<string>>(new Set())

function illustrationSrc(filename: string): string {
  const token = getAuthToken()
  if (!token) {
    // Local mode: direct URL, browser fetches without auth header
    return api.illustrationUrl(props.novel, filename)
  }
  // Remote mode: use cached objectURL if available
  return objectUrls.value.get(filename) ?? ''
}

async function loadIllustrationBlob(filename: string): Promise<void> {
  if (objectUrls.value.has(filename) || loadingImages.value.has(filename)) return
  loadingImages.value.add(filename)
  try {
    const url = api.illustrationUrl(props.novel, filename)
    const token = getAuthToken()
    const resp = await fetch(url, token ? { headers: { Authorization: `Bearer ${token}` } } : {})
    if (!resp.ok) return
    const blob = await resp.blob()
    const objUrl = URL.createObjectURL(blob)
    objectUrls.value.set(filename, objUrl)
  } finally {
    loadingImages.value.delete(filename)
  }
}

watch(
  segments,
  (segs) => {
    const token = getAuthToken()
    if (!token) return // local mode: direct URL, no pre-fetch needed
    for (const seg of segs) {
      if (seg.type === 'illustration') {
        void loadIllustrationBlob(seg.filename)
      }
    }
  },
  { immediate: true }
)

// Revoke objectURLs on unmount to free memory
onUnmounted(() => {
  for (const url of objectUrls.value.values()) {
    URL.revokeObjectURL(url)
  }
})
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
            v-if="seg.type === 'illustration' && (illustrationSrc(seg.filename) || !getAuthToken())"
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
