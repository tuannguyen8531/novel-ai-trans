<script setup lang="ts">
import { ref } from 'vue'
import CrawlSource from '@/components/CrawlSource.vue'
import ImportSource from '@/components/ImportSource.vue'

type SourceKind = 'website' | 'epub'

const activeSource = ref<SourceKind>('website')

function selectSource(source: SourceKind) {
  activeSource.value = source
}
</script>

<template>
  <section class="flex-col gap-3">
    <nav class="source-tabs" aria-label="Source type" role="tablist">
      <button
        id="website-source-tab"
        type="button"
        class="source-tab"
        role="tab"
        :aria-selected="activeSource === 'website'"
        aria-controls="website-source-panel"
        @click="selectSource('website')"
      >
        From Website
      </button>
      <button
        id="epub-source-tab"
        type="button"
        class="source-tab"
        role="tab"
        :aria-selected="activeSource === 'epub'"
        aria-controls="epub-source-panel"
        @click="selectSource('epub')"
      >
        From EPUB
      </button>
    </nav>

    <div
      v-if="activeSource === 'website'"
      id="website-source-panel"
      role="tabpanel"
      aria-labelledby="website-source-tab"
    >
      <CrawlSource />
    </div>
    <div
      v-else
      id="epub-source-panel"
      role="tabpanel"
      aria-labelledby="epub-source-tab"
    >
      <ImportSource />
    </div>
  </section>
</template>

<style scoped>
.source-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
}

.source-tab {
  position: relative;
  padding: 0.75rem 1.1rem;
  background: transparent;
  color: var(--fg-dim);
  border: 0;
  border-radius: 0;
}

.source-tab:hover:not(:disabled) {
  background: var(--bg-elev);
  color: var(--fg);
}

.source-tab[aria-selected='true'] {
  color: var(--accent);
}

.source-tab[aria-selected='true']::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: var(--accent);
  content: '';
}
</style>
