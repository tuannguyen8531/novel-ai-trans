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
    <div class="card source-intro">
      <h2>Add source chapters</h2>
      <p class="muted">
        Fetch a novel from its website or upload an EPUB. Both methods prepare source chapters
        in the novel input directory for translation.
      </p>
    </div>

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
.source-intro h2,
.source-intro p {
  margin-top: 0;
}

.source-intro p {
  margin-bottom: 0;
}

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
