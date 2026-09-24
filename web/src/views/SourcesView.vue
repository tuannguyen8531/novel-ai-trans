<script setup lang="ts">
import { ref } from 'vue'
import { Globe, BookUp, FolderDown } from '@lucide/vue'
import CrawlSource from '@/components/CrawlSource.vue'
import ImportSource from '@/components/ImportSource.vue'

type SourceKind = 'website' | 'epub'

const activeSource = ref<SourceKind>('website')

function selectSource(source: SourceKind) {
  activeSource.value = source
}
</script>

<template>
  <div class="sources-view-root">
    <!-- Header -->
    <header class="sources-header card-panel">
      <div class="header-icon-box">
        <FolderDown :size="22" />
      </div>
      <div>
        <h2 class="sources-title">{{ $t("novel_ingestion_sources") }}</h2>
        <p class="sources-subtitle">
          {{ $t("import_sources_description") }}
        </p>
      </div>
    </header>

    <!-- Source Type Navigation Tabs -->
    <nav class="source-nav-tabs" :aria-label="$t('source_type')" role="tablist">
      <button
        id="website-source-tab"
        type="button"
        class="source-nav-tab"
        :class="{ active: activeSource === 'website' }"
        role="tab"
        :aria-selected="activeSource === 'website'"
        aria-controls="website-source-panel"
        @click="selectSource('website')"
      >
        <Globe :size="16" />
        <span>{{ $t("from_website") }}</span>
      </button>

      <button
        id="epub-source-tab"
        type="button"
        class="source-nav-tab"
        :class="{ active: activeSource === 'epub' }"
        role="tab"
        :aria-selected="activeSource === 'epub'"
        aria-controls="epub-source-panel"
        @click="selectSource('epub')"
      >
        <BookUp :size="16" />
        <span>{{ $t("from_epub_file") }}</span>
      </button>
    </nav>

    <!-- Tab Panels -->
    <div
      v-if="activeSource === 'website'"
      id="website-source-panel"
      role="tabpanel"
      aria-labelledby="website-source-tab"
      class="panel-fade"
    >
      <CrawlSource />
    </div>

    <div
      v-else
      id="epub-source-panel"
      role="tabpanel"
      aria-labelledby="epub-source-tab"
      class="panel-fade"
    >
      <ImportSource />
    </div>
  </div>
</template>

<style scoped>
.sources-view-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.sources-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
}

.header-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  background: var(--accent-subtle);
  border: 1px solid rgba(79, 125, 249, 0.25);
  color: var(--accent);
  flex-shrink: 0;
}

.sources-title {
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.sources-subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

/* Nav Tabs */
.source-nav-tabs {
  display: inline-flex;
  gap: 0.5rem;
  padding: 0.35rem;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  align-self: flex-start;
}

.source-nav-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.25rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 600;
  background: transparent;
  color: var(--fg-secondary);
  border: 1px solid transparent;
  cursor: pointer;
  box-shadow: none;
  transition: all var(--transition-fast);
}

.source-nav-tab:hover {
  color: var(--fg-primary);
  background: var(--bg-surface);
  transform: none;
}

.source-nav-tab.active {
  background: var(--bg-surface);
  color: var(--accent);
  border-color: var(--border-base);
  box-shadow: var(--shadow-subtle);
}

.panel-fade {
  animation: modal-fade-in 0.18s ease;
}
</style>
